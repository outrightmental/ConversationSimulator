# SPDX-License-Identifier: Apache-2.0
"""Reply speed — the plain-language "make the model respond faster" setting.

Issue #501 §1: the knobs that existed were all written in runtime terms and
none of them named the thing the player wanted. Reply speed names it, and it
has to actually do something: scale the NPC's word budget in the prompt and the
runtime's generation budget for the turn.
"""
import pytest

from convsim_core.services.reply_speed import (
    DEFAULT_REPLY_SPEED,
    MAX_SCALED_MAX_WORDS,
    MIN_SCALED_MAX_WORDS,
    REPLY_SPEED_PROFILES,
    normalize_reply_speed,
    profile_for,
    scaled_max_words,
)


# ── The profiles themselves ──────────────────────────────────────────────────


def test_three_named_speeds():
    assert set(REPLY_SPEED_PROFILES) == {"fast", "balanced", "detailed"}


def test_balanced_is_the_default():
    assert DEFAULT_REPLY_SPEED == "balanced"


def test_balanced_preserves_pre_change_behaviour():
    """'balanced' must leave the turn exactly as it was before this setting."""
    assert profile_for("balanced").max_tokens == 1024
    assert scaled_max_words(90, "balanced") == 90


def test_fast_shortens_and_detailed_lengthens():
    assert scaled_max_words(90, "fast") < 90 < scaled_max_words(90, "detailed")
    assert (
        profile_for("fast").max_tokens
        < profile_for("balanced").max_tokens
        < profile_for("detailed").max_tokens
    )


def test_scaling_is_relative_to_the_authored_cap():
    """A pack that writes terse NPCs stays terser than one that writes long ones."""
    assert scaled_max_words(120, "fast") > scaled_max_words(80, "fast")


def test_scaled_cap_is_clamped_at_both_ends():
    # Unclamped, halving 90 and 50 gives 45 and 25; the floor bites on the
    # second.
    assert scaled_max_words(90, "fast") == 45
    assert scaled_max_words(50, "fast") == MIN_SCALED_MAX_WORDS
    # Unclamped, 1.5× of 120 and 180 gives 180 and 270; the ceiling bites on
    # the second.
    assert scaled_max_words(120, "detailed") == 180
    assert scaled_max_words(180, "detailed") == MAX_SCALED_MAX_WORDS


def test_clamps_never_override_the_authored_cap():
    """``scenario.schema.json`` allows max_words anywhere in 10–500.

    Applied as plain bounds the clamps rewrote any cap outside them at every
    speed: a pack writing 10-word replies came out at 30 under all three, so
    "Quick replies" tripled the cap it was asked to shorten and the three
    options were indistinguishable; a pack writing 300 came out at 200 on
    `balanced`, which is meant to be the pre-#501 behaviour exactly.
    """
    # Already terser than the floor: nothing to shorten, nothing to lengthen.
    assert scaled_max_words(10, "fast") == 10
    assert scaled_max_words(10, "balanced") == 10
    # Already longer than the ceiling: `detailed` may not shorten it, and the
    # default may not touch it at all.
    assert scaled_max_words(300, "balanced") == 300
    assert scaled_max_words(300, "detailed") == 300
    assert scaled_max_words(500, "balanced") == 500


@pytest.mark.parametrize("authored", [10, 20, 40, 90, 150, 300, 500])
def test_fast_never_lengthens_and_detailed_never_shortens(authored):
    assert scaled_max_words(authored, "fast") <= authored
    assert scaled_max_words(authored, "balanced") == authored
    assert scaled_max_words(authored, "detailed") >= authored


@pytest.mark.parametrize("value", [None, "", "turbo", 3, "FAST"])
def test_unknown_values_fall_back_to_the_default(value):
    """Reply pacing is a preference; a bad value must never fail a turn."""
    assert normalize_reply_speed(value) == DEFAULT_REPLY_SPEED


# ── The settings endpoint ────────────────────────────────────────────────────


def test_reply_speed_is_exposed_by_the_settings_endpoint(client):
    body = client.get("/api/runtime/settings").json()
    assert "reply_speed" in body["settings"]
    assert body["settings"]["reply_speed"] is None
    assert body["recommended"]["reply_speed"] == DEFAULT_REPLY_SPEED


def test_reply_speed_persists(client):
    resp = client.put("/api/runtime/settings", json={"reply_speed": "fast"})
    assert resp.status_code == 200
    assert resp.json()["settings"]["reply_speed"] == "fast"
    assert client.get("/api/runtime/settings").json()["settings"]["reply_speed"] == "fast"


