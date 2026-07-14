# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from convsim_core.runtime.scripted import ScriptedChatRuntime
from convsim_core.runtime.types import (
    ChatFinal,
    ChatMessage,
    ChatRequest,
    ChatToken,
    RuntimeStatus,
)


@pytest.fixture()
def runtime() -> ScriptedChatRuntime:
    return ScriptedChatRuntime()


# ── Identity and metadata ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scripted_runtime_id(runtime):
    assert runtime.id == "scripted"


@pytest.mark.asyncio
async def test_scripted_runtime_display_name_indicates_scripted(runtime):
    assert "scripted" in runtime.display_name.lower() or "tutorial" in runtime.display_name.lower()


@pytest.mark.asyncio
async def test_scripted_runtime_capabilities(runtime):
    caps = runtime.capabilities
    assert caps.streaming is True
    assert caps.json_schema is True
    assert caps.grammar is False
    assert caps.tool_calling is False
    assert caps.embeddings is False


@pytest.mark.asyncio
async def test_scripted_runtime_list_models(runtime):
    models = await runtime.list_models()
    assert len(models) >= 1
    assert models[0].id == "first-words-tutorial"


@pytest.mark.asyncio
async def test_scripted_runtime_health_is_ready(runtime):
    h = await runtime.health()
    assert h.status == RuntimeStatus.READY
    assert h.runtime_id == "scripted"
    assert h.checked_at


# ── Streaming ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scripted_runtime_streams_tokens_then_final(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hello")],
        scripted_turn_index=1,
    )
    chunks = []
    async for chunk in runtime.chat_stream(request):
        chunks.append(chunk)

    tokens = [c for c in chunks if isinstance(c, ChatToken)]
    finals = [c for c in chunks if isinstance(c, ChatFinal)]

    assert len(tokens) > 0
    assert len(finals) == 1
    assert finals[0].type == "final"
    assert finals[0].text
    assert finals[0].model_id == "first-words-tutorial"


@pytest.mark.asyncio
async def test_scripted_runtime_final_text_matches_joined_tokens(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hi")],
        scripted_turn_index=1,
    )
    token_texts = []
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatToken):
            token_texts.append(chunk.text)
        elif isinstance(chunk, ChatFinal):
            final = chunk

    assert final is not None
    joined = "".join(token_texts).strip()
    assert joined == final.text.strip()


# ── Structured output / NPC turn schema ──────────────────────────────────────

@pytest.mark.asyncio
async def test_scripted_runtime_returns_structured_npc_turn_with_schema(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hello")],
        json_schema={"type": "object", "properties": {"npc_utterance": {}, "safety": {}}},
        scripted_turn_index=1,
    )
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            final = chunk

    assert final is not None
    assert final.structured is not None
    assert "npc_utterance" in final.structured
    assert "safety" in final.structured
    assert final.structured["safety"]["status"] == "ok"
    assert final.structured["session_control"]["continue_session"] is True


@pytest.mark.asyncio
async def test_scripted_runtime_returns_debrief_with_debrief_schema(runtime):
    debrief_schema = {
        "type": "object",
        "properties": {
            "summary": {},
            "replay_suggestions": {},  # discriminant key
        },
    }
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="end")],
        json_schema=debrief_schema,
        scripted_turn_index=1,
    )
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            final = chunk

    assert final is not None
    assert final.structured is not None
    assert "summary" in final.structured
    assert "replay_suggestions" in final.structured
    assert "strengths" in final.structured


@pytest.mark.asyncio
async def test_scripted_runtime_no_structured_output_without_schema(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hello")],
    )
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            final = chunk

    assert final is not None
    assert final.structured is None


# ── Turn sequencing ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scripted_runtime_different_turns_return_different_utterances(runtime):
    schema = {"type": "object", "properties": {"npc_utterance": {}}}

    async def get_utterance(turn_idx: int) -> str:
        request = ChatRequest(
            messages=[ChatMessage(role="user", content="test")],
            json_schema=schema,
            scripted_turn_index=turn_idx,
        )
        async for chunk in runtime.chat_stream(request):
            if isinstance(chunk, ChatFinal):
                assert chunk.structured is not None
                return chunk.structured["npc_utterance"]
        return ""

    turn1 = await get_utterance(1)
    turn2 = await get_utterance(2)
    assert turn1 != turn2, "different turns should return different utterances"


@pytest.mark.asyncio
async def test_scripted_runtime_turn1_engages_player(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hi")],
        json_schema={"type": "object", "properties": {"npc_utterance": {}}},
        scripted_turn_index=1,
    )
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            assert chunk.structured is not None
            utterance = chunk.structured["npc_utterance"]
            assert utterance  # non-empty
            assert chunk.structured["session_control"]["continue_session"] is True
            return
    pytest.fail("No ChatFinal received")


