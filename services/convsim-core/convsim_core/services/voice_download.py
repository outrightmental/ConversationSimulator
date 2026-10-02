# SPDX-License-Identifier: Apache-2.0
"""Checksummed download of a single voice asset file.

The GGUF downloader in ``model_download_service`` is bound to an
``installed_models`` row — voice assets have no such row, so this module keeps
the same guarantees against a plain destination path instead:

  * streamed to ``<dest>.part`` so a half-written file is never mistaken for an
    installed model;
  * SHA-256 verified before the ``.part`` file is promoted — a mismatch deletes
    it and raises, so an unverified byte is never visible to an engine;
  * cancellable between chunks, leaving nothing behind.

A ``.part`` file only survives the app being *killed* mid-transfer; the next
attempt resumes it with an HTTP Range request (falling back to a clean restart
when the server answers 200 instead of 206). Every in-process failure — cancel,
transport error, checksum mismatch — removes it, matching the GGUF downloader.

Network access goes through the same ``NetworkMode.EXPLICIT_DOWNLOAD`` gate as
model weights, so nothing here can be reached from play-mode code.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable

import httpx

from convsim_core.network_policy import NetworkMode, require_network
from convsim_core.services.model_download_service import (
    parse_content_range_total,
    verify_sha256,
)

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 65_536  # 64 KB
_PROGRESS_INTERVAL = 1_048_576  # report progress at most every 1 MB


class ChecksumMismatch(Exception):
    """Raised when a completed download does not match its registry SHA-256."""


class DownloadCancelled(Exception):
    """Raised when the caller's cancel event fired mid-transfer."""


async def download_voice_asset(
    *,
    url: str,
    dest_path: Path,
    expected_sha256: str,
    progress_cb: Callable[[int, int | None], None] | None = None,
    cancel_event: asyncio.Event | None = None,
    _client: httpx.AsyncClient | None = None,
) -> int:
    """Download *url* to *dest_path*, verify it, and return the byte count.

    Raises ``DownloadCancelled`` when *cancel_event* fires, ``ChecksumMismatch``
    when verification fails, and propagates transport errors unchanged. Every
    failure path removes the ``.part`` file.
    """
    require_network(NetworkMode.EXPLICIT_DOWNLOAD)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest_path.with_name(dest_path.name + ".part")

    resume_from = part_path.stat().st_size if part_path.exists() else 0
    headers = {"Range": f"bytes={resume_from}-"} if resume_from > 0 else {}

    bytes_written = 0
    bytes_since_update = 0
    own_client = _client is None
    client = _client or httpx.AsyncClient(follow_redirects=True, timeout=30.0)

    try:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()

                resuming = resume_from > 0 and response.status_code == 206
                if resuming:
                    total: int | None = parse_content_range_total(
                        response.headers.get("content-range")
                    )
                    if total is None:
                        cl = response.headers.get("content-length")
                        total = resume_from + int(cl) if cl else None
                    open_mode = "ab"
                    bytes_written = resume_from
                    logger.info("voice-download: resuming %s from byte %d", dest_path.name, resume_from)
                else:
                    cl = response.headers.get("content-length")
                    total = int(cl) if cl else None
                    open_mode = "wb"

                if progress_cb is not None:
                    progress_cb(bytes_written, total)

                with open(part_path, open_mode) as f:
                    async for chunk in response.aiter_bytes(chunk_size=_CHUNK_SIZE):
                        if cancel_event is not None and cancel_event.is_set():
                            raise DownloadCancelled()
                        f.write(chunk)
                        bytes_written += len(chunk)
                        bytes_since_update += len(chunk)
                        if bytes_since_update >= _PROGRESS_INTERVAL and progress_cb is not None:
                            progress_cb(bytes_written, total)
                            bytes_since_update = 0
        finally:
            if own_client:
                await client.aclose()

        if progress_cb is not None:
            progress_cb(bytes_written, bytes_written)

        # Hashing is CPU/IO-bound; keep it off the event loop so progress polling
        # stays responsive while a several-hundred-MB model is verified.
        if not await asyncio.to_thread(verify_sha256, part_path, expected_sha256):
            part_path.unlink(missing_ok=True)
            raise ChecksumMismatch(
                f"SHA-256 of {dest_path.name} did not match the registry value. "
                "The downloaded file has been deleted."
            )

        part_path.replace(dest_path)
        logger.info("voice-download: %s complete (%d bytes)", dest_path, bytes_written)
        return bytes_written

    except BaseException:
        # Covers DownloadCancelled, transport errors and task cancellation alike.
        # Only a killed process leaves a .part behind to resume from; an
        # in-process failure cleans up, so a retry never resumes into bytes
        # fetched before a registry revision changed under it.
        part_path.unlink(missing_ok=True)
        raise
