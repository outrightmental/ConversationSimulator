# SPDX-License-Identifier: Apache-2.0
"""The flyting calibration suites, run against the real scoring pipeline.

This is the CI half of ``scripts/flyting-calibration.py``: the deterministic
expectations (gate outcomes, fouls, flags, the plagiarism cap) need no model, so
they run on every commit. A change to the gates, the cliché corpus, or the craft
metrics that moves scoring shows up here instead of in a player's run.

The judged expectations — bands, hooks — are skipped by definition without a
model; ``--judge RUNTIME_ID`` on the script is the nightly, real-model path.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "flyting-calibration.py"
_OFFICIAL_PACKS = _REPO_ROOT / "packs" / "official"


def _load_runner():
    """Import the calibration runner from scripts/ (not an installed module)."""
    if not _SCRIPT.is_file():
        pytest.skip(f"Calibration runner not found: {_SCRIPT}")
    spec = importlib.util.spec_from_file_location("flyting_calibration", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


@pytest.fixture(scope="module")
def pack_dirs(runner):
    if not _OFFICIAL_PACKS.is_dir():
        pytest.skip(f"Official packs directory not found: {_OFFICIAL_PACKS}")
    dirs = runner.default_pack_dirs()
    if not dirs:
        pytest.skip("No official pack ships a calibration suite")
    return dirs


class TestOfficialCalibration:
    def test_every_deterministic_expectation_holds(self, runner, pack_dirs):
        failures: list[str] = []
        checked = 0
        for pack_dir in pack_dirs:
            for suite in runner.run_pack(pack_dir):
                checked += suite.checked
                failures += [f"{suite.path}: {error}" for error in suite.errors]
                failures += [
                    f"{suite.path} [{volley.volley_id}] {failure}"
                    for volley in suite.volleys
                    for failure in volley.failures
                ]
        assert not failures, "Calibration drift:\n  " + "\n  ".join(failures)
        # A suite that asserts nothing would pass silently, which is the one
        # failure mode a calibration runner cannot be allowed to have.
        assert checked > 0

    def test_the_flyting_pack_ships_a_suite_per_scenario(self, runner):
        """Every shipped flyting scenario is covered, so drift cannot hide."""
        pack_dir = _OFFICIAL_PACKS / "flyting-school"
        if not pack_dir.is_dir():
            pytest.skip("Flyting School pack not found")
        covered = {suite.scenario_id for suite in runner.run_pack(pack_dir)}
        assert covered == set(runner._flyting_scenarios(pack_dir))
