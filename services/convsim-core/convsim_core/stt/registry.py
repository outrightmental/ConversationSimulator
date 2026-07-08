# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from convsim_core.stt.base import SttWorker

_REGISTRY: dict[str, type] = {}


def register_stt(worker_id: str):
    """Class decorator that registers an SttWorker subclass under the given id."""

    def decorator(cls: type) -> type:
        _REGISTRY[worker_id] = cls
        return cls

    return decorator


def build_stt_worker(worker_id: str) -> "SttWorker":
    """Instantiate a registered STT worker by id.

    Raises KeyError if the id is unknown.
    """
    if worker_id not in _REGISTRY:
        available = sorted(_REGISTRY.keys())
        raise KeyError(
            f"Unknown STT worker {worker_id!r}. Available workers: {available}"
        )
    return _REGISTRY[worker_id]()


def list_stt_worker_ids() -> list[str]:
    """Return sorted list of registered STT worker ids."""
    return sorted(_REGISTRY.keys())
