"""
Per-session controlled vocabulary.

The vocabulary is the curated, user-validated set of terms (column names,
semantic types, units, allowed values, metadata field keys) that downstream
LLM calls are constrained to. It plays the role of a lightweight "schema
ontology" without the overhead of true ontology infrastructure (SKOS, OWL,
reasoners). Its job is hallucination prevention through vocabulary alignment.

Lifecycle:
  1. Initialised from the profiled columns at upload time (`version=1`,
     `validated=False`).
  2. The user reviews and either:
       - Approves → `validate()` flips `validated=True`, bumps version.
       - Extends → `extend_terms()` adds proposed terms, bumps version.
  3. Each bump invalidates older HITL suggestions (see hitl.mark_stale).

LLM calls must:
  - Inject the vocabulary as a *cached* system-prompt block.
  - Use dynamically-built tool schemas whose enums are drawn from this
    vocabulary, so the model physically cannot return out-of-schema values.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional


# Hard-coded across the app (also referenced by llm_column_enricher).
SEMANTIC_TYPES: List[str] = [
    "identifier", "biological_descriptor", "experimental_condition",
    "measurement", "time_variable", "free_text_note",
    "metadata_field", "categorical", "unknown",
]

# Common SI / domain units seen in pre-clinical and clinical CSVs.
_DEFAULT_UNITS: List[str] = [
    "kg", "g", "mg", "µg", "ng", "pg",
    "mg/kg", "mg/mL", "mg/m²", "µg/mL", "ng/mL", "ng/g",
    "L", "mL", "µL", "nL",
    "mm", "cm", "m", "µm", "nm",
    "s", "min", "h", "d", "wk", "mo", "yr",
    "°C", "K",
    "%", "ratio", "count", "U/L", "IU/L", "mEq/L", "mmol/L", "mol/L", "M",
    "bpm", "mmHg", "kPa",
]

_DEFAULT_METADATA_KEYS: List[str] = [
    "title", "description", "creator", "institution", "contact_email",
    "date_created", "version", "license", "access_conditions",
    "species", "study_type", "design", "protocol_reference",
    "funding_source", "keywords", "row_represents", "primary_identifier",
    "base_uri",
]

_DEFAULT_LICENSES: List[str] = [
    "CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0",
    "MIT", "Apache-2.0", "ODbL-1.0", "proprietary",
]

_DEFAULT_STUDY_TYPES: List[str] = [
    "interventional", "observational", "randomised_controlled_trial",
    "case_control", "cohort", "cross_sectional",
    "pre_clinical_in_vivo", "pre_clinical_in_vitro",
    "dose_response", "parallel_group", "crossover", "repeated_measures",
    "longitudinal", "toxicology", "pharmacology",
]


def DEFAULT_VOCABULARY() -> Dict[str, Any]:
    return {
        "version": 0,           # 0 = uninitialised; first init() call sets 1
        "validated": False,
        "validated_at": None,
        "column_names": [],
        "semantic_types": list(SEMANTIC_TYPES),
        "units": list(_DEFAULT_UNITS),
        "metadata_keys": list(_DEFAULT_METADATA_KEYS),
        "licenses": list(_DEFAULT_LICENSES),
        "study_types": list(_DEFAULT_STUDY_TYPES),
        "controlled_values": {},   # column_name -> list[str]
        "history": [],             # [{"version": int, "at": float, "source": str, "added": {...}}]
    }


def ensure_vocabulary(session: Dict[str, Any]) -> Dict[str, Any]:
    """Initialise from session columns on first call; otherwise return existing."""
    vocab = session.get("vocabulary")
    if not isinstance(vocab, dict):
        vocab = DEFAULT_VOCABULARY()
        session["vocabulary"] = vocab
    if vocab["version"] == 0:
        _init_from_session(session, vocab)
    return vocab


def _init_from_session(session: Dict[str, Any], vocab: Dict[str, Any]) -> None:
    columns = session.get("columns") or []
    vocab["column_names"] = [c["name"] for c in columns]

    # Seed units from any rule-based guesses already on the columns.
    seen_units = set(vocab["units"])
    for c in columns:
        for key in ("user_unit", "unit_guess"):
            u = c.get(key)
            if u and u not in seen_units:
                vocab["units"].append(u)
                seen_units.add(u)

    # Controlled-value sets only for clearly categorical columns. Cap the size
    # to keep enum lists tractable for the model.
    for c in columns:
        if c.get("inferred_type") in ("experimental_condition", "categorical") or c.get("user_type") in ("experimental_condition", "categorical"):
            samples = [str(v) for v in (c.get("sample_values") or [])][:25]
            if 1 < len(samples) <= 25:
                vocab["controlled_values"][c["name"]] = sorted(set(samples))

    vocab["version"] = 1
    vocab["history"].append({
        "version": 1, "at": time.time(), "source": "init",
        "added": {"column_names": list(vocab["column_names"])},
    })


def bump_version(
    vocab: Dict[str, Any], source: str, added: Optional[Dict[str, Any]] = None
) -> int:
    vocab["version"] = int(vocab.get("version", 0)) + 1
    vocab["history"].append({
        "version": vocab["version"],
        "at": time.time(),
        "source": source,
        "added": added or {},
    })
    return vocab["version"]


def extend_terms(
    session: Dict[str, Any],
    key: str,
    new_values: Iterable[str],
    source: str,
) -> Dict[str, Any]:
    """
    Add new terms to a vocabulary list (units/study_types/licenses/etc.) or
    to a controlled_values entry like 'controlled_values:group_col'.

    Returns {"added": [...], "version": int}.
    """
    vocab = ensure_vocabulary(session)
    added: List[str] = []

    if key.startswith("controlled_values:"):
        col = key.split(":", 1)[1]
        target = vocab["controlled_values"].setdefault(col, [])
        for v in new_values:
            v = str(v)
            if v and v not in target:
                target.append(v)
                added.append(v)
        target.sort()
    elif key in ("units", "metadata_keys", "licenses", "study_types"):
        target = vocab[key]
        for v in new_values:
            v = str(v)
            if v and v not in target:
                target.append(v)
                added.append(v)
    else:
        raise ValueError(f"Unknown vocabulary key: {key}")

    if added:
        bump_version(vocab, source=source, added={key: added})
    return {"added": added, "version": vocab["version"]}


def validate(session: Dict[str, Any]) -> Dict[str, Any]:
    """Mark vocabulary as user-validated and bump version."""
    vocab = ensure_vocabulary(session)
    vocab["validated"] = True
    vocab["validated_at"] = time.time()
    bump_version(vocab, source="user_validate")
    return vocab


# ── LLM integration helpers ──────────────────────────────────────────────────

def schema_prompt_block(session: Dict[str, Any], max_controlled: int = 8) -> str:
    """
    Render the vocabulary as a compact, cache-friendly system-prompt block.

    Format is intentionally stable (sorted, deterministic) so the ephemeral
    prompt cache hits across calls within the same vocabulary version.
    """
    vocab = ensure_vocabulary(session)
    lines = [
        "## VALIDATED VOCABULARY (use these terms verbatim; do not invent new ones).",
        f"schema_version: {vocab['version']} (validated={vocab['validated']})",
        f"column_names: {_csv(vocab['column_names'])}",
        f"semantic_types: {_csv(vocab['semantic_types'])}",
        f"units: {_csv(vocab['units'])}",
        f"metadata_keys: {_csv(vocab['metadata_keys'])}",
        f"licenses: {_csv(vocab['licenses'])}",
        f"study_types: {_csv(vocab['study_types'])}",
    ]
    cv = vocab.get("controlled_values", {})
    if cv:
        lines.append("controlled_values:")
        for col in sorted(cv.keys())[:max_controlled]:
            lines.append(f"  - {col}: {_csv(cv[col])}")
    lines.append(
        "RULE: If you need a term not in this vocabulary, prefer the closest "
        "existing term, set the field to null, or describe the gap in your "
        "rationale. Never invent column names or units."
    )
    return "\n".join(lines)


def _csv(values: List[str]) -> str:
    return ", ".join(str(v) for v in values) if values else "(none)"


def enum_or_null(values: List[str]) -> Dict[str, Any]:
    """JSON-schema fragment: enum-constrained value, or null."""
    enum = list(values) if values else []
    if not enum:
        return {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {"anyOf": [{"enum": enum}, {"type": "null"}]}


def enum_array(values: List[str]) -> Dict[str, Any]:
    """JSON-schema fragment: array of enum strings (empty allowed)."""
    if not values:
        return {"type": "array", "items": {"type": "string"}}
    return {"type": "array", "items": {"enum": list(values)}}
