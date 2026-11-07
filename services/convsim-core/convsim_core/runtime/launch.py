# SPDX-License-Identifier: Apache-2.0
"""Launch configuration for the managed llama-server (issue #523).

The engine's own defaults suit a shared inference server, not one player
having one conversation on an 8 GB machine. The log in issue #489 showed what
accepting them costs: four slots, the model's full trained context (40,960
tokens where the registry says 8,192), 6,759 MiB of projected memory for a
2.5 GB model, an 8 GiB prompt cache in host memory, and a single progress
update for a 22-second prompt because the default batch is 2,048 tokens.

This module is the one place that decides how the app launches the engine:

* :class:`LaunchConfig` — the frozen set of launch settings.
* :func:`resolve_launch_config` — the settings for a given model file, with
  the context size read from the model registry (``DEFAULT_CONTEXT_LENGTH``
  when the model has no registry row, e.g. a player-supplied GGUF).
* :func:`launch_env` — the ``LLAMA_ARG_*`` environment the engine is spawned
  with.
* :func:`context_length_for_command` — the ``--ctx-size`` to put on the
  command line, honouring an operator override in the environment.

Every place that starts the engine (``ensure_llama_sidecar_running``, the
install pipeline's warmup, ``POST /api/sidecar/start``) resolves its
configuration here and hands it to ``LlamaCppSidecar.start()``, so the three
cannot drift apart. Issue #529 turns this into a player-configurable launch
profile; the shape is kept small so that change stays mechanical.

Only an engine the app launches is affected. An external llama-server the
player runs by hand is configured by the player.

How the settings reach the engine
---------------------------------
``--ctx-size`` goes on the command line: every llama-server build has the
flag, and an engine too old to read ``LLAMA_ARG_*`` would otherwise load the
model's full trained context — the memory problem #489 describes. The other
settings are passed as ``LLAMA_ARG_*`` environment variables (llama.cpp's
``common/arg.cpp`` maps each flag to one: ``--parallel`` →
``LLAMA_ARG_N_PARALLEL``, ``--batch-size`` → ``LLAMA_ARG_BATCH``,
``--cache-ram`` → ``LLAMA_ARG_CACHE_RAM``, ``--ctx-size`` →
``LLAMA_ARG_CTX_SIZE``). An engine build that lacks one of them still starts:
an unknown flag is fatal, an unknown variable is ignored. All of them are
applied with ``setdefault``, exactly like ``LLAMA_ARG_REASONING`` before
them, so a value already in the app's environment is an operator override
that wins.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: Context size when the model has no registry row and no stated context (a
#: player-supplied GGUF), or when the lookup fails.
DEFAULT_CONTEXT_LENGTH = 8192
#: One player, one conversation: one slot. Each extra slot divides the context
#: between slots and multiplies the KV-cache memory.
DEFAULT_PARALLEL = 1
#: Prompt-processing batch, in tokens. About 3 s per batch at the CPU rate
#: seen in #489 (87 tokens/s), so progress and cancellation act at that
#: granularity instead of once per prompt.
DEFAULT_BATCH_SIZE = 256
#: Upper bound, in MiB, on the prompt cache the server keeps in host memory.
DEFAULT_CACHE_RAM_MIB = 1024

# llama.cpp environment names, as common/arg.cpp binds them to the flags.
ENV_CTX_SIZE = "LLAMA_ARG_CTX_SIZE"
ENV_N_PARALLEL = "LLAMA_ARG_N_PARALLEL"
ENV_BATCH = "LLAMA_ARG_BATCH"
ENV_CACHE_RAM = "LLAMA_ARG_CACHE_RAM"
ENV_REASONING = "LLAMA_ARG_REASONING"

#: Every variable the app may set on a launch, for logging and tests.
LAUNCH_ENV_VARS: tuple[str, ...] = (
    ENV_CTX_SIZE,
    ENV_N_PARALLEL,
    ENV_BATCH,
    ENV_CACHE_RAM,
    ENV_REASONING,
)


@dataclass(frozen=True)
class LaunchConfig:
    """How the app launches llama-server for one model.

    ``context_length`` becomes ``--ctx-size``; the other three are passed as
    ``LLAMA_ARG_*`` environment variables (see :func:`launch_env`).
    """

    context_length: int = DEFAULT_CONTEXT_LENGTH
    parallel: int = DEFAULT_PARALLEL
    batch_size: int = DEFAULT_BATCH_SIZE
    cache_ram_mib: int = DEFAULT_CACHE_RAM_MIB

    def __post_init__(self) -> None:
        for name, minimum in (
            ("context_length", 1),
            ("parallel", 1),
            ("batch_size", 1),
            ("cache_ram_mib", 0),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"LaunchConfig.{name} must be an int >= {minimum}, got {value!r}")

    def env_variables(self) -> dict[str, str]:
        """The ``LLAMA_ARG_*`` variables that carry the settings not on the command line."""
        return {
            ENV_N_PARALLEL: str(self.parallel),
            ENV_BATCH: str(self.batch_size),
            ENV_CACHE_RAM: str(self.cache_ram_mib),
        }


def launch_env(config: LaunchConfig, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the environment to spawn llama-server with.

    Starts from ``base`` (the current process environment when omitted) and
    applies the launch variables with ``setdefault``, so anything already set
    in the environment — an explicit operator override — wins. ``base`` is
    never mutated.

    ``LLAMA_ARG_REASONING=off`` rides along for the same reason as before:
    NPC turns need fast, in-character JSON, not visible chain-of-thought.
    Reasoning-family models otherwise spend hundreds of tokens thinking, blow
    the turn token budget (truncated JSON → fallback utterance) and multiply
    latency.
    """
    env = dict(os.environ if base is None else base)
    env.setdefault(ENV_REASONING, "off")
    for key, value in config.env_variables().items():
        env.setdefault(key, value)
    return env


