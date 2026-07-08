# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from convsim_core.tts.base import TtsWorker

_REGISTRY: dict[str, type] = {}


def register_tts(worker_id: str):
    """Class decorator that registers a TtsWorker subclass under the given id."""

    def decorator(cls: type) -> type:
        _REGISTRY[worker_id] = cls
        return cls

    return decorator


def build_tts_worker(worker_id: str) -> "TtsWorker":
    """Instantiate a registered TTS worker by id.

    Raises KeyError if the id is unknown.
    """
    if worker_id not in _REGISTRY:
        available = sorted(_REGISTRY.keys())
        raise KeyError(
            f"Unknown TTS worker {worker_id!r}. Available workers: {available}"
        )
    return _REGISTRY[worker_id]()


def list_tts_worker_ids() -> list[str]:
    """Return sorted list of registered TTS worker ids."""
    return sorted(_REGISTRY.keys())
