"""
Two-layer NTS (Non-Technical Summary) analyser.

Layer 1 (deterministic): pdfminer.six text extraction + regex citation detection for
ARRIVE and PREPARE guidelines.

Layer 2 (LLM, optional): forced tool-call schema extraction of NTS metadata mapped to
ARRIVE/PREPARE field IDs using the Anthropic API with native PDF document input.
"""

import base64
import io
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 32 MB — Anthropic's hard limit for native PDF input
_PDF_MAX_BYTES = 32 * 1024 * 1024

# ---------------------------------------------------------------------------
# Layer 1 — compiled regex patterns for citation detection
# ---------------------------------------------------------------------------

# Each entry: (compiled_pattern, tier_string)
# Tiers: "doi" | "full_title" | "author_year" | "explicit_name"

_ARRIVE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'10\.1371/journal\.pbio\.3000410', re.IGNORECASE), "doi"),
    (re.compile(r'10\.1371/journal\.pbio\.1000412', re.IGNORECASE), "doi"),
    (re.compile(r'Animal\s+Research:\s*Reporting\s+of\s+In\s+Vivo\s+Experiments', re.IGNORECASE), "full_title"),
    (re.compile(r'Animal\s+Research[:\s]+Reporting[^\n]{0,50}In\s+Vivo', re.IGNORECASE), "full_title"),
    (re.compile(r'Kilkenny\s+et\s+al[.,\s]+\(?\s*(?:200[0-9]|20[12][0-9])', re.IGNORECASE), "author_year"),
    (re.compile(r'Percie\s+du\s+Sert\s+et\s+al[.,\s]+\(?\s*(?:20[12][0-9])', re.IGNORECASE), "author_year"),
    (re.compile(r'\bARRIVE\s+2\.0\b'), "explicit_name"),
    (re.compile(r'\bARRIVE\b'), "explicit_name"),
]

_PREPARE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'10\.1111/bph\.14376', re.IGNORECASE), "doi"),
    (re.compile(r'Planning\s+Research\s+and\s+Experimental\s+Procedures\s+on\s+Animals', re.IGNORECASE), "full_title"),
    (re.compile(r'Smith\s+et\s+al[.,\s]+\(?\s*(?:2018|2019)', re.IGNORECASE), "author_year"),
    (re.compile(r'\bNorecopa\b', re.IGNORECASE), "author_year"),
    (re.compile(r'\bPREPARE\s+(?:guidelines|checklist|recommendations|criteria|planning|framework)\b'), "explicit_name"),
    (re.compile(r'\bPREPARE\b'), "explicit_name"),
]

# ---------------------------------------------------------------------------
# Layer 2 — NTS field registry and LLM tool definition
# ---------------------------------------------------------------------------

# Each tuple: (field_id, description, arrive_field_id_or_None, prepare_field_id_or_None)
_NTS_FIELD_REGISTRY: List[Tuple[str, str, Optional[str], Optional[str]]] = [
    ("study_title", "Full title of the research project as stated in the NTS", "study_title", None),
    ("project_licence", "Project licence, permit, or authorization number and issuing authority (e.g. PPL P1234567, Home Office UK)", "project_licence", "prepare_legal_issues"),
    ("regulatory_authority", "Name of the competent authority that approved the project (e.g. Home Office, ANSES, BMEL)", None, None),
    ("nts_date", "Year or full date the NTS was submitted or approved", None, None),
    ("species", "Scientific name(s) of species to be used (e.g. Mus musculus)", "species", None),
    ("strain", "Strain, breed, substrain, or genetic line", "strain", None),
    ("sex", "Sex of animals: male / female / both / not specified", "sex", None),
    ("age", "Age or developmental stage at start of procedures", "age", None),
    ("total_n", "Total number of animals requested or to be used", "total_n", None),
    ("experimental_groups", "Description of experimental treatment and control groups", "experimental_groups", None),
    ("sample_size_per_group", "Number of animals per experimental group", "sample_size_per_group", None),
    ("severity_classification", "Severity band: non-recovery / mild / moderate / severe", "severity_classification", "prepare_severity"),
    ("humane_endpoints", "Predefined humane endpoints and criteria for early termination of procedures", "humane_endpoints", "prepare_humane_endpoints"),
    ("adverse_events", "Expected adverse events and their predicted incidence", "adverse_events", None),
    ("procedures_description", "Summary of main experimental procedures applied to animals", "procedures_description", None),
    ("outcome_measures", "Primary and secondary outcome measures or endpoints", "outcome_measures", None),
    ("three_rs_replacement", "Justification that animals cannot be replaced by non-animal alternatives (Replacement principle)", None, None),
    ("three_rs_reduction", "Measures to minimise the number of animals used (Reduction principle), including statistical justification", None, None),
    ("three_rs_refinement", "Refinements applied to minimise pain, suffering, distress or lasting harm (Refinement principle)", None, None),
    ("prepare_lay_summary", "Plain-language explanation of project objectives, expected benefits, and relevance to animal welfare or human medicine", None, "prepare_lay_summary"),
    ("prepare_harm_benefit", "Harm-benefit assessment: animal welfare costs weighed against expected scientific or social benefits", None, "prepare_harm_benefit_assessment"),
    ("prepare_literature_searches", "Evidence of systematic literature review; justification for species or model choice; description of search strategy", None, "prepare_literature_searches"),
]

