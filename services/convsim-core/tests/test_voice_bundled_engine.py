# SPDX-License-Identifier: Apache-2.0
"""A speech engine shipped inside the app, and voice in the macOS App Sandbox.

The Mac App Store edition runs in the App Sandbox, where an app may not
download a program and run it (App Review guideline 2.5.2, and the sandbox
quarantines what the app writes). There the engine either ships in the app,
under the bundled runtime folder, or voice is unavailable: the API then says
``supported: false`` and the first-run screen does not offer voice.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

from convsim_core.voice import catalog, engine as voice_engine
from convsim_core.voice.layout import VoiceLayout


def _ship_engine(runtime_dir, *, version=None):
    """Lay out an engine under <runtime_dir>/voice-engine as a store build does."""
    asset = catalog._engine_asset_for()
    directory = runtime_dir / catalog.BUNDLED_ENGINE_SUBDIR
    for rel in asset.required_files:
        (directory / rel).parent.mkdir(parents=True, exist_ok=True)
        (directory / rel).write_bytes(b"\x7fELF")
    (directory / "lib").mkdir(exist_ok=True)
    (directory / catalog.INSTALL_MARKER).write_text(
        json.dumps({"asset_id": "engine", "version": version or asset.version}),
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def no_sandbox(monkeypatch):
    monkeypatch.delenv("APP_SANDBOX_CONTAINER_ID", raising=False)
    monkeypatch.delenv("CONVSIM_BUNDLED_RUNTIME_DIR", raising=False)


def test_a_shipped_engine_counts_as_installed_and_is_the_one_run(tmp_path, monkeypatch, no_sandbox):
    shipped = _ship_engine(tmp_path / "runtimes")
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path / "runtimes"))
    layout = VoiceLayout(tmp_path / "voice")

    assert catalog.bundled_engine_dir() == shipped
    assert layout.engine_installed()
    assert layout.engine_dir == shipped
    assert layout.asset_dir(catalog.engine_asset()) == shipped
    program = layout.engine_program(catalog.ENGINE_STT_PROGRAM)
    assert program.parent == shipped / "bin"
    # Nothing to download for the engine: only the models are left.
    assert catalog.engine_asset() not in [
        a for a in layout.component_assets(catalog.STT_COMPONENT) if not layout.is_installed(a)
    ]


def test_a_shipped_engine_of_another_version_is_ignored(tmp_path, monkeypatch, no_sandbox):
    _ship_engine(tmp_path / "runtimes", version="0.0.1-old")
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path / "runtimes"))
    layout = VoiceLayout(tmp_path / "voice")

    assert catalog.bundled_engine_dir() is None
    assert not layout.engine_installed()
    assert layout.engine_dir == tmp_path / "voice" / "engine"


def test_without_a_shipped_engine_the_download_location_is_unchanged(tmp_path, no_sandbox):
    layout = VoiceLayout(tmp_path / "voice")
    assert layout.engine_dir == tmp_path / "voice" / "engine"
    assert layout.engine_program(catalog.ENGINE_TTS_PROGRAM).parent == tmp_path / "voice" / "engine" / "bin"


def test_the_engine_finds_its_libraries_where_it_was_shipped(tmp_path, monkeypatch, no_sandbox):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(catalog, "detect_platform_key", lambda: "osx-arm64")
    shipped = _ship_engine(tmp_path / "runtimes")
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path / "runtimes"))
    env = voice_engine._engine_env(VoiceLayout(tmp_path / "voice"))
    assert env["DYLD_LIBRARY_PATH"].split(os.pathsep)[0] == str(shipped / "lib")


def test_in_the_mac_sandbox_voice_is_unavailable_without_a_shipped_engine(tmp_path, monkeypatch, no_sandbox):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(catalog, "detect_platform_key", lambda: "osx-arm64")
    monkeypatch.setenv("APP_SANDBOX_CONTAINER_ID", "com.outrightmental.convsim")

    assert catalog.in_macos_app_sandbox()
    assert catalog.engine_asset() is None
    assert VoiceLayout(tmp_path / "voice").component_assets(catalog.STT_COMPONENT) == []


def test_in_the_mac_sandbox_a_shipped_engine_makes_voice_available(tmp_path, monkeypatch, no_sandbox):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(catalog, "detect_platform_key", lambda: "osx-arm64")
    monkeypatch.setenv("APP_SANDBOX_CONTAINER_ID", "com.outrightmental.convsim")
    shipped = _ship_engine(tmp_path / "runtimes")
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(tmp_path / "runtimes"))

    asset = catalog.engine_asset()
    assert asset is not None and asset.version.endswith("osx-arm64")
    assert VoiceLayout(tmp_path / "voice").engine_dir == shipped


def test_outside_macos_the_sandbox_variable_changes_nothing(monkeypatch, no_sandbox):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("APP_SANDBOX_CONTAINER_ID", "x")
    assert not catalog.in_macos_app_sandbox()
