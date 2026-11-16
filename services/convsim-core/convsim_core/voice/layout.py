# SPDX-License-Identifier: Apache-2.0
"""Where voice files live on disk, and whether an asset is installed.

Everything sits under one *voice root* (``ServiceConfig.voice_dir``)::

    <voice root>/
      engine/   bin/sherpa-onnx-offline[.exe] ...   the speech engine
      stt/      base-encoder.int8.onnx ...          Whisper
      tts/      model.onnx voices.bin ...           Kokoro
      tmp/                                          audio in flight
      .staging/                                     downloads in progress

The folder names are fixed ASCII on purpose. The engine is always started
with the voice root as its working directory and handed paths relative to it,
so a Windows user name with an accent in it (which is part of the root's
absolute path) never reaches the engine's command line.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from convsim_core.voice import catalog
from convsim_core.voice.catalog import INSTALL_MARKER, VoiceAsset, VoiceComponent


class VoiceLayout:
    """Paths under one voice root."""

    def __init__(self, voice_root: str | Path) -> None:
        self.root = Path(voice_root)

    def asset_dir(self, asset: VoiceAsset) -> Path:
        return self.root / asset.install_dir

    @property
    def staging_root(self) -> Path:
        return self.root / ".staging"

    def staging_dir(self, asset: VoiceAsset) -> Path:
        return self.staging_root / asset.id

    @property
    def tmp_dir(self) -> Path:
        return self.root / "tmp"

    # ── Install state ─────────────────────────────────────────────────────────

    def installed_version(self, asset: VoiceAsset) -> Optional[str]:
        """The version recorded by the asset's marker, or None without one."""
        marker = self.asset_dir(asset) / INSTALL_MARKER
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        version = data.get("version") if isinstance(data, dict) else None
        return version if isinstance(version, str) else None

    def is_installed(self, asset: Optional[VoiceAsset]) -> bool:
        """True when the catalog's version of *asset* is fully on disk."""
        if asset is None:
            return False
        if self.installed_version(asset) != asset.version:
            return False
        base = self.asset_dir(asset)
        return all((base / rel).is_file() for rel in asset.required_files)

    def write_marker(self, asset: VoiceAsset, directory: Path) -> None:
        payload = {
            "asset_id": asset.id,
            "version": asset.version,
            "installed_at": datetime.now(timezone.utc).isoformat(),
        }
        (directory / INSTALL_MARKER).write_text(json.dumps(payload), encoding="utf-8")

    # ── Components ────────────────────────────────────────────────────────────

    def engine_installed(self) -> bool:
        return self.is_installed(catalog.engine_asset())

    def component_assets(self, component: VoiceComponent) -> list[VoiceAsset]:
        """Every asset a component needs, engine first. Empty when unsupported."""
        engine = catalog.engine_asset()
        if engine is None:
            return []
        return [engine] + [catalog.MODEL_ASSETS[a] for a in component.asset_ids]

    def component_installed(self, component: VoiceComponent) -> bool:
        assets = self.component_assets(component)
        return bool(assets) and all(self.is_installed(a) for a in assets)

    def stt_installed(self) -> bool:
        return self.component_installed(catalog.STT_COMPONENT)

    def tts_installed(self) -> bool:
        return self.component_installed(catalog.TTS_COMPONENT)

    def installed_bytes(self) -> int:
        """Bytes on disk under the voice folder, staged downloads included."""
        total = 0
        if not self.root.is_dir():
            return 0
        for path in self.root.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                pass
        return total

    def engine_program(self, program: str) -> Path:
        """Absolute path of an engine program in the installed engine."""
        engine = catalog.engine_asset()
        install_dir = engine.install_dir if engine is not None else "engine"
        return self.root / install_dir / "bin" / catalog.engine_program_filename(program)
