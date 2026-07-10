# SPDX-License-Identifier: Apache-2.0
"""Tests for the /api/logbook endpoints (aggregated local skill profile)."""
import json
from datetime import datetime, timedelta, timezone


def _conn(client):
    return client.app.state.db.connection()


def _date_str(days_ago: int) -> str:
    d = datetime.now(timezone.utc).date() - timedelta(days=days_ago)
    return d.isoformat()


def _insert_session(
    client,
    session_id: str,
    *,
    scenario_id: str = "job_interview",
    flow_state: str = "DebriefReady",
    difficulty: str = "standard",
    created_days_ago: int = 0,
    duration_seconds: int = 300,
    ended: bool = True,
):
    conn = _conn(client)
    created = f"{_date_str(created_days_ago)} 12:00:00"
    ended_at = None
    if ended:
        end_dt = datetime.fromisoformat(created) + timedelta(seconds=duration_seconds)
        ended_at = end_dt.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO turn_sessions "
        "(session_id, scenario_id, flow_state, setup_json, created_at, ended_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            session_id,
            scenario_id,
            flow_state,
            json.dumps({"difficulty": difficulty}),
            created,
            ended_at,
        ),
    )
    conn.commit()


def _insert_debrief(
    client, session_id: str, *, scores: dict, overall_score, scenario_id="job_interview"
):
    conn = _conn(client)
    content = {
        "session_id": session_id,
        "scenario_id": scenario_id,
        "outcome": "success",
        "scores": scores,
        "overall_score": overall_score,
    }
    conn.execute(
        "INSERT INTO session_debriefs (session_id, content_json) VALUES (?, ?)",
        (session_id, json.dumps(content)),
    )
    conn.commit()


# ── Zero state ───────────────────────────────────────────────────────────────

def test_profile_returns_200(client):
    assert client.get("/api/logbook/profile").status_code == 200


def test_profile_zero_state(client):
    data = client.get("/api/logbook/profile").json()
    assert data["total_sessions"] == 0
    assert data["total_practice_seconds"] == 0
    assert data["streak_days"] == 0
    assert data["last_session_date"] is None
    assert data["dimension_scores"] == []
    assert data["personal_records"] == []
    assert data["strongest_dimension"] is None
    assert data["weakest_dimension"] is None
    assert data["last_session_delta"] is None


# ── Session counting & exclusions ────────────────────────────────────────────

def test_counts_completed_sessions(client):
    _insert_session(client, "s1", created_days_ago=0)
    _insert_session(client, "s2", created_days_ago=1)
    data = client.get("/api/logbook/profile").json()
    assert data["total_sessions"] == 2


def test_excludes_non_terminal_sessions(client):
    _insert_session(client, "active", flow_state="PlayerTurnListening", ended=False)
    _insert_session(client, "done", flow_state="Ended")
    data = client.get("/api/logbook/profile").json()
    assert data["total_sessions"] == 1


def test_excludes_workbench_sessions(client):
    _insert_session(client, "wb", scenario_id="workbench_test")
    _insert_session(client, "real", scenario_id="job_interview")
    data = client.get("/api/logbook/profile").json()
    assert data["total_sessions"] == 1


# ── Practice time ────────────────────────────────────────────────────────────

def test_practice_time_sums_durations(client):
    _insert_session(client, "s1", created_days_ago=0, duration_seconds=120)
    _insert_session(client, "s2", created_days_ago=1, duration_seconds=180)
    data = client.get("/api/logbook/profile").json()
    assert data["total_practice_seconds"] == 300


def test_practice_time_ignores_sessions_without_ended_at(client):
    _insert_session(client, "s1", flow_state="Ended", ended=False)
    data = client.get("/api/logbook/profile").json()
    assert data["total_sessions"] == 1
    assert data["total_practice_seconds"] == 0


def test_practice_time_with_production_timestamp_formats(client):
    # Production writes created_at as tz-aware ISO (_now_iso, '...+00:00') but
    # ended_at via SQLite datetime('now') as a naive 'YYYY-MM-DD HH:MM:SS'.
    # Subtracting the two must not raise (regression: aware/naive mismatch).
    conn = _conn(client)
    created_dt = datetime.now(timezone.utc).replace(microsecond=0)
    created = created_dt.isoformat()  # aware, ends in "+00:00"
    ended = (created_dt + timedelta(seconds=240)).strftime("%Y-%m-%d %H:%M:%S")  # naive
    conn.execute(
        "INSERT INTO turn_sessions "
        "(session_id, scenario_id, flow_state, setup_json, created_at, ended_at) "
        "VALUES (?, ?, 'DebriefReady', ?, ?, ?)",
        ("mixed", "job_interview", json.dumps({"difficulty": "standard"}), created, ended),
    )
    conn.commit()
    resp = client.get("/api/logbook/profile")
    assert resp.status_code == 200
    assert resp.json()["total_practice_seconds"] == 240


# ── Streak ───────────────────────────────────────────────────────────────────

def test_streak_counts_consecutive_days(client):
    _insert_session(client, "s0", created_days_ago=0)
    _insert_session(client, "s1", created_days_ago=1)
    _insert_session(client, "s2", created_days_ago=2)
    data = client.get("/api/logbook/profile").json()
    assert data["streak_days"] == 3


