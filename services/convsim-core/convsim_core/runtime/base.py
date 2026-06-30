# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from convsim_core.runtime.types import (
    ChatFinal,
    ChatRequest,
    ChatToken,
    ModelInfo,
    RuntimeCapabilities,
    RuntimeHealth,
)


class ChatRuntime(ABC):
    """Provider-agnostic interface for a local chat model runtime.

    The scenario engine depends only on this interface; concrete adapters
    (llama_cpp, ollama, …) are registered separately and never imported
    by scenario-engine code.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Stable machine-readable identifier (e.g. "llama_cpp", "fake")."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @property
    @abstractmethod
    def capabilities(self) -> RuntimeCapabilities:
        """Feature flags advertised by this runtime."""

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return models available through this runtime."""

    @abstractmethod
    def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatToken | ChatFinal]:
        """Return an async iterator that yields ChatToken chunks then a single ChatFinal."""

    @abstractmethod
    async def health(self) -> RuntimeHealth:
        """Return a point-in-time health snapshot for this runtime."""