# ── Ending branch keyword detection ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_scripted_runtime_excited_ending_branch(runtime):
    schema = {"type": "object", "properties": {"npc_utterance": {}, "session_control": {}}}
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="I'm so excited and ready to go!")],
        json_schema=schema,
        scripted_turn_index=99,  # beyond script length → triggers ending branch
    )
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            assert chunk.structured is not None
            sc = chunk.structured["session_control"]
            assert sc["continue_session"] is False
            assert sc["ending_type"] == "success"
            return
    pytest.fail("No ChatFinal received")


@pytest.mark.asyncio
async def test_scripted_runtime_curious_ending_branch(runtime):
    schema = {"type": "object", "properties": {"npc_utterance": {}, "session_control": {}}}
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="I'm curious how the meters actually work")],
        json_schema=schema,
        scripted_turn_index=99,
    )
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            assert chunk.structured is not None
            utterance = chunk.structured["npc_utterance"]
            assert "curio" in utterance.lower() or "question" in utterance.lower() or "learn" in utterance.lower() or "interest" in utterance.lower() or "explor" in utterance.lower()
            sc = chunk.structured["session_control"]
            assert sc["continue_session"] is False
            return
    pytest.fail("No ChatFinal received")


@pytest.mark.asyncio
async def test_scripted_runtime_default_steady_ending_branch(runtime):
    schema = {"type": "object", "properties": {"npc_utterance": {}, "session_control": {}}}
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="I don't know yet.")],
        json_schema=schema,
        scripted_turn_index=99,
    )
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            assert chunk.structured is not None
            sc = chunk.structured["session_control"]
            assert sc["continue_session"] is False
            assert sc["ending_type"] == "success"
            return
    pytest.fail("No ChatFinal received")


# ── State deltas ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scripted_runtime_turn3_state_delta_raises_engagement(runtime):
    """Turn 3 should push engagement above the warm_moment event threshold (60)."""
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="I see the meter moving!")],
        json_schema={"type": "object", "properties": {"state_delta": {}}},
        scripted_turn_index=3,
    )
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            assert chunk.structured is not None
            delta = chunk.structured.get("state_delta", {})
            assert delta.get("engagement", 0) > 0
            return
    pytest.fail("No ChatFinal received")


# ── Registry registration ─────────────────────────────────────────────────────

def test_scripted_runtime_is_registered():
    from convsim_core.runtime.registry import list_runtime_ids
    import convsim_core.runtime  # noqa: F401 — triggers registration
    assert "scripted" in list_runtime_ids()


# ── Output-schema compatibility ───────────────────────────────────────────────
# The turn pipeline feeds every runtime's structured output through the
# prompt-composer validators (parse_turn_output / parse_debrief_narrative).
# Any field the scripted script gets wrong — an unknown npc_emotion, a
# malformed turning_point — is silently replaced with a safe fallback, which
# would break the tutorial without failing the isolated runtime tests above.
# These tests validate the scripted content against the real validators so a
# schema drift is caught here instead of at runtime.

def test_scripted_turns_pass_npc_output_validation():
    from convsim_prompt.turn_output import _validate as validate_turn_output
    from convsim_core.runtime.scripted import _FIRST_WORDS_SCRIPT, _pick_ending_turn

    for i, turn in enumerate(_FIRST_WORDS_SCRIPT, start=1):
        # Raises ValidationError (and fails the test) on any invalid field.
        validate_turn_output(turn), f"turn {i} failed validation"

    for player_text in ("I'm so excited!", "how does this work?", "ok"):
        validate_turn_output(_pick_ending_turn(player_text))


def test_scripted_debrief_passes_debrief_validation():
    from convsim_prompt.debrief_output import _validate_narrative
    from convsim_core.runtime.scripted import _DEBRIEF_RESPONSE

    narrative = _validate_narrative(_DEBRIEF_RESPONSE)
    assert narrative.used_fallback is False
    assert narrative.turning_points  # scripted debrief keeps its turning point


# ── Session router integration — scripted runtime selection (issue #427) ──────
# When use_model selects the "scripted" runtime, submit_turn and generate_debrief
# must use ScriptedChatRuntime (not the fake runtime stored in app.state.runtime).
# These tests drive the tutorial scenario via the HTTP API to confirm end-to-end.

_TUTORIAL_SESSION_SETUP = {
    "scenario_id": "first_words_tutorial",
    "difficulty": "standard",
    "player_role_name": "New Player",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": True,
    "save_transcript": True,
    "seed": None,
}


