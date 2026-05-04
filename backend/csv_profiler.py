import io
import re
import csv as csv_module
import warnings
from typing import Dict, List, Any, Tuple, Optional

import chardet
import pandas as pd

IDENTIFIER_PATTERNS = [
    r'.*_id$', r'.*_ID$', r'^id$', r'^ID$', r'.*identifier.*',
    r'.*subject.*id.*', r'.*animal.*id.*', r'.*sample.*id.*',
    r'.*mouse.*id.*', r'.*rat.*id.*', r'.*patient.*id.*',
]

MEASUREMENT_PATTERNS = [
    r'.*_g$', r'.*_mg.*', r'.*_kg$', r'.*_cm$', r'.*_mm$', r'.*_ml.*',
    r'.*_s$', r'.*_sec$', r'.*_min$', r'.*_h$', r'.*_hr$',
    r'.*weight.*', r'.*distance.*', r'.*latency.*', r'.*duration.*',
    r'.*count.*', r'.*score.*', r'.*level.*', r'.*concentration.*',
    r'.*amount.*', r'.*volume.*', r'.*ratio.*', r'.*index.*',
    r'.*_pct$', r'.*_percent$', r'.*response.*', r'.*reading.*',
]

BIOLOGICAL_PATTERNS = [
    r'^sex$', r'^gender$', r'^genotype$', r'^strain$', r'^species$',
    r'^age.*', r'^breed.*', r'^phenotype.*', r'^background.*',
]

CONDITION_PATTERNS = [
    r'^group$', r'^treatment.*', r'^dose.*', r'^exposure.*',
    r'^arm$', r'^cohort.*', r'^condition.*', r'^intervention.*',
    r'^drug.*', r'^compound.*', r'^vehicle.*',
]

TIME_PATTERNS = [
    r'^day.*', r'^timepoint.*', r'^time.*', r'^week.*', r'^hour.*',
    r'^visit.*', r'^session.*', r'^date.*', r'^timestamp.*', r'^period.*',
    r'^baseline.*', r'^followup.*', r'^follow.*up.*',
]

NOTE_PATTERNS = [
    r'^comment.*', r'^note.*', r'^observation.*', r'^remark.*',
    r'^description.*', r'^details.*', r'^annotation.*',
]

METADATA_PATTERNS = [
    r'^operator.*', r'^device.*', r'^instrument.*', r'^protocol.*',
    r'^experimenter.*', r'^technician.*', r'^lab.*', r'^batch.*',
    r'^run.*', r'^plate.*', r'^cage.*', r'^rack.*',
]

UNIT_MAP = {
    'g': ['_g', 'weight_g', 'mass_g', 'bw_g'],
    'mg': ['_mg', '_milligram'],
    'kg': ['_kg', '_kilogram'],
    'mg/kg': ['_mg_kg', 'dose_mg', 'mpk'],
    'cm': ['_cm', '_centimeter'],
    'mm': ['_mm', '_millimeter'],
    'µm': ['_um', '_micron', '_micrometer'],
    'm': ['_meter', 'dist_m'],
    'mL': ['_ml', '_milliliter', '_mL'],
    'µL': ['_ul', '_microliter', '_µl'],
    's': ['_s', '_sec', '_second'],
    'min': ['_min', '_minute'],
    'h': ['_h', '_hr', '_hour'],
    '%': ['_pct', '_percent', '_%'],
    'µg/mL': ['_ug_ml', '_µg_ml', 'conc_ug'],
    'ng/mL': ['_ng_ml', 'conc_ng'],
}


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


def infer_semantic_type(col_name: str, series: pd.Series) -> Tuple[str, float]:
    for pattern in IDENTIFIER_PATTERNS:
        if re.match(pattern, col_name, re.IGNORECASE):
            return 'identifier', 0.90

    for pattern in TIME_PATTERNS:
        if re.match(pattern, col_name, re.IGNORECASE):
            return 'time_variable', 0.85

    for pattern in BIOLOGICAL_PATTERNS:
        if re.match(pattern, col_name, re.IGNORECASE):
            return 'biological_descriptor', 0.88

    for pattern in CONDITION_PATTERNS:
        if re.match(pattern, col_name, re.IGNORECASE):
            return 'experimental_condition', 0.85

    for pattern in NOTE_PATTERNS:
        if re.match(pattern, col_name, re.IGNORECASE):
            return 'free_text_note', 0.80

    for pattern in METADATA_PATTERNS:
        if re.match(pattern, col_name, re.IGNORECASE):
            return 'metadata_field', 0.80

    for pattern in MEASUREMENT_PATTERNS:
        if re.match(pattern, col_name, re.IGNORECASE):
            return 'measurement', 0.82

    # Data-driven fallbacks
    try:
        numeric_series = pd.to_numeric(series, errors='coerce')
        if numeric_series.notna().sum() / max(len(series), 1) > 0.8:
            unique_ratio = series.nunique() / max(len(series), 1)
            if unique_ratio > 0.7:
                return 'measurement', 0.60
            return 'experimental_condition', 0.50
    except Exception:
        pass

    if series.dtype == object:
        n_unique = series.nunique()
        n_total = len(series.dropna())
        if n_total > 0 and n_unique == n_total:
            return 'identifier', 0.65
        if n_total > 0 and n_unique / n_total < 0.15 and n_unique < 25:
            return 'categorical', 0.60

    return 'unknown', 0.40


def guess_unit(col_name: str) -> Optional[str]:
    name_lower = col_name.lower()
    for unit, patterns in UNIT_MAP.items():
        for p in patterns:
            if p.lower() in name_lower:
                return unit
    return None


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

        sem_type, confidence = infer_semantic_type(col, s_str)
        data_type = infer_data_type(s_typed)
        unit = guess_unit(col)

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
        },
        'columns': columns,
        'df': df_typed,
        'content': content,
    }
