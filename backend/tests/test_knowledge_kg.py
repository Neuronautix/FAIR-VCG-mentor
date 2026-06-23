"""Tests for the preclinical metadata knowledge graph (backend/knowledge).

Offline: the KG loader, retriever, grounding block, and IRI suggestion need no
network. Verifies concept loading, column→concept matching (by name and by
value), exact offline IRI resolution for controlled values, and scheme-level
hints for online resolution.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from knowledge.kg import load_kg  # noqa: E402
from knowledge.retriever import (  # noqa: E402
    grounding_block,
    match_columns,
    suggest_iris,
)

_ALLOWED = {
    "identifier", "biological_descriptor", "experimental_condition", "measurement",
    "time_variable", "free_text_note", "metadata_field", "categorical", "unknown",
}


@pytest.fixture
def kg():
    return load_kg(force=True)


# ── Loading ──────────────────────────────────────────────────────────────────

def test_kg_loads_with_concepts_and_schemes(kg):
    assert len(kg.concepts) >= 12
    assert "NCBITaxon" in kg.schemes
    assert kg.schemes["NCBITaxon"].iri_base.endswith("NCBITaxon_")
    for c in kg.concepts:
        assert c.semantic_type in _ALLOWED, f"{c.id} -> {c.semantic_type}"


def test_species_controlled_values_have_iris(kg):
    organism = kg.concept("organism")
    assert organism is not None
    cvs = kg.controlled_values(organism)
    assert len(cvs) >= 15
    mus = next(cv for cv in cvs if cv.label == "Mus musculus")
    assert mus.iri == "http://purl.obolibrary.org/obo/NCBITaxon_10090"
    # synonym match works
    assert kg.iri_for_value(organism, "mouse").iri == mus.iri


# ── Column matching ──────────────────────────────────────────────────────────

def test_match_by_name(kg):
    cols = [
        {"name": "species", "sample_values": []},
        {"name": "strain", "sample_values": []},
        {"name": "compound_name", "sample_values": []},
        {"name": "tissue", "sample_values": []},
    ]
    by_col = {m.column: m.concept_id for m in match_columns(cols, kg)}
    assert by_col["species"] == "organism"
    assert by_col["strain"] == "strain"
    assert by_col["compound_name"] == "molecule"
    assert by_col["tissue"] == "anatomy"


def test_match_by_value_when_name_is_blind(kg):
    # Header is uninformative ("var_1") but the values reveal the concept.
    cols = [{"name": "var_1", "sample_values": ["Mus musculus", "Rattus norvegicus"]}]
    matches = match_columns(cols, kg)
    assert len(matches) == 1
    assert matches[0].concept_id == "organism"
    assert matches[0].matched_on == "value"


# ── Grounding block ──────────────────────────────────────────────────────────

def test_grounding_block_mentions_scheme_and_type(kg):
    cols = [{"name": "species", "sample_values": ["Mus musculus"]}]
    block = grounding_block(cols, kg)
    assert "NCBITaxon" in block
    assert "biological_descriptor" in block
    assert "species" in block


def test_grounding_block_empty_when_no_match(kg):
    cols = [{"name": "xyz_random_metric", "sample_values": ["1.2", "3.4"]}]
    assert grounding_block(cols, kg) == ""


# ── IRI suggestions ──────────────────────────────────────────────────────────

def test_suggest_iris_exact_offline_for_species(kg):
    cols = [{"name": "species", "sample_values": ["Mus musculus", "Rattus norvegicus"]}]
    sugg = suggest_iris(cols, kg)
    assert "species" in sugg
    iris = {s["iri"] for s in sugg["species"] if not s["online"]}
    assert "http://purl.obolibrary.org/obo/NCBITaxon_10090" in iris
    assert "http://purl.obolibrary.org/obo/NCBITaxon_10116" in iris


def test_suggest_iris_scheme_hint_when_no_exact(kg):
    # A molecule column whose values aren't in any controlled list → online hint.
    cols = [{"name": "drug", "sample_values": ["CompoundX", "CompoundY"]}]
    sugg = suggest_iris(cols, kg)
    assert "drug" in sugg
    hint = sugg["drug"][0]
    assert hint["online"] is True
    assert hint["scheme"] == "ChEBI"
    assert hint["resolver"] == "ols_chebi"


def test_uri_suggester_includes_ontology_suggestions():
    from uri_suggester import suggest_uris

    cols = [{"name": "species", "inferred_type": "biological_descriptor", "sample_values": ["Mus musculus"]}]
    out = suggest_uris(cols, {}, {"filename": "d.csv"})
    assert "ontology_suggestions" in out
    assert "species" in out["ontology_suggestions"]
