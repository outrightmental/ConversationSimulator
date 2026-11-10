# SPDX-License-Identifier: Apache-2.0
"""The engine's own account of a request reaches ChatFinal.timings (issue #519).

Fixtures under tests/fixtures/ are raw engine streams; a name starting with
``synthetic_`` was written from the engine's documented wire format rather than
captured (see tests/fixtures/README.md).
"""
from __future__ import annotations

from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from convsim_core.runtime.fake import FAKE_READING_TPS, FAKE_WRITING_TPS, FakeChatRuntime
from convsim_core.runtime.llama_cpp import LlamaCppConfig, LlamaCppRuntime
from convsim_core.runtime.ollama_adapter import OllamaChatRuntime
from convsim_core.runtime.scripted import ScriptedChatRuntime
from convsim_core.runtime.types import ChatFinal, ChatMessage, ChatProgress, ChatRequest, ChatToken

FIXTURES = Path(__file__).parent / "fixtures"

_EXTRA_FIELDS = ("stream_options", "return_progress", "timings_per_token")


def _fixture_lines(name: str) -> list[str]:
    return FIXTURES.joinpath(name).read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------
# llama-server (OpenAI-compatible SSE)
# ---------------------------------------------------------------------------


#: What a server that forbids unknown body fields answers (HTTP 422).
_EXTRAS_REJECTED_BODY = (
    b'{"detail":[{"loc":["body","return_progress"],"msg":"extra fields not permitted"}]}'
)
#: llama-server's own 400 for a prompt that does not fit the context: nothing
#: to do with the timing fields.
_CONTEXT_EXCEEDED_BODY = (
    b'{"error":{"code":400,"message":"the request exceeds the available context size, '
    b'try increasing it","type":"exceed_context_size_error"}}'
)


class _SseResponse:
    def __init__(self, lines: list[str], status_code: int = 200, body: bytes | None = None) -> None:
        self.status_code = status_code
        self._lines = lines
        self._body = _EXTRAS_REJECTED_BODY if body is None else body

    async def aiter_lines(self) -> AsyncGenerator[str, None]:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return self._body

    async def __aenter__(self) -> "_SseResponse":
        return self

    async def __aexit__(self, *_) -> None:
        pass


def _llama_client(*responses: _SseResponse) -> MagicMock:
    client = MagicMock()
    client.stream = MagicMock(side_effect=list(responses))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


async def _run_llama(runtime: LlamaCppRuntime, client: MagicMock, request: ChatRequest):
    chunks = []
    with patch("convsim_core.runtime.llama_cpp.httpx.AsyncClient", return_value=client):
        async for chunk in runtime.chat_stream(request):
            chunks.append(chunk)
    return chunks


def _request() -> ChatRequest:
    return ChatRequest(
        messages=[ChatMessage(role="user", content="hi")],
        json_schema={"type": "object"},
    )


@pytest.fixture()
def llama() -> LlamaCppRuntime:
    return LlamaCppRuntime(LlamaCppConfig(base_url="http://127.0.0.1:7356"))


@pytest.mark.asyncio
async def test_llama_turn_fixture_fills_every_timing_field(llama):
    client = _llama_client(_SseResponse(_fixture_lines("synthetic_llama_server_b9415_turn.sse")))
    chunks = await _run_llama(llama, client, _request())

    progress = [c for c in chunks if isinstance(c, ChatProgress)]
    assert [p.processed for p in progress] == [256, 1024, 2034]
    assert all(p.stage == "reading" and p.total == 2034 and p.cached == 0 for p in progress)
    # Progress arrives before any token.
    first_token_idx = next(i for i, c in enumerate(chunks) if isinstance(c, ChatToken))
    assert all(i < first_token_idx for i, c in enumerate(chunks) if isinstance(c, ChatProgress))

    final = chunks[-1]
    assert isinstance(final, ChatFinal)
    assert final.finish_reason == "stop"
    # The usage chunk has no choices and must not be skipped.
    assert final.input_tokens == 2034
    assert final.output_tokens == 61
    t = final.timings
    assert t is not None
    assert t.prompt_tokens == 2034
    assert t.cached_tokens == 0
    assert t.evaluated_tokens == 2034
    assert t.output_tokens == 61
    assert t.prompt_ms == 23400.0
    assert t.generation_ms == 9384.0
    assert t.reading_tps == 86.9
    assert t.writing_tps == 6.5
    assert final.structured is not None and final.structured["npc_emotion"] == "impressed"


