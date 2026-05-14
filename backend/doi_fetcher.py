import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict

_CROSSREF_BASE = "https://api.crossref.org/works/"
_USER_AGENT = "FAIR-VCG-Mentor/1.0 (mailto:admin@example.com)"

_LICENSE_MAP = {
    "creativecommons.org/licenses/by/4.0": "CC BY 4.0",
    "creativecommons.org/licenses/by-nc/4.0": "CC BY-NC 4.0",
    "creativecommons.org/publicdomain/zero/1.0": "CC0 1.0",
}

_MISSING = {"value": None, "status": "missing"}


def _strip_jats(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _map_license(url: str) -> str:
    for fragment, label in _LICENSE_MAP.items():
        if fragment in url:
            return label
    return url


def fetch_doi_metadata(doi: str) -> Dict[str, Any]:
    """Fetch bibliographic metadata from CrossRef for *doi* and return it in
    the same shape as ``extract_paper_metadata`` in ``paper_extractor.py``."""

    # Strip common prefixes
    doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    doi = doi.strip()

    encoded_doi = urllib.parse.quote(doi, safe="")
    url = _CROSSREF_BASE + encoded_doi

    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"CrossRef returned HTTP {exc.code} for DOI '{doi}'. "
            "Check that the DOI is correct."
        )
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach CrossRef API: {exc.reason}. "
            "Check your network connection."
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CrossRef returned invalid JSON: {exc}")

    msg = data.get("message", {})

    # ── dataset_metadata ────────────────────────────────────────────────────

    # title
    titles = msg.get("title") or []
    title = titles[0] if titles else None

    # description — strip JATS XML tags from abstract
    abstract = msg.get("abstract")
    description = _strip_jats(abstract) if abstract else None

    # creator & institution — first author
    authors = msg.get("author") or []
    creator = None
    institution = None
    if authors:
        first = authors[0]
        given = first.get("given", "").strip()
        family = first.get("family", "").strip()
        if given and family:
            creator = f"{given} {family}"
        elif family:
            creator = family

        affiliations = first.get("affiliation") or []
        if affiliations:
            institution = affiliations[0].get("name")

    # keywords — CrossRef `subject` field
    keywords = msg.get("subject") or []

    # license
    licenses = msg.get("license") or []
    license_val = None
    if licenses:
        raw_url = licenses[0].get("URL", "")
        license_val = _map_license(raw_url) if raw_url else None

    # funding_source — join first 3 funders as "name (award)"
    funders = msg.get("funder") or []
    funder_parts = []
    for funder in funders[:3]:
        name = funder.get("name", "").strip()
        awards = funder.get("award") or []
        award_str = awards[0] if awards else None
        if name and award_str:
            funder_parts.append(f"{name} ({award_str})")
        elif name:
            funder_parts.append(name)
    funding_source = "; ".join(funder_parts) if funder_parts else None

    # protocol_reference — always the canonical DOI URL
    protocol_reference = f"https://doi.org/{doi}"

    dataset_metadata = {
        "title": title,
        "description": description,
        "creator": creator,
        "institution": institution,
        "species": None,
        "study_type": None,
        "keywords": keywords,
        "license": license_val,
        "funding_source": funding_source,
        "protocol_reference": protocol_reference,
    }

    # ── ARRIVE checklist — all missing (no full text from CrossRef) ─────────
    arrive = {
        "study_design": dict(_MISSING),
        "sample_size": dict(_MISSING),
        "inclusion_exclusion_criteria": dict(_MISSING),
        "randomisation": dict(_MISSING),
        "blinding": dict(_MISSING),
        "outcome_measures": dict(_MISSING),
        "statistical_methods": dict(_MISSING),
        "experimental_animals": dict(_MISSING),
        "housing_husbandry": dict(_MISSING),
        "ethics_statement": dict(_MISSING),
        "adverse_events": dict(_MISSING),
        "interpretation": dict(_MISSING),
    }

    # ── VCG hints — all null / empty (no full text) ─────────────────────────
    vcg_hints = {
        "treatment_column_name": None,
        "control_group_label": None,
        "treatment_group_label": None,
        "outcome_columns": [],
        "covariate_columns": [],
        "n_control": None,
        "n_treatment": None,
    }

    summary = (
        f"Bibliographic metadata fetched from CrossRef for DOI {doi}. "
        "ARRIVE checklist and VCG column hints require the full PDF."
    )

    return {
        "dataset_metadata": dataset_metadata,
        "arrive": arrive,
        "vcg_hints": vcg_hints,
        "summary": summary,
        "_filename": f"DOI:{doi}",
        "_file_size_kb": 0,
        "_method": "crossref_doi",
    }
