# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from convsim_core.runtime.base import ChatRuntime

_REGISTRY: dict[str, type] = {}


def register(runtime_id: str):
    """Class decorator that registers a ChatRuntime subclass under the given id."""

    def decorator(cls: type) -> type:
        _REGISTRY[runtime_id] = cls
        return cls

    return decorator


def build_runtime(runtime_id: str) -> "ChatRuntime":
    """Instantiate a registered runtime by id.

    Raises KeyError if the id is unknown.
    """
    if runtime_id not in _REGISTRY:
        available = sorted(_REGISTRY.keys())
        raise KeyError(
            f"Unknown runtime {runtime_id!r}. Available runtimes: {available}"
        )
    return _REGISTRY[runtime_id]()


def list_runtime_ids() -> list[str]:
    """Return sorted list of registered runtime ids."""
    return sorted(_REGISTRY.keys())
