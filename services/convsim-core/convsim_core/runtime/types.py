# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


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
    json_schema: dict[str, Any] | None = None


class ChatToken(BaseModel):
    type: Literal["token"] = "token"
    text: str


class ChatFinal(BaseModel):
    type: Literal["final"] = "final"
    text: str
    model_id: str
    input_tokens: int
    output_tokens: int
    structured: dict[str, Any] | None = None
