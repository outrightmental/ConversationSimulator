# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for artifact inspection tests.

Set CONVSIM_ARTIFACT_DIR to the directory containing the built Tauri bundle
artifacts (or an organized Steam depot content directory) before running.
All tests skip automatically when the variable is unset, so this suite is safe
to include in any CI run that does not build a desktop artifact.

Typical usage:

  # Against a platform-specific Tauri bundle directory:
  CONVSIM_ARTIFACT_DIR=apps/desktop/src-tauri/target/release/bundle/appimage \
    pytest tests/artifact/ -v

  # Against an organized Steam depot directory (after steam-deploy content prep):
  CONVSIM_ARTIFACT_DIR=steam-content/linux pytest tests/artifact/ -v

  # Via the release-smoke --full runner:
  CONVSIM_ARTIFACT_DIR=<path> ./scripts/release-smoke.sh --full
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def artifact_dir() -> Path:
    """Return Path to the artifact directory; skip all tests if not configured."""
    env = os.environ.get("CONVSIM_ARTIFACT_DIR", "")
    if not env:
        pytest.skip(
            "CONVSIM_ARTIFACT_DIR not set — "
            "set it to a built artifact directory to run artifact inspection"
        )
    p = Path(env)
    if not p.is_dir():
        pytest.fail(
            f"CONVSIM_ARTIFACT_DIR={env!r} does not exist or is not a directory"
        )
    return p


@pytest.fixture(scope="session")
def all_file_paths(artifact_dir: Path) -> list[Path]:
    """All regular files under the artifact directory (recursive)."""
    return [f for f in artifact_dir.rglob("*") if f.is_file()]


@pytest.fixture(scope="session")
def all_dir_paths(artifact_dir: Path) -> list[Path]:
    """All subdirectories under the artifact directory (recursive)."""
    return [p for p in artifact_dir.rglob("*") if p.is_dir()]
