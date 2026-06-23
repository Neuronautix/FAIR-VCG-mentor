import base64
import logging
import os
from typing import Any, Dict

from env_loader import load_local_env

logger = logging.getLogger(__name__)
load_local_env()

# 32 MB — Anthropic's hard limit for native PDF input
_PDF_MAX_BYTES = 32 * 1024 * 1024

_SYSTEM_PROMPT = (
    "You are a scientific data management assistant specialising in preclinical and "
    "clinical research. Extract structured metadata from scientific papers, including "
    "ARRIVE 2.0 reporting items and PREPARE pre-study planning topics."
)

# PREPARE-only field ids (those not already covered by the ARRIVE block).
# `housing_husbandry` is included because PREPARE expects deeper detail than ARRIVE.
_PREPARE_FIELDS = (
    "literature_searches",
    "legal_issues",
    "lay_summary",
    "harm_benefit_assessment",
    "severity_classification",
    "humane_endpoints",
    "facility_evaluation",
    "education_training",
    "health_risks_waste",
    "quarantine_health_monitoring",
    "housing_husbandry",
    "humane_killing",
    "necropsy",
)


def _prepare_field_schema(description: str) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "value": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": description,
            },
            "status": {
                "type": "string",
                "enum": ["found", "inferred", "missing"],
                "description": "found=explicitly stated, inferred=reasonable inference, missing=not present.",
            },
        },
        "required": ["value", "status"],
    }


_PREPARE_FIELD_DESCRIPTIONS: Dict[str, str] = {
    "literature_searches": "Systematic literature review, search strategy, species relevance and translatability rationale, or null.",
    "legal_issues": "Applicable legislation, regulatory permits, guidance documents observed, or null.",
    "lay_summary": "Plain-language summary of the project as required by project licensing, or null.",
    "harm_benefit_assessment": "Harm-benefit analysis weighing animal welfare costs against scientific benefit, or null.",
    "severity_classification": "Procedure severity classification (e.g. mild, moderate, severe) per EU Directive 2010/63 or equivalent, or null.",
    "humane_endpoints": "Predefined humane endpoints and criteria for early termination, or null.",
    "facility_evaluation": "Assessment of facility suitability (housing, equipment, biosecurity) for the planned study, or null.",
    "education_training": "Personnel qualifications, training records, and competency assurance, or null.",
    "health_risks_waste": "Occupational health risks (zoonoses, allergens, sharps) and waste-handling procedures, or null.",
    "quarantine_health_monitoring": "Quarantine policy, acclimatisation period, and sentinel/health-monitoring programme, or null.",
    "housing_husbandry": "Detailed housing, husbandry, environmental enrichment and social housing arrangements (PREPARE expects more depth than ARRIVE), or null.",
    "humane_killing": "Method of humane killing, operator competency, and confirmation of death, or null.",
    "necropsy": "Planned necropsy procedures, tissue collection, and post-mortem analyses, or null.",
}

