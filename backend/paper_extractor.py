import base64
import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 32 MB — Anthropic's hard limit for native PDF input
_PDF_MAX_BYTES = 32 * 1024 * 1024

_SYSTEM_PROMPT = (
    "You are a scientific data management assistant specialising in preclinical and "
    "clinical research. Extract structured metadata from scientific papers. "
    "Return only valid JSON — no markdown fences, no extra explanation."
)

_EXTRACTION_SCHEMA = """\
Return a JSON object with EXACTLY this structure:
{
  "dataset_metadata": {
    "title": "paper or dataset title (string or null)",
    "description": "brief study description suitable as a dataset description (string or null)",
    "creator": "first author full name (string or null)",
    "institution": "primary affiliation (string or null)",
    "species": "scientific name e.g. Mus musculus (string or null)",
    "study_type": "e.g. interventional, observational, randomised controlled trial (string or null)",
    "keywords": ["keyword1", "keyword2"],
    "license": "suggested open license e.g. CC BY 4.0 (string or null)",
    "funding_source": "funding body and grant reference if stated (string or null)",
    "protocol_reference": "DOI or URL to preregistration/protocol if stated (string or null)"
  },
  "arrive": {
    "study_design": {"value": "description or null", "status": "found|inferred|missing"},
    "sample_size": {"value": "e.g. n=10 per group or null", "status": "found|inferred|missing"},
    "inclusion_exclusion_criteria": {"value": "description or null", "status": "found|inferred|missing"},
    "randomisation": {"value": "description or null", "status": "found|inferred|missing"},
    "blinding": {"value": "description or null", "status": "found|inferred|missing"},
    "outcome_measures": {"value": "list of primary and secondary endpoints or null", "status": "found|inferred|missing"},
    "statistical_methods": {"value": "statistical tests and software used or null", "status": "found|inferred|missing"},
    "experimental_animals": {"value": "species, strain, sex, age, weight or null", "status": "found|inferred|missing"},
    "housing_husbandry": {"value": "housing conditions, diet, light cycle or null", "status": "found|inferred|missing"},
    "ethics_statement": {"value": "ethics committee name and approval number or null", "status": "found|inferred|missing"},
    "adverse_events": {"value": "description of adverse events or null", "status": "found|inferred|missing"},
    "interpretation": {"value": "main findings and conclusions or null", "status": "found|inferred|missing"}
  },
  "vcg_hints": {
    "treatment_column_name": "plausible snake_case CSV column name for treatment/group variable or null",
    "control_group_label": "exact label used for control group e.g. Vehicle, Sham, Control or null",
    "treatment_group_label": "exact label used for treatment group or null",
    "outcome_columns": ["plausible", "snake_case", "csv", "column", "names"],
    "covariate_columns": ["plausible", "snake_case", "csv", "column", "names"],
    "n_control": null,
    "n_treatment": null
  },
  "summary": "2-3 sentence summary of what was successfully extracted and what key information is missing"
}

Field status rules:
- "found": information is explicitly stated verbatim in the paper
- "inferred": you are making a reasonable inference from context
- "missing": information is not present in the text (set value to null)

n_control and n_treatment must be integers if mentioned, otherwise null.
Outcome and covariate column name lists may be empty arrays if nothing can be inferred.
"""


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
        # Cache the static schema — saves input tokens on repeated calls within
        # the same server process (ephemeral cache TTL is ~5 min).
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT + "\n\n" + _EXTRACTION_SCHEMA,
                "cache_control": {"type": "ephemeral"},
            }
        ],
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

    raw = message.content[0].text.strip()

    # Strip accidental markdown fences the model might add despite instructions
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:])
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned invalid JSON: %s\nSnippet: %.500s", exc, raw)
        raise RuntimeError(f"LLM returned malformed JSON: {exc}") from exc

    result["_filename"] = filename
    result["_file_size_kb"] = round(len(pdf_bytes) / 1024)
    result["_method"] = "native_pdf"
    return result
