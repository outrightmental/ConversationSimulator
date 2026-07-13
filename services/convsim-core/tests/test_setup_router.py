# SPDX-License-Identifier: Apache-2.0
"""Tests for the server-authoritative setup status / onboarding outcome API.

These cover the derivation that issue #380 makes the single source of truth:
the server, not localStorage, decides whether the first-run wizard should run.
"""
from __future__ import annotations


def test_status_is_never_run_before_any_outcome(client):
    """A fresh install with no recorded outcome reports never-run."""
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "never-run"
    assert body["onboarding_outcome"] is None
    assert body["pending_install_id"] is None


def test_recording_outcome_persists_and_flips_off_never_run(client):
    """Once an outcome is recorded, status is derived from system state.

    With no packs seeded and no model installed in the test DB, the derived
    state is 'incomplete' — the key point is that it is no longer 'never-run',
    so clearing the client cache cannot resurrect the wizard.
    """
    rec = client.post("/api/setup/outcome", json={"outcome": "completed-with-model"})
    assert rec.status_code == 204

    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] != "never-run"
    assert body["onboarding_outcome"]["outcome"] == "completed-with-model"
    # No packs seeded and no model present in the throwaway DB.
    assert "packs-seeded" in body["missing"]
    assert "llm-present" in body["missing"]
    assert body["kind"] == "incomplete"


def test_most_recent_outcome_wins(client):
    """The latest recorded outcome is the one reported back."""
    client.post("/api/setup/outcome", json={"outcome": "skipped"})
    client.post("/api/setup/outcome", json={"outcome": "demo"})

    body = client.get("/api/setup/status").json()
    assert body["onboarding_outcome"]["outcome"] == "demo"


def test_demo_choice_satisfies_the_llm_requirement(client):
    """A deliberate demo choice counts as a model per issue #380.

    'ready' is engine + (model | demo choice) + packs, so a demo user with no
    installed model must NOT be told the LLM is missing — otherwise they'd see a
    permanent, wrong "finish setup" banner. (packs-seeded is still reported
    missing here because the throwaway DB seeds none.)
    """
    client.post("/api/setup/outcome", json={"outcome": "demo"})

    body = client.get("/api/setup/status").json()
    assert "llm-present" not in body["missing"]


def test_completed_with_model_still_reports_missing_llm_without_a_model(client):
    """Contrast with demo: a completed-with-model outcome but no installed model
    still reports the LLM as missing, so a failed install is not hidden."""
    client.post("/api/setup/outcome", json={"outcome": "completed-with-model"})

    body = client.get("/api/setup/status").json()
    assert "llm-present" in body["missing"]
