# SPDX-License-Identifier: Apache-2.0
"""Tests for the Ollama runtime adapter.  No real Ollama server is required."""
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import convsim_core.runtime  # noqa: F401 — ensures built-in adapters are registered
from convsim_core.runtime.ollama_adapter import (
    OllamaChatRuntime,
    _map_model_info,
    _size_category,
)
from convsim_core.runtime.registry import list_runtime_ids
from convsim_core.runtime.types import (
    ChatFinal,
    ChatMessage,
    ChatRequest,
    ChatToken,
    RuntimeStatus,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _get_response(json_data):
    """Mock a successful httpx GET response with a JSON body."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    return resp


class _StreamContext:
    """Async context manager that replays a fixed list of NDJSON lines."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self) -> None:
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _make_runtime(*, get_json=None, stream_lines=None, connect_error=False):
    """Build an OllamaChatRuntime with injected httpx mock."""
    client = MagicMock()
    if connect_error:
        client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    elif get_json is not None:
        client.get = AsyncMock(return_value=_get_response(get_json))
    if stream_lines is not None:
        client.stream = MagicMock(return_value=_StreamContext(stream_lines))
    return OllamaChatRuntime(client=client)


# ---------------------------------------------------------------------------
# Utility function unit tests
# ---------------------------------------------------------------------------


def test_size_category_small():
    assert _size_category(2 * 1024**3) == "small"


def test_size_category_medium():
    assert _size_category(6 * 1024**3) == "medium"


def test_size_category_large():
    assert _size_category(15 * 1024**3) == "large"


def test_size_category_none_input():
    assert _size_category(None) is None


def test_map_model_info_name_and_size():
    info = _map_model_info({"name": "llama3.2:latest", "size": 2_100_000_000})
    assert info.id == "llama3.2:latest"
    assert info.name == "llama3.2:latest"
    assert info.size_category == "small"
    assert info.context_length is None


def test_map_model_info_large_model():
    info = _map_model_info({"name": "llama2:70b", "size": 40 * 1024**3})
    assert info.size_category == "large"


def test_map_model_info_missing_size():
    info = _map_model_info({"name": "codellama:latest"})
    assert info.size_category is None


# ---------------------------------------------------------------------------
# list_models tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models_maps_api_response():
    runtime = _make_runtime(
        get_json={
            "models": [
                {"name": "llama3.2:latest", "size": 2_100_000_000},
                {"name": "mistral:7b", "size": 5_000_000_000},
            ]
        }
    )
    models = await runtime.list_models()
    assert len(models) == 2
    assert models[0].id == "llama3.2:latest"
    assert models[0].size_category == "small"
    assert models[1].id == "mistral:7b"
    assert models[1].size_category == "medium"


@pytest.mark.asyncio
async def test_list_models_empty_when_none_installed():
    runtime = _make_runtime(get_json={"models": []})
    assert await runtime.list_models() == []


@pytest.mark.asyncio
async def test_list_models_empty_on_connection_error():
    runtime = _make_runtime(connect_error=True)
    assert await runtime.list_models() == []


@pytest.mark.asyncio
async def test_list_models_empty_on_http_error():
    resp = MagicMock()
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
    )
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    runtime = OllamaChatRuntime(client=client)
    assert await runtime.list_models() == []


# ---------------------------------------------------------------------------
# chat_stream tests
# ---------------------------------------------------------------------------

_STREAM_LINES = [
    json.dumps(
        {"model": "llama3.2", "message": {"role": "assistant", "content": "Hello "}, "done": False}
    ),
    json.dumps(
        {"model": "llama3.2", "message": {"role": "assistant", "content": "world"}, "done": False}
    ),
    json.dumps(
        {
            "model": "llama3.2",
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "prompt_eval_count": 5,
            "eval_count": 2,
        }
    ),
]


