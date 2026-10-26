"""Tests for the dissemination bundle builder (Milestone F).

These tests do not import fastapi/main; they call ``build()`` directly with a
temporary output directory so the real repo ``dist/`` is never touched.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.build_dissemination import build


@pytest.fixture(scope="module")
def bundle(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("dissemination")
    return build(out_dir=out)


def test_build_returns_output_dir(bundle: Path):
    assert bundle.exists()
    assert bundle.is_dir()


def test_expected_files_exist(bundle: Path):
    expected = [
        "README.md",
        "scorecard_deterministic.md",
        "scorecard_kg.md",
        "vcg_poc/vcg_synthetic_controls.csv",
        "vcg_poc/vcg_report.md",
        "vcg_poc/poc_results.json",
        "local_llm_deployment/docker-compose.local-llm.yml",
        "local_llm_deployment/.env.local-llm.example",
        "local_llm_deployment/local-llm-setup.md",
    ]
    missing = [p for p in expected if not (bundle / p).exists()]
    assert not missing, f"missing artifacts: {missing}"


def test_readme_contains_parsed_accuracy_metric(bundle: Path):
    readme = (bundle / "README.md").read_text(encoding="utf-8")
    # The README must surface a real accuracy percentage parsed from the scorecard,
    # not a placeholder.
    assert "Headline metrics" in readme
    assert re.search(r"accuracy.*\|\s*\d+\.\d+%\s*\|", readme), readme

    # Cross-check: the deterministic accuracy in the README matches the scorecard.
    scorecard = (bundle / "scorecard_deterministic.md").read_text(encoding="utf-8")
    sc_acc = re.search(r"Overall accuracy:\s*\*\*([0-9.]+%)\*\*", scorecard)
    assert sc_acc, "scorecard missing Overall accuracy line"
    assert sc_acc.group(1) in readme


def test_readme_contains_reliability_from_poc(bundle: Path):
    import json

    readme = (bundle / "README.md").read_text(encoding="utf-8")
    poc = json.loads((bundle / "vcg_poc" / "poc_results.json").read_text(encoding="utf-8"))
    rel = poc["reliability_score"]
    assert f"{rel:.3f}" in readme


def test_readme_mentions_3rs_reduction(bundle: Path):
    readme = (bundle / "README.md").read_text(encoding="utf-8")
    assert "What this demonstrates for the 3Rs" in readme
    assert "Reduction" in readme


def test_build_is_idempotent(tmp_path: Path):
    out = tmp_path / "bundle"
    build(out_dir=out)
    first = (out / "README.md").read_text(encoding="utf-8")
    build(out_dir=out)
    second = (out / "README.md").read_text(encoding="utf-8")
    assert first == second
