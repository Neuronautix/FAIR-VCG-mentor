"""Metadata masking for the validation harness.

A fresh CSV upload carries no human-authored metadata, so the meaningful
"mask" is over the *signal a predictor is allowed to use*:

- ``raw``   — headers kept. Matches a normal upload; tests name + value inference.
- ``blind`` — headers replaced with neutral tokens (``var_1`` …). Forces
  value-only inference, exposing how much a predictor leans on column-name
  patterns vs the data itself (a key robustness signal for local LLMs).

Values are never altered; only the header row changes. Masking returns the
``name_map`` so predictions made on masked headers can be scored against the
original ground truth.
"""
from __future__ import annotations

import csv
import io
from typing import Dict, Tuple

MASKING_LEVELS = ("raw", "blind")


def mask_dataset(csv_bytes: bytes, level: str) -> Tuple[bytes, Dict[str, str]]:
    """Return ``(masked_csv_bytes, name_map)``.

    ``name_map`` maps each *emitted* header to the *original* header so the
    caller can translate predictions back to ground-truth column names.
    """
    if level not in MASKING_LEVELS:
        raise ValueError(f"unknown masking level: {level!r} (expected one of {MASKING_LEVELS})")

    text = csv_bytes.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return csv_bytes, {}

    header = rows[0]
    if level == "raw":
        return csv_bytes, {h: h for h in header}

    # blind: anonymize headers, keep value rows untouched.
    new_header = [f"var_{i + 1}" for i in range(len(header))]
    name_map = {new_header[i]: header[i] for i in range(len(header))}

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(new_header)
    writer.writerows(rows[1:])
    return out.getvalue().encode("utf-8"), name_map
