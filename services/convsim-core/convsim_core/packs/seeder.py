# SPDX-License-Identifier: Apache-2.0
"""Startup seeding: import official packs from the configured official_packs_dir.

On first launch (and whenever a new official pack appears), this module reads every
pack subdirectory under official_packs_dir and imports any that are not already in
the database.  Already-installed packs are skipped via a lightweight manifest read
so subsequent startups remain fast.  When the bundled pack version is newer than the
installed version the old copy is removed and the new one imported, so app upgrades
automatically upgrade bundled packs.  User-created local-dev copies are separate and
are never touched by the seeder.
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Optional

import yaml

from convsim_core.config import ServiceConfig
from convsim_core.packs.importer import PackConflictError, import_from_folder
from convsim_core.storage.repositories.pack_repo import get_pack_by_slug, remove_pack_by_slug

logger = logging.getLogger(__name__)


def _quick_read_manifest_field(pack_dir: Path, field: str) -> Optional[str]:
    """Return a single string field from a manifest file without full validation."""
    for filename in ("manifest.yaml", "pack.json"):
        path = pack_dir / filename
        if not path.is_file():
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
            data = json.loads(raw_text) if filename.endswith(".json") else yaml.safe_load(raw_text)
            if isinstance(data, dict):
                return data.get(field) or None
        except Exception:
            pass
    return None


def _quick_read_pack_id(pack_dir: Path) -> Optional[str]:
    """Return the pack_id from a manifest file without full validation."""
    return _quick_read_manifest_field(pack_dir, "pack_id")


def _parse_version(v: str) -> tuple:
    """Parse a semver-like version string into a comparable tuple of ints."""
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def _remove_installed_pack(slug: str, packs_dir: Path, conn: sqlite3.Connection) -> None:
    """Remove a pack's DB record and its installed directory."""
    source_path = remove_pack_by_slug(conn, slug)
    conn.commit()
    if source_path:
        installed = Path(source_path)
        try:
            installed.resolve().relative_to(packs_dir.resolve())
            within = True
        except ValueError:
            within = False
        if within and installed.is_dir():
            shutil.rmtree(installed, ignore_errors=True)


def seed_official_packs(config: ServiceConfig, conn: sqlite3.Connection) -> int:
    """Import official packs that are not yet installed, upgrading outdated copies.

    Scans ``config.official_packs_dir`` for pack subdirectories and imports any
    that are missing from the database.  Packs already installed at the same
    version are skipped (fast warm start).  When the bundled pack is at a higher
    version than the installed copy the old record is removed and the bundled pack
    is re-imported so that app upgrades propagate to the pack library.  Packs
    that fail validation are skipped with a warning rather than aborting the
    startup sequence.

    Returns the count of newly seeded (or upgraded) packs (0 on a warm start
    where all packs are up to date).
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

        pack_id = _quick_read_pack_id(entry)
        existing = get_pack_by_slug(conn, pack_id) if pack_id else None

        if existing is not None:
            bundled_version = _quick_read_manifest_field(entry, "version")
            if not bundled_version or _parse_version(bundled_version) <= _parse_version(existing.version):
                logger.debug(
                    "Official pack '%s' is up to date (v%s), skipping",
                    pack_id, existing.version,
                )
                continue
            # Bundled version is newer — remove stale copy before re-seeding.
            logger.info(
                "Upgrading official pack '%s' v%s → v%s",
                pack_id, existing.version, bundled_version,
            )
            _remove_installed_pack(existing.slug, packs_dir, conn)

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
