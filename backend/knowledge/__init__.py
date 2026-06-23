"""Preclinical metadata knowledge graph (grant Milestone A).

A lightweight, ontology-bound term graph derived from the precliniverse
"Open Science Dataset Registration Wizard" schema (see
`sources/precliniverse_schema_v3.json`). It grounds metadata reasoning for both
cloud and local LLMs and suggests ontology IRIs for recognised biological
values — fully offline, with optional online IRI resolution.
"""
from .kg import Concept, ControlledValue, KnowledgeGraph, Scheme, load_kg
from .retriever import ConceptMatch, grounding_block, match_columns, suggest_iris

__all__ = [
    "load_kg",
    "KnowledgeGraph",
    "Concept",
    "Scheme",
    "ControlledValue",
    "ConceptMatch",
    "match_columns",
    "grounding_block",
    "suggest_iris",
]
