# SPDX-License-Identifier: Apache-2.0
import pytest

from convsim_core.runtime.fake import FakeChatRuntime
from convsim_core.runtime.types import (
    ChatFinal,
    ChatMessage,
    ChatRequest,
    ChatToken,
    RuntimeStatus,
)


@pytest.fixture()
def runtime() -> FakeChatRuntime:
    return FakeChatRuntime()


@pytest.mark.asyncio
async def test_fake_runtime_id(runtime):
    assert runtime.id == "fake"


@pytest.mark.asyncio
async def test_fake_runtime_display_name(runtime):
    assert "Fake" in runtime.display_name


@pytest.mark.asyncio
async def test_fake_runtime_capabilities(runtime):
    caps = runtime.capabilities
    assert caps.streaming is True
    assert caps.json_schema is True
    assert caps.grammar is False
    assert caps.tool_calling is False
    assert caps.embeddings is False


@pytest.mark.asyncio
async def test_fake_runtime_list_models(runtime):
    models = await runtime.list_models()
    assert len(models) >= 1
    ids = [m.id for m in models]
    assert "fake-small" in ids


@pytest.mark.asyncio
async def test_fake_runtime_health_ready(runtime):
    h = await runtime.health()
    assert h.status == RuntimeStatus.READY
    assert h.runtime_id == "fake"
    assert h.checked_at  # non-empty ISO timestamp


@pytest.mark.asyncio
async def test_fake_runtime_streams_tokens_then_final(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hello")]
    )
    chunks = []
    async for chunk in runtime.chat_stream(request):
        chunks.append(chunk)

    tokens = [c for c in chunks if isinstance(c, ChatToken)]
    finals = [c for c in chunks if isinstance(c, ChatFinal)]

    assert len(tokens) > 0, "expected at least one ChatToken"
    assert len(finals) == 1, "expected exactly one ChatFinal"
    assert finals[0].type == "final"
    assert finals[0].text  # non-empty response text
    assert finals[0].model_id == "fake-small"
    assert finals[0].output_tokens == len(tokens)


@pytest.mark.asyncio
async def test_fake_runtime_final_text_matches_joined_tokens(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hello")]
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


@pytest.mark.asyncio
async def test_fake_runtime_structured_output_when_schema_provided(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="go")],
        json_schema={"type": "object"},
    )
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            final = chunk

    assert final is not None
    assert final.structured is not None
    assert "npc_utterance" in final.structured
    assert "safety" in final.structured


@pytest.mark.asyncio
async def test_fake_runtime_no_structured_output_without_schema(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hello")]
    )
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            final = chunk

    assert final is not None
    assert final.structured is None


@pytest.mark.asyncio
async def test_fake_runtime_model_id_uses_request_model(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hi")],
        model_id="fake-large",
    )
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            final = chunk

    assert final is not None
    assert final.model_id == "fake-large"
