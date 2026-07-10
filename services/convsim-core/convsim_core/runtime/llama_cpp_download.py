# SPDX-License-Identifier: Apache-2.0
"""Platform-aware downloader for the llama-server binary.

Downloads a pre-built llama-server from GitHub releases, verifies the
SHA-256 checksum against the release's sha256sum.txt, extracts the binary
from the ZIP archive, and installs it to a caller-specified directory.

This module provides the programmatic equivalent of runtimes/llama_cpp/
download-runtime.sh so the desktop app can trigger a binary install from
Settings without the user leaving the app or running a shell script.

Supported platforms
-------------------
  Linux  x86_64  → linux-x64
  Linux  aarch64 → linux-arm64
  macOS  arm64   → macos-arm64  (Apple Silicon)
  macOS  x86_64  → macos-x64   (Intel Mac)

Windows native binaries are not supported here; Windows users should use
WSL2 (targeting the linux-x64 asset) or build from source.

Usage
-----
::

    from pathlib import Path
    from convsim_core.runtime.llama_cpp_download import download_binary

    binary_path = await download_binary(
        dest_dir=Path.home() / ".convsim" / "bin",
        version="b5140",          # omit for latest
    )
    # binary_path is the absolute path to the installed llama-server binary
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import platform as _platform
import sys
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

import httpx

_GITHUB_REPO = "ggml-org/llama.cpp"
_GITHUB_API = "https://api.github.com"
_GITHUB_RELEASES = "https://github.com"
_BINARY_NAME = "llama-server"
_CHUNK_SIZE = 65_536  # 64 KB


class DownloadState(str, Enum):
    IDLE = "idle"
    FETCHING_RELEASE = "fetching_release"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    EXTRACTING = "extracting"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadProgress:
    """Point-in-time snapshot of a binary download operation."""

    state: DownloadState = DownloadState.IDLE
    bytes_downloaded: int = 0
    total_bytes: int | None = None
    error: str | None = None
    binary_path: str | None = None
    release_tag: str | None = None


def detect_platform_string() -> str:
    """Return the llama.cpp release platform tag for this machine.

    Matches the naming used by the GitHub release assets so the download URL
    can be constructed deterministically.

    Raises RuntimeError for unsupported OS/architecture combinations.
    """
    system = sys.platform
    machine = _platform.machine().lower()

    if system.startswith("linux"):
        if machine in ("x86_64", "amd64"):
            return "linux-x64"
        if machine in ("aarch64", "arm64"):
            return "linux-arm64"
    elif system == "darwin":
        if machine == "arm64":
            return "macos-arm64"
        if machine in ("x86_64", "amd64"):
            return "macos-x64"
    elif system == "win32":
        raise RuntimeError(
            "Native Windows binary download is not supported. "
            "Use WSL2 with the Linux binary, or build from source: "
            "https://github.com/ggml-org/llama.cpp#build"
        )

    raise RuntimeError(
        f"Unsupported platform: {system}/{machine}. "
        "Build from source: https://github.com/ggml-org/llama.cpp#build"
    )


def build_asset_name(release_tag: str, platform_string: str) -> str:
    """Return the expected ZIP asset name for a llama.cpp release.

    Convention: ``llama-{tag}-bin-{platform}-cpu.zip``
    """
    return f"llama-{release_tag}-bin-{platform_string}-cpu.zip"


def build_asset_url(release_tag: str, asset_name: str) -> str:
    """Return the GitHub download URL for *asset_name* in *release_tag*."""
    return f"{_GITHUB_RELEASES}/{_GITHUB_REPO}/releases/download/{release_tag}/{asset_name}"


def build_sha256sum_url(release_tag: str) -> str:
    """Return the URL for the sha256sum.txt file published alongside a release."""
    return f"{_GITHUB_RELEASES}/{_GITHUB_REPO}/releases/download/{release_tag}/sha256sum.txt"


async def fetch_latest_release_tag(client: httpx.AsyncClient) -> str:
    """Return the latest llama.cpp release tag from the GitHub API.

    Raises httpx.HTTPStatusError on non-200 responses.
    """
    resp = await client.get(
        f"{_GITHUB_API}/repos/{_GITHUB_REPO}/releases/latest",
        headers={"Accept": "application/vnd.github.v3+json"},
        follow_redirects=True,
    )
    resp.raise_for_status()
    tag = resp.json().get("tag_name", "")
    if not tag:
        raise RuntimeError("GitHub API returned a release with no tag_name.")
    return tag


async def fetch_expected_sha256(
    client: httpx.AsyncClient, sha256sum_url: str, asset_name: str
) -> str | None:
    """Return the expected hex digest for *asset_name* from sha256sum.txt.

    Returns None when the file is absent (404) or the asset isn't listed.
    The caller decides whether a missing checksum is acceptable.
    """
    try:
        resp = await client.get(sha256sum_url, follow_redirects=True)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.TransportError):
        return None

    for line in resp.text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            digest, name = parts
            if name.lstrip("*") == asset_name:
                return digest.lower()
    return None


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def _extract_binary_from_zip(data: bytes) -> bytes:
    """Return the llama-server binary bytes from a ZIP archive.

    Raises RuntimeError when the expected binary is not found.
    """
    target_names = {"llama-server", "llama-server.exe"}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if Path(name).name.lower() in target_names:
                return zf.read(name)
    raise RuntimeError(
        "llama-server binary not found in the downloaded archive. "
        "The release asset format may have changed."
    )


async def download_binary(
    *,
    dest_dir: Path,
    version: str | None = None,
    platform_string: str | None = None,
    cancel_event: asyncio.Event | None = None,
    progress_cb: Callable[[DownloadProgress], None] | None = None,
    _client: httpx.AsyncClient | None = None,
    _timeout: float = 120.0,
) -> str:
    """Download, verify, and install the llama-server binary.

    Args:
        dest_dir: Directory where the binary will be placed.
        version: Exact release tag to download (e.g. ``"b5140"``).  Omit to
            auto-fetch the latest release.
        platform_string: Override the auto-detected platform (useful in
            tests).  Must match a llama.cpp release asset segment, e.g.
            ``"linux-x64"``.
        cancel_event: When set, the download stops cleanly and
            ``asyncio.CancelledError`` is raised.  Checked between chunks.
        progress_cb: Called after each significant state or byte-count change
            with a ``DownloadProgress`` snapshot.
        _client: Injected ``httpx.AsyncClient`` for tests.  Production code
            leaves this None; a client is created and closed internally.
        _timeout: HTTP request timeout in seconds.

    Returns:
        Absolute path string of the installed binary.

    Raises:
        RuntimeError: Platform not supported, download failed, checksum
            mismatch, or binary missing from archive.
        asyncio.CancelledError: *cancel_event* was set.
    """
    if platform_string is None:
        platform_string = detect_platform_string()

    progress = DownloadProgress(state=DownloadState.FETCHING_RELEASE)
    if progress_cb:
        progress_cb(progress)

    def _check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError("Binary download cancelled by user.")

    own_client = _client is None
    client = _client or httpx.AsyncClient(follow_redirects=True, timeout=_timeout)

    try:
        release_tag = version
        if release_tag is None:
            release_tag = await fetch_latest_release_tag(client)
        progress.release_tag = release_tag

        asset_name = build_asset_name(release_tag, platform_string)
        asset_url = build_asset_url(release_tag, asset_name)
        sha256sum_url = build_sha256sum_url(release_tag)

        expected_sha256 = await fetch_expected_sha256(client, sha256sum_url, asset_name)

        _check_cancel()
        progress.state = DownloadState.DOWNLOADING
        if progress_cb:
            progress_cb(progress)

        data = bytearray()
        async with client.stream("GET", asset_url) as resp:
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Download failed: HTTP {resp.status_code} for {asset_url}. "
                    f"Check that release {release_tag} has asset {asset_name}. "
                    f"Browse releases: https://github.com/{_GITHUB_REPO}/releases"
                )
            content_length = resp.headers.get("content-length")
            progress.total_bytes = int(content_length) if content_length else None
            async for chunk in resp.aiter_bytes(_CHUNK_SIZE):
                _check_cancel()
                data.extend(chunk)
                progress.bytes_downloaded = len(data)
                if progress_cb:
                    progress_cb(progress)

        _check_cancel()
        progress.state = DownloadState.VERIFYING
        if progress_cb:
            progress_cb(progress)

        actual_sha256 = await asyncio.to_thread(_sha256_of_bytes, bytes(data))
        if expected_sha256 is not None and actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"SHA-256 checksum mismatch for {asset_name}. "
                f"Expected {expected_sha256}, got {actual_sha256}. "
                "The downloaded file may be corrupted. Try again."
            )

        _check_cancel()
        progress.state = DownloadState.EXTRACTING
        if progress_cb:
            progress_cb(progress)

        binary_data: bytes = await asyncio.to_thread(_extract_binary_from_zip, bytes(data))

        dest_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".exe" if sys.platform == "win32" else ""
        dest_path = dest_dir / f"{_BINARY_NAME}{suffix}"

        def _write() -> None:
            dest_path.write_bytes(binary_data)
            dest_path.chmod(0o755)

        await asyncio.to_thread(_write)

        progress.state = DownloadState.COMPLETE
        progress.binary_path = str(dest_path)
        if progress_cb:
            progress_cb(progress)

        return str(dest_path)

    except asyncio.CancelledError:
        progress.state = DownloadState.CANCELLED
        if progress_cb:
            progress_cb(progress)
        raise

    except Exception as exc:
        progress.state = DownloadState.FAILED
        progress.error = str(exc)
        if progress_cb:
            progress_cb(progress)
        raise

    finally:
        if own_client:
            await client.aclose()