@pytest.mark.asyncio
async def test_chat_stream_yields_tokens_then_final():
    runtime = _make_runtime(stream_lines=_STREAM_LINES)
    request = ChatRequest(
        model_id="llama3.2:latest",
        messages=[ChatMessage(role="user", content="hello")],
    )
    chunks = []
    async for chunk in runtime.chat_stream(request):
        chunks.append(chunk)

    tokens = [c for c in chunks if isinstance(c, ChatToken)]
    finals = [c for c in chunks if isinstance(c, ChatFinal)]

    assert len(tokens) == 2
    assert tokens[0].text == "Hello "
    assert tokens[1].text == "world"
    assert len(finals) == 1
    assert finals[0].text == "Hello world"
    assert finals[0].model_id == "llama3.2:latest"
    assert finals[0].input_tokens == 5
    assert finals[0].output_tokens == 2


@pytest.mark.asyncio
async def test_chat_stream_final_text_matches_joined_tokens():
    runtime = _make_runtime(stream_lines=_STREAM_LINES)
    request = ChatRequest(
        model_id="llama3.2:latest",
        messages=[ChatMessage(role="user", content="hello")],
    )
    token_texts = []
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatToken):
            token_texts.append(chunk.text)
        elif isinstance(chunk, ChatFinal):
            final = chunk

    assert final is not None
    assert "".join(token_texts) == final.text


@pytest.mark.asyncio
async def test_chat_stream_structured_output_when_schema_provided():
    payload = {"npc_utterance": "Hello!", "safety": {"status": "ok"}}
    structured_lines = [
        json.dumps(
            {
                "model": "llama3.2",
                "message": {"role": "assistant", "content": json.dumps(payload)},
                "done": False,
            }
        ),
        json.dumps(
            {
                "model": "llama3.2",
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "prompt_eval_count": 3,
                "eval_count": 5,
            }
        ),
    ]
    runtime = _make_runtime(stream_lines=structured_lines)
    request = ChatRequest(
        model_id="llama3.2:latest",
        messages=[ChatMessage(role="user", content="go")],
        json_schema={"type": "object"},
    )
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            final = chunk

    assert final is not None
    assert final.structured is not None
    assert final.structured["npc_utterance"] == "Hello!"
    assert "safety" in final.structured


@pytest.mark.asyncio
async def test_chat_stream_no_structured_output_without_schema():
    runtime = _make_runtime(stream_lines=_STREAM_LINES)
    request = ChatRequest(
        model_id="llama3.2:latest",
        messages=[ChatMessage(role="user", content="hello")],
    )
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            final = chunk

    assert final is not None
    assert final.structured is None


@pytest.mark.asyncio
async def test_chat_stream_raises_on_connection_error():
    client = MagicMock()
    client.stream = MagicMock(side_effect=httpx.ConnectError("refused"))
    runtime = OllamaChatRuntime(client=client)
    request = ChatRequest(
        model_id="llama3.2:latest",
        messages=[ChatMessage(role="user", content="hello")],
    )
    with pytest.raises(RuntimeError, match="[Oo]llama"):
        async for _ in runtime.chat_stream(request):
            pass


@pytest.mark.asyncio
async def test_chat_stream_raises_runtime_error_on_timeout():
    """A timeout during generation should raise RuntimeError, not TimeoutException."""
    client = MagicMock()
    client.stream = MagicMock(side_effect=httpx.TimeoutException("timed out"))
    runtime = OllamaChatRuntime(client=client)
    request = ChatRequest(
        model_id="llama3.2:latest",
        messages=[ChatMessage(role="user", content="hello")],
    )
    with pytest.raises(RuntimeError, match="[Oo]llama"):
        async for _ in runtime.chat_stream(request):
            pass


@pytest.mark.asyncio
async def test_chat_stream_raises_when_no_models_and_no_model_id():
    runtime = _make_runtime(get_json={"models": []})
    request = ChatRequest(messages=[ChatMessage(role="user", content="hello")])
    with pytest.raises(RuntimeError, match="[Mm]odel"):
        async for _ in runtime.chat_stream(request):
            pass


@pytest.mark.asyncio
async def test_chat_stream_raises_not_running_when_ollama_down_and_no_model_id():
    """When Ollama is unreachable *and* no model_id is supplied, the error must
    say the server is not reachable — not that it has no models installed."""
    runtime = _make_runtime(connect_error=True)
    request = ChatRequest(messages=[ChatMessage(role="user", content="hello")])
    with pytest.raises(RuntimeError, match="[Oo]llama"):
        async for _ in runtime.chat_stream(request):
            pass


