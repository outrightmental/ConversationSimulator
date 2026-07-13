# SPDX-License-Identifier: Apache-2.0
"""Tests for model download service: SHA-256 verification and download lifecycle."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

import convsim_core.runtime  # noqa: F401 — register built-in adapters
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.services.model_download_service import execute_download, verify_sha256
from convsim_core.services.model_manager_service import (
    create_install_record,
    get_install_record,
    mark_install_ready,
)
from convsim_core.storage.database import Database


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db(tmp_path):
    database = Database.open(str(tmp_path / "db"))
    yield database
    database.close()


@pytest.fixture()
def tmp_config(tmp_path):
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        models_dir=str(tmp_path / "models"),
    )


@pytest.fixture()
def client(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        yield c


def _insert_registry_model(conn, model_id: str, sha256: str = "a" * 64) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO model_registry
           (id, name, provider, license_spdx, sha256, source_type)
           VALUES (?, ?, 'test', 'MIT', ?, 'registry')""",
        (model_id, model_id, sha256),
    )
    conn.commit()


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── verify_sha256: unit tests ─────────────────────────────────────────────────


def test_verify_sha256_passes_for_correct_checksum(tmp_path):
    data = b"hello model weights"
    f = tmp_path / "model.gguf"
    f.write_bytes(data)
    assert verify_sha256(f, _sha256_of(data)) is True


def test_verify_sha256_fails_for_wrong_checksum(tmp_path):
    data = b"correct content"
    f = tmp_path / "model.gguf"
    f.write_bytes(data)
    assert verify_sha256(f, "a" * 64) is False


def test_verify_sha256_case_insensitive(tmp_path):
    data = b"case test"
    f = tmp_path / "model.gguf"
    f.write_bytes(data)
    correct = _sha256_of(data).upper()
    assert verify_sha256(f, correct) is True


def test_verify_sha256_empty_file(tmp_path):
    f = tmp_path / "empty.gguf"
    f.write_bytes(b"")
    expected = hashlib.sha256(b"").hexdigest()
    assert verify_sha256(f, expected) is True


def test_verify_sha256_large_file(tmp_path):
    data = b"x" * (3 * 65_536 + 17)  # spans multiple 64 KB chunks
    f = tmp_path / "big.gguf"
    f.write_bytes(data)
    assert verify_sha256(f, _sha256_of(data)) is True
    assert verify_sha256(f, "0" * 64) is False


# ── execute_download: mocked HTTP download ────────────────────────────────────


def _make_mock_client(content: bytes, content_length: bool = True) -> httpx.AsyncClient:
    """Return a mock httpx.AsyncClient that streams *content* from any GET request."""
    chunk_size = 1024

    async def _aiter_bytes(chunk_size=None):
        offset = 0
        while offset < len(content):
            yield content[offset : offset + (chunk_size or 65_536)]
            offset += chunk_size or 65_536

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = (
        {"content-length": str(len(content))} if content_length else {}
    )
    mock_response.aiter_bytes = _aiter_bytes

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.stream = MagicMock(return_value=mock_cm)
    mock_client.aclose = AsyncMock()
    return mock_client


