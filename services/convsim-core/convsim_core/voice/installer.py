# SPDX-License-Identifier: Apache-2.0
"""Download, verify and unpack one voice asset.

The rules are the model download policy's (``docs/model-download-policy.md``):

* nothing is fetched that the catalog does not pin;
* every file is streamed to a ``.part`` and promoted only once its SHA-256
  matches, so a damaged or substituted download is never installed;
* an interrupted download resumes from where it stopped;
* a cancel leaves nothing behind.

An asset is assembled in a staging folder and swapped into place in one step,
with its marker written last, so a half-finished install is never mistaken
for a finished one.
"""
from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import logging
import os
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

import httpx

from convsim_core.network_policy import NetworkMode, require_network
from convsim_core.voice.catalog import VoiceAsset, VoiceDownload
from convsim_core.voice.layout import VoiceLayout

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 65_536

ERROR_CODE_CHECKSUM = "CHECKSUM"
ERROR_CODE_DISK = "DISK"
ERROR_CODE_ARCHIVE = "ARCHIVE"


class VoiceInstallError(Exception):
    """An install failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class VoiceInstallCancelled(Exception):
    """The player cancelled; everything staged has been removed."""


ProgressCallback = Callable[[int, int], None]
"""Called with (bytes so far, total bytes) for the asset being installed."""


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest().lower()


def _download_name(index: int, download: VoiceDownload) -> str:
    """A flat, collision-free staging name for one download."""
    tail = PurePosixPath(download.dest or download.url).name
    return f"{index:02d}-{tail}"


async def _fetch(
    client: httpx.AsyncClient,
    download: VoiceDownload,
    final_path: Path,
    *,
    cancel_event: Optional[asyncio.Event],
    on_bytes: Callable[[int], None],
) -> None:
    """Stream one download to ``final_path``, verified.

    A file already at ``final_path`` was verified by an earlier attempt and is
    kept. A ``.part`` beside it is resumed with a Range request.
    """
    if final_path.is_file() and final_path.stat().st_size == download.size_bytes:
        on_bytes(download.size_bytes)
        return

    part_path = final_path.with_name(final_path.name + ".part")
    resume_from = part_path.stat().st_size if part_path.exists() else 0
    if resume_from > download.size_bytes:
        # Longer than the pinned file can be: not a resumable piece of it.
        part_path.unlink()
        resume_from = 0
    headers = {"Range": f"bytes={resume_from}-"} if resume_from > 0 else {}

    if resume_from < download.size_bytes:
        async with client.stream("GET", download.url, headers=headers) as response:
            response.raise_for_status()
            # Honour the resume only when the server confirms it with a 206; a
            # plain 200 means the Range was ignored and the body starts at zero.
            resuming = resume_from > 0 and response.status_code == 206
            written = resume_from if resuming else 0
            on_bytes(written)
            with open(part_path, "ab" if resuming else "wb") as fh:
                async for chunk in response.aiter_bytes(chunk_size=_CHUNK_SIZE):
                    if cancel_event is not None and cancel_event.is_set():
                        raise VoiceInstallCancelled()
                    fh.write(chunk)
                    written += len(chunk)
                    on_bytes(written)

    if cancel_event is not None and cancel_event.is_set():
        raise VoiceInstallCancelled()

    actual_size = part_path.stat().st_size
    actual_sha256 = await asyncio.to_thread(_sha256_of, part_path)
    if actual_size != download.size_bytes or actual_sha256 != download.sha256.lower():
        part_path.unlink(missing_ok=True)
        logger.warning(
            "voice install: %s did not verify (size %d, expected %d; sha256 %s, expected %s)",
            download.url, actual_size, download.size_bytes, actual_sha256, download.sha256,
        )
        raise VoiceInstallError(
            ERROR_CODE_CHECKSUM,
            "A downloaded file did not match its expected checksum, so it was "
            "discarded and nothing was installed. Try again; if it keeps "
            "happening, the file may have changed at its source.",
        )
    os.replace(part_path, final_path)


def _member_target(name: str, download: VoiceDownload) -> Optional[str]:
    """Where an archive member unpacks to, or None when it is not wanted.

    Returns a POSIX-style path relative to the asset folder. A member whose
    path is absolute or climbs out with ``..`` is refused.
    """
    parts = [p for p in PurePosixPath(name).parts if p not in ("", ".")]
    if not parts or PurePosixPath(name).is_absolute() or ".." in parts:
        return None
    parts = parts[download.strip_components:]
    if not parts:
        return None
    relative = "/".join(parts)
    if download.keep and not any(fnmatch.fnmatchcase(relative, pat) for pat in download.keep):
        return None
    return relative


def _unpack(
    archive_path: Path,
    download: VoiceDownload,
    content_dir: Path,
    cancel_event: Optional[asyncio.Event],
) -> int:
    """Unpack the wanted regular files of a tar archive. Returns the count.

    Only regular files are written. Links and device nodes are skipped: none
    of the pinned archives needs one, and they are how a hostile archive
    writes outside its folder.
    """
    count = 0
    root = content_dir.resolve()
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            for member in archive:
                if cancel_event is not None and cancel_event.is_set():
                    raise VoiceInstallCancelled()
                if not member.isfile():
                    continue
                relative = _member_target(member.name, download)
                if relative is None:
                    continue
                target = (content_dir / relative).resolve()
                if root != target and root not in target.parents:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    continue
                with source, open(target, "wb") as out:
                    shutil.copyfileobj(source, out, length=1_048_576)
                if sys.platform != "win32" and member.mode & 0o111:
                    target.chmod(0o755)
                count += 1
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise VoiceInstallError(
            ERROR_CODE_ARCHIVE, f"A downloaded archive could not be unpacked ({exc})."
        ) from exc
    return count


def discard_staging(layout: VoiceLayout, asset: Optional[VoiceAsset] = None) -> None:
    """Remove staged downloads: one asset's, or all of them."""
    target = layout.staging_dir(asset) if asset is not None else layout.staging_root
    shutil.rmtree(target, ignore_errors=True)