@pytest.mark.asyncio
async def test_chat_stream_raises_runtime_error_on_404():
    """A 404 from Ollama (model not found) should raise RuntimeError, not HTTPStatusError."""

    class _Http404StreamContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def raise_for_status(self):
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            raise httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp)

        async def aiter_lines(self):
            return
            yield  # pragma: no cover — makes this a valid async generator

    client = MagicMock()
    client.stream = MagicMock(return_value=_Http404StreamContext())
    runtime = OllamaChatRuntime(client=client)
    request = ChatRequest(
        model_id="nonexistent:latest",
        messages=[ChatMessage(role="user", content="hello")],
    )
    with pytest.raises(RuntimeError, match="[Mm]odel"):
        async for _ in runtime.chat_stream(request):
            pass


@pytest.mark.asyncio
async def test_chat_stream_raises_runtime_error_on_server_error():
    """A 5xx from Ollama during generation should raise RuntimeError, not HTTPStatusError."""

    class _Http500StreamContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def raise_for_status(self):
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            raise httpx.HTTPStatusError("500", request=MagicMock(), response=mock_resp)

        async def aiter_lines(self):
            return
            yield  # pragma: no cover

    client = MagicMock()
    client.stream = MagicMock(return_value=_Http500StreamContext())
    runtime = OllamaChatRuntime(client=client)
    request = ChatRequest(
        model_id="llama3.2:latest",
        messages=[ChatMessage(role="user", content="hello")],
    )
    with pytest.raises(RuntimeError, match="500"):
        async for _ in runtime.chat_stream(request):
            pass


# ---------------------------------------------------------------------------
# health tests
# ---------------------------------------------------------------------------


def _dual_get_client(root_json, tags_json):
    """Build a mock client that routes GET / and GET /api/tags to different responses."""
    root_resp = _get_response(root_json)
    tags_resp = _get_response(tags_json)

    async def _get(path):
        if path == "/":
            return root_resp
        return tags_resp

    client = MagicMock()
    client.get = _get
    return client


@pytest.mark.asyncio
async def test_health_ready_when_running_with_models():
    client = _dual_get_client(
        root_json=None,
        tags_json={"models": [{"name": "llama3.2:latest", "size": 2_100_000_000}]},
    )
    runtime = OllamaChatRuntime(client=client)
    health = await runtime.health()

    assert health.status == RuntimeStatus.READY
    assert health.model_id == "llama3.2:latest"
    assert health.latency_ms is not None
    assert health.runtime_id == "ollama"
    assert health.checked_at


@pytest.mark.asyncio
async def test_health_unavailable_when_not_running():
    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    runtime = OllamaChatRuntime(client=client)
    health = await runtime.health()

    assert health.status == RuntimeStatus.UNAVAILABLE
    assert health.message is not None
    assert health.runtime_id == "ollama"


@pytest.mark.asyncio
async def test_health_degraded_when_no_models():
    client = _dual_get_client(root_json=None, tags_json={"models": []})
    runtime = OllamaChatRuntime(client=client)
    health = await runtime.health()

    assert health.status == RuntimeStatus.DEGRADED
    assert health.message is not None
    assert health.latency_ms is not None


# ---------------------------------------------------------------------------
# Adapter identity and capability tests
# ---------------------------------------------------------------------------


def test_ollama_runtime_id():
    runtime = OllamaChatRuntime(base_url="http://127.0.0.1:11434")
    assert runtime.id == "ollama"


def test_ollama_runtime_display_name_contains_ollama():
    runtime = OllamaChatRuntime(base_url="http://127.0.0.1:11434")
    assert "Ollama" in runtime.display_name


def test_ollama_runtime_capabilities():
    caps = OllamaChatRuntime(base_url="http://127.0.0.1:11434").capabilities
    assert caps.streaming is True
    assert caps.json_schema is True
    assert caps.grammar is False
    assert caps.tool_calling is False
    assert caps.embeddings is False


def test_ollama_is_registered():
    assert "ollama" in list_runtime_ids()


def test_runtime_ids_remain_sorted():
    ids = list_runtime_ids()
    assert ids == sorted(ids)
