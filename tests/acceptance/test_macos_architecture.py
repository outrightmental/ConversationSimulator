# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — what the docs say a Mac needs is what the depot contains.

The release workflow builds macOS on one leg, ``macOS-aarch64`` on
``macos-latest``, so the Steam macOS depot carries an Apple Silicon bundle and
nothing else. The store page's system requirements, the QA matrix, the depot
template and the publishing docs used to promise Intel Macs as well (issue
#563), and an Intel Mac owner who installed from Steam got a binary that would
not run — the demo gate (D-09) forbids store copy that claims what the build
does not do.

These tests read the architectures the build matrix produces and fail when a
document claims a Mac architecture the matrix does not build. Adding an Intel
or universal leg to ``release.yml`` turns the check off by itself; the docs can
then say Intel again.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_YML = _REPO_ROOT / ".github" / "workflows" / "release.yml"

# Every document that states which Macs the Steam build runs on. The docs-site
# pages are hand-kept copies of the docs/ pages, so both are listed.
_CLAIM_FILES = (
    "steam/depot_macos.vdf.tpl",
    "publishing/STEAM_STORE_PAGE.md",
    "publishing/STEAM_APP_REGISTRATION.md",
    "publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md",
    "publishing/STEAM_DEPOT_CONTENTS.md",
    "publishing/STEAM_REVIEW_SUBMISSION.md",
    "publishing/LAUNCH_ANNOUNCEMENT.md",
    "docs/QA_STEAM_PLATFORM_MATRIX.md",
    "docs/STEAM_BETA_VERIFICATION_REPORT.md",
    "docs-site/src/content/docs/dev/qa-steam-platform-matrix.md",
    "docs-site/src/content/docs/dev/steam-beta-verification.md",
    "docs/platform-notes.md",
    "docs-site/src/content/docs/play/platform-notes.md",
    "docs/release-checklist.md",
    "docs-site/src/content/docs/dev/release-checklist.md",
    "docs/STEAM_ROADMAP.md",
    "docs-site/src/content/docs/dev/steam-roadmap.md",
    "docs/release-notes-template.md",
)

# Phrasings that promise an Intel Mac can run the Steam build. Deliberately
# narrow: "Intel Mac" in a sentence that says it is NOT supported is fine, and
# Intel CPUs in the Windows and Linux requirements are unrelated.
_INTEL_CLAIMS = (
    re.compile(r"Apple Silicon (?:\+|and|&) Intel", re.I),
    re.compile(r"Apple M\d+ or Intel", re.I),
    re.compile(r"\bmacOS\s*(?:—|-|\()\s*Intel\b.*\|\s*Required", re.I),
    re.compile(r"macOS \(Intel\)", re.I),
    re.compile(r"macOS \(Universal\)", re.I),
    re.compile(r"universal binary", re.I),
    re.compile(r"Apple Silicon[^|\n]{0,24}\bor Intel\b", re.I),
    re.compile(r"Apple M\d+\s*/\s*Intel\b", re.I),
    re.compile(r"\bmacOS\s*[—–-]\s*Intel\b", re.I),
    re.compile(r"\bIntel\s*=\s*x64\b", re.I),
    re.compile(r"_x64\.dmg\b", re.I),
)


def _macos_build_legs() -> list[str]:
    workflow = yaml.safe_load(_RELEASE_YML.read_text(encoding="utf-8"))
    legs: list[str] = []
    for job in workflow["jobs"].values():
        include = (job.get("strategy") or {}).get("matrix", {}).get("include") or []
        legs += [entry["name"] for entry in include if str(entry.get("name", "")).startswith("macOS-")]
    return legs


def _builds_intel(legs: list[str]) -> bool:
    return any(re.search(r"x86_64|x64|intel|universal", leg, re.I) for leg in legs)


def test_release_builds_macos() -> None:
    legs = _macos_build_legs()
    assert legs, (
        "release.yml has no matrix leg named macOS-<arch>; update this test to "
        "read the macOS build architectures from wherever they moved."
    )


@pytest.mark.parametrize("relpath", _CLAIM_FILES)
def test_docs_claim_only_the_macs_the_build_supports(relpath: str) -> None:
    legs = _macos_build_legs()
    if _builds_intel(legs):
        pytest.skip(f"release.yml builds {legs}: Intel claims are true")
    text = (_REPO_ROOT / relpath).read_text(encoding="utf-8")
    hits = [
        f"line {text.count(chr(10), 0, m.start()) + 1}: {m.group(0)!r}"
        for pattern in _INTEL_CLAIMS
        for m in pattern.finditer(text)
    ]
    assert not hits, (
        f"{relpath} says the Steam build runs on Intel Macs, but release.yml builds "
        f"macOS only as {legs} (issue #563): " + "; ".join(hits)
    )


def test_store_page_says_apple_silicon_only() -> None:
    """The macOS requirements table names the limit, not just omits Intel."""
    text = (_REPO_ROOT / "publishing" / "STEAM_STORE_PAGE.md").read_text(encoding="utf-8")
    section = text.split("### macOS", 1)[1].split("\n### ", 1)[0]
    if _builds_intel(_macos_build_legs()):
        pytest.skip("release.yml builds an Intel leg")
    assert re.search(r"Apple Silicon only", section), (
        "STEAM_STORE_PAGE.md's macOS system requirements must say the build is "
        "Apple Silicon only while release.yml builds no Intel leg (issue #563)."
    )