_NTS_SYSTEM_PROMPT = (
    "You are a regulatory document analyst specialising in animal research Non-Technical "
    "Summaries (NTS) as required under EU Directive 2010/63/EU and equivalent national "
    "legislation. Extract structured metadata from the NTS document."
)


def _build_llm_tool() -> dict:
    """Build the Anthropic tool definition dict dynamically from _NTS_FIELD_REGISTRY."""
    properties: Dict[str, dict] = {}
    for field_id, description, _arrive_fid, _prepare_fid in _NTS_FIELD_REGISTRY:
        properties[field_id] = {
            "type": "object",
            "properties": {
                "value": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "description": description,
                },
                "status": {
                    "type": "string",
                    "enum": ["found", "inferred", "missing"],
                    "description": (
                        "found=explicitly stated in document; "
                        "inferred=reasonably deduced from context; "
                        "missing=not present"
                    ),
                },
                "evidence": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "description": (
                        "Verbatim quote from the document supporting this value, "
                        "max 300 chars, or null"
                    ),
                },
            },
            "required": ["value", "status", "evidence"],
        }

    return {
        "name": "extract_nts_metadata",
        "description": (
            "Extract structured metadata from a Non-Technical Summary (NTS) of an animal "
            "research project. Each field must have a value (or null), a status, and a "
            "verbatim evidence quote from the document."
        ),
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": [entry[0] for entry in _NTS_FIELD_REGISTRY],
        },
    }


# Build the tool once at module level — zero network calls, just dict construction.
_NTS_TOOL = _build_llm_tool()

# ---------------------------------------------------------------------------
# Layer 1 — text extraction and citation detection
# ---------------------------------------------------------------------------


