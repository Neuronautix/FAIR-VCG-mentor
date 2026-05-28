import io
import re
import csv as csv_module
import warnings
from typing import Dict, List, Any, Tuple, Optional

import chardet
import pandas as pd

from column_constants import (
    BIOLOGICAL_PATTERNS,
    CONDITION_PATTERNS,
    IDENTIFIER_PATTERNS,
    IDENTIFIER_VALUE_PATTERNS,
    MEASUREMENT_PATTERNS,
    METADATA_PATTERNS,
    NOTE_PATTERNS,
    SEX_KEYWORDS,
    STRAIN_KEYWORDS,
    TIME_PATTERNS,
    UNIT_MAP,
)


# ── Encoding / delimiter detection ──────────────────────────────────────────


def detect_encoding(file_bytes: bytes) -> str:
    result = chardet.detect(file_bytes)
    return result.get('encoding') or 'utf-8'


def detect_delimiter(content: str) -> str:
    try:
        sniffer = csv_module.Sniffer()
        dialect = sniffer.sniff(content[:4096], delimiters=',;\t|')
        return dialect.delimiter
    except Exception:
        counts = {d: content[:2000].count(d) for d in [',', ';', '\t', '|']}
        return max(counts, key=counts.get)


# ── Value-shape validators (Stage 1, deterministic) ─────────────────────────


def _non_null_values(series: pd.Series, limit: int = 50) -> List[str]:
    """Return up to `limit` stripped non-empty string values."""
    if series is None or len(series) == 0:
        return []
    cleaned = series.astype(str).str.strip()
    cleaned = cleaned[cleaned.ne('') & cleaned.str.lower().ne('nan')]
    if len(cleaned) == 0:
        return []
    return cleaned.head(limit).tolist()


def values_look_like_identifiers(series: pd.Series, threshold: float = 0.6) -> bool:
    """True if at least `threshold` of non-null values match a known ID shape."""
    sample = _non_null_values(series, limit=50)
    if not sample:
        return False
    matches = 0
    for v in sample:
        for pattern in IDENTIFIER_VALUE_PATTERNS:
            if re.match(pattern, v):
                matches += 1
                break
    return matches / len(sample) >= threshold


def values_look_like_dates(series: pd.Series, threshold: float = 0.7) -> bool:
    """True if at least `threshold` of non-null values parse as dates."""
    sample = _non_null_values(series, limit=20)
    if not sample:
        return False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(pd.Series(sample), errors='coerce')
    return bool(parsed.notna().sum() / len(sample) >= threshold)


def values_are_numeric(series: pd.Series, threshold: float = 0.8) -> bool:
    """True if at least `threshold` of non-null values are numeric."""
    sample = _non_null_values(series, limit=50)
    if not sample:
        return False
    parsed = pd.to_numeric(pd.Series(sample), errors='coerce')
    return bool(parsed.notna().sum() / len(sample) >= threshold)


def categorical_cardinality(series: pd.Series) -> Tuple[int, float]:
    """Return (n_unique, unique_ratio) for non-null values."""
    non_null = series.dropna() if series is not None else pd.Series(dtype=object)
    if hasattr(non_null, 'astype'):
        non_null = non_null.astype(str).str.strip()
        non_null = non_null[non_null.ne('') & non_null.str.lower().ne('nan')]
    n = len(non_null)
    if n == 0:
        return 0, 0.0
    return non_null.nunique(), non_null.nunique() / n


def values_match_keywords(series: pd.Series, keywords: List[str]) -> bool:
    """True if any non-null value matches one of `keywords` (case-insensitive contains)."""
    sample = _non_null_values(series, limit=20)
    lowered = [v.lower() for v in sample]
    return any(any(kw in v for kw in keywords) for v in lowered)


# ── Semantic type inference ─────────────────────────────────────────────────


def _name_match(patterns: List[str], col_name: str) -> bool:
    return any(re.match(p, col_name, re.IGNORECASE) for p in patterns)


