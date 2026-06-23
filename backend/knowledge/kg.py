"""Loader for the preclinical metadata knowledge graph.

Loads `preclinical_kg.yaml` (curated from the precliniverse schema) into typed
Concept / Scheme objects and exposes lookups: concepts, schemes, controlled
value lists, and value→IRI resolution. Pure/offline — no network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

KG_PATH = Path(__file__).parent / "preclinical_kg.yaml"

# The nine canonical FAIR-VCG semantic types (mirrors vocabulary + eval.datasets).
_ALLOWED_SEMANTIC_TYPES = {
    "identifier",
    "biological_descriptor",
    "experimental_condition",
    "measurement",
    "time_variable",
    "free_text_note",
    "metadata_field",
    "categorical",
    "unknown",
}


@dataclass(frozen=True)
class Scheme:
    id: str
    label: str
    iri_base: Optional[str] = None
    resolver: Optional[str] = None


@dataclass(frozen=True)
class ControlledValue:
    label: str
    synonyms: List[str] = field(default_factory=list)
    iri: Optional[str] = None

    def matches(self, token: str) -> bool:
        t = (token or "").strip().lower()
        if not t:
            return False
        if t == self.label.lower():
            return True
        return any(t == s.lower() for s in self.synonyms)


@dataclass(frozen=True)
class Concept:
    id: str
    label: str
    semantic_type: str
    scheme: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    value_set: Optional[str] = None


@dataclass(frozen=True)
class KnowledgeGraph:
    version: str
    source: Dict[str, str]
    schemes: Dict[str, Scheme]
    concepts: List[Concept]
    values: Dict[str, List[ControlledValue]]

    def concept(self, cid: str) -> Optional[Concept]:
        return next((c for c in self.concepts if c.id == cid), None)

    def scheme(self, sid: Optional[str]) -> Optional[Scheme]:
        return self.schemes.get(sid) if sid else None

    def controlled_values(self, concept: Concept) -> List[ControlledValue]:
        if not concept.value_set:
            return []
        return self.values.get(concept.value_set, [])

    def iri_for_value(self, concept: Concept, value: str) -> Optional[ControlledValue]:
        for cv in self.controlled_values(concept):
            if cv.matches(value):
                return cv
        return None


_CACHE: Optional[KnowledgeGraph] = None


def _build_values(raw: Dict[str, list]) -> Dict[str, List[ControlledValue]]:
    out: Dict[str, List[ControlledValue]] = {}
    for key, items in (raw or {}).items():
        out[key] = [
            ControlledValue(
                label=str(it.get("label")),
                synonyms=[str(s) for s in (it.get("synonyms") or [])],
                iri=it.get("iri"),
            )
            for it in items
            if isinstance(it, dict) and it.get("label")
        ]
    return out


def load_kg(force: bool = False) -> KnowledgeGraph:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE

    with open(KG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    schemes = {
        sid: Scheme(id=sid, label=s.get("label", sid), iri_base=s.get("iri_base"), resolver=s.get("resolver"))
        for sid, s in (data.get("schemes") or {}).items()
    }

    concepts: List[Concept] = []
    for c in data.get("concepts") or []:
        st = c.get("semantic_type", "unknown")
        if st not in _ALLOWED_SEMANTIC_TYPES:
            raise ValueError(f"KG concept '{c.get('id')}' has invalid semantic_type '{st}'")
        concepts.append(
            Concept(
                id=c["id"],
                label=c.get("label", c["id"]),
                semantic_type=st,
                scheme=c.get("scheme"),
                keywords=[str(k) for k in (c.get("keywords") or [])],
                examples=[str(e) for e in (c.get("examples") or [])],
                value_set=c.get("value_set"),
            )
        )

    kg = KnowledgeGraph(
        version=str(data.get("version", "0")),
        source=dict(data.get("source") or {}),
        schemes=schemes,
        concepts=concepts,
        values=_build_values(data.get("values") or {}),
    )
    _CACHE = kg
    return kg
