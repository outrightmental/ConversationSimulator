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
