# SPDX-License-Identifier: Apache-2.0
"""State and job tracking behind the guided voice setup flow (issue #487).

Two things live here:

``build_plan``
    Reads the machine — which weight files are on disk, which engines resolve,
    whether the optional Python extras are importable — and returns one
    structure the UI can render end to end: per-capability readiness plus the
    ordered list of steps still outstanding. Everything the confirmation screen
    must disclose (source URL, licence, exact size, SHA-256, destination path)
    comes from the same structure, so no screen has to re-derive it.

``voice_install_jobs`` helpers
    Mirror ``setup_install_service`` for the download job: a row per guided
    install, a JSON stage list the client polls, and terminal states that
    distinguish a user cancel from a failure.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from convsim_core.services.setup_install_service import StageState
from convsim_core.services.voice_registry import (
    VOICE_ENGINES,
    Capability,
    VoiceAsset,
    VoiceEngine,
    assets_for,
    configured_stt_model_path,
    engine_command,
    engine_command_note,
    ffmpeg_installed,
    find_whisper_binary,
    install_path,
    onnxruntime_installable,
    onnxruntime_installed,
    recommended_asset,
)

logger = logging.getLogger(__name__)

# user_settings key holding the STT model the player chose during onboarding.
STT_MODEL_PATH_KEY = "stt_model_path"


# ── Persisted STT model selection ─────────────────────────────────────────────


def get_stt_model_path(conn: sqlite3.Connection) -> str | None:
    """Return the STT model path the player installed, or None."""
    row = conn.execute(
        "SELECT value FROM user_settings WHERE key = ?", (STT_MODEL_PATH_KEY,)
    ).fetchone()
    value = row["value"] if row is not None else None
    return value or None


def set_stt_model_path(conn: sqlite3.Connection, path: str) -> None:
    """Persist the STT model path so the choice survives a restart."""
    conn.execute(
        """
        INSERT INTO user_settings (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (STT_MODEL_PATH_KEY, path),
    )
    conn.commit()


def apply_stt_model_path(worker: Any, path: str) -> None:
    """Point a live STT worker at *path*, if it supports being re-pointed.

    The fake worker (used in tests and packaged smoke builds) has no model file,
    so the capability check keeps this a no-op there rather than an error.
    """
    setter = getattr(worker, "set_model_path", None)
    if callable(setter):
        setter(path)


# ── Plan ──────────────────────────────────────────────────────────────────────


def _asset_view(asset: VoiceAsset) -> dict[str, Any]:
    dest = install_path(asset)
    return {
        "id": asset.id,
        "capability": asset.capability,
        "name": asset.name,
        "description": asset.description,
        "language_note": asset.language_note,
        "recommended": asset.recommended,
        "size_bytes": asset.size_bytes,
        "license": asset.license,
        "license_url": asset.license_url,
        "source_url": asset.url,
        "sha256": asset.sha256,
        "install_path": str(dest),
        "installed": dest.is_file(),
    }


def _engine_view(
    engine: VoiceEngine, *, found_at: str | None, serving: bool = False
) -> dict[str, Any]:
    return {
        "id": engine.id,
        "capability": engine.capability,
        "name": engine.name,
        "why_manual": engine.why_manual,
        "docs_url": engine.docs_url,
        "command": engine_command(engine, sys.platform),
        "command_note": engine_command_note(engine, sys.platform),
        "startable": engine.startable,
        # Nothing left to install either way, but the two reasons differ: the
        # app located the program, or the capability is answering from
        # somewhere the app cannot see (so there is also nothing to start).
        "installed": found_at is not None or serving,
        "found_at": found_at,
        "serving": serving,
    }


def _engine_location(engine: VoiceEngine) -> str | None:
    """Resolve where *engine* is installed, or None when it is missing."""
    if engine.id == "whisper-cli":
        return find_whisper_binary()
    if engine.id == "kokoro-server":
        from convsim_core.runtime.kokoro_sidecar import find_kokoro_executable

        return find_kokoro_executable()
    return None


