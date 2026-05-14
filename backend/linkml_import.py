"""Convert a LinkML schema YAML to a starter FAIR-VCG template dict."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

import yaml

from template_engine import _validate_template_dict

NUMERIC_RANGES = {"float", "double", "decimal", "integer", "int", "number"}
STRUCTURAL_CLASSES = {"NamedThing", "ModelsRelationship", "Reference", "Term"}
DATA_LIKE_PATTERNS = re.compile(r"(Result|Assay|Metric|Measurement|Statistic)", re.IGNORECASE)


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "imported-schema"


def _slot_id(name: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_").lower()
    return out or "field"


def extract_classes(linkml: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return all class definitions from a LinkML schema."""
    classes = linkml.get("classes") or {}
    if not isinstance(classes, dict):
        return {}
    return {k: (v or {}) for k, v in classes.items()}


def flatten_attributes(
    class_def: Dict[str, Any],
    all_classes: Dict[str, Dict[str, Any]],
    _seen: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Merge attributes from is_a parent chain. Child overrides parent."""
    _seen = _seen or set()
    attrs: Dict[str, Dict[str, Any]] = {}
    parent = class_def.get("is_a")
    if parent and parent in all_classes and parent not in _seen:
        _seen.add(parent)
        attrs.update(flatten_attributes(all_classes[parent], all_classes, _seen))
    own = class_def.get("attributes") or {}
    if isinstance(own, dict):
        for slot_name, slot_def in own.items():
            attrs[slot_name] = slot_def or {}
    return attrs


def _is_object_range(range_value: Any, all_classes: Dict[str, Dict[str, Any]]) -> bool:
    return isinstance(range_value, str) and range_value in all_classes


def _column_for_slot(
    slot_name: str,
    slot_def: Dict[str, Any],
    class_name: str,
    prefix: str,
    class_iri_map: Dict[str, str],
) -> Dict[str, Any]:
    field_id = _slot_id(slot_name)
    rng = slot_def.get("range")
    if rng in NUMERIC_RANGES:
        semantic_type = "measurement"
    else:
        semantic_type = "categorical"
    required = bool(slot_def.get("required", False))
    severity = "high" if required else "low"
    class_iri_map[field_id] = f"{prefix}:{class_name}.{slot_name}"
    return {
        "id": field_id,
        "name_patterns": [slot_name.lower(), field_id],
        "semantic_type": semantic_type,
        "required": required,
        "severity": severity,
    }


def _metadata_for_slot(
    slot_name: str,
    class_name: str,
    prefix: str,
    class_iri_map: Dict[str, str],
) -> Dict[str, Any]:
    field_id = _slot_id(slot_name)
    class_iri_map[field_id] = f"{prefix}:{class_name}.{slot_name}"
    return {
        "id": field_id,
        "arrive_section": f"{prefix} / {class_name}",
        "severity": "medium",
    }


def linkml_to_template(linkml: Dict[str, Any], target_class: Optional[str] = None) -> Dict[str, Any]:
    """Convert a LinkML schema dict into a FAIR-VCG template dict.

    target_class: when given, build required_columns from that class's attributes.
    When None, build a metadata-only template from data-like classes.
    """
    if not isinstance(linkml, dict):
        raise ValueError("LinkML schema must be a mapping.")
    if "classes" not in linkml and "slots" not in linkml:
        raise ValueError("Input does not look like a LinkML schema (no 'classes' or 'slots' block).")

    schema_id = linkml.get("id") or linkml.get("name") or "imported"
    base_slug = _slugify(str(schema_id))
    tid = f"{base_slug}-imported-v1"

    prefixes = linkml.get("prefixes") or {}
    prefix_key = ""
    iri = ""
    if isinstance(prefixes, dict) and prefixes:
        first_key = next(iter(prefixes))
        first_val = prefixes[first_key]
        prefix_key = str(first_key)
        if isinstance(first_val, dict):
            iri = str(first_val.get("prefix_reference") or first_val.get("prefix") or "")
        elif isinstance(first_val, str):
            iri = first_val
    if not iri:
        iri = str(schema_id) if str(schema_id).startswith("http") else ""
    if not prefix_key:
        prefix_key = base_slug.upper().replace("-", "_")

    all_classes = extract_classes(linkml)
    class_iri_map: Dict[str, str] = {}
    required_columns: List[Dict[str, Any]] = []
    required_metadata: List[Dict[str, Any]] = []

    template_description = (
        str(linkml.get("description") or "").strip().split("\n")[0]
        if linkml.get("description") else ""
    )
    description = (
        "Auto-imported from LinkML schema. Review required_columns and "
        "required_metadata before assigning."
    )
    if template_description:
        description = f"{template_description} (auto-imported — review before use)"

    if target_class:
        if target_class not in all_classes:
            raise ValueError(f"target_class '{target_class}' not found in schema.")
        cls = all_classes[target_class]
        attrs = flatten_attributes(cls, all_classes)
        for slot_name, slot_def in attrs.items():
            rng = slot_def.get("range")
            if _is_object_range(rng, all_classes):
                continue
            required_columns.append(_column_for_slot(slot_name, slot_def, target_class, prefix_key, class_iri_map))
    else:
        seen_field_ids: Set[str] = set()
        for cname, cdef in all_classes.items():
            if cdef.get("abstract"):
                continue
            if cname in STRUCTURAL_CLASSES:
                continue
            attrs = flatten_attributes(cdef, all_classes)
            has_numeric = any(
                (a or {}).get("range") in NUMERIC_RANGES for a in attrs.values()
            )
            is_data_like = bool(DATA_LIKE_PATTERNS.search(cname)) or has_numeric
            if not is_data_like:
                continue
            for slot_name, slot_def in attrs.items():
                if _is_object_range(slot_def.get("range"), all_classes):
                    continue
                field_id = _slot_id(slot_name)
                if field_id in seen_field_ids:
                    continue
                seen_field_ids.add(field_id)
                required_metadata.append(_metadata_for_slot(slot_name, cname, prefix_key, class_iri_map))

    template: Dict[str, Any] = {
        "id": tid,
        "name": str(linkml.get("title") or linkml.get("name") or tid),
        "version": str(linkml.get("version") or "1.0"),
        "description": description,
        "conforms_to": [],
        "ontology": {"iri": iri, "prefix": prefix_key} if iri or prefix_key else {},
        "class_iri_map": class_iri_map,
    }
    if iri:
        template["identifier"] = iri
    if required_columns:
        template["required_columns"] = required_columns
    if required_metadata:
        template["required_metadata"] = required_metadata

    _validate_template_dict(template)
    return template


def parse_linkml_yaml(content: str) -> Dict[str, Any]:
    """Parse LinkML YAML content with a clean error message on failure."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("LinkML schema must be a YAML mapping at the top level.")
    return data