def infer_semantic_type(
    col_name: str,
    series: pd.Series,
) -> Tuple[str, float, List[str]]:
    """
    Returns (inferred_role, confidence, reason_codes).

    `reason_codes` is a list of short string tags explaining the decision,
    intended for audit logs and user-facing tooltips.  Each call appends
    the codes that contributed to the chosen type, plus any conflicting
    signals (prefixed with ``conflict:``).
    """
    col_lower = col_name.lower()
    reasons: List[str] = []

    # Strong explicit overrides for known high-signal metadata/time fields.
    if col_lower in {
        'collection_date', 'study.start_date', 'study.end_date',
        'procedure.date', 'provenance.created_at',
    }:
        return 'time_variable', 0.95, ['name:exact_time_field']

    if col_lower in {
        'field_label', 'data_type', 'unit', 'required_for_vcg', 'vcg_role',
        'arrive_mapping', 'allowed_values_or_format', 'source_status',
        'future_value_to_fill', 'current_publication_value_or_example',
        'entity_level',
    }:
        return 'metadata_field', 0.92, ['name:exact_metadata_field']

    if col_lower in {'definition', 'study.objective', 'notes'}:
        return 'free_text_note', 0.92, ['name:exact_note_field']

    # ── Identifier ───────────────────────────────────────────────────────
    name_id = _name_match(IDENTIFIER_PATTERNS, col_name)
    value_id = values_look_like_identifiers(series)
    if name_id and value_id:
        return 'identifier', 0.95, ['name:identifier_pattern', 'value:identifier_shape']
    if name_id:
        reasons.append('name:identifier_pattern')
        # Soft-confirm via uniqueness
        n_unique, unique_ratio = categorical_cardinality(series)
        if unique_ratio >= 0.95:
            reasons.append('value:high_uniqueness')
            return 'identifier', 0.92, reasons
        return 'identifier', 0.85, reasons

    # ── Time variable ────────────────────────────────────────────────────
    name_time = _name_match(TIME_PATTERNS, col_name)
    value_time = values_look_like_dates(series)
    if name_time and value_time:
        return 'time_variable', 0.93, ['name:time_pattern', 'value:date_parseable']
    if name_time:
        return 'time_variable', 0.82, ['name:time_pattern']
    if value_time and not values_are_numeric(series):
        return 'time_variable', 0.78, ['value:date_parseable']

    # ── Biological descriptor ────────────────────────────────────────────
    name_bio = _name_match(BIOLOGICAL_PATTERNS, col_name)
    if name_bio:
        reasons.append('name:biological_pattern')
        if values_match_keywords(series, SEX_KEYWORDS) or values_match_keywords(series, STRAIN_KEYWORDS):
            reasons.append('value:bio_keyword_match')
            return 'biological_descriptor', 0.92, reasons
        return 'biological_descriptor', 0.86, reasons

    # ── Experimental condition / treatment ───────────────────────────────
    name_cond = _name_match(CONDITION_PATTERNS, col_name)
    if name_cond:
        reasons.append('name:condition_pattern')
        n_unique, unique_ratio = categorical_cardinality(series)
        if 1 < n_unique <= 25 and unique_ratio < 0.5:
            reasons.append('value:low_cardinality')
            return 'experimental_condition', 0.90, reasons
        return 'experimental_condition', 0.78, reasons

    # ── Free-text note ───────────────────────────────────────────────────
    name_note = _name_match(NOTE_PATTERNS, col_name)
    if name_note:
        return 'free_text_note', 0.82, ['name:note_pattern']

    # ── Metadata field (broad name patterns) ─────────────────────────────
    name_meta = _name_match(METADATA_PATTERNS, col_name)
    if name_meta:
        return 'metadata_field', 0.80, ['name:metadata_pattern']

    # ── Measurement (numeric outcome) ────────────────────────────────────
    name_meas = _name_match(MEASUREMENT_PATTERNS, col_name)
    numeric_ok = values_are_numeric(series)
    if name_meas and numeric_ok:
        return 'measurement', 0.92, ['name:measurement_pattern', 'value:numeric']
    if name_meas and not numeric_ok:
        # Name says measurement but values are not numeric — likely a path
        # or placeholder.  Return measurement at low confidence and flag the
        # conflict so the user can review.
        return 'measurement', 0.55, ['name:measurement_pattern', 'conflict:non_numeric_values']

    # ── Data-driven fallbacks ────────────────────────────────────────────
    if numeric_ok:
        n_unique, unique_ratio = categorical_cardinality(series)
        if unique_ratio > 0.7:
            return 'measurement', 0.62, ['value:numeric', 'value:high_uniqueness']
        return 'experimental_condition', 0.50, ['value:numeric', 'value:low_uniqueness']

    if series.dtype == object:
        n_unique, unique_ratio = categorical_cardinality(series)
        if re.search(r'(definition|description|note|comment|title|objective)', col_lower):
            return 'free_text_note', 0.55, ['name:note_keyword']
        if n_unique > 0 and unique_ratio >= 0.95:
            return 'identifier', 0.65, ['value:high_uniqueness']
        if 1 < n_unique < 25 and unique_ratio < 0.15:
            return 'categorical', 0.62, ['value:low_cardinality']

    return 'unknown', 0.40, ['fallback:no_signal']


# ── Unit & data-type inference ──────────────────────────────────────────────


