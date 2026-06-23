"""Deterministic KG retriever: match dataset columns to preclinical concepts,
build a compact LLM grounding block, and suggest ontology IRIs for values.

This realises "the agent accesses the knowledge graph" as retrieval-augmented
injection — a Python retriever selects the relevant subgraph per column, so it
works robustly even with local models that handle tool-calling poorly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .kg import Concept, KnowledgeGraph, load_kg

_MAX_GROUNDING_CONCEPTS = 12


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _name_tokens(name: str) -> str:
    # space-normalised column name for substring keyword matching
    return f" {_norm(name)} "


@dataclass(frozen=True)
class ConceptMatch:
    column: str
    concept_id: str
    matched_on: str  # "name" | "value"
    evidence: str


def _concept_matches_column(
    concept: Concept,
    name: str,
    samples: List[str],
) -> Optional[ConceptMatch]:
    haystack_name = _name_tokens(name)
    for kw in concept.keywords:
        if f" {_norm(kw)} " in haystack_name or _norm(kw) in _norm(name):
            return ConceptMatch(name, concept.id, "name", kw)
    # value-based match: example tokens or controlled values appear in samples
    norm_samples = [_norm(s) for s in samples]
    for ex in concept.examples:
        ne = _norm(ex)
        if ne and any(ne in s or s in ne for s in norm_samples if s):
            return ConceptMatch(name, concept.id, "value", ex)
    return None


def match_columns(
    columns: List[Dict[str, Any]],
    kg: Optional[KnowledgeGraph] = None,
) -> List[ConceptMatch]:
    """Return one best concept match per column (first concept that matches)."""
    kg = kg or load_kg()
    matches: List[ConceptMatch] = []
    for col in columns:
        name = str(col.get("name") or "")
        samples = [str(v) for v in (col.get("sample_values") or [])[:8]]
        for concept in kg.concepts:
            m = _concept_matches_column(concept, name, samples)
            if m is not None:
                matches.append(m)
                break  # first (highest-priority) concept wins for this column
    return matches


def grounding_block(
    columns: List[Dict[str, Any]],
    kg: Optional[KnowledgeGraph] = None,
) -> str:
    """Compact, cache-friendly system block describing the KG-relevant concepts
    for the matched columns. Empty string when nothing matches (so callers can
    skip adding it)."""
    kg = kg or load_kg()
    matches = match_columns(columns, kg)
    if not matches:
        return ""

    seen: set = set()
    lines = [
        "## PRECLINICAL KNOWLEDGE GRAPH (grounding — prefer these mappings)",
        "Recognised columns and their expected semantic type / ontology:",
    ]
    count = 0
    for m in matches:
        if m.column in seen:
            continue
        seen.add(m.column)
        concept = kg.concept(m.concept_id)
        if concept is None:
            continue
        scheme = kg.scheme(concept.scheme)
        scheme_s = f" → ontology {scheme.label} ({concept.scheme})" if scheme else ""
        lines.append(
            f"- column \"{m.column}\": {concept.label} "
            f"[semantic_type={concept.semantic_type}{scheme_s}] (matched on {m.matched_on}: {m.evidence})"
        )
        count += 1
        if count >= _MAX_GROUNDING_CONCEPTS:
            break
    lines.append(
        "RULE: when a column matches above, use the stated semantic_type. Do not "
        "invent ontologies; use the named scheme or leave the IRI to the curator."
    )
    return "\n".join(lines)


def suggest_iris(
    columns: List[Dict[str, Any]],
    kg: Optional[KnowledgeGraph] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Per-column ontology IRI suggestions.

    For a matched column we either (a) resolve an exact IRI offline when a
    sample value is in the concept's controlled-value list (e.g. "Mus musculus"
    → NCBITaxon_10090), or (b) emit a scheme-level hint (base IRI + resolver)
    for online resolution. The result is additive metadata for the UI/exports.
    """
    kg = kg or load_kg()
    out: Dict[str, List[Dict[str, Any]]] = {}
    matches_by_col: Dict[str, ConceptMatch] = {m.column: m for m in match_columns(columns, kg)}
    samples_by_col = {
        str(c.get("name")): [str(v) for v in (c.get("sample_values") or [])[:12]] for c in columns
    }

    for col_name, match in matches_by_col.items():
        concept = kg.concept(match.concept_id)
        if concept is None:
            continue
        scheme = kg.scheme(concept.scheme)
        suggestions: List[Dict[str, Any]] = []

        # (a) exact offline IRIs from controlled values present in the samples
        exact_seen: set = set()
        for sample in samples_by_col.get(col_name, []):
            cv = kg.iri_for_value(concept, sample)
            if cv and cv.iri and cv.iri not in exact_seen:
                exact_seen.add(cv.iri)
                suggestions.append(
                    {
                        "value": sample,
                        "label": cv.label,
                        "iri": cv.iri,
                        "scheme": concept.scheme,
                        "online": False,
                        "confidence": 0.95,
                    }
                )

        # (b) scheme-level hint for online resolution when no exact match
        if not suggestions and scheme is not None:
            suggestions.append(
                {
                    "value": None,
                    "label": None,
                    "iri_base": scheme.iri_base,
                    "scheme": concept.scheme,
                    "resolver": scheme.resolver,
                    "online": True,
                    "confidence": 0.5,
                }
            )

        if suggestions:
            out[col_name] = suggestions
    return out
