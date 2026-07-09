# SPDX-License-Identifier: Apache-2.0
"""Startup seeding: import official packs from the configured official_packs_dir.

On first launch (and whenever a new official pack appears), this module reads every
pack subdirectory under official_packs_dir and imports any that are not already in
the database.  Already-installed packs are skipped via a lightweight manifest read
so subsequent startups remain fast.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

import yaml

from convsim_core.config import ServiceConfig
from convsim_core.packs.importer import PackConflictError, import_from_folder
from convsim_core.storage.repositories.pack_repo import get_pack_by_slug

logger = logging.getLogger(__name__)


def _quick_read_pack_id(pack_dir: Path) -> Optional[str]:
    """Return the pack_id from a manifest file without full validation."""
    for filename in ("manifest.yaml", "pack.json"):
        path = pack_dir / filename
        if not path.is_file():
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
            if filename.endswith(".json"):
                data = json.loads(raw_text)
            else:
                data = yaml.safe_load(raw_text)
            if isinstance(data, dict):
                return data.get("pack_id") or None
        except Exception:
            pass
    return None


def seed_official_packs(config: ServiceConfig, conn: sqlite3.Connection) -> int:
    """Import official packs that are not yet installed.

    Scans ``config.official_packs_dir`` for pack subdirectories and imports any
    that are missing from the database.  Packs that fail validation are skipped
    with a warning rather than aborting the startup sequence.

    Returns the count of newly seeded packs (0 on a warm start).
    """
    official_dir = Path(config.official_packs_dir)
    if not official_dir.is_dir():
        return 0

    packs_dir = Path(config.packs_dir)
    packs_dir.mkdir(parents=True, exist_ok=True)

    seeded = 0
    for entry in sorted(official_dir.iterdir()):
        if not entry.is_dir():
            continue

        has_manifest = (entry / "manifest.yaml").is_file() or (entry / "pack.json").is_file()
        if not has_manifest:
            continue

        # Skip the (fast) work if the pack is already installed.
        pack_id = _quick_read_pack_id(entry)
        if pack_id and get_pack_by_slug(conn, pack_id) is not None:
            logger.debug("Official pack '%s' already installed, skipping", pack_id)
            continue

        try:
            result = import_from_folder(entry, packs_dir, conn)
            seeded += 1
            logger.info("Seeded official pack '%s' v%s", result.pack_slug, result.pack_version)
        except PackConflictError:
            # Another process beat us to it — not an error.
            pass
        except Exception as exc:
            logger.warning(
                "Failed to seed official pack at '%s': %s: %s",
                entry,
                type(exc).__name__,
                exc,
            )

    return seeded
