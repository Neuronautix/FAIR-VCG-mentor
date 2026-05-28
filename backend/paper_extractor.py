import base64
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF using pypdf. Returns empty string on failure."""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages[:30]]
        return "\n\n".join(p for p in pages if p.strip())
    except Exception as exc:
        logger.warning("pypdf extraction failed: %s", exc)
        return ""

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


def _extract_with_anthropic(pdf_bytes: bytes, filename: str, api_key: str) -> Dict[str, Any]:
    """Extract paper metadata using Anthropic's native PDF input."""
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
    result["_method"] = "native_pdf"
    return result


def _extract_with_openai(pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract paper metadata using OpenAI function calling with pypdf text extraction."""
    import json
    import openai_service

    if not openai_service.is_configured():
        raise RuntimeError("OpenAI API key not configured.")

    text = _extract_text_from_pdf(pdf_bytes)
    if not text.strip():
        raise RuntimeError(
            "Could not extract text from PDF. The file may be scanned or image-only. "
            "An Anthropic API key supports native PDF layout-aware extraction for such files."
        )

    try:
        import openai
    except ImportError:
        raise RuntimeError("The 'openai' package is not installed.")

    client = openai.OpenAI(api_key=openai_service._api_key)
    oai_tool = {
        "type": "function",
        "function": {
            "name": _EXTRACT_TOOL["name"],
            "description": _EXTRACT_TOOL["description"],
            "parameters": _EXTRACT_TOOL["input_schema"],
        },
    }
    resp = client.chat.completions.create(
        model=openai_service.OPENAI_MODEL,
        max_tokens=4096,
        tools=[oai_tool],
        tool_choice={"type": "function", "function": {"name": _EXTRACT_TOOL["name"]}},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Extract metadata from this scientific paper:\n\n{text[:12000]}"
                ),
            },
        ],
        temperature=0.1,
    )
    for choice in resp.choices:
        if choice.message.tool_calls:
            return json.loads(choice.message.tool_calls[0].function.arguments)
    raise RuntimeError("OpenAI returned no structured extraction result.")


def extract_from_text(text: str) -> Dict[str, Any]:
    """Extract ARRIVE/PREPARE metadata from plain text (e.g. protocol notes).

    Works with both Anthropic and OpenAI providers.
    """
    import openai_service

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        # Use Anthropic path with text as a simple user message
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("The 'anthropic' package is not installed.")
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=os.getenv("PAPER_EXTRACTION_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=4096,
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "extract_paper_metadata"},
            messages=[{"role": "user", "content": f"Extract metadata from this text:\n\n{text[:12000]}"}],
        )
        result = message.content[0].input
        result["_method"] = "text_input"
    elif openai_service.is_configured():
        result = _extract_with_openai(text.encode("utf-8"), "text_input.txt")
        # _extract_with_openai falls back to passing pdf_bytes through pypdf;
        # for plain text we call OpenAI directly instead
        import json
        try:
            import openai
        except ImportError:
            raise RuntimeError("The 'openai' package is not installed.")
        client = openai.OpenAI(api_key=openai_service._api_key)
        oai_tool = {
            "type": "function",
            "function": {
                "name": _EXTRACT_TOOL["name"],
                "description": _EXTRACT_TOOL["description"],
                "parameters": _EXTRACT_TOOL["input_schema"],
            },
        }
        resp = client.chat.completions.create(
            model=openai_service.OPENAI_MODEL,
            max_tokens=4096,
            tools=[oai_tool],
            tool_choice={"type": "function", "function": {"name": _EXTRACT_TOOL["name"]}},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract metadata from this text:\n\n{text[:12000]}"},
            ],
            temperature=0.1,
        )
        result = {}
        for choice in resp.choices:
            if choice.message.tool_calls:
                result = json.loads(choice.message.tool_calls[0].function.arguments)
                break
        if not result:
            raise RuntimeError("OpenAI returned no structured extraction result.")
        result["_method"] = "text_input"
    else:
        raise RuntimeError(
            "No AI provider configured. Add an OpenAI key in Settings or set ANTHROPIC_API_KEY."
        )

    result["_filename"] = "text_input"
    result["_file_size_kb"] = round(len(text.encode()) / 1024)
    # Defensive default-fill
    prepare_block = result.get("prepare") or {}
    for field_id in _PREPARE_FIELDS:
        entry = prepare_block.get(field_id)
        if not isinstance(entry, dict) or "value" not in entry or "status" not in entry:
            prepare_block[field_id] = {"value": None, "status": "missing"}
    result["prepare"] = prepare_block
    return result


def extract_paper_metadata(pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    if len(pdf_bytes) > _PDF_MAX_BYTES:
        raise RuntimeError(
            f"PDF is {len(pdf_bytes) // (1024*1024):.1f} MB — "
            f"the Anthropic API limit is 32 MB. Please use a smaller file."
        )

    import openai_service

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        result = _extract_with_anthropic(pdf_bytes, filename, api_key)
    elif openai_service.is_configured():
        result = _extract_with_openai(pdf_bytes, filename)
    else:
        raise RuntimeError(
            "No AI provider configured. Add an OpenAI key in Settings or set ANTHROPIC_API_KEY."
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
    if "_method" not in result:
        result["_method"] = "native_pdf"
    return result
