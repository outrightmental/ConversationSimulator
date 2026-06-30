# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the llama.cpp OpenAI-compatible runtime adapter.

All HTTP calls are intercepted by in-process mocks; no real llama-server or
model weights are required.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from convsim_core.runtime.llama_cpp import LlamaCppConfig, LlamaCppRuntime
from convsim_core.runtime.types import (
    ChatFinal,
    ChatMessage,
    ChatRequest,
    ChatToken,
    RuntimeStatus,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_get_response(status_code: int = 200, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=body or {})
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    return resp


class _MockStreamResponse:
    """Async context manager that yields pre-scripted SSE lines."""

    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self.status_code = status_code
        self._lines = lines

    async def aiter_lines(self) -> AsyncGenerator[str, None]:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b"error body"

    async def __aenter__(self) -> "_MockStreamResponse":
        return self

    async def __aexit__(self, *_) -> None:
        pass


def _sse_lines(*chunks: dict, done: bool = True) -> list[str]:
    """Build SSE lines from a sequence of chunk dicts."""
    lines = [f"data: {json.dumps(c)}" for c in chunks]
    if done:
        lines.append("data: [DONE]")
    return lines


def _token_chunk(content: str, usage: dict | None = None) -> dict:
    chunk: dict = {
        "choices": [{"delta": {"content": content}, "finish_reason": None}],
    }
    if usage:
        chunk["usage"] = usage
    return chunk


def _final_chunk(usage: dict | None = None) -> dict:
    chunk: dict = {
        "choices": [{"delta": {}, "finish_reason": "stop"}],
    }
    if usage:
        chunk["usage"] = usage
    return chunk


def _mock_client(
    get_response: MagicMock | None = None,
    stream_response: _MockStreamResponse | None = None,
    connect_error: bool = False,
    timeout_error: bool = False,
) -> MagicMock:
    """Return a mock AsyncClient context manager."""
    client = MagicMock()

    async def _get(url, **kwargs):
        if connect_error:
            raise httpx.ConnectError("refused")
        if timeout_error:
            raise httpx.TimeoutException("timed out")
        return get_response

    client.get = _get
    client.stream = MagicMock(return_value=stream_response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def runtime() -> LlamaCppRuntime:
    return LlamaCppRuntime(LlamaCppConfig(base_url="http://127.0.0.1:7356"))


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

def test_runtime_id(runtime):
    assert runtime.id == "llama_cpp"


def test_runtime_display_name(runtime):
    assert "llama" in runtime.display_name.lower()


def test_runtime_capabilities(runtime):
    caps = runtime.capabilities
    assert caps.streaming is True
    assert caps.json_schema is True
    assert caps.grammar is False
    assert caps.tool_calling is False
    assert caps.embeddings is False


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_models_returns_server_models(runtime):
    body = {"data": [{"id": "my-model.gguf"}, {"id": "other-model.gguf"}]}
    client = _mock_client(get_response=_make_get_response(200, body))

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        models = await runtime.list_models()

    assert len(models) == 2
    ids = [m.id for m in models]
    assert "my-model.gguf" in ids
    assert "other-model.gguf" in ids


@pytest.mark.asyncio
async def test_list_models_connect_error_raises_connection_error(runtime):
    client = _mock_client(connect_error=True)

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        with pytest.raises(ConnectionError, match="llama-server"):
            await runtime.list_models()


@pytest.mark.asyncio
async def test_list_models_http_error_raises_connection_error(runtime):
    resp = _make_get_response(500)
    client = _mock_client(get_response=resp)

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        with pytest.raises(ConnectionError, match="HTTP 500"):
            await runtime.list_models()


@pytest.mark.asyncio
async def test_list_models_timeout_raises_timeout_error(runtime):
    client = _mock_client(timeout_error=True)

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        with pytest.raises(TimeoutError, match="timed out"):
            await runtime.list_models()


# ---------------------------------------------------------------------------
# chat_stream — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_stream_yields_tokens_then_final(runtime):
    lines = _sse_lines(
        _token_chunk("Hello"),
        _token_chunk(", "),
        _token_chunk("world"),
        _final_chunk(usage={"prompt_tokens": 5, "completion_tokens": 3}),
    )
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    chunks = []
    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for chunk in runtime.chat_stream(request):
            chunks.append(chunk)

    tokens = [c for c in chunks if isinstance(c, ChatToken)]
    finals = [c for c in chunks if isinstance(c, ChatFinal)]

    assert len(tokens) == 3
    assert len(finals) == 1
    assert finals[0].text == "Hello, world"
    assert finals[0].output_tokens == 3
    assert finals[0].input_tokens == 5


@pytest.mark.asyncio
async def test_chat_stream_final_text_joins_tokens(runtime):
    lines = _sse_lines(
        _token_chunk("foo"),
        _token_chunk("bar"),
        _final_chunk(),
    )
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(messages=[ChatMessage(role="user", content="x")])

    token_texts: list[str] = []
    final = None
    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for chunk in runtime.chat_stream(request):
            if isinstance(chunk, ChatToken):
                token_texts.append(chunk.text)
            else:
                final = chunk

    assert final is not None
    assert "".join(token_texts) == final.text


@pytest.mark.asyncio
async def test_chat_stream_uses_request_model_id(runtime):
    lines = _sse_lines(_token_chunk("ok"), _final_chunk())
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hi")],
        model_id="custom-model.gguf",
    )

    final = None
    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for chunk in runtime.chat_stream(request):
            if isinstance(chunk, ChatFinal):
                final = chunk

    assert final is not None
    assert final.model_id == "custom-model.gguf"


@pytest.mark.asyncio
async def test_chat_stream_uses_request_temperature(runtime):
    lines = _sse_lines(_token_chunk("ok"), _final_chunk())
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(messages=[ChatMessage(role="user", content="hi")], temperature=0.3)

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for _ in runtime.chat_stream(request):
            pass

    sent_payload = client.stream.call_args.kwargs["json"]
    assert sent_payload["temperature"] == 0.3


@pytest.mark.asyncio
async def test_chat_stream_structured_output_when_schema_provided(runtime):
    structured_obj = {"answer": 42}
    lines = _sse_lines(_token_chunk(json.dumps(structured_obj)), _final_chunk())
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="go")],
        json_schema={"type": "object"},
    )

    final = None
    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for chunk in runtime.chat_stream(request):
            if isinstance(chunk, ChatFinal):
                final = chunk

    assert final is not None
    assert final.structured == structured_obj