def build_plan(
    conn: sqlite3.Connection,
    *,
    stt_ready: bool,
    tts_ready: bool,
    kokoro_state: str | None = None,
) -> dict[str, Any]:
    """Describe what voice needs on this machine and what is already satisfied.

    *stt_ready* and *tts_ready* come from the live worker health checks, so the
    plan agrees with what Home and Settings report rather than re-deriving
    readiness from file existence alone.
    """
    # A capability can be satisfied without the app locating the program. The
    # Kokoro command this very plan hands out runs the server in Docker, which
    # puts no `kokoro-server` binary on PATH — so resolving the row from the
    # binary alone would re-offer the command the player has just run, behind a
    # "Check again" that could never turn green, beside a capability the worker
    # already reports as ready.
    capability_ready: dict[str, bool] = {"stt": stt_ready, "tts": tts_ready}
    engines: dict[str, dict[str, Any]] = {}
    for engine in VOICE_ENGINES:
        found_at = _engine_location(engine)
        engines[engine.id] = _engine_view(
            engine,
            found_at=found_at,
            serving=found_at is None and capability_ready.get(engine.capability, False),
        )

    # Which STT model is actually in use: the player's recorded choice, or the
    # worker's configured path when they have not made one. Deriving it from
    # the worker rather than from "the recommended one exists" keeps the answer
    # right for anyone who set CONVSIM_WHISPER_CPP_MODEL_PATH themselves.
    active_stt = get_stt_model_path(conn) or str(configured_stt_model_path())

    stt_assets = [_asset_view(a) for a in assets_for("stt")]
    for view in stt_assets:
        view["selected"] = view["installed"] and view["install_path"] == active_stt

    vad_assets = [_asset_view(a) for a in assets_for("vad")]
    vad_installed = any(v["installed"] for v in vad_assets)

    capabilities = [
        {
            "id": "stt",
            "label": "Speak your turns",
            "description": "Transcribes what you say, on this machine, so you can rehearse out loud.",
            "ready": stt_ready,
            "required_engine_ids": ["whisper-cli"],
            "asset_ids": [a["id"] for a in stt_assets],
        },
        {
            "id": "tts",
            "label": "Hear the NPC",
            "description": "Reads the NPC's replies aloud in one of the built-in voices.",
            "ready": tts_ready,
            "required_engine_ids": ["kokoro-server"],
            "asset_ids": [],
        },
        {
            "id": "vad",
            "label": "Hands-free turn-taking",
            "description": "Optional. Detects when you stop speaking so you need no push-to-talk key.",
            "ready": vad_installed and onnxruntime_installed(),
            "required_engine_ids": [],
            "asset_ids": [a["id"] for a in vad_assets],
        },
    ]

    return {
        "capabilities": capabilities,
        "assets": stt_assets + vad_assets,
        "engines": list(engines.values()),
        "platform": sys.platform,
        "kokoro_state": kokoro_state,
        "onnxruntime_installed": onnxruntime_installed(),
        # Whether the one command that would close that gap can reach this
        # server at all. False in every packaged build, where the UI must say
        # so rather than print a pip command into a frozen interpreter.
        "onnxruntime_installable": onnxruntime_installable(),
        "ffmpeg_installed": ffmpeg_installed(),
        "active_job_id": _active_job_id(conn),
    }


def default_asset_ids() -> list[str]:
    """The asset ids the one-click path installs: recommended STT, plus VAD when it can work.

    Hands-free runs the VAD model through ``onnxruntime``, and a packaged build
    has neither the extra nor a ``pip`` that could reach its interpreter — the
    plan reports that as ``onnxruntime_installable: false`` and the screen
    replaces the install command with the reason. Keeping the weights in the
    one-click set anyway would have the same screen disclose, charge for and
    fetch a file for the one capability it has just said is impossible here.
    That is the dead end this flow exists to remove, in download form, so the
    asset is dropped when hands-free can never come up on this machine.

    A source checkout *without* the extra still gets it: there the command is
    offered, so the model is a step on a route that goes somewhere.
    """
    hands_free_possible = onnxruntime_installed() or onnxruntime_installable()
    ids: list[str] = []
    for capability in ("stt", "vad"):
        if capability == "vad" and not hands_free_possible:
            continue
        asset = recommended_asset(capability)  # type: ignore[arg-type]
        if asset is not None:
            ids.append(asset.id)
    return ids