@pytest.mark.asyncio
async def test_execute_download_success(db, tmp_path):
    content = b"fake gguf weights"
    sha = _sha256_of(content)
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    mock_client = _make_mock_client(content)
    dest_dir = tmp_path / "models"

    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        sha,
        dest_dir,
        "test.gguf",
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record is not None
    assert record["install_status"] == "ready"
    assert record["verified_sha256"] == sha
    assert record["size_bytes"] == len(content)
    assert (dest_dir / "test.gguf").exists()
    assert not (dest_dir / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_execute_download_checksum_mismatch(db, tmp_path):
    content = b"corrupted download"
    wrong_sha = "b" * 64
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")
    dest_dir = tmp_path / "models"

    mock_client = _make_mock_client(content)

    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        wrong_sha,
        dest_dir,
        "test.gguf",
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record is not None
    assert record["install_status"] == "checksum_mismatch"
    assert "mismatch" in (record["error_message"] or "")
    # File must be deleted, not left on disk.
    assert not (dest_dir / "test.gguf").exists()
    assert not (dest_dir / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_execute_download_cancel(db, tmp_path):
    content = b"x" * 200_000
    sha = _sha256_of(content)
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")
    dest_dir = tmp_path / "models"
    cancel_event = asyncio.Event()

    # Pre-set the event so the first chunk causes cancel.
    cancel_event.set()
    mock_client = _make_mock_client(content)

    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        sha,
        dest_dir,
        "test.gguf",
        cancel_event=cancel_event,
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record is not None
    assert record["install_status"] == "cancelled"
    assert not (dest_dir / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_execute_download_network_error(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")
    dest_dir = tmp_path / "models"

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.stream = MagicMock(return_value=mock_cm)
    mock_client.aclose = AsyncMock()

    await execute_download(
        conn,
        install_id,
        "http://unreachable.test/model.gguf",
        "a" * 64,
        dest_dir,
        "test.gguf",
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record is not None
    assert record["install_status"] == "failed"
    assert record["error_message"] is not None


@pytest.mark.asyncio
async def test_execute_download_no_part_file_left_on_mismatch(db, tmp_path):
    content = b"data that will fail checksum"
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")
    dest_dir = tmp_path / "models"

    mock_client = _make_mock_client(content)

    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        "f" * 64,
        dest_dir,
        "test.gguf",
        _client=mock_client,
    )

    assert not (dest_dir / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_execute_download_sets_downloading_status_before_completion(db, tmp_path):
    """The install record must be set to 'downloading' immediately after the task starts."""
    content = b"model data"
    sha = _sha256_of(content)
    conn = db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    dest_dir = tmp_path / "models"

    status_during_download: list[str] = []

    async def _aiter_bytes(chunk_size=None):
        # Check the DB status while "in" the download.
        r = conn.execute(
            "SELECT install_status FROM installed_models WHERE id = ?", (install_id,)
        ).fetchone()
        status_during_download.append(r[0])
        yield content

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {"content-length": str(len(content))}
    mock_response.aiter_bytes = _aiter_bytes

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.stream = MagicMock(return_value=mock_cm)
    mock_client.aclose = AsyncMock()

    await execute_download(
        conn, install_id, "http://x.test/m.gguf", sha, dest_dir, "m.gguf", _client=mock_client
    )

    assert status_during_download == ["downloading"]


# ── Resume: interrupted .part continues from its byte offset ──────────────────


def _make_mock_client_with_response(
    *, status_code: int, chunks: bytes, extra_headers: dict[str, str] | None = None
) -> httpx.AsyncClient:
    """Mock client whose GET yields *chunks* with a given status and headers."""

    async def _aiter_bytes(chunk_size=None):
        yield chunks

    headers = {"content-length": str(len(chunks))}
    if extra_headers:
        headers.update(extra_headers)

    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = headers
    mock_response.aiter_bytes = _aiter_bytes

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.stream = MagicMock(return_value=mock_cm)
    mock_client.aclose = AsyncMock()
    return mock_client


@pytest.mark.asyncio
async def test_execute_download_resumes_from_part_offset(db, tmp_path):
    """A surviving .part file is continued via a Range request, not restarted."""
    first_half = b"the-first-half-of-the-weights"
    second_half = b"and-the-remaining-second-half"
    full = first_half + second_half
    sha = _sha256_of(full)
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    dest_dir = tmp_path / "models"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Simulate an interrupted download: the first half is already on disk.
    (dest_dir / "test.gguf.part").write_bytes(first_half)

    total = len(full)
    mock_client = _make_mock_client_with_response(
        status_code=206,
        chunks=second_half,
        extra_headers={"content-range": f"bytes {len(first_half)}-{total - 1}/{total}"},
    )

    await execute_download(
        conn, install_id, "http://example.test/model.gguf", sha, dest_dir, "test.gguf",
        _client=mock_client,
    )

    # The Range header must have been sent from the existing offset.
    _, kwargs = mock_client.stream.call_args
    assert kwargs["headers"]["Range"] == f"bytes={len(first_half)}-"

    record = get_install_record(conn, install_id)
    assert record["install_status"] == "ready"
    assert record["size_bytes"] == total
    assert (dest_dir / "test.gguf").read_bytes() == full
    assert not (dest_dir / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_execute_download_restarts_when_server_ignores_range(db, tmp_path):
    """If the server answers 200 (Range ignored), the stale .part is overwritten."""
    full = b"a-complete-fresh-download-of-the-model"
    sha = _sha256_of(full)
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    dest_dir = tmp_path / "models"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # A stale/partial .part exists, but the server will ignore the Range header.
    (dest_dir / "test.gguf.part").write_bytes(b"stale-bytes-that-must-be-discarded")

    mock_client = _make_mock_client_with_response(status_code=200, chunks=full)

    await execute_download(
        conn, install_id, "http://example.test/model.gguf", sha, dest_dir, "test.gguf",
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record["install_status"] == "ready"
    assert record["size_bytes"] == len(full)
    assert (dest_dir / "test.gguf").read_bytes() == full


# ── Network policy: download must not work in PLAY mode ──────────────────────


@pytest.mark.asyncio
async def test_execute_download_uses_explicit_download_mode(db, tmp_path, monkeypatch):
    """execute_download must call require_network(EXPLICIT_DOWNLOAD), not PLAY."""
    import convsim_core.network_policy as policy

    monkeypatch.setattr(policy, "LOCAL_MODE", True)
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")
    dest_dir = tmp_path / "models"

    mock_client = _make_mock_client(b"data")

    # With LOCAL_MODE=True only PLAY calls are blocked; EXPLICIT_DOWNLOAD still passes.
    # So execute_download must NOT raise even in LOCAL_MODE.
    # (If it used PLAY mode, it would raise NetworkBlockedError here.)
    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        _sha256_of(b"data"),
        dest_dir,
        "test.gguf",
        _client=mock_client,
    )
    # If we reach here without exception, network policy was respected.
    record = get_install_record(conn, install_id)
    assert record["install_status"] == "ready"


# ── GET /api/models/install/{install_id} ─────────────────────────────────────


def test_get_install_status_not_found(client):
    resp = client.get("/api/models/install/9999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INSTALL_NOT_FOUND"


def test_get_install_status_returns_record(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "/tmp/m.gguf")
    resp = client.get(f"/api/models/install/{install_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == install_id
    assert body["install_status"] == "pending"
    assert body["filename"] == "m.gguf"


def test_get_install_status_shows_progress_fields(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    resp = client.get(f"/api/models/install/{install_id}")
    body = resp.json()
    assert "progress_bytes" in body
    assert "error_message" in body
    assert "verified_sha256" in body


def test_get_install_status_shows_ready_after_mark_ready(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    mark_install_ready(conn, install_id, 12345, "a" * 64, "/tmp/m.gguf")
    resp = client.get(f"/api/models/install/{install_id}")
    body = resp.json()
    assert body["install_status"] == "ready"
    assert body["verified_sha256"] == "a" * 64
    assert body["size_bytes"] == 12345


# ── DELETE /api/models/install/{install_id} ───────────────────────────────────


def test_cancel_install_not_found(client):
    resp = client.delete("/api/models/install/9999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INSTALL_NOT_FOUND"


def test_cancel_install_pending_record(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    resp = client.delete(f"/api/models/install/{install_id}")
    assert resp.status_code == 204
    record = get_install_record(conn, install_id)
    assert record["install_status"] == "cancelled"


def test_cancel_install_terminal_state_returns_409(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    mark_install_ready(conn, install_id, 100, "a" * 64, "/tmp/m.gguf")
    resp = client.delete(f"/api/models/install/{install_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INSTALL_NOT_CANCELLABLE"


def test_cancel_install_failed_state_returns_409(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    from convsim_core.services.model_manager_service import mark_install_failed
    mark_install_failed(conn, install_id, "some error")
    resp = client.delete(f"/api/models/install/{install_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INSTALL_NOT_CANCELLABLE"


# ── POST /api/models/install guards (explicit-download mode) ──────────────────


def test_install_does_not_download_when_sha256_pending(client):
    """A PENDING sha256 must block download at the API layer, no network call made."""
    conn = client.app.state.db.connection()
    conn.execute(
        """INSERT INTO model_registry (id, name, provider, license_spdx, sha256, source_type)
           VALUES ('pending-m', 'Pending', 'test', 'MIT', 'PENDING', 'registry')"""
    )
    conn.commit()
    resp = client.post("/api/models/install", json={"registry_id": "pending-m"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MISSING_CHECKSUM"


def test_install_does_not_download_when_url_missing(client):
    """A registry entry with a valid checksum but no download URL must be rejected."""
    conn = client.app.state.db.connection()
    _insert_registry_model(conn, "no-url-model", "c" * 64)
    resp = client.post("/api/models/install", json={"registry_id": "no-url-model"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MISSING_DOWNLOAD_URL"
    # No install record must be created for a model that cannot be downloaded.
    rows = conn.execute(
        "SELECT id FROM installed_models WHERE registry_id = 'no-url-model'"
    ).fetchall()
    assert rows == []


def test_install_accepted_model_creates_install_record(client):
    conn = client.app.state.db.connection()
    _insert_registry_model(conn, "valid-model", "c" * 64)
    conn.execute(
        "UPDATE model_registry SET download_url = 'http://example.test/m.gguf' WHERE id = 'valid-model'"
    )
    conn.commit()

    # Suppress the fire-and-forget download so the freshly created record is
    # observed deterministically without racing (or making a real network call
    # from) the background task.
    with patch(
        "convsim_core.routers.models._spawn_download_task",
        side_effect=lambda coro: coro.close(),
    ):
        resp = client.post("/api/models/install", json={"registry_id": "valid-model"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    install_id = body["install_id"]
    record = get_install_record(conn, install_id)
    assert record is not None
    assert record["install_status"] == "pending"
