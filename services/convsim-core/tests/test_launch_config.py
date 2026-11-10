# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the managed engine's launch configuration (issue #523).

The engine's defaults are wrong for one player having one conversation: four
slots, the model's full trained context, an 8 GiB prompt cache and 2,048-token
batches (the log in issue #489). These tests pin the configuration the app
launches with instead — context size from the registry, one slot, 256-token
batches, a 1 GiB cache bound — and how it reaches the engine: ``--ctx-size`` on
the command line, the rest as ``LLAMA_ARG_*`` variables applied with
``setdefault`` so an operator's own value wins.
"""
from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from convsim_core.runtime.launch import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CACHE_RAM_MIB,
    DEFAULT_CONTEXT_LENGTH,
    DEFAULT_PARALLEL,
    LAUNCH_ENV_VARS,
    LaunchConfig,
    context_length_for_command,
    launch_env,
    registry_id_for_model_path,
    resolve_launch_config,
)
from convsim_core.runtime.sidecar import build_command
from convsim_core.services.model_manager_service import register_user_gguf
from convsim_core.storage.database import Database


@pytest.fixture()
def clean_launch_env(monkeypatch):
    """Make sure no LLAMA_ARG_* from the developer's shell leaks into a test."""
    for name in LAUNCH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def db(tmp_path):
    database = Database.open(str(tmp_path / "db"))
    try:
        yield database
    finally:
        database.close()


def _seed_registry_model(
    conn: sqlite3.Connection, *, registry_id: str, context_length: int | None, file_path: str
) -> None:
    """A registry row plus the installed-model row that points at ``file_path``."""
    conn.execute(
        "INSERT INTO model_registry (id, name, provider, context_length) VALUES (?, ?, ?, ?)",
        (registry_id, "Registry Model", "test", context_length),
    )
    conn.execute(
        "INSERT INTO installed_models (registry_id, filename, file_path, install_status) "
        "VALUES (?, ?, ?, 'ready')",
        (registry_id, Path(file_path).name, file_path),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# LaunchConfig
# ---------------------------------------------------------------------------


def test_defaults_are_one_slot_explicit_context_small_batches_bounded_cache():
    config = LaunchConfig()
    assert config.context_length == DEFAULT_CONTEXT_LENGTH == 8192
    assert config.parallel == DEFAULT_PARALLEL == 1
    assert config.batch_size == DEFAULT_BATCH_SIZE == 256
    assert config.cache_ram_mib == DEFAULT_CACHE_RAM_MIB == 1024


def test_launch_config_is_frozen_and_comparable():
    config = LaunchConfig(context_length=4096)
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.context_length = 1  # type: ignore[misc]
    assert config == LaunchConfig(context_length=4096)
    assert config != LaunchConfig()


@pytest.mark.parametrize(
    "field, bad",
    [
        ("context_length", 0),
        ("context_length", -1),
        ("parallel", 0),
        ("batch_size", 0),
        ("cache_ram_mib", -1),
        ("context_length", "8192"),
        ("parallel", True),
    ],
)
def test_launch_config_rejects_values_the_engine_would_choke_on(field, bad):
    with pytest.raises(ValueError):
        LaunchConfig(**{field: bad})


def test_cache_ram_zero_is_allowed():
    # llama-server accepts 0 (no host prompt cache); only negatives are refused.
    assert LaunchConfig(cache_ram_mib=0).cache_ram_mib == 0


# ---------------------------------------------------------------------------
# resolve_launch_config — context size from the registry
# ---------------------------------------------------------------------------


def test_registry_model_gets_its_registry_context_length(db, tmp_path):
    conn = db.connection()
    model = tmp_path / "registry-model.gguf"
    model.write_bytes(b"gguf")
    _seed_registry_model(conn, registry_id="reg-model", context_length=6144, file_path=str(model))

    config = resolve_launch_config(str(model), conn)

    assert config == LaunchConfig(context_length=6144)
    # Only the context differs from the defaults; the rest is policy, not per-model.
    assert (config.parallel, config.batch_size, config.cache_ram_mib) == (1, 256, 1024)


def test_player_supplied_model_without_registry_row_gets_8192(db, tmp_path):
    conn = db.connection()
    model = tmp_path / "my-own.gguf"
    model.write_bytes(b"gguf")
    register_user_gguf(conn, path=str(model))  # no context stated

    assert resolve_launch_config(str(model), conn) == LaunchConfig(context_length=8192)


def test_player_supplied_model_with_stated_context_uses_it(db, tmp_path):
    conn = db.connection()
    model = tmp_path / "my-own.gguf"
    model.write_bytes(b"gguf")
    register_user_gguf(conn, path=str(model), context_length_default=4096)

    assert resolve_launch_config(str(model), conn).context_length == 4096


def test_registry_row_without_context_length_falls_back_to_8192(db, tmp_path):
    conn = db.connection()
    model = tmp_path / "registry-model.gguf"
    model.write_bytes(b"gguf")
    _seed_registry_model(conn, registry_id="reg-model", context_length=None, file_path=str(model))

    assert resolve_launch_config(str(model), conn).context_length == 8192


def test_unusable_registry_context_length_falls_back_to_8192(db, tmp_path):
    conn = db.connection()
    model = tmp_path / "registry-model.gguf"
    model.write_bytes(b"gguf")
    _seed_registry_model(conn, registry_id="reg-model", context_length=0, file_path=str(model))

    assert resolve_launch_config(str(model), conn).context_length == 8192


def test_unknown_path_gets_8192(db, tmp_path):
    assert resolve_launch_config(str(tmp_path / "never-installed.gguf"), db.connection()) == LaunchConfig()


def test_no_connection_or_no_path_gets_defaults(db):
    assert resolve_launch_config("/some/model.gguf", None) == LaunchConfig()
    assert resolve_launch_config(None, db.connection()) == LaunchConfig()
    assert resolve_launch_config("", db.connection()) == LaunchConfig()


def test_path_is_matched_after_normalisation(db, tmp_path):
    """The start sites spell the path differently (``~``, ``.`` segments);
    all of them must map back to the same installed-model row."""
    conn = db.connection()
    model = tmp_path / "registry-model.gguf"
    model.write_bytes(b"gguf")
    _seed_registry_model(conn, registry_id="reg-model", context_length=6144, file_path=str(model))

    dotted = str(tmp_path / "." / "registry-model.gguf")
    assert resolve_launch_config(dotted, conn).context_length == 6144


def test_newest_installed_row_for_a_path_wins(db, tmp_path):
    """A re-install of the same file leaves an older row behind; the newest
    describes the file that is actually there."""
    conn = db.connection()
    model = tmp_path / "registry-model.gguf"
    model.write_bytes(b"gguf")
    _seed_registry_model(conn, registry_id="old-row", context_length=2048, file_path=str(model))
    _seed_registry_model(conn, registry_id="new-row", context_length=6144, file_path=str(model))

    assert resolve_launch_config(str(model), conn).context_length == 6144


def test_lookup_failure_never_blocks_a_start(caplog):
    """A broken table must not stop the engine: log and fall back to 8192."""
    conn = MagicMock()
    conn.execute.side_effect = sqlite3.OperationalError("no such table: installed_models")

    with caplog.at_level("WARNING"):
        config = resolve_launch_config("/models/m.gguf", conn)

    assert config == LaunchConfig()
    assert any("launch config" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# registry_id_for_model_path — the same lookup, for a turn's sampling (#580)
# ---------------------------------------------------------------------------


def test_registry_id_for_model_path_maps_a_file_as_the_launch_does(db, tmp_path):
    conn = db.connection()
    model = tmp_path / "registry-model.gguf"
    model.write_bytes(b"gguf")
    _seed_registry_model(conn, registry_id="old-row", context_length=2048, file_path=str(model))
    _seed_registry_model(conn, registry_id="reg-model", context_length=6144, file_path=str(model))
    mine = tmp_path / "my-own.gguf"
    mine.write_bytes(b"gguf")
    register_user_gguf(conn, path=str(mine))

    # The newest row for the file, matched after normalisation.
    assert registry_id_for_model_path(str(model), conn) == "reg-model"
    assert registry_id_for_model_path(str(tmp_path / "." / "registry-model.gguf"), conn) == "reg-model"
    # A player-supplied GGUF, an unknown file, and no file or connection have none.
    assert registry_id_for_model_path(str(mine), conn) is None
    assert registry_id_for_model_path(str(tmp_path / "never-installed.gguf"), conn) is None
    assert registry_id_for_model_path(None, conn) is None
    assert registry_id_for_model_path(str(model), None) is None


def test_registry_id_for_model_path_never_raises(caplog):
    conn = MagicMock()
    conn.execute.side_effect = sqlite3.OperationalError("no such table: installed_models")

    with caplog.at_level("WARNING"):
        assert registry_id_for_model_path("/models/m.gguf", conn) is None

    assert any("registry lookup" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# launch_env — LLAMA_ARG_* with setdefault
# ---------------------------------------------------------------------------


def test_launch_env_carries_the_settings_that_are_not_flags():
    env = launch_env(LaunchConfig(), base={})
    assert env == {
        "LLAMA_ARG_REASONING": "off",
        "LLAMA_ARG_N_PARALLEL": "1",
        "LLAMA_ARG_BATCH": "256",
        "LLAMA_ARG_CACHE_RAM": "1024",
    }
    # The context size travels on the command line, not in the environment.
    assert "LLAMA_ARG_CTX_SIZE" not in env


def test_launch_env_reflects_a_non_default_config():
    env = launch_env(LaunchConfig(parallel=2, batch_size=512, cache_ram_mib=0), base={})
    assert env["LLAMA_ARG_N_PARALLEL"] == "2"
    assert env["LLAMA_ARG_BATCH"] == "512"
    assert env["LLAMA_ARG_CACHE_RAM"] == "0"


def test_launch_env_operator_override_wins_and_base_is_untouched():
    base = {"LLAMA_ARG_N_PARALLEL": "3", "LLAMA_ARG_REASONING": "on", "PATH": "/bin"}
    env = launch_env(LaunchConfig(), base=base)

    assert env["LLAMA_ARG_N_PARALLEL"] == "3"
    assert env["LLAMA_ARG_REASONING"] == "on"
    assert env["LLAMA_ARG_BATCH"] == "256"  # not overridden → the app's value
    assert env["PATH"] == "/bin"
    assert base == {"LLAMA_ARG_N_PARALLEL": "3", "LLAMA_ARG_REASONING": "on", "PATH": "/bin"}


def test_launch_env_defaults_to_the_process_environment(monkeypatch, clean_launch_env):
    monkeypatch.setenv("CONVSIM_TEST_MARKER", "present")
    env = launch_env(LaunchConfig())
    assert env["CONVSIM_TEST_MARKER"] == "present"
    assert env["LLAMA_ARG_N_PARALLEL"] == "1"


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def test_context_length_goes_on_the_command_line_unless_the_operator_pinned_it():
    config = LaunchConfig(context_length=6144)
    assert context_length_for_command(config, {}) == 6144
    # The uniform rule: a LLAMA_ARG_* already in the environment wins, and a
    # flag would silently beat the variable, so the flag is left off.
    assert context_length_for_command(config, {"LLAMA_ARG_CTX_SIZE": "4096"}) is None
    assert context_length_for_command(config, {"LLAMA_ARG_CTX_SIZE": ""}) == 6144


def test_command_line_for_a_registry_model(db, tmp_path):
    conn = db.connection()
    model = tmp_path / "registry-model.gguf"
    model.write_bytes(b"gguf")
    _seed_registry_model(conn, registry_id="reg-model", context_length=6144, file_path=str(model))

    config = resolve_launch_config(str(model), conn)
    env = launch_env(config, base={})
    cmd = build_command(
        "/opt/llama-server", str(model), context_length=context_length_for_command(config, env)
    )

    assert cmd[cmd.index("--ctx-size") + 1] == "6144"
    # Slots, batch and cache are variables, never flags: an engine build that
    # lacks one of the flags must still start.
    for flag in ("--parallel", "-np", "--batch-size", "-b", "--cache-ram"):
        assert flag not in cmd
    assert env["LLAMA_ARG_N_PARALLEL"] == "1"
    assert env["LLAMA_ARG_BATCH"] == "256"
    assert env["LLAMA_ARG_CACHE_RAM"] == "1024"


def test_command_line_for_a_player_supplied_model(db, tmp_path):
    conn = db.connection()
    model = tmp_path / "my-own.gguf"
    model.write_bytes(b"gguf")
    register_user_gguf(conn, path=str(model))

    config = resolve_launch_config(str(model), conn)
    env = launch_env(config, base={})
    cmd = build_command(
        "/opt/llama-server", str(model), context_length=context_length_for_command(config, env)
    )

    assert cmd[cmd.index("--ctx-size") + 1] == "8192"
    assert env["LLAMA_ARG_N_PARALLEL"] == "1"