def missing_assets(asset_ids: list[str]) -> list[VoiceAsset]:
    """Return the subset of *asset_ids* whose file is not already on disk."""
    from convsim_core.services.voice_registry import get_asset

    out: list[VoiceAsset] = []
    for asset_id in asset_ids:
        asset = get_asset(asset_id)
        if asset is not None and not install_path(asset).is_file():
            out.append(asset)
    return out


def total_download_bytes(asset_ids: list[str]) -> int:
    """Bytes the player is about to transfer for *asset_ids* (already-installed excluded)."""
    return sum(a.size_bytes for a in missing_assets(asset_ids))


# ── Job rows ──────────────────────────────────────────────────────────────────


def create_job(conn: sqlite3.Connection, *, asset_ids: list[str], stages: list[StageState]) -> int:
    """Insert a pending voice install job and return its id."""
    cursor = conn.execute(
        "INSERT INTO voice_install_jobs (asset_ids, stages_json) VALUES (?, ?)",
        (json.dumps(asset_ids), json.dumps([asdict(s) for s in stages])),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    job = dict(row)
    job["stages"] = json.loads(job.pop("stages_json"))
    job["asset_ids"] = json.loads(job.pop("asset_ids"))
    return job


_JOB_COLUMNS = (
    "id, status, asset_ids, stages_json, error_message, created_at, updated_at"
)


def get_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    """Return a single voice install job by id, or None."""
    row = conn.execute(
        f"SELECT {_JOB_COLUMNS} FROM voice_install_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    return _row_to_job(row) if row is not None else None


def get_active_job(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the most recent non-terminal voice install job, or None."""
    row = conn.execute(
        f"SELECT {_JOB_COLUMNS} FROM voice_install_jobs "
        "WHERE status IN ('pending', 'running') ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return _row_to_job(row) if row is not None else None


def _active_job_id(conn: sqlite3.Connection) -> int | None:
    try:
        job = get_active_job(conn)
    except sqlite3.Error:  # pragma: no cover - table missing pre-migration
        return None
    return job["id"] if job else None


def update_job_status(
    conn: sqlite3.Connection, job_id: int, status: str, error_message: str | None = None
) -> None:
    """Update the top-level status (and optional error) of a voice install job."""
    conn.execute(
        "UPDATE voice_install_jobs "
        "SET status = ?, error_message = ?, updated_at = datetime('now') WHERE id = ?",
        (status, error_message, job_id),
    )
    conn.commit()


def update_job_stages(conn: sqlite3.Connection, job_id: int, stages: list[StageState]) -> None:
    """Persist the current stage snapshot for a voice install job."""
    conn.execute(
        "UPDATE voice_install_jobs "
        "SET stages_json = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps([asdict(s) for s in stages]), job_id),
    )
    conn.commit()


def retire_orphaned_jobs(conn: sqlite3.Connection) -> int:
    """Fail any job the process death left non-terminal; returns how many.

    Called once at startup. Unlike the LLM pipeline these jobs are not
    re-driven: the downloads are small, and a player who reopens voice setup
    gets a plan that already reflects whatever did land on disk, with a single
    button to fetch the rest. Leaving the rows 'running' would instead have the
    client poll a job no task is advancing.
    """
    try:
        rows = conn.execute(
            "SELECT id FROM voice_install_jobs WHERE status IN ('pending', 'running')"
        ).fetchall()
    except sqlite3.Error:  # pragma: no cover - table missing pre-migration
        return 0
    for row in rows:
        update_job_status(
            conn,
            row["id"],
            "failed",
            "Interrupted when the app closed. Start voice setup again to finish.",
        )
    return len(rows)


def stage_label(asset: VoiceAsset) -> str:
    """Progress label for the stage that downloads *asset*."""
    return f"Downloading {asset.name}"


def resolved_install_path(asset: VoiceAsset) -> Path:
    """Re-export of the registry path resolver, for routers and tests."""
    return install_path(asset)


__all__ = [
    "STT_MODEL_PATH_KEY",
    "Capability",
    "apply_stt_model_path",
    "build_plan",
    "create_job",
    "default_asset_ids",
    "get_active_job",
    "get_job",
    "get_stt_model_path",
    "missing_assets",
    "resolved_install_path",
    "retire_orphaned_jobs",
    "set_stt_model_path",
    "stage_label",
    "total_download_bytes",
    "update_job_stages",
    "update_job_status",
]
