# SPDX-License-Identifier: Apache-2.0
"""Tests for the /api/relationship-memory endpoints."""
import json


def _conn(client):
    return client.app.state.db.connection()


def _insert_recap(client, npc_id: str, pack_id: str, *, session_count: int = 1, observations: list | None = None):
    conn = _conn(client)
    recap = {
        "schema_version": "1",
        "session_count": session_count,
        "last_session_at": "2026-07-10T12:00:00+00:00",
        "key_observations": observations or ["Sample observation"],
        "player_style_tags": ["direct"],
        "last_outcome": "success",
    }
    conn.execute(
        "INSERT INTO relationship_state (npc_id, pack_id, recap_json, session_count) VALUES (?, ?, ?, ?)",
        (npc_id, pack_id, json.dumps(recap), session_count),
    )
    conn.commit()


class TestListRelationshipMemory:
    def test_empty_when_no_recaps(self, client):
        r = client.get("/api/relationship-memory")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["recaps"] == []

    def test_returns_inserted_recaps(self, client):
        _insert_recap(client, "npc_alice", "negotiation_pack")
        _insert_recap(client, "npc_bob", "hr_pack")
        r = client.get("/api/relationship-memory")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        npc_ids = {x["npc_id"] for x in body["recaps"]}
        assert npc_ids == {"npc_alice", "npc_bob"}

    def test_recap_has_expected_fields(self, client):
        _insert_recap(client, "npc_alice", "negotiation_pack", session_count=3)
        r = client.get("/api/relationship-memory")
        recap = r.json()["recaps"][0]
        assert recap["npc_id"] == "npc_alice"
        assert recap["pack_id"] == "negotiation_pack"
        assert recap["session_count"] == 3
        assert "key_observations" in recap
        assert "player_style_tags" in recap


class TestDeleteRelationshipMemory:
    def test_delete_existing_recap(self, client):
        _insert_recap(client, "npc_alice", "negotiation_pack")
        r = client.delete("/api/relationship-memory/npc_alice/negotiation_pack")
        assert r.status_code == 204

        r2 = client.get("/api/relationship-memory")
        assert r2.json()["total"] == 0

    def test_delete_nonexistent_returns_404(self, client):
        r = client.delete("/api/relationship-memory/ghost/nopack")
        assert r.status_code == 404

    def test_delete_only_targets_specific_entry(self, client):
        _insert_recap(client, "npc_alice", "pack_a")
        _insert_recap(client, "npc_bob", "pack_a")
        client.delete("/api/relationship-memory/npc_alice/pack_a")
        r = client.get("/api/relationship-memory")
        body = r.json()
        assert body["total"] == 1
        assert body["recaps"][0]["npc_id"] == "npc_bob"


class TestDeleteAllRelationshipMemory:
    def test_delete_all_clears_every_recap(self, client):
        _insert_recap(client, "npc_alice", "pack_a")
        _insert_recap(client, "npc_bob", "pack_a")
        r = client.delete("/api/relationship-memory")
        assert r.status_code == 200
        body = r.json()
        assert body["deleted"] == 2

        r2 = client.get("/api/relationship-memory")
        assert r2.json()["total"] == 0

    def test_delete_all_when_empty(self, client):
        r = client.delete("/api/relationship-memory")
        assert r.status_code == 200
        assert r.json()["deleted"] == 0