def test_streak_breaks_on_gap(client):
    _insert_session(client, "s0", created_days_ago=0)
    _insert_session(client, "s1", created_days_ago=1)
    _insert_session(client, "s3", created_days_ago=3)
    data = client.get("/api/logbook/profile").json()
    assert data["streak_days"] == 2


def test_streak_zero_when_last_session_stale(client):
    _insert_session(client, "s", created_days_ago=5)
    data = client.get("/api/logbook/profile").json()
    assert data["streak_days"] == 0


def test_streak_survives_from_yesterday(client):
    _insert_session(client, "s", created_days_ago=1)
    data = client.get("/api/logbook/profile").json()
    assert data["streak_days"] == 1


# ── Dimension scores ─────────────────────────────────────────────────────────

def test_dimension_scores_and_trajectory(client):
    # Oldest first so debrief ids ascend with session recency.
    _insert_session(client, "s1", created_days_ago=2)
    _insert_debrief(client, "s1", scores={"clarity": 40}, overall_score=40)
    _insert_session(client, "s2", created_days_ago=1)
    _insert_debrief(client, "s2", scores={"clarity": 80}, overall_score=80)

    data = client.get("/api/logbook/profile").json()
    dims = {d["dimension_id"]: d for d in data["dimension_scores"]}
    assert "clarity" in dims
    assert dims["clarity"]["session_count"] == 2
    # trajectory is chronological (oldest → newest)
    assert dims["clarity"]["trajectory"] == [40, 80]
    # recency-weighted: (80*1 + 40*0.85) / (1 + 0.85) ≈ 61.6
    assert dims["clarity"]["rolling_score"] == 61.6


def test_strongest_and_weakest_dimension(client):
    _insert_session(client, "s1", created_days_ago=0)
    _insert_debrief(client, "s1", scores={"empathy": 90, "assertiveness": 30}, overall_score=60)
    data = client.get("/api/logbook/profile").json()
    assert data["strongest_dimension"] == "empathy"
    assert data["weakest_dimension"] == "assertiveness"


# ── Personal records ─────────────────────────────────────────────────────────

def test_personal_record_keeps_best(client):
    _insert_session(client, "s1", created_days_ago=2)
    _insert_debrief(client, "s1", scores={"clarity": 50}, overall_score=50)
    _insert_session(client, "s2", created_days_ago=1)
    _insert_debrief(client, "s2", scores={"clarity": 70}, overall_score=70)
    data = client.get("/api/logbook/profile").json()
    records = data["personal_records"]
    assert len(records) == 1
    assert records[0]["best_score"] == 70
    assert records[0]["scenario_id"] == "job_interview"
    assert records[0]["difficulty"] == "standard"


def test_personal_records_split_by_difficulty(client):
    _insert_session(client, "s1", difficulty="standard", created_days_ago=1)
    _insert_debrief(client, "s1", scores={"clarity": 50}, overall_score=50)
    _insert_session(client, "s2", difficulty="hard", created_days_ago=0)
    _insert_debrief(client, "s2", scores={"clarity": 60}, overall_score=60)
    data = client.get("/api/logbook/profile").json()
    assert len(data["personal_records"]) == 2


# ── Last session delta ───────────────────────────────────────────────────────

def test_last_session_delta(client):
    _insert_session(client, "s1", created_days_ago=1)
    _insert_debrief(client, "s1", scores={"clarity": 50}, overall_score=50)
    _insert_session(client, "s2", created_days_ago=0)
    _insert_debrief(client, "s2", scores={"clarity": 65}, overall_score=65)
    data = client.get("/api/logbook/profile").json()
    assert data["last_session_delta"] == 15


def test_last_session_delta_none_with_single_session(client):
    _insert_session(client, "s1", created_days_ago=0)
    _insert_debrief(client, "s1", scores={"clarity": 50}, overall_score=50)
    data = client.get("/api/logbook/profile").json()
    assert data["last_session_delta"] is None


# ── Export ───────────────────────────────────────────────────────────────────

def test_export_structure(client):
    _insert_session(client, "s1", created_days_ago=0)
    _insert_debrief(client, "s1", scores={"clarity": 55}, overall_score=55)
    data = client.get("/api/logbook/export").json()
    assert "exported_at" in data
    assert "profile" in data
    assert data["profile"]["total_sessions"] == 1
    assert len(data["session_scores"]) == 1
    record = data["session_scores"][0]
    assert record["session_id"] == "s1"
    assert record["overall_score"] == 55
    assert record["scores"] == {"clarity": 55}


def test_export_excludes_workbench(client):
    _insert_session(client, "wb", scenario_id="workbench_test")
    _insert_debrief(
        client, "wb", scores={"clarity": 99}, overall_score=99, scenario_id="workbench_test"
    )
    _insert_session(client, "real", created_days_ago=0)
    _insert_debrief(client, "real", scores={"clarity": 55}, overall_score=55)
    data = client.get("/api/logbook/export").json()
    ids = {r["session_id"] for r in data["session_scores"]}
    assert ids == {"real"}