def test_reply_speed_needs_no_restart(client):
    """It is read per turn, so the next message already uses it."""
    resp = client.put("/api/runtime/settings", json={"reply_speed": "detailed"})
    assert resp.json()["requires_restart"] is False


def test_unknown_reply_speed_is_rejected(client):
    resp = client.put("/api/runtime/settings", json={"reply_speed": "ludicrous"})
    assert resp.status_code == 422
    assert "Reply speed" in resp.text


def test_reply_speed_survives_a_partial_update_of_other_fields(client):
    client.put("/api/runtime/settings", json={"reply_speed": "fast"})
    client.put("/api/runtime/settings", json={"threads": 4})
    settings = client.get("/api/runtime/settings").json()["settings"]
    assert settings["reply_speed"] == "fast"
    assert settings["threads"] == 4


def test_reset_clears_reply_speed(client):
    client.put("/api/runtime/settings", json={"reply_speed": "fast"})
    body = client.post("/api/runtime/settings/reset").json()
    assert body["settings"]["reply_speed"] is None


def test_stored_garbage_reads_back_as_unset(client):
    """A value a newer build wrote must not surface as an option the UI can't render."""
    from convsim_core.services.reply_speed import REPLY_SPEED_SETTING_KEY

    conn = client.app.state.db.connection()
    conn.execute(
        "INSERT INTO user_settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (REPLY_SPEED_SETTING_KEY, "hypersonic"),
    )
    conn.commit()
    assert client.get("/api/runtime/settings").json()["settings"]["reply_speed"] is None


# ── End-to-end through a real turn ───────────────────────────────────────────


_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "standard",
    "player_role_name": "Test Player",
    "save_transcript": True,
    "runtime_id": "fake",
}


def _play_one_turn(client) -> dict:
    """Create → start → one turn; returns the recorded prompt metadata."""
    session_id = client.post("/api/sessions", json=_SETUP).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start")
    resp = client.post(f"/api/sessions/{session_id}/turn", json={"content": "Hello."})
    assert resp.status_code == 200, resp.text

    conn = client.app.state.db.connection()
    row = conn.execute(
        "SELECT content FROM turn_session_turns "
        "WHERE session_id = ? AND role = 'player' ORDER BY turn_number DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    assert row is not None
    return {"session_id": session_id}


def test_word_cap_reaches_the_prompt(client, monkeypatch):
    """The scaled cap must land in the RESPONSE_STYLE layer the model reads."""
    captured: list[str] = []

    from convsim_core.services import turn_pipeline as tp

    real_compose = tp.compose_turn_prompt

    def _spy(inp):
        bundle = real_compose(inp)
        captured.append(bundle.system_prompt)
        return bundle

    monkeypatch.setattr(tp, "compose_turn_prompt", _spy)

    client.put("/api/runtime/settings", json={"reply_speed": "fast"})
    _play_one_turn(client)
    assert captured, "compose_turn_prompt was never called"
    assert "NPC utterance must be at most 45 words." in captured[0]


def test_balanced_prompt_keeps_the_authored_cap(client, monkeypatch):
    captured: list[str] = []

    from convsim_core.services import turn_pipeline as tp

    real_compose = tp.compose_turn_prompt

    def _spy(inp):
        bundle = real_compose(inp)
        captured.append(bundle.system_prompt)
        return bundle

    monkeypatch.setattr(tp, "compose_turn_prompt", _spy)

    _play_one_turn(client)
    assert "NPC utterance must be at most 90 words." in captured[0]


def test_token_budget_reaches_the_runtime(client, monkeypatch):
    captured: list[int] = []

    from convsim_core.services import turn_pipeline as tp

    real_collect = tp._collect_runtime_output

    async def _spy(runtime, request):
        captured.append(request.max_tokens)
        return await real_collect(runtime, request)

    monkeypatch.setattr(tp, "_collect_runtime_output", _spy)

    client.put("/api/runtime/settings", json={"reply_speed": "fast"})
    _play_one_turn(client)
    assert captured[0] == REPLY_SPEED_PROFILES["fast"].max_tokens


def test_scenario_data_is_not_mutated_across_sessions(client):
    """The preference belongs to the player, not to the shared scenario object."""
    from convsim_core.scenarios import resolve_scenario_info

    client.put("/api/runtime/settings", json={"reply_speed": "fast"})
    _play_one_turn(client)

    info = resolve_scenario_info("behavioral_interview")
    assert info is not None
    data = info.get_scenario_data("standard")
    authored = data.response_style.max_words if data.response_style else 90
    assert authored == 90, (
        "process_turn must copy the scenario data before scaling its word cap; "
        f"the shared object came back with max_words={authored}"
    )