@pytest.mark.asyncio
async def test_chat_stream_no_structured_without_schema(runtime):
    lines = _sse_lines(_token_chunk("plain text"), _final_chunk())
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    final = None
    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for chunk in runtime.chat_stream(request):
            if isinstance(chunk, ChatFinal):
                final = chunk

    assert final is not None
    assert final.structured is None


@pytest.mark.asyncio
async def test_chat_stream_sends_response_format_hint_when_schema_provided(runtime):
    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
    lines = _sse_lines(_token_chunk('{"answer": 1}'), _final_chunk())
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="go")],
        json_schema=schema,
    )

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for _ in runtime.chat_stream(request):
            pass

    sent_payload = client.stream.call_args.kwargs["json"]
    assert "response_format" in sent_payload
    rf = sent_payload["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["schema"] == schema


@pytest.mark.asyncio
async def test_chat_stream_omits_response_format_when_no_schema(runtime):
    lines = _sse_lines(_token_chunk("ok"), _final_chunk())
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for _ in runtime.chat_stream(request):
            pass

    sent_payload = client.stream.call_args.kwargs["json"]
    assert "response_format" not in sent_payload


# ---------------------------------------------------------------------------
# chat_stream — malformed / edge-case stream input
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_stream_skips_malformed_json_lines(runtime):
    lines = [
        "data: not-json",
        "data: [DONE]",
    ]
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    chunks = []
    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for chunk in runtime.chat_stream(request):
            chunks.append(chunk)

    # Should still yield a ChatFinal with empty text — no crash
    finals = [c for c in chunks if isinstance(c, ChatFinal)]
    assert len(finals) == 1
    assert finals[0].text == ""


@pytest.mark.asyncio
async def test_chat_stream_skips_non_data_lines(runtime):
    lines = [
        ": keep-alive",
        "",
        "data: [DONE]",
    ]
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    chunks = []
    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for chunk in runtime.chat_stream(request):
            chunks.append(chunk)

    assert len([c for c in chunks if isinstance(c, ChatFinal)]) == 1


@pytest.mark.asyncio
async def test_chat_stream_non_200_raises_connection_error(runtime):
    stream = _MockStreamResponse([], status_code=503)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        with pytest.raises(ConnectionError, match="HTTP 503"):
            async for _ in runtime.chat_stream(request):
                pass


# ---------------------------------------------------------------------------
# chat_stream — error paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_stream_connect_error_raises_connection_error(runtime):
    class _ConnectErrorStream:
        async def __aenter__(self):
            raise httpx.ConnectError("refused")

        async def __aexit__(self, *_):
            pass

    client = MagicMock()
    client.stream = MagicMock(return_value=_ConnectErrorStream())
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    request = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        with pytest.raises(ConnectionError, match="llama-server"):
            async for _ in runtime.chat_stream(request):
                pass


@pytest.mark.asyncio
async def test_chat_stream_timeout_raises_timeout_error(runtime):
    class _TimeoutStream:
        async def __aenter__(self):
            raise httpx.TimeoutException("timed out")

        async def __aexit__(self, *_):
            pass

    client = MagicMock()
    client.stream = MagicMock(return_value=_TimeoutStream())
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    request = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        with pytest.raises(TimeoutError, match="timed out"):
            async for _ in runtime.chat_stream(request):
                pass


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_ready_when_server_returns_200(runtime):
    client = _mock_client(get_response=_make_get_response(200))

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        h = await runtime.health()

    assert h.status == RuntimeStatus.READY
    assert h.runtime_id == "llama_cpp"
    assert h.latency_ms is not None
    assert h.latency_ms >= 0
    assert h.checked_at  # non-empty ISO timestamp


@pytest.mark.asyncio
async def test_health_starting_when_server_returns_503(runtime):
    client = _mock_client(get_response=_make_get_response(503))

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        h = await runtime.health()

    assert h.status == RuntimeStatus.STARTING
    assert "loading" in (h.message or "").lower()


@pytest.mark.asyncio
async def test_health_degraded_on_unexpected_status(runtime):
    client = _mock_client(get_response=_make_get_response(500))

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        h = await runtime.health()

    assert h.status == RuntimeStatus.DEGRADED
    assert "500" in (h.message or "")


@pytest.mark.asyncio
async def test_health_unavailable_on_connect_error(runtime):
    client = _mock_client(connect_error=True)

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        h = await runtime.health()

    assert h.status == RuntimeStatus.UNAVAILABLE
    assert h.message is not None
    assert "llama-server" in h.message


@pytest.mark.asyncio
async def test_health_degraded_on_timeout(runtime):
    client = _mock_client(timeout_error=True)

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        h = await runtime.health()

    assert h.status == RuntimeStatus.DEGRADED
    assert h.message is not None
    assert "timed out" in h.message.lower()


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

def test_llama_cpp_is_registered():
    from convsim_core.runtime.registry import list_runtime_ids
    assert "llama_cpp" in list_runtime_ids()


def test_build_runtime_returns_llama_cpp_instance():
    from convsim_core.runtime.registry import build_runtime
    rt = build_runtime("llama_cpp")
    assert isinstance(rt, LlamaCppRuntime)


def test_runtime_ids_remain_sorted():
    from convsim_core.runtime.registry import list_runtime_ids
    ids = list_runtime_ids()
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# json_schema_enabled config flag
# ---------------------------------------------------------------------------

def test_runtime_capabilities_json_schema_disabled():
    rt = LlamaCppRuntime(LlamaCppConfig(base_url="http://127.0.0.1:7356", json_schema_enabled=False))
    assert rt.capabilities.json_schema is False


def test_runtime_capabilities_json_schema_enabled_by_default(runtime):
    assert runtime.capabilities.json_schema is True


@pytest.mark.asyncio
async def test_chat_stream_omits_response_format_when_json_schema_disabled():
    rt = LlamaCppRuntime(LlamaCppConfig(base_url="http://127.0.0.1:7356", json_schema_enabled=False))
    lines = _sse_lines(_token_chunk('{"x": 1}'), _final_chunk())
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="go")],
        json_schema={"type": "object"},
    )

    final = None
    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for chunk in rt.chat_stream(request):
            if isinstance(chunk, ChatFinal):
                final = chunk

    sent_payload = client.stream.call_args.kwargs["json"]
    assert "response_format" not in sent_payload
    assert final is not None
    assert final.structured is None


# ---------------------------------------------------------------------------
# Config parameters forwarded in payload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_stream_sends_top_p_and_repeat_penalty_from_config():
    cfg = LlamaCppConfig(base_url="http://127.0.0.1:7356", top_p=0.7, repeat_penalty=1.3)
    rt = LlamaCppRuntime(cfg)
    lines = _sse_lines(_token_chunk("ok"), _final_chunk())
    stream = _MockStreamResponse(lines)
    client = _mock_client(stream_response=stream)
    request = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for _ in rt.chat_stream(request):
            pass

    sent_payload = client.stream.call_args.kwargs["json"]
    assert sent_payload["top_p"] == 0.7
    assert sent_payload["repeat_penalty"] == 1.3
