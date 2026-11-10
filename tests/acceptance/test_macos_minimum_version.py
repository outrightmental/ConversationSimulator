# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — the macOS app declares the bundled engine's floor.

The bundled llama-server (the pin in runtimes/llama_cpp/download-runtime.sh)
targets macOS 14.0: no upstream prebuilt targets macOS 13 or older, and dyld
kills it the moment it launches on an older OS (issue #469). The download
script gates the binaries at that floor, and the QA matrix drops macOS 13
Ventura for that reason (issue #472). But the app itself still declared
``minimumSystemVersion`` 13.0, which Tauri writes to the bundle's
``LSMinimumSystemVersion``, so macOS 13 opened the app, and the player then
watched the engine fail to start, instead of macOS refusing an app it cannot
run.

These tests keep the two floors together: the base config, and any overlay
the release build stacks on it (Steam, demo), must declare a macOS minimum at
or above the floor download-runtime.sh enforces on the engine. Nothing here
needs a build; tests/artifact/ checks the same thing on the built bundle.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_TAURI = _REPO_ROOT / "apps" / "desktop" / "src-tauri"
_BASE_CONF = _SRC_TAURI / "tauri.conf.json"
# The overlays release.yml passes to `tauri build --config`.
_OVERLAYS = (_SRC_TAURI / "tauri.steam.conf.json", _SRC_TAURI / "tauri.demo.conf.json")
_DOWNLOAD_RUNTIME = _REPO_ROOT / "runtimes" / "llama_cpp" / "download-runtime.sh"

_FLOOR_RE = re.compile(r'^MACOS_MINOS_FLOOR="\$\{CONVSIM_MACOS_MINOS_FLOOR:-([0-9.]+)\}"', re.M)


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _engine_floor() -> str:
    match = _FLOOR_RE.search(_DOWNLOAD_RUNTIME.read_text(encoding="utf-8"))
    assert match, (
        f"{_DOWNLOAD_RUNTIME.relative_to(_REPO_ROOT)} no longer sets "
        'MACOS_MINOS_FLOOR="${CONVSIM_MACOS_MINOS_FLOOR:-<version>}"; update '
        "this test to read the engine's macOS floor from wherever it moved."
    )
    return match.group(1)


def _declared_minimum(conf: dict) -> str | None:
    return conf.get("bundle", {}).get("macOS", {}).get("minimumSystemVersion")


def test_engine_floor_is_readable() -> None:
    floor = _engine_floor()
    assert _version(floor) >= (14, 0), (
        f"download-runtime.sh's macOS floor is {floor}; the engine pin has never "
        "supported anything older than 14.0, so a lower floor means the gate "
        "was loosened by mistake."
    )


def test_base_config_declares_the_engine_floor() -> None:
    floor = _engine_floor()
    declared = _declared_minimum(json.loads(_BASE_CONF.read_text(encoding="utf-8")))
    assert declared, (
        "tauri.conf.json sets no bundle.macOS.minimumSystemVersion, so Tauri "
        f"falls back to its own default, far below the engine's {floor}."
    )
    assert _version(declared) >= _version(floor), (
        f"tauri.conf.json declares macOS {declared}, but the bundled llama-server "
        f"needs macOS {floor} (download-runtime.sh MACOS_MINOS_FLOOR). macOS would "
        "open the app on a version where its engine cannot start. Raise "
        f"bundle.macOS.minimumSystemVersion to {floor}."
    )


@pytest.mark.parametrize("overlay", _OVERLAYS, ids=lambda p: p.name)
def test_overlays_do_not_lower_the_floor(overlay: Path) -> None:
    floor = _engine_floor()
    declared = _declared_minimum(json.loads(overlay.read_text(encoding="utf-8")))
    if declared is None:
        return  # Inherits the base config's value, checked above.
    assert _version(declared) >= _version(floor), (
        f"{overlay.name} overrides bundle.macOS.minimumSystemVersion with "
        f"{declared}, below the engine's macOS {floor}."
    )
