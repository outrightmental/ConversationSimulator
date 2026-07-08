# SPDX-License-Identifier: Apache-2.0
"""Download service for registry-managed GGUF models.

All downloads are streamed to a .part file, then:
  1. SHA-256 is verified against the registry-declared checksum.
  2. On match: the .part file is renamed to the final filename and the
     install record is marked 'ready' with the verified checksum stored.
  3. On mismatch: the .part file is deleted and the record is marked
     'checksum_mismatch'.  The mismatched file is never left on disk.
  4. On network or disk error: the .part file is deleted (if present)
     and the record is marked 'failed'.

Network calls are gated by NetworkMode.EXPLICIT_DOWNLOAD, blocking
any accidental call from play-mode code.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sqlite3
from pathlib import Path

import httpx

from convsim_core.network_policy import NetworkMode, require_network
from convsim_core.services.model_manager_service import (
    mark_install_failed,
    mark_install_ready,
    update_install_progress,
)

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 65_536  # 64 KB
_PROGRESS_INTERVAL = 1_048_576  # report progress every 1 MB


def verify_sha256(file_path: Path, expected_hex: str) -> bool:
    """Return True when the file's SHA-256 matches *expected_hex* (case-insensitive).

    Streams the file in 64 KB blocks so large GGUFs never load fully into RAM.
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected_hex.lower()


async def execute_download(
    conn: sqlite3.Connection,
    install_id: int,
    download_url: str,
    expected_sha256: str,
    dest_dir: Path,
    filename: str,
    *,
    cancel_event: asyncio.Event | None = None,
    _client: httpx.AsyncClient | None = None,
) -> None:
    """Stream *download_url* to *dest_dir*/*filename*, verify checksum, and finalize.

    Args:
        conn: Shared SQLite connection (check_same_thread=False assumed).
        install_id: Row ID in installed_models to update throughout the download.
        download_url: Remote URL to fetch.
        expected_sha256: 64-char lowercase hex digest to verify after download.
        dest_dir: Directory to store the completed file in (created if missing).
        filename: Final filename inside *dest_dir*.
        cancel_event: When set, the download stops cleanly and the record is
            marked 'cancelled'.  Checked between chunks so latency is bounded
            by *_CHUNK_SIZE*.
        _client: Injected httpx.AsyncClient for tests; production code leaves
            this None and a client is created and closed internally.
    """
    require_network(NetworkMode.EXPLICIT_DOWNLOAD)

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    part_path = dest_dir / f"{filename}.part"

    conn.execute(
        "UPDATE installed_models SET install_status = 'downloading', file_path = ? WHERE id = ?",
        (str(dest_path), install_id),
    )
    conn.commit()

    bytes_written = 0
    bytes_since_update = 0
    own_client = _client is None

    try:
        client = _client or httpx.AsyncClient(follow_redirects=True, timeout=30.0)
        try:
            async with client.stream("GET", download_url) as response:
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                size_bytes: int | None = int(content_length) if content_length else None

                with open(part_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=_CHUNK_SIZE):
                        if cancel_event is not None and cancel_event.is_set():
                            logger.info(
                                "download: cancel requested for install_id=%d", install_id
                            )
                            break
                        f.write(chunk)
                        bytes_written += len(chunk)
                        bytes_since_update += len(chunk)
                        if bytes_since_update >= _PROGRESS_INTERVAL:
                            update_install_progress(conn, install_id, bytes_written, size_bytes)
                            bytes_since_update = 0
        finally:
            if own_client:
                await client.aclose()

        if cancel_event is not None and cancel_event.is_set():
            if part_path.exists():
                part_path.unlink()
            mark_install_failed(
                conn, install_id, "Download cancelled by user.", status="cancelled"
            )
            return

        # Write final progress before verifying.
        update_install_progress(conn, install_id, bytes_written, bytes_written or None)

        if not verify_sha256(part_path, expected_sha256):
            logger.warning(
                "download: checksum mismatch for install_id=%d; deleting partial file", install_id
            )
            part_path.unlink()
            mark_install_failed(
                conn,
                install_id,
                "SHA-256 checksum mismatch. The downloaded file has been deleted.",
                status="checksum_mismatch",
            )
            return

        part_path.rename(dest_path)
        mark_install_ready(
            conn,
            install_id,
            size_bytes=bytes_written,
            verified_sha256=expected_sha256,
            file_path=str(dest_path),
        )
        logger.info(
            "download: install_id=%d complete; %d bytes at %s",
            install_id,
            bytes_written,
            dest_path,
        )

    except Exception as exc:
        logger.exception("download: error for install_id=%d", install_id)
        if part_path.exists():
            part_path.unlink()
        mark_install_failed(conn, install_id, str(exc))
