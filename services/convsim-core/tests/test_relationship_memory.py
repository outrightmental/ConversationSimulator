# SPDX-License-Identifier: Apache-2.0
"""Tests for the relationship memory service and repository."""
import json

import pytest

from convsim_core.services.relationship_memory import (
    RECAP_SCHEMA_VERSION,
    extract_recap,
    validate_recap,
)


# ---------------------------------------------------------------------------
# extract_recap
# ---------------------------------------------------------------------------


class TestExtractRecap:
    def test_first_session_no_existing(self):
        recap = extract_recap(
            outcome="success",
            scores={"clarity": 75.0, "empathy": 30.0},
            improvements=["Try asking more open questions", "Avoid interrupting the NPC"],
            generated_at="2026-07-10T12:00:00+00:00",
            existing_recap=None,
        )
        assert recap["schema_version"] == RECAP_SCHEMA_VERSION
        assert recap["session_count"] == 1
        assert recap["last_outcome"] == "success"
        assert "Try asking more open questions" in recap["key_observations"]
        assert "Avoid interrupting the NPC" in recap["key_observations"]
        assert len(recap["key_observations"]) == 2

    def test_increments_session_count(self):
        existing = {
            "schema_version": "1",
            "session_count": 3,
            "last_session_at": "2026-07-08T10:00:00+00:00",
            "key_observations": ["Old observation"],
            "player_style_tags": [],
            "last_outcome": "failure",
        }
        recap = extract_recap(
            outcome="success",
            scores={},
            improvements=["New thing"],
            generated_at="2026-07-10T12:00:00+00:00",
            existing_recap=existing,
        )
        assert recap["session_count"] == 4

    def test_rolling_window_prepends_new_observations(self):
        existing_obs = [f"Old observation {i}" for i in range(4)]
        existing = {
            "schema_version": "1",
            "session_count": 5,
            "last_session_at": "2026-07-09T10:00:00+00:00",
            "key_observations": existing_obs,
            "player_style_tags": [],
            "last_outcome": "success",
        }
        recap = extract_recap(
            outcome="success",
            scores={},
            improvements=["Brand new observation A", "Brand new observation B"],
            generated_at="2026-07-10T12:00:00+00:00",
            existing_recap=existing,
        )
        # New ones prepended, capped at 5
        assert recap["key_observations"][0] == "Brand new observation A"
        assert recap["key_observations"][1] == "Brand new observation B"
        assert len(recap["key_observations"]) == 5

    def test_max_two_improvements_per_session(self):
        recap = extract_recap(
            outcome="success",
            scores={},
            improvements=["A", "B", "C", "D"],
            generated_at="2026-07-10T12:00:00+00:00",
            existing_recap=None,
        )
        assert len(recap["key_observations"]) == 2
        assert "A" in recap["key_observations"]
        assert "B" in recap["key_observations"]

    def test_long_observation_truncated(self):
        long_obs = "x" * 200
        recap = extract_recap(
            outcome="success",
            scores={},
            improvements=[long_obs],
            generated_at="2026-07-10T12:00:00+00:00",
            existing_recap=None,
        )
        assert len(recap["key_observations"][0]) == 150

    def test_style_tags_from_weak_scores(self):
        recap = extract_recap(
            outcome="success",
            scores={"assertiveness": 35.0},
            improvements=[],
            generated_at="2026-07-10T12:00:00+00:00",
            existing_recap=None,
        )
        assert "hesitant under pressure" in recap["player_style_tags"]

    def test_style_tags_from_strong_scores(self):
        recap = extract_recap(
            outcome="success",
            scores={"clarity": 80.0},
            improvements=[],
            generated_at="2026-07-10T12:00:00+00:00",
            existing_recap=None,
        )
        assert "clear communicator" in recap["player_style_tags"]

    def test_style_tags_capped_at_three(self):
        recap = extract_recap(
            outcome="success",
            scores={
                "listening": 80.0,
                "questioning": 80.0,
                "empathy": 80.0,
                "assertiveness": 80.0,
            },
            improvements=[],
            generated_at="2026-07-10T12:00:00+00:00",
            existing_recap=None,
        )
        assert len(recap["player_style_tags"]) <= 3

    def test_empty_improvements_list(self):
        recap = extract_recap(
            outcome="failure",
            scores={},
            improvements=[],
            generated_at="2026-07-10T12:00:00+00:00",
            existing_recap=None,
        )
        assert recap["key_observations"] == []
        assert recap["last_outcome"] == "failure"


# ---------------------------------------------------------------------------
# validate_recap
# ---------------------------------------------------------------------------