def _extract_text_pages(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """Extract per-page text from a PDF using pdfminer.six.

    Returns a list of (page_number_1based, text_string) tuples.
    Raises RuntimeError if pdfminer.six is not installed or extraction fails.
    """
    try:
        from pdfminer.pdfpage import PDFPage
        from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
        from pdfminer.converter import TextConverter
        from pdfminer.layout import LAParams
    except ImportError:
        raise RuntimeError(
            "pdfminer.six is not installed. "
            "Add 'pdfminer.six' to requirements.txt and reinstall dependencies."
        )

    try:
        pages: List[Tuple[int, str]] = []
        rsrcmgr = PDFResourceManager()
        pdf_file = io.BytesIO(pdf_bytes)

        for page_num, page in enumerate(
            PDFPage.get_pages(pdf_file, check_extractable=False), start=1
        ):
            output = io.StringIO()
            device = TextConverter(rsrcmgr, output, laparams=LAParams())
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            interpreter.process_page(page)
            device.close()
            pages.append((page_num, output.getvalue()))

        return pages
    except Exception as exc:
        raise RuntimeError(
            f"pdfminer.six failed to extract text from PDF: {exc}"
        ) from exc


def _find_matches(
    pages: List[Tuple[int, str]],
    patterns: List[Tuple[re.Pattern, str]],
) -> List[Dict]:
    """Search all pages for pattern matches, deduplicate, and return match dicts.

    Each dict has keys: matched_text, context, page, tier.
    Context is 150 characters before and after the match (newlines replaced with spaces).
    Deduplication is by lowercased matched_text.
    """
    results: List[Dict] = []
    seen_lower: set = set()

    for page_num, text in pages:
        for pattern, tier in patterns:
            for match in pattern.finditer(text):
                matched_text = match.group(0)
                lower_key = matched_text.lower()
                if lower_key in seen_lower:
                    continue
                seen_lower.add(lower_key)

                start = max(0, match.start() - 150)
                end = min(len(text), match.end() + 150)
                context = text[start:end].replace("\n", " ")

                results.append(
                    {
                        "matched_text": matched_text,
                        "context": context,
                        "page": page_num,
                        "tier": tier,
                    }
                )

    return results


def detect_citations(pages: List[Tuple[int, str]]) -> Dict:
    """Run citation detection for ARRIVE and PREPARE patterns.

    Returns:
        {
            "arrive": {"cited": bool, "evidence": [...]},
            "prepare": {"cited": bool, "evidence": [...]}
        }
    """
    arrive_matches = _find_matches(pages, _ARRIVE_PATTERNS)
    prepare_matches = _find_matches(pages, _PREPARE_PATTERNS)

    return {
        "arrive": {
            "cited": len(arrive_matches) > 0,
            "evidence": arrive_matches,
        },
        "prepare": {
            "cited": len(prepare_matches) > 0,
            "evidence": prepare_matches,
        },
    }


def _classify(citation_result: Dict) -> str:
    """Classify citation result into one of four categories."""
    a = citation_result["arrive"]["cited"]
    p = citation_result["prepare"]["cited"]
    if a and p:
        return "BOTH"
    if a:
        return "ARRIVE_ONLY"
    if p:
        return "PREPARE_ONLY"
    return "NEITHER"


# ---------------------------------------------------------------------------
# Layer 2 — LLM metadata extraction
# ---------------------------------------------------------------------------


def _extract_metadata_llm(pdf_bytes: bytes, filename: str) -> Dict:
    """Extract structured NTS metadata using the Anthropic API (forced tool call).

    Raises RuntimeError if ANTHROPIC_API_KEY is not set, anthropic is not installed,
    or the PDF exceeds the size limit.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured. "
            "Set this environment variable to enable LLM-powered NTS analysis."
        )

    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "The 'anthropic' package is not installed. "
            "Add it to requirements.txt and reinstall dependencies."
        )

    if len(pdf_bytes) > _PDF_MAX_BYTES:
        raise RuntimeError(
            f"PDF is {len(pdf_bytes) / (1024 * 1024):.1f} MB — "
            f"the Anthropic API limit is 32 MB. Please use a smaller file."
        )

    client = anthropic.Anthropic(api_key=api_key)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    message = client.messages.create(
        model=os.getenv("PAPER_EXTRACTION_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": _NTS_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tool_choice={"type": "tool", "name": "extract_nts_metadata"},
        tools=[_NTS_TOOL],
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
                    {
                        "type": "text",
                        "text": "Extract all metadata from this Non-Technical Summary document.",
                    },
                ],
            }
        ],
    )

    # With tool_choice forced, content[0] is always the tool_use block.
    result: Dict = message.content[0].input

    # Build a lookup from field_id → (arrive_fid, prepare_fid) for programmatic addition
    registry_lookup: Dict[str, Tuple[Optional[str], Optional[str]]] = {
        entry[0]: (entry[2], entry[3]) for entry in _NTS_FIELD_REGISTRY
    }

    # Defensive fill: ensure every field_id is present and well-formed
    for field_id, (arrive_fid, prepare_fid) in registry_lookup.items():
        entry = result.get(field_id)
        if not isinstance(entry, dict) or not all(
            k in entry for k in ("value", "status", "evidence")
        ):
            result[field_id] = {"value": None, "status": "missing", "evidence": None}

        # Add field IDs from the registry (not from LLM)
        result[field_id]["arrive_field_id"] = arrive_fid
        result[field_id]["prepare_field_id"] = prepare_fid

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze_nts(pdf_bytes: bytes, filename: str, use_llm: bool = True) -> Dict:
    """Analyse a Non-Technical Summary PDF.

    Runs Layer 1 (pdfminer text extraction + regex citation detection) unconditionally.
    Runs Layer 2 (LLM metadata extraction) if use_llm=True and ANTHROPIC_API_KEY is set.

    Returns a result dict with keys:
        filename, analyzed_at, text_quality, layer1, classification,
        layer2, layer2_available, layer2_error, layer1_error
    """
    result: Dict = {
        "filename": filename,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "text_quality": {
            "page_count": 0,
            "total_chars": 0,
            "extraction_method": "pdfminer.six",
            "extraction_warning": None,
        },
        "layer1": {
            "arrive": {"cited": False, "evidence": []},
            "prepare": {"cited": False, "evidence": []},
        },
        "classification": "NEITHER",
        "layer2": None,
        "layer2_available": False,
        "layer2_error": None,
        "layer1_error": None,
    }

    # --- Layer 1: text extraction ---
    pages: List[Tuple[int, str]] = []
    try:
        pages = _extract_text_pages(pdf_bytes)
        total_chars = sum(len(text) for _, text in pages)
        result["text_quality"] = {
            "page_count": len(pages),
            "total_chars": total_chars,
            "extraction_method": "pdfminer.six",
            "extraction_warning": (
                "Very little text extracted — the PDF may be image-based or encrypted."
                if total_chars < 200
                else None
            ),
        }
    except RuntimeError as exc:
        logger.warning("NTS text extraction failed for '%s': %s", filename, exc)
        result["layer1_error"] = str(exc)
        result["text_quality"] = {
            "page_count": 0,
            "total_chars": 0,
            "extraction_method": "pdfminer.six",
            "extraction_warning": "Text extraction failed.",
        }

    # --- Layer 1: citation detection ---
    citation_result = detect_citations(pages)
    result["layer1"] = citation_result
    result["classification"] = _classify(citation_result)

    # --- Layer 2: LLM metadata extraction (optional) ---
    if use_llm and os.getenv("ANTHROPIC_API_KEY"):
        try:
            result["layer2"] = _extract_metadata_llm(pdf_bytes, filename)
            result["layer2_available"] = True
            logger.info("NTS Layer 2 extraction succeeded for '%s'", filename)
        except Exception as exc:
            logger.warning("NTS Layer 2 extraction failed for '%s': %s", filename, exc)
            result["layer2_error"] = str(exc)
            result["layer2"] = None
            result["layer2_available"] = False
    else:
        if use_llm and not os.getenv("ANTHROPIC_API_KEY"):
            logger.info(
                "Skipping NTS Layer 2 for '%s': ANTHROPIC_API_KEY not set.", filename
            )

    return result
