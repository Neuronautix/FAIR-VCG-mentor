import base64
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 32 MB — Anthropic's hard limit for native PDF input
_PDF_MAX_BYTES = 32 * 1024 * 1024

_SYSTEM_PROMPT = (
    "You are a scientific data management assistant specialising in preclinical and "
    "clinical research. Extract structured metadata from scientific papers."
)

# Tool definition with input_schema mirroring the original _EXTRACTION_SCHEMA structure
_EXTRACT_TOOL = {
    "name": "extract_paper_metadata",
    "description": (
        "Extract structured metadata from a scientific paper PDF, including dataset "
        "metadata, ARRIVE 2.0 checklist items, VCG configuration hints, and a summary."
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
        "required": ["dataset_metadata", "arrive", "vcg_hints", "summary"],
    },
}


def extract_paper_metadata(pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    if len(pdf_bytes) > _PDF_MAX_BYTES:
        raise RuntimeError(
            f"PDF is {len(pdf_bytes) // (1024*1024):.1f} MB — "
            f"the Anthropic API limit is 32 MB. Please use a smaller file."
        )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured. "
            "Set this environment variable to enable LLM-powered paper extraction."
        )

    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "The 'anthropic' package is not installed. "
            "Add it to requirements.txt and reinstall dependencies."
        )

    client = anthropic.Anthropic(api_key=api_key)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    message = client.messages.create(
        model=os.getenv("PAPER_EXTRACTION_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=4096,
        # Cache the static system prompt — saves input tokens on repeated calls within
        # the same server process (ephemeral cache TTL is ~5 min).
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[_EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_paper_metadata"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": "Extract metadata from this scientific paper."},
                ],
            }
        ],
    )

    # With tool_choice forced, content[0] is always the tool_use block.
    # .input is already a parsed dict — no JSON parsing needed.
    result = message.content[0].input

    result["_filename"] = filename
    result["_file_size_kb"] = round(len(pdf_bytes) / 1024)
    result["_method"] = "native_pdf"
    return result