# Tool definition with input_schema mirroring the original _EXTRACTION_SCHEMA structure
_EXTRACT_TOOL = {
    "name": "extract_paper_metadata",
    "description": (
        "Extract structured metadata from a scientific paper PDF, including dataset "
        "metadata, ARRIVE 2.0 checklist items, PREPARE pre-study planning topics, "
        "VCG configuration hints, and a summary."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "dataset_metadata": {
                "type": "object",
                "description": "Core bibliographic and study-level metadata.",
                "properties": {
                    "title": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Paper or dataset title.",
                    },
                    "description": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Brief study description suitable as a dataset description.",
                    },
                    "creator": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "First author full name.",
                    },
                    "institution": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Primary affiliation.",
                    },
                    "species": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Scientific name e.g. Mus musculus.",
                    },
                    "study_type": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "e.g. interventional, observational, randomised controlled trial.",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of keywords describing the study.",
                    },
                    "license": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Suggested open license e.g. CC BY 4.0.",
                    },
                    "funding_source": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Funding body and grant reference if stated.",
                    },
                    "protocol_reference": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "DOI or URL to preregistration/protocol if stated.",
                    },
                },
                "required": [
                    "title", "description", "creator", "institution", "species",
                    "study_type", "keywords", "license", "funding_source", "protocol_reference",
                ],
            },
            "arrive": {
                "type": "object",
                "description": "ARRIVE 2.0 checklist fields. Each field is an object with a value and a status.",
                "properties": {
                    "study_design": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Description of study design or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"], "description": "found=explicitly stated, inferred=reasonable inference, missing=not present."},
                        },
                        "required": ["value", "status"],
                    },
                    "sample_size": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "e.g. n=10 per group or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                    "inclusion_exclusion_criteria": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Description of inclusion/exclusion criteria or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                    "randomisation": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Description of randomisation method or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                    "blinding": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Description of blinding approach or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                    "outcome_measures": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "List of primary and secondary endpoints or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                    "statistical_methods": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Statistical tests and software used or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                    "experimental_animals": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Species, strain, sex, age, weight or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                    "housing_husbandry": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Housing conditions, diet, light cycle or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                    "ethics_statement": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Ethics committee name and approval number or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                    "adverse_events": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Description of adverse events or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                    "interpretation": {
                        "type": "object",
                        "properties": {
                            "value": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Main findings and conclusions or null."},
                            "status": {"type": "string", "enum": ["found", "inferred", "missing"]},
                        },
                        "required": ["value", "status"],
                    },
                },
                "required": [
                    "study_design", "sample_size", "inclusion_exclusion_criteria",
                    "randomisation", "blinding", "outcome_measures", "statistical_methods",
                    "experimental_animals", "housing_husbandry", "ethics_statement",
                    "adverse_events", "interpretation",
                ],
            },
            "prepare": {
                "type": "object",
                "description": (
                    "PREPARE (Smith et al. 2018) pre-study planning checklist fields not "
                    "already covered by ARRIVE. Each field is an object with a value and a status."
                ),
                "properties": {
                    field_id: _prepare_field_schema(_PREPARE_FIELD_DESCRIPTIONS[field_id])
                    for field_id in _PREPARE_FIELDS
                },
                "required": list(_PREPARE_FIELDS),
            },
            "vcg_hints": {
                "type": "object",
                "description": "Hints for pre-filling the Virtual Control Group configuration wizard.",
                "properties": {
                    "treatment_column_name": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Plausible snake_case CSV column name for treatment/group variable.",
                    },
                    "control_group_label": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Exact label used for control group e.g. Vehicle, Sham, Control.",
                    },
                    "treatment_group_label": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "Exact label used for treatment group.",
                    },
                    "outcome_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Plausible snake_case CSV column names for outcome variables.",
                    },
                    "covariate_columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Plausible snake_case CSV column names for covariate variables.",
                    },
                    "n_control": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": "Number of control subjects if mentioned, otherwise null.",
                    },
                    "n_treatment": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": "Number of treatment subjects if mentioned, otherwise null.",
                    },
                },
                "required": [
                    "treatment_column_name", "control_group_label", "treatment_group_label",
                    "outcome_columns", "covariate_columns", "n_control", "n_treatment",
                ],
            },
            "summary": {
                "type": "string",
                "description": (
                    "2-3 sentence summary of what was successfully extracted and "
                    "what key information is missing."
                ),
            },
        },
        "required": ["dataset_metadata", "arrive", "prepare", "vcg_hints", "summary"],
    },
}


def extract_paper_metadata(pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    if len(pdf_bytes) > _PDF_MAX_BYTES:
        raise RuntimeError(
            f"PDF is {len(pdf_bytes) // (1024*1024):.1f} MB — "
            f"the Anthropic API limit is 32 MB. Please use a smaller file."
        )

    from llm_service import call_haiku

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()
    user_content = [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_b64,
            },
        },
        {"type": "text", "text": "Extract metadata from this scientific paper."},
    ]

    # Provider-agnostic: under the local (openai) provider the document block is
    # converted to text locally inside call_haiku; under anthropic it is sent as
    # a native PDF block.
    result = call_haiku(
        system_prompt=_SYSTEM_PROMPT,
        tool=_EXTRACT_TOOL,
        user_message=user_content,
        model_env="PAPER_EXTRACTION_MODEL",
        max_tokens=4096,
    )

    # Defensive default-fill: ensure every PREPARE field is present even if the
    # model omits one. Same shape used for arrive — missing => {"value": None, "status": "missing"}.
    prepare_block = result.get("prepare") or {}
    for field_id in _PREPARE_FIELDS:
        entry = prepare_block.get(field_id)
        if not isinstance(entry, dict) or "value" not in entry or "status" not in entry:
            prepare_block[field_id] = {"value": None, "status": "missing"}
    result["prepare"] = prepare_block

    result["_filename"] = filename
    result["_file_size_kb"] = round(len(pdf_bytes) / 1024)
    result["_method"] = "native_pdf"
    return result
