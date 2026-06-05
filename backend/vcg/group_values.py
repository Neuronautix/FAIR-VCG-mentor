from __future__ import annotations

from typing import Any, List

import pandas as pd


MISSING_GROUP_VALUE = "__MISSING_CONTROL_VALUE__"
MISSING_GROUP_LABEL = "(blank / missing)"


def has_missing_group_values(series: pd.Series) -> bool:
    as_text = series.astype("string")
    return bool(series.isna().any() or as_text.str.strip().eq("").fillna(False).any())


def visible_group_values(series: pd.Series, limit: int = 12) -> List[str]:
    values = [str(v) for v in series.dropna().astype(str).unique().tolist() if str(v).strip()]
    if has_missing_group_values(series):
        values.append(MISSING_GROUP_LABEL)
    return values[:limit]


def normalize_group_value(value: Any, series: pd.Series) -> Any:
    if value == MISSING_GROUP_VALUE:
        return MISSING_GROUP_VALUE
    if value is None:
        return MISSING_GROUP_VALUE if has_missing_group_values(series) else None
    text = str(value).strip()
    if not text and has_missing_group_values(series):
        return MISSING_GROUP_VALUE
    if text.lower() in {"none", "null", "nan", "blank", "missing", "untreated", "no treatment"}:
        return MISSING_GROUP_VALUE if has_missing_group_values(series) else text
    return text


def group_mask(series: pd.Series, value: Any) -> pd.Series:
    normalized = normalize_group_value(value, series)
    if normalized == MISSING_GROUP_VALUE:
        as_text = series.astype("string")
        return series.isna() | as_text.str.strip().eq("").fillna(False)
    return series.astype(str) == str(normalized)
