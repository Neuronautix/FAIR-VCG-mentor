# Preclinical metadata knowledge graph

Grant **Milestone A**. A lightweight, ontology-bound term graph that grounds
metadata reasoning (for cloud *and* local LLMs) and suggests ontology IRIs for
recognised biological values. Fully offline; online IRI resolution is opt-in.

## Source & provenance

Derived from the **precliniverse "Open Science Dataset Registration Wizard"**
schema, vendored at [`sources/precliniverse_schema_v3.json`](sources/precliniverse_schema_v3.json)
(project: `precliniverse/Dynamic_Metadata_form`, schema v3.0.0). That schema
contributes three things the KG reuses:

1. **ontology-bound entity types** — organism→NCBITaxon, strain/diet→EFO,
   molecule→ChEBI, disease→DOID, tissue→UBERON, gene/allele, plus DataCite
   descriptive fields;
2. **controlled vocabularies** — 15 model-organism presets *with NCBITaxon
   IRIs*, CRediT roles, etc.;
3. **resolver API registry** — OLS4 / ORCID / ROR / MyGene endpoints (used only
   for opt-in online IRI resolution behind `ENABLE_ONLINE_ENRICHMENT`).

`preclinical_kg.yaml` is the curated runtime KG normalised from that source.

## How it grounds the LLM

A deterministic retriever (`retriever.py`) matches each dataset column to a KG
concept — by **name** (keywords) or, when the header is uninformative, by
**value** (sample tokens / controlled values). It then:

- **`grounding_block(columns)`** → a compact system block injected via the
  existing `extra_system_blocks` path (so it is cached alongside the validated
  vocabulary) telling the model each recognised column's expected
  `semantic_type` + ontology scheme. This is retrieval-augmented injection — no
  reliance on local-model tool-calling.
- **`suggest_iris(columns)`** → per-column ontology IRI suggestions: an exact
  offline IRI when a value is a known controlled term (e.g. `Mus musculus` →
  `NCBITaxon_10090`), otherwise a scheme-level hint (base IRI + resolver) for
  online resolution. Surfaced additively on `uri_suggester` output.

## Wiring

| Consumer | Use |
| --- | --- |
| `llm_column_enricher` | adds `grounding_block` to the LLM system blocks |
| `uri_suggester` | adds `ontology_suggestions` to its output |

## Files

| File | Role |
| --- | --- |
| `preclinical_kg.yaml` | curated runtime KG (concepts, schemes, controlled values) |
| `kg.py` | loader → `Concept` / `Scheme` / `ControlledValue`; value→IRI lookup |
| `retriever.py` | column→concept matching, grounding block, IRI suggestions |
| `sources/precliniverse_schema_v3.json` | pinned upstream source (provenance) |

Tests: `backend/tests/test_knowledge_kg.py`.
