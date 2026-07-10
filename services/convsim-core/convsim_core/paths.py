# SPDX-License-Identifier: Apache-2.0
"""Platform-specific data directory resolution for convsim-core.

Resolution order for the data root:
  1. CONVSIM_DATA_ROOT env var — explicit override; used by the Tauri shell in
     packaged builds to point at the OS-native app data directory.
  2. Platform OS convention:
       macOS   — ~/Library/Application Support/com.outrightmental.convsim
       Windows — %LOCALAPPDATA%\\outrightmental\\convsim
                 (LocalAppData avoids the Roaming profile that some sync tools
                 and enterprise policies replicate across machines)
       Linux / Steam Deck — $XDG_DATA_HOME/convsim
                            or ~/.local/share/convsim when XDG_DATA_HOME is unset
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def platform_data_root() -> Path:
    """Return the platform-appropriate root directory for all convsim user data.

    All sub-directories (data, db, logs, packs, models, cache, exports, crashes)
    live under this root.  The CONVSIM_DATA_ROOT env var is checked first so
    the Tauri shell can redirect to the OS-native app data folder without
    recompiling Python, and test fixtures can redirect to a tmp directory.
    """
    override = os.environ.get("CONVSIM_DATA_ROOT")
    if override:
        return Path(override)

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "com.outrightmental.convsim"

    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "outrightmental" / "convsim"

    # Linux (including Steam Deck) — XDG Base Directory Specification.
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / "convsim"


def legacy_convsim_dir() -> Path:
    """Return the legacy ~/.convsim directory used before platform-specific paths.

    Only used by the migration helper; callers should prefer ``platform_data_root``.
    """
    return Path.home() / ".convsim"


def is_steam_deck() -> bool:
    """Return True when running on Steam Deck hardware.

    The Steam Runtime sets the ``SteamDeck`` environment variable to ``1``
    on actual Steam Deck hardware.  This is reliable without the Steamworks SDK.
    """
    return os.environ.get("SteamDeck") == "1"
