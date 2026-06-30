# SPDX-License-Identifier: Apache-2.0
"""Ollama runtime adapter.

Communicates with a local Ollama server via its HTTP REST API using httpx.
The `ollama` PyPI package is intentionally not used here so that convsim_core
stays importable on machines where the Ollama SDK is not installed — and so
that the architecture guard (test_architecture.py) stays green.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import httpx

from convsim_core.runtime.base import ChatRuntime
from convsim_core.runtime.registry import register
from convsim_core.runtime.types import (
    ChatFinal,
    ChatRequest,
    ChatToken,
    ModelInfo,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeStatus,
)

_DEFAULT_BASE_URL = "http://127.0.0.1:11434"

_NOT_RUNNING_HINT = (
    "Ollama is not reachable at the configured endpoint. "
    "Start it with 'ollama serve', or install it from https://ollama.com. "
    "Override the endpoint with the CONVSIM_OLLAMA_BASE_URL environment variable."
)

_NO_MODELS_HINT = (
    "Ollama is running but has no models installed. "
    "Pull a compatible model with e.g. 'ollama pull llama3.2'."
)


def _size_category(size_bytes: int | None) -> str | None:
    """Map a raw byte count to a coarse size bucket."""
    if size_bytes is None:
        return None
    gib = size_bytes / (1024**3)
    if gib < 4:
        return "small"
    if gib < 12:
        return "medium"
    return "large"


def _map_model_info(raw: dict[str, Any]) -> ModelInfo:
    """Convert one entry from Ollama's /api/tags response into a ModelInfo."""
    name: str = raw.get("name", "")
    return ModelInfo(
        id=name,
        name=name,
        size_category=_size_category(raw.get("size")),
        # Ollama's tag list does not expose context length; leave it None.
        context_length=None,
    )


@register("ollama")
class OllamaChatRuntime(ChatRuntime):
    """ChatRuntime adapter that forwards requests to a local Ollama server.

    The base URL defaults to http://127.0.0.1:11434 and can be overridden
    via the CONVSIM_OLLAMA_BASE_URL environment variable or the *base_url*
    constructor argument.  A custom *client* may be injected for testing.
    """

    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        resolved = base_url or os.environ.get("CONVSIM_OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        self._base_url = resolved.rstrip("/")
        self._client = client or httpx.AsyncClient(base_url=self._base_url, timeout=60.0)

    # ------------------------------------------------------------------
    # ChatRuntime interface
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama (local)"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            streaming=True,
            json_schema=True,
            grammar=False,
            tool_calling=False,
            embeddings=False,
        )

    async def list_models(self) -> list[ModelInfo]:
        """Return models available in the local Ollama installation."""
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            return []
        data = resp.json()
        return [_map_model_info(m) for m in data.get("models", [])]

    def chat_stream(self, request: ChatRequest) -> AsyncGenerator[ChatToken | ChatFinal, None]:
        return self._stream(request)

    async def _stream(self, request: ChatRequest) -> AsyncGenerator[ChatToken | ChatFinal, None]:
        model_id = request.model_id
        if not model_id:
            models = await self.list_models()
            if not models:
                raise RuntimeError(_NO_MODELS_HINT)
            model_id = models[0].id

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": [
                {"role": msg.role, "content": msg.content} for msg in request.messages
            ],
            "stream": True,
            "options": {
                "num_predict": request.max_tokens,
                "temperature": request.temperature,
            },
        }
        if request.json_schema is not None:
            payload["format"] = request.json_schema

        full_text = ""
        input_tokens = 0
        output_tokens = 0

        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    content: str = chunk.get("message", {}).get("content", "")
                    done: bool = chunk.get("done", False)
                    if content and not done:
                        full_text += content
                        yield ChatToken(text=content)
                    if done:
                        input_tokens = chunk.get("prompt_eval_count", 0)
                        output_tokens = chunk.get("eval_count", 0)
        except httpx.ConnectError as exc:
            raise RuntimeError(_NOT_RUNNING_HINT) from exc

        structured: dict[str, Any] | None = None
        if request.json_schema is not None:
            try:
                structured = json.loads(full_text)
            except json.JSONDecodeError:
                structured = None

        yield ChatFinal(
            text=full_text,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            structured=structured,
        )

    async def health(self) -> RuntimeHealth:
        checked_at = datetime.now(timezone.utc).isoformat()
        t0 = datetime.now(timezone.utc)

        try:
            resp = await self._client.get("/")
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            return RuntimeHealth(
                runtime_id=self.id,
                runtime_name=self.display_name,
                status=RuntimeStatus.UNAVAILABLE,
                message=_NOT_RUNNING_HINT,
                checked_at=checked_at,
            )

        latency_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
        models = await self.list_models()
        if not models:
            return RuntimeHealth(
                runtime_id=self.id,
                runtime_name=self.display_name,
                status=RuntimeStatus.DEGRADED,
                latency_ms=latency_ms,
                message=_NO_MODELS_HINT,
                checked_at=checked_at,
            )

        return RuntimeHealth(
            runtime_id=self.id,
            runtime_name=self.display_name,
            status=RuntimeStatus.READY,
            model_id=models[0].id,
            latency_ms=latency_ms,
            checked_at=checked_at,
        )
