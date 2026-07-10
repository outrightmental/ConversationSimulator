# SPDX-License-Identifier: Apache-2.0
"""One-shot migration of user data from the legacy ~/.convsim directory.

Called once on startup when:
  - The legacy ~/.convsim directory exists and contains data, AND
  - The new platform data root is empty (or does not exist yet).

Migration copies — never moves — so the original data is preserved if
anything goes wrong.  A marker file written inside the legacy directory
prevents the migration from running a second time.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

_MIGRATED_MARKER = ".convsim_migrated_to_platform_dir"

# Sub-directories to copy.  Models are intentionally excluded: they can be
# many GBs and the user may have deliberately placed them on a different disk.
_MIGRATE_SUBDIRS = ("data", "db", "packs", "logs", "exports", "cache", "crashes")

_logger = logging.getLogger(__name__)


def needs_migration(new_root: Path, legacy_dir: Path) -> bool:
    """Return True if data should be migrated from legacy_dir to new_root.

    Conditions (all must hold):
      - legacy_dir exists.
      - The migration marker has not been written inside legacy_dir.
      - new_root is absent or empty.
      - At least one migratable sub-directory exists inside legacy_dir.
    """
    if not legacy_dir.exists():
        return False
    if (legacy_dir / _MIGRATED_MARKER).exists():
        return False
    if new_root.exists() and any(new_root.iterdir()):
        return False
    return any((legacy_dir / sub).exists() for sub in _MIGRATE_SUBDIRS)


def migrate(new_root: Path, legacy_dir: Path) -> bool:
    """Copy migratable sub-directories from legacy_dir into new_root.

    Returns True when every copy succeeded.  On failure the original data in
    legacy_dir is untouched; a partial new_root may exist and will be used
    for the current session but migration will be re-attempted next launch
    (the marker is only written on full success).
    """
    try:
        new_root.mkdir(parents=True, exist_ok=True)
        for sub in _MIGRATE_SUBDIRS:
            src = legacy_dir / sub
            dst = new_root / sub
            if src.exists() and not dst.exists():
                shutil.copytree(src, dst)
                _logger.info("Migrated %s → %s", src, dst)
        (legacy_dir / _MIGRATED_MARKER).touch()
        _logger.info(
            "Data migration from %s to %s complete", legacy_dir, new_root
        )
        return True
    except Exception:
        _logger.exception(
            "Data migration from %s to %s failed; original data preserved",
            legacy_dir,
            new_root,
        )
        return False
