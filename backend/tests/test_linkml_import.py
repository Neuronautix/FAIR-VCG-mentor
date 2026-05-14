"""Tests for LinkML schema -> template conversion + NAMO assay template."""
import os
import sys
from pathlib import Path

import pytest
import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from linkml_import import (  # noqa: E402
    flatten_attributes,
    linkml_to_template,
    parse_linkml_yaml,
)
from template_engine import (  # noqa: E402
    _validate_template_dict,
    get_template,
    load_templates,
    match_template,
)

NAMO_PATH = Path("/tmp/namo.yaml")


def _load_namo() -> dict:
    if not NAMO_PATH.exists():
        pytest.skip("NAMO schema not available at /tmp/namo.yaml")
    with open(NAMO_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_convert_namo_full_schema():
    namo = _load_namo()
    template = linkml_to_template(namo, target_class=None)
    _validate_template_dict(template)
    assert template["id"]
    assert template.get("required_metadata"), "Expected metadata entries from data-like classes"
    assert len(template["required_metadata"]) >= 5


def test_convert_namo_target_class_functional_assay():
    namo = _load_namo()
    template = linkml_to_template(namo, target_class="FunctionalAssay")
    ids = {c["id"] for c in template.get("required_columns", [])}
    assert "assay_type" in ids
    assert "assay_result" in ids
    assert "reference_value" in ids
    _validate_template_dict(template)


def test_convert_namo_dose_response():
    namo = _load_namo()
    template = linkml_to_template(namo, target_class="DoseResponseSimilarity")
    ids = {c["id"] for c in template.get("required_columns", [])}
    assert "correlation_coefficient" in ids
    assert "ec50_ratio" in ids
    assert "max_response_ratio" in ids
    assert "compound_tested" in ids


def test_class_iri_map_populated():
    namo = _load_namo()
    template = linkml_to_template(namo, target_class="FunctionalAssay")
    iri_map = template.get("class_iri_map", {})
    assert iri_map, "class_iri_map must be populated"
    for col in template.get("required_columns", []):
        assert col["id"] in iri_map, f"Missing iri mapping for {col['id']}"


def test_invalid_linkml_yaml_rejected():
    with pytest.raises(ValueError):
        parse_linkml_yaml("not: [valid: yaml: structure")
    with pytest.raises(ValueError):
        linkml_to_template({"some": "dict"})
    with pytest.raises(ValueError):
        linkml_to_template({"classes": {"X": {}}}, target_class="NotARealClass")


def test_namo_nam_assay_template_loads():
    templates = load_templates(force=True)
    assert "namo-nam-assay-v1" in templates
    tpl = get_template("namo-nam-assay-v1")
    assert tpl is not None
    assert tpl.vcg_defaults is not None
    assert tpl.vcg_defaults.treatment_col == "compound_id"
    column_ids = {c.id for c in tpl.required_columns}
    assert "compound_id" in column_ids
    assert "concentration" in column_ids
    assert "response_value" in column_ids


def test_namo_match_score_on_screening_csv():
    tpl = get_template("namo-nam-assay-v1")
    columns = [
        {"name": "model_system_id", "inferred_type": "identifier"},
        {"name": "compound_id", "inferred_type": "experimental_condition"},
        {"name": "concentration", "inferred_type": "measurement"},
        {"name": "concentration_unit", "inferred_type": "categorical"},
        {"name": "response_value", "inferred_type": "measurement"},
        {"name": "response_unit", "inferred_type": "categorical"},
        {"name": "assay_endpoint", "inferred_type": "experimental_condition"},
        {"name": "model_system_type", "inferred_type": "experimental_condition"},
    ]
    result = match_template(tpl, columns, {})
    assert result["score"] >= 0.7


def test_flatten_attributes_walks_is_a_chain():
    schema = {
        "classes": {
            "Parent": {"attributes": {"p1": {"range": "string"}}},
            "Child": {"is_a": "Parent", "attributes": {"c1": {"range": "float"}}},
        }
    }
    classes = schema["classes"]
    attrs = flatten_attributes(classes["Child"], classes)
    assert "p1" in attrs
    assert "c1" in attrs


def test_namo_template_has_class_iri_map():
    tpl_dict = get_template("namo-nam-assay-v1").to_dict()
    raw = yaml.safe_load(
        (BACKEND_DIR / "templates" / "namo-nam-assay-v1.yaml").read_text(encoding="utf-8")
    )
    assert raw.get("class_iri_map"), "Hand-crafted NAMO template must carry class_iri_map"
    assert "response_value" in raw["class_iri_map"]
