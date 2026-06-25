"""Assemble a self-contained dissemination bundle for the 3RCC grant (Milestone F).

Runs from the ``backend/`` directory:

    python -m scripts.build_dissemination
    python scripts/build_dissemination.py

It collects, into ``dist/dissemination/`` at the repo root:

1. Provider scorecards from the masked-metadata eval harness
   (``scorecard_deterministic.md`` and ``scorecard_kg.md``).
2. The VCG proof-of-concept outputs (synthetic controls CSV, report, results JSON).
3. The local-LLM deployment assets (compose file, env example, setup doc).
4. A ``README.md`` MANIFEST listing every artifact, the headline metrics
   (parsed from the generated scorecards and the PoC results), and a short
   "What this demonstrates for the 3Rs" paragraph.

The function ``build(out_dir=None)`` is the importable entry point used by the
test-suite; the CLI calls it with the default location. Missing optional
artifacts produce a warning and are skipped — the build never crashes on them.
The script is idempotent: re-running overwrites the bundle in place.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Repo root is two levels up from this file: <repo>/backend/scripts/build_dissemination.py
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

# Ensure `import eval.*`, `csv_profiler`, etc. resolve when run as a plain script.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _log(msg: str) -> None:
    print(f"[build_dissemination] {msg}")


def _warn(msg: str) -> None:
    print(f"[build_dissemination] WARNING: {msg}")


# ── Scorecards ────────────────────────────────────────────────────────────────


def _write_scorecard(predictor: str, dest: Path) -> bool:
    """Run the eval harness in-process for ``predictor`` and write markdown to ``dest``.

    Returns True on success. Imports are local so a failure in the harness only
    affects scorecard generation, not the rest of the bundle.
    """
    try:
        from eval.run_eval import evaluate, _make_predictor

        card = evaluate(_make_predictor(predictor))
        dest.write_text(card.to_markdown(), encoding="utf-8")
        _log(f"wrote {dest.name} (predictor={predictor})")
        return True
    except Exception as exc:  # pragma: no cover - defensive
        _warn(f"could not generate scorecard for predictor '{predictor}': {exc}")
        return False


# ── Metric parsing ────────────────────────────────────────────────────────────


def _parse_scorecard_metrics(path: Path) -> Dict[str, Optional[str]]:
    """Parse 'Overall accuracy' and 'Hallucination rate' lines from a scorecard."""
    metrics: Dict[str, Optional[str]] = {"accuracy": None, "hallucination": None}
    if not path.exists():
        return metrics
    text = path.read_text(encoding="utf-8")
    acc = re.search(r"Overall accuracy:\s*\*\*([0-9.]+%)\*\*", text)
    hall = re.search(r"Hallucination rate:\s*\*\*([0-9.]+%)\*\*", text)
    if acc:
        metrics["accuracy"] = acc.group(1)
    if hall:
        metrics["hallucination"] = hall.group(1)
    return metrics


def _parse_poc_reliability(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        val = data.get("reliability_score")
        return float(val) if val is not None else None
    except Exception:
        return None


# ── Copy helpers ──────────────────────────────────────────────────────────────


def _rel(path: Path) -> str:
    """Repo-relative path string when possible, else the absolute path."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _copy(src: Path, dest: Path) -> bool:
    if not src.exists():
        _warn(f"optional artifact missing, skipping: {src}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    _log(f"copied {_rel(src)} -> {_rel(dest)}")
    return True


# ── README / MANIFEST ─────────────────────────────────────────────────────────


def _render_readme(
    out_dir: Path,
    included: List[Tuple[str, str]],
    det_metrics: Dict[str, Optional[str]],
    kg_metrics: Dict[str, Optional[str]],
    reliability: Optional[float],
) -> str:
    def fmt(v: Optional[str]) -> str:
        return v if v else "n/a"

    rel_str = f"{reliability:.3f}" if reliability is not None else "n/a"

    lines: List[str] = []
    lines.append("# FAIR-VCG Mentor — Dissemination Package")
    lines.append("")
    lines.append(
        "Self-contained evidence bundle for the Swiss 3RCC animal-reduction grant. "
        "Every artifact below is reproducible offline from this repository; no "
        "external LLM API is required."
    )
    lines.append("")
    lines.append("## Headline metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(
        f"| Masked-metadata accuracy (deterministic predictor) | "
        f"{fmt(det_metrics.get('accuracy'))} |"
    )
    lines.append(
        f"| Masked-metadata hallucination rate (deterministic) | "
        f"{fmt(det_metrics.get('hallucination'))} |"
    )
    lines.append(
        f"| Masked-metadata accuracy (KG-grounded predictor) | "
        f"{fmt(kg_metrics.get('accuracy'))} |"
    )
    lines.append(
        f"| Masked-metadata hallucination rate (KG-grounded) | "
        f"{fmt(kg_metrics.get('hallucination'))} |"
    )
    lines.append(f"| VCG proof-of-concept reliability score | {rel_str} |")
    lines.append("")
    lines.append("## Contents (MANIFEST)")
    lines.append("")
    lines.append("| Artifact | Description |")
    lines.append("| --- | --- |")
    for rel_path, desc in included:
        lines.append(f"| `{rel_path}` | {desc} |")
    lines.append("")
    lines.append("## What this demonstrates for the 3Rs")
    lines.append("")
    lines.append(
        "**Reduction.** The Virtual Control Group (VCG) pipeline synthesises a "
        "statistically validated control cohort from an existing concurrent control "
        "group, so future studies can borrow synthetic controls instead of breeding "
        "and treating additional animals. The proof-of-concept reaches a reliability "
        f"score of {rel_str} (1.0 = synthetic and real controls are statistically "
        "indistinguishable), with per-endpoint effect sizes, confidence intervals and "
        "Kolmogorov–Smirnov diagnostics provided for transparent reporting."
    )
    lines.append("")
    lines.append(
        "**Offline / local LLM.** The metadata-grounding and assistant layers run "
        "against a local OpenAI-compatible endpoint (see `local_llm_deployment/`), so "
        "no animal-study data ever leaves the institution and the tool works in air-gapped "
        "settings — a prerequisite for responsible deployment on confidential preclinical data."
    )
    lines.append("")
    lines.append(
        "**Metadata grounding.** The masked-metadata scorecards quantify how reliably "
        "the assistant recovers column semantics from de-identified data. A "
        "hallucination rate at or near zero, combined with knowledge-graph grounding, "
        "means proposed FAIR annotations are anchored to real evidence rather than "
        "fabricated — making the resulting datasets trustworthy enough to reuse, which "
        "is itself a Reduction lever (reusable controls displace new animal experiments)."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# ── Main build ────────────────────────────────────────────────────────────────


def build(out_dir: Optional[Path] = None) -> Path:
    """Assemble the dissemination bundle. Returns the output directory path."""
    out_dir = Path(out_dir) if out_dir is not None else (REPO_ROOT / "dist" / "dissemination")
    out_dir.mkdir(parents=True, exist_ok=True)
    _log(f"building dissemination bundle into {out_dir}")

    included: List[Tuple[str, str]] = []

    # 1. Scorecards (in-process eval harness) ─────────────────────────────────
    det_path = out_dir / "scorecard_deterministic.md"
    kg_path = out_dir / "scorecard_kg.md"
    if _write_scorecard("deterministic", det_path):
        included.append(
            (det_path.name, "Masked-metadata scorecard — offline rule-based predictor")
        )
    if _write_scorecard("kg", kg_path):
        included.append(
            (kg_path.name, "Masked-metadata scorecard — knowledge-graph grounded predictor")
        )

    det_metrics = _parse_scorecard_metrics(det_path)
    kg_metrics = _parse_scorecard_metrics(kg_path)

    # 2. VCG proof-of-concept outputs ─────────────────────────────────────────
    poc_src_dir = REPO_ROOT / "docs" / "vcg_poc" / "outputs"
    poc_dest_dir = out_dir / "vcg_poc"
    poc_artifacts = [
        ("vcg_synthetic_controls.csv", "Synthetic control cohort generated by the VCG pipeline"),
        ("vcg_report.md", "Markdown statistical validation report for the synthetic controls"),
        ("poc_results.json", "Machine-readable PoC results (reliability, per-endpoint stats)"),
    ]
    for fname, desc in poc_artifacts:
        if _copy(poc_src_dir / fname, poc_dest_dir / fname):
            included.append((f"vcg_poc/{fname}", desc))

    reliability = _parse_poc_reliability(poc_dest_dir / "poc_results.json")

    # 3. Local-LLM deployment assets ──────────────────────────────────────────
    llm_dest_dir = out_dir / "local_llm_deployment"
    llm_artifacts = [
        (
            REPO_ROOT / "docker-compose.local-llm.yml",
            "docker-compose.local-llm.yml",
            "Compose file to run an offline OpenAI-compatible LLM alongside the app",
        ),
        (
            REPO_ROOT / "backend" / ".env.local-llm.example",
            ".env.local-llm.example",
            "Example environment file pointing the backend at the local LLM endpoint",
        ),
        (
            REPO_ROOT / "docs" / "local-llm-setup.md",
            "local-llm-setup.md",
            "Step-by-step local / offline LLM deployment guide",
        ),
    ]
    for src, dest_name, desc in llm_artifacts:
        if _copy(src, llm_dest_dir / dest_name):
            included.append((f"local_llm_deployment/{dest_name}", desc))

    # 4. README / MANIFEST ────────────────────────────────────────────────────
    readme = _render_readme(out_dir, included, det_metrics, kg_metrics, reliability)
    (out_dir / "README.md").write_text(readme, encoding="utf-8")
    included_with_readme = included + [("README.md", "This manifest")]
    _log("wrote README.md (MANIFEST)")

    # Summary ─────────────────────────────────────────────────────────────────
    _log(f"done — {len(included_with_readme)} artifacts written to {out_dir}:")
    for rel_path, _desc in included_with_readme:
        _log(f"  - {rel_path}")
    _log(
        "headline metrics: "
        f"deterministic accuracy={det_metrics.get('accuracy')}, "
        f"kg accuracy={kg_metrics.get('accuracy')}, "
        f"reliability={reliability}"
    )
    return out_dir


def main(argv: Optional[List[str]] = None) -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