def context_length_for_command(config: LaunchConfig, env: Mapping[str, str]) -> int | None:
    """The ``--ctx-size`` value for the command line, or None to leave it off.

    The context size is the one setting passed as a flag (every engine build
    has it). To keep the override rule uniform — "a ``LLAMA_ARG_*`` already in
    the environment wins" — the flag is omitted when the operator pinned
    ``LLAMA_ARG_CTX_SIZE``, because a flag would silently beat the variable.
    """
    if env.get(ENV_CTX_SIZE):
        return None
    return config.context_length


def resolve_launch_config(
    model_path: str | None,
    conn: sqlite3.Connection | None,
) -> LaunchConfig:
    """Build the launch configuration for the model at ``model_path``.

    The context size is the ``context_length`` of the model's registry row,
    found by mapping the file path back to its ``installed_models`` row and
    that row's ``registry_id``. A player-supplied GGUF (no registry row) uses
    the ``context_length_default`` the player stated when registering it, or
    ``DEFAULT_CONTEXT_LENGTH`` when they stated none. The lookup is cheap and
    never raises: any failure is logged and falls back to the default, because
    a bookkeeping problem must not stop the engine from starting.
    """
    return LaunchConfig(context_length=_context_length_for_model(model_path, conn))


# ── Registry lookup ───────────────────────────────────────────────────────────


def _normalise_path(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(os.path.expanduser(path))))


def _installed_row_for_path(conn: sqlite3.Connection, model_path: str) -> dict[str, Any] | None:
    """The newest ``installed_models`` row whose file is ``model_path``.

    Paths are compared after normalisation so a ``~``-form or a path with a
    ``.`` segment still matches the stored absolute path. The table holds a
    handful of rows, so scanning it is cheaper than second-guessing how each
    caller spelled the path.
    """
    wanted = _normalise_path(model_path)
    rows = conn.execute(
        "SELECT id, registry_id, file_path, context_length_default "
        "FROM installed_models WHERE file_path != '' ORDER BY id DESC"
    ).fetchall()
    for row in rows:
        stored = row["file_path"]
        if stored and _normalise_path(str(stored)) == wanted:
            return dict(row)
    return None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _context_length_for_model(model_path: str | None, conn: sqlite3.Connection | None) -> int:
    if not model_path or conn is None:
        return DEFAULT_CONTEXT_LENGTH
    try:
        row = _installed_row_for_path(conn, model_path)
        if row is None:
            logger.info(
                "launch config: %s is not an installed model; using the %d-token context",
                model_path, DEFAULT_CONTEXT_LENGTH,
            )
            return DEFAULT_CONTEXT_LENGTH

        registry_value: Any = None
        registry_id = row.get("registry_id")
        if registry_id:
            hit = conn.execute(
                "SELECT context_length FROM model_registry WHERE id = ? LIMIT 1",
                (registry_id,),
            ).fetchone()
            if hit is not None:
                registry_value = hit["context_length"]

        context_length = _positive_int(registry_value)
        if context_length is None:
            # A player-supplied GGUF carries the context the player stated, if any.
            context_length = _positive_int(row.get("context_length_default"))
        if context_length is None:
            logger.info(
                "launch config: no context length on record for %s; using %d",
                model_path, DEFAULT_CONTEXT_LENGTH,
            )
            return DEFAULT_CONTEXT_LENGTH
        return context_length
    except Exception as exc:  # noqa: BLE001 — never block an engine start on bookkeeping
        logger.warning(
            "launch config: context lookup for %s failed (%s); using %d",
            model_path, exc, DEFAULT_CONTEXT_LENGTH,
        )
        return DEFAULT_CONTEXT_LENGTH