def test_tutorial_turn_uses_scripted_runtime_when_active_config_is_scripted(tmp_config):
    """When active_runtime_id='scripted', submit_turn produces the tutorial script, not a fake response."""
    from convsim_core.app import create_app
    from convsim_core.services.model_manager_service import set_active_config
    from fastapi.testclient import TestClient

    app = create_app(tmp_config)
    with TestClient(app) as client:
        # Seed the official packs so first_words_tutorial is resolvable.
        import convsim_core.scenarios  # noqa: F401
        set_active_config(app.state.db.connection(), runtime_id="scripted")

        res = client.post("/api/sessions", json=_TUTORIAL_SESSION_SETUP)
        assert res.status_code == 201, res.text
        session_id = res.json()["session_id"]

        client.post(f"/api/sessions/{session_id}/start")
        turn_res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Hello, let's get started!"},
        )
        assert turn_res.status_code == 200, turn_res.text
        body = turn_res.json()
        npc_events = [e for e in body["events"] if e["event_type"] == "npc_turn"]
        assert npc_events, "No npc_turn event found in turn response"
        npc_text = npc_events[0]["payload"]["content"]
        # Scripted runtime produces the authored tutorial text, not the fake placeholder.
        assert "meter" in npc_text.lower() or "engagement" in npc_text.lower() or "turn" in npc_text.lower(), (
            f"Expected scripted tutorial response, got: {npc_text!r}"
        )
        assert "simulated npc" not in npc_text.lower(), (
            f"Got fake runtime response instead of scripted: {npc_text!r}"
        )


def test_tutorial_debrief_uses_scripted_debrief_when_active_config_is_scripted(tmp_config):
    """Debrief for a tutorial session uses the scripted runtime's authored debrief content."""
    from convsim_core.app import create_app
    from convsim_core.services.model_manager_service import set_active_config
    from convsim_core.runtime.scripted import _DEBRIEF_RESPONSE
    from fastapi.testclient import TestClient

    app = create_app(tmp_config)
    with TestClient(app) as client:
        set_active_config(app.state.db.connection(), runtime_id="scripted")

        res = client.post("/api/sessions", json=_TUTORIAL_SESSION_SETUP)
        assert res.status_code == 201, res.text
        session_id = res.json()["session_id"]

        client.post(f"/api/sessions/{session_id}/start")
        for _ in range(6):
            client.post(
                f"/api/sessions/{session_id}/turn",
                json={"content": "I'm excited to learn!"},
            )
        client.post(f"/api/sessions/{session_id}/end")

        debrief_res = client.post(f"/api/sessions/{session_id}/debrief")
        assert debrief_res.status_code == 200, debrief_res.text
        body = debrief_res.json()
        # Scripted debrief has the authored summary, not the fake boilerplate.
        assert body["summary"] == _DEBRIEF_RESPONSE["summary"]


def test_tutorial_stays_scripted_after_a_model_install_flips_the_active_runtime(tmp_config):
    """A tutorial in progress keeps its scripted runtime when an install completes mid-play.

    The "Start now" CTA runs the tutorial while a model downloads in the
    background; the setup-install pipeline calls set_active_config(llama_cpp)
    when that download finishes. The session must stay pinned to the runtime it
    was created with, or the rest of the tutorial — and its authored debrief —
    would be routed to the freshly installed model.
    """
    from convsim_core.app import create_app
    from convsim_core.services.model_manager_service import set_active_config
    from convsim_core.runtime.scripted import _DEBRIEF_RESPONSE
    from fastapi.testclient import TestClient

    app = create_app(tmp_config)
    with TestClient(app) as client:
        conn = app.state.db.connection()
        set_active_config(conn, runtime_id="scripted")

        res = client.post("/api/sessions", json=_TUTORIAL_SESSION_SETUP)
        assert res.status_code == 201, res.text
        session_id = res.json()["session_id"]
        client.post(f"/api/sessions/{session_id}/start")
        client.post(f"/api/sessions/{session_id}/turn", json={"content": "Hello!"})

        # The background install finishes: the pipeline flips the global runtime.
        set_active_config(conn, runtime_id="llama_cpp", model_id="/tmp/model.gguf")

        turn_res = client.post(
            f"/api/sessions/{session_id}/turn",
            json={"content": "Still here — what next?"},
        )
        assert turn_res.status_code == 200, turn_res.text
        npc_events = [e for e in turn_res.json()["events"] if e["event_type"] == "npc_turn"]
        assert npc_events, "No npc_turn event found in turn response"
        npc_text = npc_events[0]["payload"]["content"]
        assert "simulated npc" not in npc_text.lower(), (
            f"Tutorial fell back to app.state.runtime after the install: {npc_text!r}"
        )

        for _ in range(5):
            client.post(f"/api/sessions/{session_id}/turn", json={"content": "Go on."})
        client.post(f"/api/sessions/{session_id}/end")

        debrief_res = client.post(f"/api/sessions/{session_id}/debrief")
        assert debrief_res.status_code == 200, debrief_res.text
        assert debrief_res.json()["summary"] == _DEBRIEF_RESPONSE["summary"]
