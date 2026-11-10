# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RuntimeStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    ERROR = "error"


class RuntimeCapabilities(BaseModel):
    streaming: bool = False
    json_schema: bool = False
    grammar: bool = False
    tool_calling: bool = False
    embeddings: bool = False


class ModelInfo(BaseModel):
    id: str
    name: str
    size_category: Literal["small", "medium", "large"] | None = None
    context_length: int | None = None


class RuntimeHealth(BaseModel):
    runtime_id: str
    runtime_name: str
    status: RuntimeStatus
    model_id: str | None = None
    latency_ms: float | None = None
    message: str | None = None
    checked_at: str  # ISO 8601


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model_id: str | None = None
    max_tokens: int = 512
    temperature: float = 0.8
    #: Nucleus-sampling cut-off for this request, or None to leave it to the
    #: adapter's own setting (the llama.cpp adapter's CONVSIM_LLAMA_CPP_TOP_P,
    #: 0.95 unless set). Turns and debriefs set it, with the temperature, from
    #: the model registry when the model's entry declares one (issue #580); see
    #: SamplingDefaults. Only the llama.cpp adapter reads it, because only
    #: llama.cpp registry entries declare it.
    top_p: float | None = None
    json_schema: dict[str, Any] | None = None
    # 1-based game turn number; set by the turn pipeline so scripted adapters can
    # return the correct sequential response without parsing the system prompt.
    scripted_turn_index: int | None = None


class SamplingDefaults(BaseModel):
    """The sampling a model's registry entry declares for its requests (issue #580).

    ``model-registry/registry.yaml`` gives each llama.cpp model a
    ``temperature_default`` and a ``top_p_default``. A field is None when the
    entry declares no value, or when the model has no entry at all (a
    player-supplied GGUF, an Ollama model); the request then keeps its own
    default for it. Built by
    ``convsim_core.services.model_registry_service.active_model_sampling``.
    """

    model_config = ConfigDict(frozen=True)

    temperature: float | None = None
    top_p: float | None = None

    def request_fields(self) -> dict[str, float]:
        """The ChatRequest fields to set: only the ones the registry declared."""
        fields: dict[str, float] = {}
        if self.temperature is not None:
            fields["temperature"] = self.temperature
        if self.top_p is not None:
            fields["top_p"] = self.top_p
        return fields


class ChatToken(BaseModel):
    type: Literal["token"] = "token"
    text: str


class ChatProgress(BaseModel):
    """A progress signal the engine sent before or between tokens (issue #519).

    ``stage`` is one of the engine-side turn stages: ``waiting`` (the engine
    has accepted the request but not started reading — loading, or queued behind
    other work), ``reading`` (prompt evaluation; ``processed`` of ``total``
    prompt tokens are done, ``cached`` of them came from the engine's cache) or
    ``writing``. Counts are None when the engine did not report them. Adapters
    emit this only from a real signal; nothing here is estimated.
    """

    type: Literal["progress"] = "progress"
    stage: Literal["waiting", "reading", "writing"]
    processed: int | None = None
    total: int | None = None
    cached: int | None = None


class ChatTimings(BaseModel):
    """What the engine itself reported about one request (issue #519).

    Every field is None when the engine did not say. ``prompt_tokens`` is the
    whole prompt (``evaluated_tokens`` read this request plus ``cached_tokens``
    reused from the engine's cache); ``prompt_ms`` and ``generation_ms`` are the
    engine's own wall-clock figures for reading and writing, and the two rates
    are derived from them. ``load_ms`` is the model load the engine attributed
    to this request, where it reports one (Ollama does).
    """

    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    evaluated_tokens: int | None = None
    output_tokens: int | None = None
    prompt_ms: float | None = None
    generation_ms: float | None = None
    load_ms: float | None = None
    reading_tps: float | None = None
    writing_tps: float | None = None


FinishReason = Literal["stop", "length", "cancelled"]


class ChatFinal(BaseModel):
    type: Literal["final"] = "final"
    text: str
    model_id: str
    input_tokens: int
    output_tokens: int
    structured: dict[str, Any] | None = None
    # The engine's own account of the request, when it gave one (issue #519).
    timings: ChatTimings | None = None
    # Why generation ended: ``stop`` (the model finished), ``length`` (the
    # token cap cut it off), ``cancelled`` (the caller closed the stream), or
    # None when the engine did not say.
    finish_reason: FinishReason | None = None


#: Everything ``ChatRuntime.chat_stream`` may yield.
ChatChunk = ChatToken | ChatProgress | ChatFinal
