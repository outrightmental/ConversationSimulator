# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

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

_HEALTH_TIMEOUT = 5.0


class LlamaCppConfig(BaseSettings):
    """Configuration for the llama.cpp adapter, read from CONVSIM_LLAMA_CPP_* env vars."""

    model_config = SettingsConfigDict(
        env_prefix="CONVSIM_LLAMA_CPP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "http://127.0.0.1:7356"
    model_id: str | None = None
    context_length: int | None = None
    temperature: float = 0.8
    top_p: float = 0.95
    repeat_penalty: float = 1.1
    threads: int | None = None
    gpu_layers: int | None = None
    timeout: float = 30.0


@register("llama_cpp")
class LlamaCppRuntime(ChatRuntime):
    """ChatRuntime adapter for a local llama-server (OpenAI-compatible API).

    Connects to llama-server's /v1/chat/completions endpoint using server-sent
    events. Configuration is read from CONVSIM_LLAMA_CPP_* environment variables
    or supplied directly via LlamaCppConfig for testing.
    """

    def __init__(self, config: LlamaCppConfig | None = None) -> None:
        cfg = config or LlamaCppConfig()
        self._base_url = cfg.base_url.rstrip("/")
        self._model_id = cfg.model_id
        self._context_length = cfg.context_length
        self._temperature = cfg.temperature
        self._top_p = cfg.top_p
        self._repeat_penalty = cfg.repeat_penalty
        self._threads = cfg.threads
        self._gpu_layers = cfg.gpu_layers
        self._timeout = cfg.timeout

    @property
    def id(self) -> str:
        return "llama_cpp"

    @property
    def display_name(self) -> str:
        return "llama.cpp (local)"

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
        """Return models available from the local llama-server via GET /v1/models."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/v1/models")
                resp.raise_for_status()
                data = resp.json()
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot reach llama-server at {self._base_url}. "
                "Start it with: llama-server --port 7356 --model /path/to/model.gguf"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ConnectionError(
                f"llama-server returned HTTP {exc.response.status_code} for /v1/models"
            ) from exc
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"llama-server /v1/models timed out after {self._timeout}s. "
                "Increase CONVSIM_LLAMA_CPP_TIMEOUT or check server responsiveness."
            ) from exc

        return [
            ModelInfo(
                id=m.get("id", ""),
                name=m.get("id", ""),
                size_category=None,
                context_length=self._context_length,
            )
            for m in data.get("data", [])
            if m.get("id")
        ]

    def chat_stream(self, request: ChatRequest) -> AsyncGenerator[ChatToken | ChatFinal, None]:
        return self._stream(request)

    async def _stream(
        self, request: ChatRequest
    ) -> AsyncGenerator[ChatToken | ChatFinal, None]:
        model_id = request.model_id or self._model_id or "default"
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        payload: dict = {
            "model": model_id,
            "messages": messages,
            "stream": True,
            "temperature": self._temperature,
            "max_tokens": request.max_tokens,
            "top_p": self._top_p,
            "repeat_penalty": self._repeat_penalty,
        }

        if request.json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": request.json_schema,
                    "strict": False,
                },
            }

        full_text = ""
        input_tokens = 0
        output_tokens = 0

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                    headers={"Accept": "text/event-stream"},
                    timeout=self._timeout,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise ConnectionError(
                            f"llama-server returned HTTP {resp.status_code}: "
                            f"{body.decode(errors='replace')[:200]}"
                        )

                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or line == "data: [DONE]":
                            continue
                        if not line.startswith("data: "):
                            continue

                        raw = line[len("data: "):]
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        # Capture token usage from any chunk that includes it
                        usage = chunk.get("usage")
                        if usage:
                            input_tokens = usage.get("prompt_tokens", 0)
                            output_tokens = usage.get("completion_tokens", 0)

                        choices = chunk.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            full_text += content
                            yield ChatToken(text=content)

        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot reach llama-server at {self._base_url}. "
                "Start it with: llama-server --port 7356 --model /path/to/model.gguf"
            ) from exc
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"llama-server request timed out after {self._timeout}s. "
                "Increase CONVSIM_LLAMA_CPP_TIMEOUT or check server responsiveness."
            ) from exc

        structured = None
        if request.json_schema is not None and full_text:
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

        try:
            t0 = datetime.now(timezone.utc)
            async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT) as client:
                resp = await client.get(f"{self._base_url}/health")
            latency_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000

            if resp.status_code == 200:
                status = RuntimeStatus.READY
                message = None
            elif resp.status_code == 503:
                status = RuntimeStatus.STARTING
                message = "llama-server is loading the model"
            else:
                status = RuntimeStatus.DEGRADED
                message = f"llama-server /health returned HTTP {resp.status_code}"

        except httpx.ConnectError:
            return RuntimeHealth(
                runtime_id=self.id,
                runtime_name=self.display_name,
                status=RuntimeStatus.UNAVAILABLE,
                message=(
                    f"Cannot connect to llama-server at {self._base_url}. "
                    "Start it with: llama-server --port 7356 --model /path/to/model.gguf"
                ),
                checked_at=checked_at,
            )
        except httpx.TimeoutException:
            return RuntimeHealth(
                runtime_id=self.id,
                runtime_name=self.display_name,
                status=RuntimeStatus.DEGRADED,
                message=f"Health check timed out after {_HEALTH_TIMEOUT}s",
                checked_at=checked_at,
            )

        return RuntimeHealth(
            runtime_id=self.id,
            runtime_name=self.display_name,
            status=status,
            model_id=self._model_id,
            latency_ms=latency_ms,
            message=message,
            checked_at=checked_at,
        )
