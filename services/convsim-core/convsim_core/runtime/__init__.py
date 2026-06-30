# SPDX-License-Identifier: Apache-2.0
"""ChatRuntime abstraction and built-in runtime implementations.

Import this package to ensure all built-in runtimes are registered before
calling build_runtime().
"""

from convsim_core.runtime.base import ChatRuntime
from convsim_core.runtime.registry import build_runtime, list_runtime_ids, register
from convsim_core.runtime.types import (
    ChatFinal,
    ChatMessage,
    ChatRequest,
    ChatToken,
    ModelInfo,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeStatus,
)

# Import built-in adapters to trigger their @register() decorators.
import convsim_core.runtime.fake  # noqa: F401, E402
import convsim_core.runtime.llama_cpp  # noqa: F401, E402

__all__ = [
    "ChatRuntime",
    "ChatFinal",
    "ChatMessage",
    "ChatRequest",
    "ChatToken",
    "ModelInfo",
    "RuntimeCapabilities",
    "RuntimeHealth",
    "RuntimeStatus",
    "build_runtime",
    "list_runtime_ids",
    "register",
]
