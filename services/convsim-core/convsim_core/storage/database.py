# SPDX-License-Identifier: Apache-2.0
import logging
import sqlite3
from pathlib import Path

from convsim_core.storage.migrations import run_migrations

logger = logging.getLogger(__name__)

_DB_FILENAME = "convsim.sqlite"


class Database:
    """Manages the SQLite connection lifecycle and schema migrations."""

    def __init__(self, path: Path, conn: sqlite3.Connection, migrations_applied: int) -> None:
        self._path = path
        self._conn = conn
        self._migrations_applied = migrations_applied

    @classmethod
    def open(cls, db_dir: str) -> "Database":
        """Open (or create) the database, running any pending migrations."""
        path = Path(db_dir) / _DB_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        migrations_applied = run_migrations(conn)
        logger.info("Opened database at %s (%d migrations applied)", path, migrations_applied)
        return cls(path, conn, migrations_applied)

    def close(self) -> None:
        self._conn.close()
        logger.info("Closed database at %s", self._path)

    @property
    def path(self) -> str:
        return str(self._path)

    @property
    def migrations_applied(self) -> int:
        return self._migrations_applied

    def connection(self) -> sqlite3.Connection:
        return self._conn

    def integrity_check(self) -> bool:
        result = self._conn.execute("PRAGMA integrity_check").fetchone()
        return result[0] == "ok"