def check_free_space(layout: VoiceLayout, assets: list[VoiceAsset]) -> None:
    """Raise when the voice folder's drive cannot hold the install.

    An archive exists twice for a moment (packed and unpacked) and unpacks to
    more than its download size, so the need is taken as three times the
    archives plus the plain files once.
    """
    layout.root.mkdir(parents=True, exist_ok=True)
    needed = 0
    for asset in assets:
        for download in asset.downloads:
            needed += download.size_bytes * (3 if download.unpack else 1)
    free = shutil.disk_usage(str(layout.root)).free
    if free < needed:
        raise VoiceInstallError(
            ERROR_CODE_DISK,
            f"Not enough disk space for voice: {free / 1024 ** 2:.0f} MB free, "
            f"about {needed / 1024 ** 2:.0f} MB needed. Free up space and try again.",
        )


async def install_asset(
    asset: VoiceAsset,
    layout: VoiceLayout,
    *,
    client: httpx.AsyncClient,
    cancel_event: Optional[asyncio.Event] = None,
    on_progress: Optional[ProgressCallback] = None,
    on_phase: Optional[Callable[[str], None]] = None,
) -> None:
    """Download, verify and install *asset*, replacing any earlier copy.

    ``on_phase`` is told ``"downloading"`` then ``"unpacking"``, so a progress
    bar that has reached 100% can say what it is still waiting for.

    Raises :class:`VoiceInstallCancelled` after removing everything staged,
    :class:`VoiceInstallError` for a checksum, disk or archive problem, and
    lets ``httpx`` errors through so the caller can offer a retry (the staged
    ``.part`` is kept for exactly that).
    """
    require_network(NetworkMode.EXPLICIT_DOWNLOAD)

    staging = layout.staging_dir(asset)
    downloads_dir = staging / "downloads"
    content_dir = staging / "content"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    total = asset.download_bytes
    done_before = 0

    def report(current_file_bytes: int) -> None:
        if on_progress is not None:
            on_progress(min(done_before + current_file_bytes, total), total)

    try:
        if on_phase is not None:
            on_phase("downloading")
        fetched: list[tuple[VoiceDownload, Path]] = []
        for index, download in enumerate(asset.downloads):
            path = downloads_dir / _download_name(index, download)
            await _fetch(client, download, path, cancel_event=cancel_event, on_bytes=report)
            done_before += download.size_bytes
            fetched.append((download, path))

        if on_phase is not None:
            on_phase("unpacking")
        # Assemble from scratch: a content folder left by an attempt that died
        # while unpacking is not trusted. Archives go first because unpacking
        # is the step that can fail; moving a verified file cannot, so a
        # failure here leaves every download in place for the retry.
        shutil.rmtree(content_dir, ignore_errors=True)
        content_dir.mkdir(parents=True)
        for download, path in fetched:
            if download.unpack:
                unpacked = await asyncio.to_thread(
                    _unpack, path, download, content_dir, cancel_event
                )
                logger.info("voice install: unpacked %d files from %s", unpacked, path.name)
        for download, path in fetched:
            if not download.unpack:
                target = content_dir / download.dest
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(path, target)

        missing = [rel for rel in asset.required_files if not (content_dir / rel).is_file()]
        if missing:
            raise VoiceInstallError(
                ERROR_CODE_ARCHIVE,
                f"The {asset.label.lower()} download is missing expected files: "
                f"{', '.join(missing)}.",
            )

        layout.write_marker(asset, content_dir)
        final_dir = layout.asset_dir(asset)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        # Steam must never sync this folder (issue #221): it is large, and
        # re-downloadable.
        (layout.root / ".nosteamcloudpath").touch(exist_ok=True)
        if final_dir.exists():
            try:
                shutil.rmtree(final_dir)
            except OSError as exc:
                raise VoiceInstallError(
                    ERROR_CODE_DISK,
                    f"Could not replace the installed {asset.label.lower()}: a file "
                    f"is in use ({exc}). Close any conversation using voice and try again.",
                ) from exc
        os.replace(content_dir, final_dir)
        shutil.rmtree(staging, ignore_errors=True)
        try:
            # Gone once nothing else is staged; a sibling asset's resumable
            # download keeps it.
            layout.staging_root.rmdir()
        except OSError:
            pass
    except VoiceInstallCancelled:
        discard_staging(layout, asset)
        raise
    except VoiceInstallError as exc:
        if exc.code != ERROR_CODE_CHECKSUM:
            # A verified download is still good; only the assembly is redone.
            shutil.rmtree(content_dir, ignore_errors=True)
        raise
