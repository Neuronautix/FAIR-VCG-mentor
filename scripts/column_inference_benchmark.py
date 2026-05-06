from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from tests.column_inference_benchmark import format_summary, run_benchmark


TARGET_PRECISION = 0.85
TARGET_RECALL = 0.80
TARGET_AMBIGUITY = 0.05


def main() -> int:
    summary = run_benchmark(ROOT / "test_data")
    print(format_summary(summary))
    print("")

    precision_ok = summary.micro_precision >= TARGET_PRECISION
    recall_ok = summary.micro_recall >= TARGET_RECALL
    ambiguity_ok = summary.ambiguity_rate <= TARGET_AMBIGUITY

    print("Stage 0 acceptance gates")
    print("------------------------")
    print(
        f"precision >= {TARGET_PRECISION:.2f}: {'PASS' if precision_ok else 'FAIL'}"
    )
    print(f"recall >= {TARGET_RECALL:.2f}: {'PASS' if recall_ok else 'FAIL'}")
    print(
        f"ambiguity <= {TARGET_AMBIGUITY:.2f}: {'PASS' if ambiguity_ok else 'FAIL'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
