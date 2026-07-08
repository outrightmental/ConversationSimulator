# SPDX-License-Identifier: Apache-2.0
"""Tests for turn transcript persistence, FTS indexing, session export, and delete cascade.

Test plan (issue #20):
  - Transcript saving on: turns appear in GET /transcript, FTS is populated.
  - Transcript saving off: GET /transcript returns empty + message; FTS not populated.
  - Session export JSON shape includes scenario, setup, turns, events, debrief.
  - Delete cascade removes turns, events, and FTS entries.
  - FTS search finds saved sessions by text content.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_config(tmp_path):
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
    )


@pytest.fixture()
def client(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        yield c


_BASE_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "normal",
    "player_role_name": "Alice",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": True,
    "seed": None,
}


def _create_and_start(client: TestClient, save_transcript: bool = True) -> str:
    """Create and start a session; return session_id."""
    setup = {**_BASE_SETUP, "save_transcript": save_transcript}
    res = client.post("/api/sessions", json=setup)
    assert res.status_code == 201
    session_id = res.json()["session_id"]
    res = client.post(f"/api/sessions/{session_id}/start")
    assert res.status_code == 200
    return session_id


def _do_turn(client: TestClient, session_id: str, content: str = "I have five years of PM experience.") -> None:
    res = client.post(f"/api/sessions/{session_id}/turn", json={"content": content})
    assert res.status_code == 200


def _db_conn(client: TestClient):
    return client.app.state.db.connection()


# ---------------------------------------------------------------------------
# Transcript saving enabled
# ---------------------------------------------------------------------------


class TestTranscriptSavingEnabled:
    def test_transcript_endpoint_returns_turns_in_order(self, client):
        session_id = _create_and_start(client, save_transcript=True)
        _do_turn(client, session_id, "I have five years of experience.")

        res = client.get(f"/api/sessions/{session_id}/transcript")
        assert res.status_code == 200
        body = res.json()
        assert body["transcript_saved"] is True
        assert body["session_id"] == session_id
        # npc_opening (turn 0) + player turn (1) + npc turn (2)
        assert len(body["turns"]) >= 2
        roles = [t["role"] for t in body["turns"]]
        assert "npc_opening" in roles
        assert "player" in roles
        assert "npc" in roles

    def test_turns_appear_in_ascending_order(self, client):
        session_id = _create_and_start(client, save_transcript=True)
        _do_turn(client, session_id, "First message.")
        _do_turn(client, session_id, "Second message.")

        res = client.get(f"/api/sessions/{session_id}/transcript")
        turns = res.json()["turns"]
        turn_numbers = [t["turn_number"] for t in turns]
        assert turn_numbers == sorted(turn_numbers)

    def test_player_turn_has_source_mode(self, client):
        session_id = _create_and_start(client, save_transcript=True)
        _do_turn(client, session_id)

        res = client.get(f"/api/sessions/{session_id}/transcript")
        player_turns = [t for t in res.json()["turns"] if t["role"] == "player"]
        assert len(player_turns) == 1
        assert player_turns[0]["source_mode"] == "text-only"

    def test_fts_is_populated_after_turn(self, client):
        session_id = _create_and_start(client, save_transcript=True)
        unique_phrase = "zyphon_robot_army_unique"
        _do_turn(client, session_id, unique_phrase)

        conn = _db_conn(client)
        rows = conn.execute(
            "SELECT session_id FROM session_transcript_fts WHERE session_transcript_fts MATCH ?",
            (unique_phrase,),
        ).fetchall()
        assert any(r["session_id"] == session_id for r in rows)

    def test_npc_opening_indexed_in_fts(self, client):
        session_id = _create_and_start(client, save_transcript=True)

        conn = _db_conn(client)
        rows = conn.execute(
            "SELECT role FROM session_transcript_fts WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        roles = {r["role"] for r in rows}
        assert "npc_opening" in roles


# ---------------------------------------------------------------------------
# Transcript saving disabled
# ---------------------------------------------------------------------------


class TestTranscriptSavingDisabled:
    def test_transcript_endpoint_returns_empty_with_message(self, client):
        session_id = _create_and_start(client, save_transcript=False)
        _do_turn(client, session_id)

        res = client.get(f"/api/sessions/{session_id}/transcript")
        assert res.status_code == 200
        body = res.json()
        assert body["transcript_saved"] is False
        assert body["turns"] == []
        assert "message" in body
        assert body["message"] is not None

    def test_fts_not_populated_when_saving_disabled(self, client):
        session_id = _create_and_start(client, save_transcript=False)
        unique_phrase = "helios_particle_accelerator_off"
        _do_turn(client, session_id, unique_phrase)

        conn = _db_conn(client)
        rows = conn.execute(
            "SELECT session_id FROM session_transcript_fts WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        assert len(rows) == 0

    def test_session_still_functional_when_saving_disabled(self, client):
        """Turn pipeline still runs even when transcript saving is off."""
        session_id = _create_and_start(client, save_transcript=False)
        res = client.post(f"/api/sessions/{session_id}/turn", json={"content": "Hello!"})
        assert res.status_code == 200
        assert res.json()["state"] == "PlayerTurnListening"


# ---------------------------------------------------------------------------
# Session export
# ---------------------------------------------------------------------------


class TestSessionExport:
    def test_export_returns_required_top_level_fields(self, client):
        session_id = _create_and_start(client)
        _do_turn(client, session_id)

        res = client.get(f"/api/sessions/{session_id}/export")
        assert res.status_code == 200
        body = res.json()

        assert body["session_id"] == session_id
        assert "exported_at" in body
        assert "scenario" in body
        assert "setup" in body
        assert "state" in body
        assert "turn_count" in body
        assert "created_at" in body
        assert "transcript_saved" in body
        assert "turns" in body
        assert "events" in body
        assert "debrief" in body  # debrief is None until debrief endpoint exists

    def test_export_scenario_includes_name(self, client):
        session_id = _create_and_start(client)
        res = client.get(f"/api/sessions/{session_id}/export")
        scenario = res.json()["scenario"]
        assert scenario["id"] == "behavioral_interview"
        assert "name" in scenario
        assert isinstance(scenario["name"], str)
        assert len(scenario["name"]) > 0

    def test_export_includes_turns(self, client):
        session_id = _create_and_start(client)
        _do_turn(client, session_id, "I built a payments platform.")

        res = client.get(f"/api/sessions/{session_id}/export")
        turns = res.json()["turns"]
        assert len(turns) >= 3  # npc_opening, player, npc
        roles = {t["role"] for t in turns}
        assert "npc_opening" in roles
        assert "player" in roles
        assert "npc" in roles

    def test_export_includes_events(self, client):
        session_id = _create_and_start(client)
        _do_turn(client, session_id)

        res = client.get(f"/api/sessions/{session_id}/export")
        events = res.json()["events"]
        assert len(events) > 0
        event_types = {e["event_type"] for e in events}
        assert "state_delta" in event_types
        assert "debug" in event_types

    def test_export_event_has_correct_shape(self, client):
        session_id = _create_and_start(client)
        _do_turn(client, session_id)

        res = client.get(f"/api/sessions/{session_id}/export")
        events = res.json()["events"]
        for event in events:
            assert "id" in event
            assert "event_type" in event
            assert "payload" in event
            assert "occurred_at" in event

    def test_export_debrief_is_null(self, client):
        session_id = _create_and_start(client)
        res = client.get(f"/api/sessions/{session_id}/export")
        assert res.json()["debrief"] is None

    def test_export_transcript_saved_reflects_session_setting(self, client):
        session_with = _create_and_start(client, save_transcript=True)
        session_without = _create_and_start(client, save_transcript=False)

        res_with = client.get(f"/api/sessions/{session_with}/export")
        res_without = client.get(f"/api/sessions/{session_without}/export")

        assert res_with.json()["transcript_saved"] is True
        assert res_without.json()["transcript_saved"] is False

    def test_export_on_unknown_session_returns_404(self, client):
        res = client.get("/api/sessions/sess-doesnotexist/export")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Delete cascade
# ---------------------------------------------------------------------------


class TestDeleteCascade:
    def test_delete_returns_204(self, client):
        session_id = _create_and_start(client)
        res = client.delete(f"/api/sessions/{session_id}")
        assert res.status_code == 204

    def test_delete_unknown_session_returns_404(self, client):
        res = client.delete("/api/sessions/sess-doesnotexist")
        assert res.status_code == 404

    def test_deleted_session_is_gone(self, client):
        session_id = _create_and_start(client)
        client.delete(f"/api/sessions/{session_id}")
        res = client.get(f"/api/sessions/{session_id}")
        assert res.status_code == 404

    def test_delete_cascades_to_turns(self, client):
        session_id = _create_and_start(client)
        _do_turn(client, session_id)

        conn = _db_conn(client)
        before = conn.execute(
            "SELECT COUNT(*) FROM turn_session_turns WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        assert before > 0

        client.delete(f"/api/sessions/{session_id}")

        after = conn.execute(
            "SELECT COUNT(*) FROM turn_session_turns WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        assert after == 0

    def test_delete_cascades_to_events(self, client):
        session_id = _create_and_start(client)
        _do_turn(client, session_id)

        conn = _db_conn(client)
        before = conn.execute(
            "SELECT COUNT(*) FROM turn_session_events WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        assert before > 0

        client.delete(f"/api/sessions/{session_id}")

        after = conn.execute(
            "SELECT COUNT(*) FROM turn_session_events WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        assert after == 0

    def test_delete_removes_fts_entries(self, client):
        session_id = _create_and_start(client, save_transcript=True)
        _do_turn(client, session_id)

        conn = _db_conn(client)
        before = conn.execute(
            "SELECT COUNT(*) FROM session_transcript_fts WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        assert before > 0

        client.delete(f"/api/sessions/{session_id}")

        after = conn.execute(
            "SELECT COUNT(*) FROM session_transcript_fts WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        assert after == 0


# ---------------------------------------------------------------------------
# FTS search
# ---------------------------------------------------------------------------


class TestFTSSearch:
    def test_fts_finds_session_by_unique_player_text(self, client):
        session_a = _create_and_start(client, save_transcript=True)
        session_b = _create_and_start(client, save_transcript=True)

        _do_turn(client, session_a, "I am an expert in quantum_flux_capacitors")
        _do_turn(client, session_b, "I specialize in regular software engineering")

        conn = _db_conn(client)
        rows = conn.execute(
            "SELECT DISTINCT session_id FROM session_transcript_fts "
            "WHERE session_transcript_fts MATCH ?",
            ("quantum_flux_capacitors",),
        ).fetchall()
        found_ids = {r["session_id"] for r in rows}

        assert session_a in found_ids
        assert session_b not in found_ids

    def test_fts_returns_both_sessions_for_shared_term(self, client):
        session_a = _create_and_start(client, save_transcript=True)
        session_b = _create_and_start(client, save_transcript=True)

        _do_turn(client, session_a, "I have experience in leadership roles")
        _do_turn(client, session_b, "I developed strong leadership skills over ten years")

        conn = _db_conn(client)
        rows = conn.execute(
            "SELECT DISTINCT session_id FROM session_transcript_fts "
            "WHERE session_transcript_fts MATCH ?",
            ("leadership",),
        ).fetchall()
        found_ids = {r["session_id"] for r in rows}

        assert session_a in found_ids
        assert session_b in found_ids

    def test_fts_excludes_unsaved_sessions(self, client):
        saved_session = _create_and_start(client, save_transcript=True)
        unsaved_session = _create_and_start(client, save_transcript=False)

        unique = "nebulatron_unique_phrase_xyz"
        _do_turn(client, saved_session, unique)
        _do_turn(client, unsaved_session, unique)

        conn = _db_conn(client)
        rows = conn.execute(
            "SELECT DISTINCT session_id FROM session_transcript_fts "
            "WHERE session_transcript_fts MATCH ?",
            (unique,),
        ).fetchall()
        found_ids = {r["session_id"] for r in rows}

        assert saved_session in found_ids
        assert unsaved_session not in found_ids

    def test_fts_search_returns_nothing_after_session_deleted(self, client):
        session_id = _create_and_start(client, save_transcript=True)
        unique = "ultraviolet_prism_42_unique"
        _do_turn(client, session_id, unique)

        conn = _db_conn(client)
        before = conn.execute(
            "SELECT COUNT(*) FROM session_transcript_fts "
            "WHERE session_transcript_fts MATCH ?",
            (unique,),
        ).fetchone()[0]
        assert before > 0

        client.delete(f"/api/sessions/{session_id}")

        after = conn.execute(
            "SELECT COUNT(*) FROM session_transcript_fts "
            "WHERE session_transcript_fts MATCH ?",
            (unique,),
        ).fetchone()[0]
        assert after == 0
