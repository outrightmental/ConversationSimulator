# SPDX-License-Identifier: Apache-2.0
"""Loading and resolving ``mode: flyting`` scenarios out of a pack directory.

Three things the loader has to get right that the API tests cannot see:

  * a scenario that does not declare the mode is not a flyting scenario,
  * a ref that points outside the pack is refused rather than followed, and
  * an edited pack is picked up without restarting the process, because an
    author in the Creator Workbench edits YAML and replays immediately.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from convsim_core.flyting.loader import (
    clear_scenario_cache,
    load_flyting_scenario,
    resolve_flyting_scenario,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FLYTING_PACK = _REPO_ROOT / "packs" / "official" / "flyting-school"
_CONVERSATION_PACK = _REPO_ROOT / "packs" / "official" / "job-interview-basic"


@pytest.fixture()
def pack_copy(tmp_path) -> Path:
    """A writable copy of the Flyting School pack."""
    if not _FLYTING_PACK.is_dir():
        pytest.skip(f"Flyting pack not found: {_FLYTING_PACK}")
    destination = tmp_path / "flyting-school"
    shutil.copytree(_FLYTING_PACK, destination)
    return destination


def index_connection(pack_dir: Path, scenario_id: str, rel_path: str) -> sqlite3.Connection:
    """The two rows of the installed-pack index that resolution reads."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE packs (id INTEGER PRIMARY KEY, slug TEXT, source_path TEXT);"
        "CREATE TABLE scenarios (id INTEGER PRIMARY KEY, pack_id INTEGER, slug TEXT, rel_path TEXT);"
    )
    conn.execute(
        "INSERT INTO packs (id, slug, source_path) VALUES (1, 'flyting-school', ?)",
        (str(pack_dir),),
    )
    conn.execute(
        "INSERT INTO scenarios (pack_id, slug, rel_path) VALUES (1, ?, ?)",
        (scenario_id, rel_path),
    )
    conn.commit()
    return conn


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_scenario_cache()
    yield
    clear_scenario_cache()


class TestModeDetection:
    def test_a_flyting_scenario_loads_with_its_target_and_rubric(self, pack_copy):
        scenario = load_flyting_scenario(pack_copy, "scenarios/whitechapel_rose.yaml")
        assert scenario is not None
        assert scenario.scenario_id == "whitechapel_rose"
        assert {t.id for t in scenario.attack_surface} >= {"hypocrisy", "cowardice"}
        assert scenario.rubric.weights["sting"] > 0
        assert scenario.audience is not None

    def test_a_conversation_scenario_is_not_a_flyting_scenario(self):
        if not _CONVERSATION_PACK.is_dir():
            pytest.skip("Conversation pack not found")
        rel = next(p for p in (_CONVERSATION_PACK / "scenarios").glob("*.yaml"))
        assert load_flyting_scenario(
            _CONVERSATION_PACK, f"scenarios/{rel.name}"
        ) is None


class TestRefContainment:
    def test_a_ref_outside_the_pack_is_refused(self, pack_copy, tmp_path):
        """A ref that escapes the pack reads nothing, rather than reading the host."""
        outside = tmp_path / "outside_npc.yaml"
        outside.write_text(
            "npc_id: smuggled\ndisplay_name: Smuggled In\n"
            "attack_surface:\n  - id: vanity\n    brief: Should never load.\n",
            encoding="utf-8",
        )
        scenario_file = pack_copy / "scenarios" / "whitechapel_rose.yaml"
        scenario_file.write_text(
            scenario_file.read_text(encoding="utf-8").replace(
                "ref: ../npcs/lord_bellingham.yaml", "ref: ../../outside_npc.yaml"
            ),
            encoding="utf-8",
        )

        scenario = load_flyting_scenario(pack_copy, "scenarios/whitechapel_rose.yaml")
        assert scenario is not None
        assert scenario.npc.display_name != "Smuggled In"
        assert scenario.attack_surface == ()


class TestResolutionCache:
    def test_a_resolved_scenario_is_cached(self, pack_copy):
        conn = index_connection(pack_copy, "whitechapel_rose", "scenarios/whitechapel_rose.yaml")
        first = resolve_flyting_scenario("whitechapel_rose", conn)
        second = resolve_flyting_scenario("whitechapel_rose", conn)
        assert first is second  # the same object, not merely an equal one

    def test_an_edited_pack_is_picked_up_without_a_restart(self, pack_copy):
        """The Workbench edits YAML in place; the next run must play the edit."""
        conn = index_connection(pack_copy, "whitechapel_rose", "scenarios/whitechapel_rose.yaml")
        before = resolve_flyting_scenario("whitechapel_rose", conn)
        assert before is not None and before.flyting.difficulty_multiplier == pytest.approx(1.2)

        scenario_file = pack_copy / "scenarios" / "whitechapel_rose.yaml"
        scenario_file.write_text(
            scenario_file.read_text(encoding="utf-8").replace(
                "difficulty_multiplier: 1.2", "difficulty_multiplier: 1.5"
            ),
            encoding="utf-8",
        )
        # st_mtime_ns has nanosecond resolution on every platform the app ships
        # on, but the size change is what guarantees this test cannot be flaky.
        scenario_file.write_text(
            scenario_file.read_text(encoding="utf-8") + "\n# edited by the author\n",
            encoding="utf-8",
        )

        after = resolve_flyting_scenario("whitechapel_rose", conn)
        assert after is not None
        assert after.flyting.difficulty_multiplier == pytest.approx(1.5)

    def test_an_unknown_scenario_resolves_to_none(self, pack_copy):
        conn = index_connection(pack_copy, "whitechapel_rose", "scenarios/whitechapel_rose.yaml")
        assert resolve_flyting_scenario("not_installed", conn) is None
