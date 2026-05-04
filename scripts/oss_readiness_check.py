#!/usr/bin/env python3
"""Open-source release readiness checks for FAIR-VCG Mentor.

Run from repository root:
    python scripts/oss_readiness_check.py

Use --strict to fail on warnings as well as hard failures.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    ".gitignore",
    "backend/main.py",
    "frontend/package.json",
    ".github/workflows/open-source-readiness.yml",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
]

RECOMMENDED_FILES = [
    "CLAUDE.md",
    "docker-compose.yml",
    "backend/tests/test_csv_profiler.py",
]

README_REQUIRED_HEADINGS = [
    "Quick Start",
    "Features",
    "Development Setup",
    "Contributing",
    "License",
]

FRONTEND_REQUIRED_SCRIPTS = ["dev", "build", "preview", "type-check"]


@dataclass
class Finding:
    level: str  # PASS | WARN | FAIL
    check: str
    message: str


class Checker:
    def __init__(self, root: Path):
        self.root = root
        self.findings: list[Finding] = []

    def add(self, level: str, check: str, message: str) -> None:
        self.findings.append(Finding(level=level, check=check, message=message))

    def exists(self, rel_path: str) -> bool:
        return (self.root / rel_path).exists()

    def read_text(self, rel_path: str) -> str:
        return (self.root / rel_path).read_text(encoding="utf-8")

    def read_json(self, rel_path: str) -> dict[str, Any]:
        return json.loads(self.read_text(rel_path))

    def check_required_files(self) -> None:
        for rel in REQUIRED_FILES:
            if self.exists(rel):
                self.add("PASS", "required-files", f"Found {rel}")
            else:
                self.add("FAIL", "required-files", f"Missing required file: {rel}")

    def check_recommended_files(self) -> None:
        for rel in RECOMMENDED_FILES:
            if self.exists(rel):
                self.add("PASS", "recommended-files", f"Found recommended file: {rel}")
            else:
                self.add("WARN", "recommended-files", f"Missing recommended file: {rel}")

    def check_readme_structure(self) -> None:
        path = self.root / "README.md"
        if not path.exists():
            self.add("FAIL", "readme", "README.md is missing")
            return

        content = self.read_text("README.md")
        for heading in README_REQUIRED_HEADINGS:
            if re.search(rf"^##\s+{re.escape(heading)}\s*$", content, flags=re.MULTILINE):
                self.add("PASS", "readme", f"README has section: {heading}")
            else:
                self.add("FAIL", "readme", f"README missing section: {heading}")

    def check_license_declaration(self) -> None:
        path = self.root / "LICENSE"
        if not path.exists():
            self.add("FAIL", "license", "LICENSE file is missing")
            return

        content = self.read_text("LICENSE")
        if "GNU General Public License" in content:
            self.add("PASS", "license", "LICENSE mentions GNU General Public License")
        else:
            self.add("FAIL", "license", "LICENSE does not clearly mention GNU GPL")

        if "SPDX-License-Identifier: GPL-3.0-only" in content:
            self.add("PASS", "license", "LICENSE includes SPDX identifier GPL-3.0-only")
        else:
            self.add("WARN", "license", "LICENSE should include SPDX-License-Identifier: GPL-3.0-only")

    def check_package_metadata(self) -> None:
        pkg_path = self.root / "frontend/package.json"
        if not pkg_path.exists():
            self.add("FAIL", "frontend-metadata", "frontend/package.json is missing")
            return

        package = self.read_json("frontend/package.json")

        license_value = package.get("license")
        if license_value == "GPL-3.0-only":
            self.add("PASS", "frontend-metadata", "frontend/package.json license is GPL-3.0-only")
        else:
            self.add(
                "FAIL",
                "frontend-metadata",
                "frontend/package.json license must be GPL-3.0-only",
            )

        scripts = package.get("scripts", {})
        missing_scripts = [name for name in FRONTEND_REQUIRED_SCRIPTS if name not in scripts]
        if missing_scripts:
            self.add(
                "FAIL",
                "frontend-metadata",
                "Missing frontend scripts: " + ", ".join(missing_scripts),
            )
        else:
            self.add("PASS", "frontend-metadata", "frontend/package.json contains required scripts")

    def check_lockfile_metadata(self) -> None:
        lock_path = self.root / "frontend/package-lock.json"
        if not lock_path.exists():
            self.add("WARN", "frontend-lockfile", "frontend/package-lock.json is missing")
            return

        lock = self.read_json("frontend/package-lock.json")
        root_package = lock.get("packages", {}).get("", {})
        license_value = root_package.get("license")

        if license_value == "GPL-3.0-only":
            self.add("PASS", "frontend-lockfile", "package-lock root license is GPL-3.0-only")
        else:
            self.add(
                "WARN",
                "frontend-lockfile",
                "package-lock root package should set license to GPL-3.0-only",
            )

    def check_ci_workflow(self) -> None:
        path = self.root / ".github/workflows/open-source-readiness.yml"
        if not path.exists():
            self.add("FAIL", "ci", "Missing .github/workflows/open-source-readiness.yml")
            return

        content = path.read_text(encoding="utf-8")
        required_tokens = [
            "oss_readiness_check.py",
            "pytest",
            "npm ci",
            "run type-check",
            "run build",
        ]

        missing_tokens = [token for token in required_tokens if token not in content]
        if missing_tokens:
            self.add("WARN", "ci", "Workflow missing expected steps: " + ", ".join(missing_tokens))
        else:
            self.add("PASS", "ci", "Workflow includes readiness, tests, and frontend verification")

    def run(self) -> list[Finding]:
        self.check_required_files()
        self.check_recommended_files()
        self.check_readme_structure()
        self.check_license_declaration()
        self.check_package_metadata()
        self.check_lockfile_metadata()
        self.check_ci_workflow()
        return self.findings


def print_report(findings: list[Finding]) -> None:
    levels = ["FAIL", "WARN", "PASS"]
    for level in levels:
        for finding in findings:
            if finding.level == level:
                print(f"[{finding.level}] {finding.check}: {finding.message}")

    fails = sum(1 for item in findings if item.level == "FAIL")
    warns = sum(1 for item in findings if item.level == "WARN")
    passes = sum(1 for item in findings if item.level == "PASS")
    print("-")
    print(f"Summary: {passes} pass, {warns} warn, {fails} fail")


def main() -> int:
    parser = argparse.ArgumentParser(description="Open-source release readiness checks")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings in addition to failures",
    )
    args = parser.parse_args()

    checker = Checker(ROOT)
    findings = checker.run()
    print_report(findings)

    has_fail = any(item.level == "FAIL" for item in findings)
    has_warn = any(item.level == "WARN" for item in findings)

    if has_fail:
        return 1
    if args.strict and has_warn:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