class TestValidateRecap:
    def test_valid_empty_recap(self):
        recap = {
            "schema_version": "1",
            "session_count": 1,
            "last_session_at": "2026-07-10T12:00:00+00:00",
            "key_observations": [],
            "player_style_tags": [],
            "last_outcome": "success",
        }
        assert validate_recap(recap) is True

    def test_valid_full_recap(self):
        recap = extract_recap(
            outcome="success",
            scores={"clarity": 75.0},
            improvements=["Work on listening"],
            generated_at="2026-07-10T12:00:00+00:00",
            existing_recap=None,
        )
        assert validate_recap(recap) is True

    def test_wrong_schema_version(self):
        recap = {
            "schema_version": "99",
            "session_count": 1,
            "last_session_at": "...",
            "key_observations": [],
            "player_style_tags": [],
            "last_outcome": "success",
        }
        assert validate_recap(recap) is False

    def test_too_many_observations(self):
        recap = {
            "schema_version": "1",
            "session_count": 1,
            "last_session_at": "...",
            "key_observations": ["obs"] * 6,
            "player_style_tags": [],
            "last_outcome": "success",
        }
        assert validate_recap(recap) is False

    def test_observation_too_long(self):
        recap = {
            "schema_version": "1",
            "session_count": 1,
            "last_session_at": "...",
            "key_observations": ["x" * 151],
            "player_style_tags": [],
            "last_outcome": "success",
        }
        assert validate_recap(recap) is False

    def test_too_many_style_tags(self):
        recap = {
            "schema_version": "1",
            "session_count": 1,
            "last_session_at": "...",
            "key_observations": [],
            "player_style_tags": ["a", "b", "c", "d"],
            "last_outcome": "success",
        }
        assert validate_recap(recap) is False

    def test_not_a_dict(self):
        assert validate_recap([]) is False  # type: ignore[arg-type]
        assert validate_recap(None) is False  # type: ignore[arg-type]
        assert validate_recap("string") is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Repository round-trip (via in-memory SQLite)
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_db():
    import sqlite3

    from convsim_core.storage.migrations import run_migrations

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    return conn


class TestRelationshipRepo:
    def test_get_nonexistent_returns_none(self, mem_db):
        from convsim_core.storage.repositories.relationship_repo import get_relationship_recap

        assert get_relationship_recap(mem_db, "npc1", "pack1") is None

    def test_upsert_then_get(self, mem_db):
        from convsim_core.storage.repositories.relationship_repo import (
            get_relationship_recap,
            upsert_relationship_recap,
        )

        recap = {
            "schema_version": "1",
            "session_count": 1,
            "last_session_at": "2026-07-10T12:00:00+00:00",
            "key_observations": ["Obs one"],
            "player_style_tags": ["direct"],
            "last_outcome": "success",
        }
        upsert_relationship_recap(mem_db, "npc1", "pack1", recap, 1)
        result = get_relationship_recap(mem_db, "npc1", "pack1")
        assert result is not None
        assert result["session_count"] == 1
        assert result["key_observations"] == ["Obs one"]

    def test_upsert_updates_existing(self, mem_db):
        from convsim_core.storage.repositories.relationship_repo import (
            get_relationship_recap,
            upsert_relationship_recap,
        )

        recap_v1 = {
            "schema_version": "1", "session_count": 1,
            "last_session_at": "2026-07-09T12:00:00+00:00",
            "key_observations": ["Old obs"],
            "player_style_tags": [], "last_outcome": "failure",
        }
        upsert_relationship_recap(mem_db, "npc1", "pack1", recap_v1, 1)

        recap_v2 = {
            "schema_version": "1", "session_count": 2,
            "last_session_at": "2026-07-10T12:00:00+00:00",
            "key_observations": ["New obs"],
            "player_style_tags": ["direct"], "last_outcome": "success",
        }
        upsert_relationship_recap(mem_db, "npc1", "pack1", recap_v2, 2)

        result = get_relationship_recap(mem_db, "npc1", "pack1")
        assert result["session_count"] == 2
        assert result["last_outcome"] == "success"

    def test_list_returns_all(self, mem_db):
        from convsim_core.storage.repositories.relationship_repo import (
            list_relationship_recaps,
            upsert_relationship_recap,
        )

        recap = {
            "schema_version": "1", "session_count": 1,
            "last_session_at": "2026-07-10T12:00:00+00:00",
            "key_observations": [], "player_style_tags": [], "last_outcome": "success",
        }
        upsert_relationship_recap(mem_db, "npc1", "pack1", recap, 1)
        upsert_relationship_recap(mem_db, "npc2", "pack1", recap, 1)

        rows = list_relationship_recaps(mem_db)
        assert len(rows) == 2
        npc_ids = {r["npc_id"] for r in rows}
        assert npc_ids == {"npc1", "npc2"}

    def test_delete_single(self, mem_db):
        from convsim_core.storage.repositories.relationship_repo import (
            delete_relationship_recap,
            get_relationship_recap,
            upsert_relationship_recap,
        )

        recap = {
            "schema_version": "1", "session_count": 1,
            "last_session_at": "2026-07-10T12:00:00+00:00",
            "key_observations": [], "player_style_tags": [], "last_outcome": "success",
        }
        upsert_relationship_recap(mem_db, "npc1", "pack1", recap, 1)
        upsert_relationship_recap(mem_db, "npc2", "pack1", recap, 1)

        found = delete_relationship_recap(mem_db, "npc1", "pack1")
        assert found is True
        assert get_relationship_recap(mem_db, "npc1", "pack1") is None
        assert get_relationship_recap(mem_db, "npc2", "pack1") is not None

    def test_delete_nonexistent_returns_false(self, mem_db):
        from convsim_core.storage.repositories.relationship_repo import delete_relationship_recap

        assert delete_relationship_recap(mem_db, "ghost", "no-pack") is False

    def test_delete_all(self, mem_db):
        from convsim_core.storage.repositories.relationship_repo import (
            delete_all_relationship_recaps,
            list_relationship_recaps,
            upsert_relationship_recap,
        )

        recap = {
            "schema_version": "1", "session_count": 1,
            "last_session_at": "2026-07-10T12:00:00+00:00",
            "key_observations": [], "player_style_tags": [], "last_outcome": "success",
        }
        upsert_relationship_recap(mem_db, "npc1", "pack1", recap, 1)
        upsert_relationship_recap(mem_db, "npc2", "pack1", recap, 1)

        deleted = delete_all_relationship_recaps(mem_db)
        assert deleted == 2
        assert list_relationship_recaps(mem_db) == []