@pytest.mark.asyncio
async def test_llama_length_fixture_reports_the_cap_and_the_cache(llama):
    client = _llama_client(_SseResponse(_fixture_lines("synthetic_llama_server_b9415_length.sse")))
    chunks = await _run_llama(llama, client, _request())
    final = chunks[-1]
    assert isinstance(final, ChatFinal)
    assert final.finish_reason == "length"
    assert final.timings is not None
    assert final.timings.cached_tokens == 1900
    assert final.timings.evaluated_tokens == 240
    assert final.timings.prompt_tokens == 2140
    progress = [c for c in chunks if isinstance(c, ChatProgress)]
    assert progress and progress[0].cached == 1900


@pytest.mark.asyncio
async def test_llama_server_that_reports_nothing_leaves_timings_null(llama):
    client = _llama_client(_SseResponse(_fixture_lines("synthetic_llama_server_no_timings.sse")))
    chunks = await _run_llama(llama, client, _request())
    assert not any(isinstance(c, ChatProgress) for c in chunks)
    final = chunks[-1]
    assert isinstance(final, ChatFinal)
    assert final.timings is None
    assert final.finish_reason == "stop"
    assert final.input_tokens == 0 and final.output_tokens == 0


@pytest.mark.asyncio
async def test_llama_request_asks_for_usage_progress_and_timings(llama):
    client = _llama_client(_SseResponse(_fixture_lines("synthetic_llama_server_no_timings.sse")))
    await _run_llama(llama, client, _request())
    payload = client.stream.call_args.kwargs["json"]
    assert payload["stream_options"] == {"include_usage": True}
    assert payload["return_progress"] is True
    assert payload["timings_per_token"] is True
    # Sampling is unchanged: the same fields are sent as before.
    assert payload["temperature"] == 0.8
    assert payload["max_tokens"] == 512
    assert payload["top_p"] == 0.95
    assert payload["repeat_penalty"] == 1.1
    assert payload["response_format"] == {"type": "json_object", "schema": {"type": "object"}}


@pytest.mark.asyncio
async def test_llama_server_rejecting_the_extra_fields_still_completes_the_turn(llama):
    rejected = _SseResponse([], status_code=422)
    accepted = _SseResponse(_fixture_lines("synthetic_llama_server_no_timings.sse"))
    client = _llama_client(rejected, accepted)
    chunks = await _run_llama(llama, client, _request())

    final = chunks[-1]
    assert isinstance(final, ChatFinal)
    assert final.text.startswith('{"npc_utterance"')
    assert final.timings is None
    assert llama.engine_extras_accepted is False

    first, second = (c.kwargs["json"] for c in client.stream.call_args_list)
    assert all(k in first for k in _EXTRA_FIELDS)
    assert not any(k in second for k in _EXTRA_FIELDS)
    # Everything the model actually sees is identical between the two attempts.
    for key in ("model", "messages", "temperature", "max_tokens", "top_p", "repeat_penalty", "response_format"):
        assert first[key] == second[key]


@pytest.mark.asyncio
async def test_llama_remembers_the_rejection_for_later_requests(llama):
    client = _llama_client(
        _SseResponse([], status_code=422),
        _SseResponse(_fixture_lines("synthetic_llama_server_no_timings.sse")),
        _SseResponse(_fixture_lines("synthetic_llama_server_no_timings.sse")),
    )
    await _run_llama(llama, client, _request())
    await _run_llama(llama, client, _request())
    assert client.stream.call_count == 3
    third = client.stream.call_args_list[2].kwargs["json"]
    assert not any(k in third for k in _EXTRA_FIELDS)


@pytest.mark.asyncio
async def test_llama_other_errors_still_raise(llama):
    client = _llama_client(_SseResponse([], status_code=500))
    with pytest.raises(ConnectionError, match="HTTP 500"):
        await _run_llama(llama, client, _request())


@pytest.mark.asyncio
async def test_a_400_about_the_request_itself_keeps_the_fields_on(llama):
    """llama-server answers 400 to any invalid request, context overflow included.

    Such a 400 is the ordinary error it always was: it is raised as before, the
    request is not re-sent, and the next request still asks for timings.
    """
    accepted = _SseResponse(_fixture_lines("synthetic_llama_server_no_timings.sse"))
    client = _llama_client(
        _SseResponse([], status_code=400, body=_CONTEXT_EXCEEDED_BODY),
        accepted,
    )
    with pytest.raises(ConnectionError, match="HTTP 400"):
        await _run_llama(llama, client, _request())

    assert llama.engine_extras_accepted is True
    assert client.stream.call_count == 1  # no re-send without the fields

    await _run_llama(llama, client, _request())
    second = client.stream.call_args_list[1].kwargs["json"]
    assert all(k in second for k in _EXTRA_FIELDS)