def guess_unit(col_name: str) -> Optional[str]:
    name_lower = col_name.lower()
    for unit, patterns in UNIT_MAP.items():
        for p in patterns:
            if p.lower() in name_lower:
                return unit
    return None


def unit_value_consistent(series: pd.Series, unit: Optional[str]) -> bool:
    """Sanity-check that a column whose name suggests a numeric unit
    actually contains numeric values.  Used to flag mismatches."""
    if unit is None:
        return True
    return values_are_numeric(series, threshold=0.8)


def infer_data_type(series: pd.Series) -> str:
    numeric = pd.to_numeric(series, errors='coerce')
    if numeric.notna().sum() / max(len(series), 1) > 0.85:
        if (numeric.dropna() % 1 == 0).all():
            return 'integer'
        return 'number'

    non_null = series.dropna()
    if len(non_null) > 0:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pd.to_datetime(non_null.head(20))
            return 'date'
        except Exception:
            pass

        lower_vals = set(str(v).lower().strip() for v in non_null.unique())
        if lower_vals.issubset({'true', 'false', 'yes', 'no', '0', '1', 't', 'f'}):
            return 'boolean'

        unique_ratio = series.nunique() / max(len(non_null), 1)
        if unique_ratio < 0.20 and series.nunique() < 30:
            return 'categorical'

    return 'string'


# ── Dataset signature (Stage 2 template lookup) ─────────────────────────────


def dataset_signature(column_names: List[str]) -> str:
    """Stable signature derived from the sorted column-name set.

    Used by the template store to recognise re-uploads of structurally
    identical datasets (same columns, possibly in a different order)
    without depending on the data values themselves.
    """
    import hashlib

    normalised = sorted(c.strip().lower() for c in column_names if c is not None)
    joined = "|".join(normalised)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


# ── Top-level profiling ─────────────────────────────────────────────────────


def profile_csv(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    encoding = detect_encoding(file_bytes)
    try:
        content = file_bytes.decode(encoding)
    except Exception:
        content = file_bytes.decode('utf-8', errors='replace')
        encoding = 'utf-8'

    delimiter = detect_delimiter(content)

    try:
        df_str = pd.read_csv(io.StringIO(content), sep=delimiter, dtype=str, keep_default_na=False)
    except Exception as e:
        raise ValueError(f'Could not parse CSV: {e}')

    try:
        df_typed = pd.read_csv(io.StringIO(content), sep=delimiter)
    except Exception:
        df_typed = df_str.copy()

    n_rows, n_cols = df_str.shape

    empty_columns = [
        col for col in df_str.columns
        if df_str[col].str.strip().eq('').all() or df_str[col].isna().all()
    ]

    seen: Dict[str, int] = {}
    dup_cols: List[str] = []
    for col in df_str.columns:
        seen[col] = seen.get(col, 0) + 1
        if seen[col] == 2:
            dup_cols.append(col)

    malformed = df_str[df_str.isna().all(axis=1)].index.tolist()[:10]

    columns = []
    for col in df_str.columns:
        s_str = df_str[col]
        s_typed = df_typed[col] if col in df_typed.columns else s_str

        sem_type, confidence, reason_codes = infer_semantic_type(col, s_str)
        data_type = infer_data_type(s_typed)
        unit = guess_unit(col)

        if unit is not None and not unit_value_consistent(s_str, unit):
            reason_codes = list(reason_codes) + ['conflict:unit_without_numeric_values']

        missing_mask = s_str.isna() | s_str.str.strip().eq('')
        missing_count = int(missing_mask.sum())

        sample_vals = s_str[~missing_mask].head(5).tolist()

        columns.append({
            'name': col,
            'label': col.replace('_', ' ').title(),
            'description': None,
            'inferred_type': sem_type,
            'data_type': data_type,
            'unique_values': int(s_str.nunique()),
            'missing_values': missing_count,
            'missing_pct': round(missing_count / max(n_rows, 1) * 100, 1),
            'sample_values': sample_vals,
            'unit_guess': unit,
            'confidence': confidence,
            'reason_codes': reason_codes,
            'user_label': None,
            'user_description': None,
            'user_unit': unit,
            'user_type': None,
            'allowed_values': None,
            'required': False,
            'uri': None,
        })

    return {
        'import_info': {
            'filename': filename,
            'n_rows': n_rows,
            'n_columns': n_cols,
            'delimiter': delimiter if delimiter != '\t' else 'tab',
            'encoding': encoding,
            'has_header': True,
            'empty_columns': empty_columns,
            'duplicate_columns': dup_cols,
            'malformed_rows': malformed,
            'signature': dataset_signature(list(df_str.columns)),
        },
        'columns': columns,
        'df': df_typed,
        'content': content,
    }
