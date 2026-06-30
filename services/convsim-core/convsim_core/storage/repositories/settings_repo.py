# SPDX-License-Identifier: Apache-2.0
import sqlite3

from convsim_core.models import AppSettings

_BOOL_TRUE = "true"
_BOOL_FALSE = "false"


def load_settings(conn: sqlite3.Connection, data_dir: str, log_dir: str) -> AppSettings:
    """Load AppSettings from the user_settings table, falling back to defaults."""
    rows = conn.execute("SELECT key, value FROM user_settings").fetchall()
    stored = {row["key"]: row["value"] for row in rows}
    return AppSettings(
        data_dir=stored.get("data_dir", data_dir),
        log_dir=stored.get("log_dir", log_dir),
        save_transcripts=stored.get("save_transcripts", _BOOL_FALSE) == _BOOL_TRUE,
        save_raw_audio=stored.get("save_raw_audio", _BOOL_FALSE) == _BOOL_TRUE,
        tts_cache_enabled=stored.get("tts_cache_enabled", _BOOL_TRUE) == _BOOL_TRUE,
        telemetry_enabled=stored.get("telemetry_enabled", _BOOL_FALSE) == _BOOL_TRUE,
        crash_logging_enabled=stored.get("crash_logging_enabled", _BOOL_FALSE) == _BOOL_TRUE,
    )


def save_settings(conn: sqlite3.Connection, settings: AppSettings) -> None:
    """Upsert AppSettings into the user_settings table."""
    fields = [
        ("data_dir", settings.data_dir),
        ("log_dir", settings.log_dir),
        ("save_transcripts", _BOOL_TRUE if settings.save_transcripts else _BOOL_FALSE),
        ("save_raw_audio", _BOOL_TRUE if settings.save_raw_audio else _BOOL_FALSE),
        ("tts_cache_enabled", _BOOL_TRUE if settings.tts_cache_enabled else _BOOL_FALSE),
        ("telemetry_enabled", _BOOL_TRUE if settings.telemetry_enabled else _BOOL_FALSE),
        ("crash_logging_enabled", _BOOL_TRUE if settings.crash_logging_enabled else _BOOL_FALSE),
    ]
    conn.executemany(
        """
        INSERT INTO user_settings (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        fields,
    )
    conn.commit()