@pytest.mark.asyncio
async def test_a_400_that_names_one_of_the_fields_turns_them_off(llama):
    """A 400 counts as a rejection of the fields only when its error names one."""
    rejected = _SseResponse(
        [],
        status_code=400,
        body=b'{"error":{"code":400,"message":"unknown field: timings_per_token","type":"invalid_request_error"}}',
    )
    accepted = _SseResponse(_fixture_lines("synthetic_llama_server_no_timings.sse"))
    client = _llama_client(rejected, accepted)
    chunks = await _run_llama(llama, client, _request())

    assert isinstance(chunks[-1], ChatFinal)
    assert llama.engine_extras_accepted is False
    first, second = (c.kwargs["json"] for c in client.stream.call_args_list)
    assert all(k in first for k in _EXTRA_FIELDS)
    assert not any(k in second for k in _EXTRA_FIELDS)


# ---------------------------------------------------------------------------
# Ollama (NDJSON)
# ---------------------------------------------------------------------------


class _NdjsonContext:
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


def _ollama(lines: list[str]) -> OllamaChatRuntime:
    client = MagicMock()
    client.stream = MagicMock(return_value=_NdjsonContext(lines))
    return OllamaChatRuntime(client=client)


async def _run_ollama(lines: list[str]) -> ChatFinal:
    runtime = _ollama(lines)
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="hi")],
        model_id="qwen3:4b",
        json_schema={"type": "object"},
    )
    final = None
    async for chunk in runtime.chat_stream(request):
        if isinstance(chunk, ChatFinal):
            final = chunk
    assert final is not None
    return final


@pytest.mark.asyncio
async def test_ollama_with_cached_count_fills_the_same_fields():
    final = await _run_ollama(_fixture_lines("synthetic_ollama_0_34_turn.ndjson"))
    t = final.timings
    assert t is not None
    assert t.prompt_tokens == 2034
    assert t.cached_tokens == 1900
    assert t.evaluated_tokens == 134
    assert t.output_tokens == 61
    assert t.prompt_ms == 1540.0
    assert t.generation_ms == 9384.0
    assert t.load_ms == 120.0
    assert t.reading_tps == 87.01
    assert t.writing_tps == 6.5
    assert final.finish_reason == "stop"
    assert final.input_tokens == 2034 and final.output_tokens == 61


@pytest.mark.asyncio
async def test_ollama_without_cached_count_leaves_reading_figures_null():
    final = await _run_ollama(_fixture_lines("synthetic_ollama_0_33_turn.ndjson"))
    t = final.timings
    assert t is not None
    assert t.prompt_tokens == 2034
    assert t.cached_tokens is None
    assert t.evaluated_tokens is None
    assert t.reading_tps is None
    assert t.writing_tps == 6.5
    assert t.generation_ms == 9384.0


@pytest.mark.asyncio
async def test_ollama_done_chunk_with_no_figures_gives_no_timings():
    lines = [
        '{"model":"m","message":{"role":"assistant","content":"hi"},"done":false}',
        '{"model":"m","message":{"role":"assistant","content":""},"done":true}',
    ]
    final = await _run_ollama(lines)
    assert final.timings is None
    assert final.finish_reason is None


# ---------------------------------------------------------------------------
# Fake and scripted runtimes report deterministic figures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime", [FakeChatRuntime(), ScriptedChatRuntime()])
async def test_model_free_runtimes_emit_progress_then_tokens_then_timings(runtime):
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="one two three four")],
        json_schema={"type": "object"},
        scripted_turn_index=1,
    )
    chunks = []
    async for chunk in runtime.chat_stream(request):
        chunks.append(chunk)

    kinds = [type(c).__name__ for c in chunks]
    assert kinds[:2] == ["ChatProgress", "ChatProgress"]
    assert kinds[-1] == "ChatFinal"
    assert kinds.count("ChatFinal") == 1
    progress = [c for c in chunks if isinstance(c, ChatProgress)]
    assert progress[0].processed == 0 and progress[-1].processed == progress[-1].total == 4

    final = chunks[-1]
    assert isinstance(final, ChatFinal)
    assert final.finish_reason == "stop"
    t = final.timings
    assert t is not None
    assert t.prompt_tokens == 4 and t.evaluated_tokens == 4 and t.cached_tokens == 0
    assert t.output_tokens == final.output_tokens == len([c for c in chunks if isinstance(c, ChatToken)])
    assert t.reading_tps == FAKE_READING_TPS
    assert t.writing_tps == FAKE_WRITING_TPS
    assert t.prompt_ms == 4.0
    assert t.generation_ms == final.output_tokens * 2.0
