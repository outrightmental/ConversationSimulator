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
  Windows x86_64 → win-x64
  Windows arm64  → win-arm64

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
import os
import platform as _platform
import shutil
import subprocess
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
    CHECKSUM_MISMATCH = "checksum_mismatch"
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
        if machine in ("x86_64", "amd64"):
            return "win-x64"
        if machine in ("aarch64", "arm64"):
            return "win-arm64"

    raise RuntimeError(
        f"Unsupported platform: {system}/{machine}. "
        "Build from source: https://github.com/ggml-org/llama.cpp#build"
    )


def detect_windows_gpu_variant() -> str:
    """Probe for GPU acceleration on Windows; return the best *downloadable* variant.

    Returns one of: ``"vulkan"`` or ``"cpu"`` (default).

    Never raises — detection failures always fall back to ``"cpu"``.  Callers
    should treat this as advisory: the CPU variant always works; the Vulkan
    variant is offered as an *opt-in* upgrade, never required for first-run.

    Vulkan is recommended for every GPU vendor (NVIDIA, AMD, Intel) because it
    ships as a single, self-contained llama.cpp release asset
    (``llama-{tag}-bin-win-vulkan-x64.zip``).  CUDA is deliberately *not*
    recommended here: llama.cpp publishes CUDA builds per toolkit version
    (``win-cuda-12.4-x64``, ``win-cuda-13.3-x64``, …) and each additionally
    requires a separate ``cudart-*`` runtime archive — neither of which the
    single-asset downloader in this module can satisfy, so recommending
    ``"cuda"`` would send the download to a nonexistent asset (404).  An NVIDIA
    GPU is therefore offered the Vulkan build; the NVIDIA driver ships the
    Vulkan runtime, so it accelerates on NVIDIA too.
    """
    try:
        if shutil.which("nvidia-smi"):
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return "vulkan"
    except Exception:  # noqa: BLE001
        pass

    try:
        if shutil.which("vulkaninfo"):
            result = subprocess.run(
                ["vulkaninfo", "--summary"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return "vulkan"
    except Exception:  # noqa: BLE001
        pass

    return "cpu"


def build_asset_name(release_tag: str, platform_string: str, *, variant: str = "cpu") -> str:
    """Return the expected ZIP asset name for a llama.cpp release.

    For Windows (``platform_string`` starts with ``"win-"``), the naming
    convention is ``llama-{tag}-bin-win-{variant}-{arch}.zip``
    e.g. ``llama-b5140-bin-win-cpu-x64.zip``.

    For Linux / macOS the convention is
    ``llama-{tag}-bin-{platform}-{variant}.zip``
    e.g. ``llama-b5140-bin-linux-x64-cpu.zip``.
    """
    if platform_string.startswith("win-"):
        arch = platform_string[len("win-"):]  # "x64" or "arm64"
        return f"llama-{release_tag}-bin-win-{variant}-{arch}.zip"
    return f"llama-{release_tag}-bin-{platform_string}-{variant}.zip"


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


def _extract_runtime_files_from_zip(data: bytes) -> tuple[bytes, dict[str, bytes]]:
    """Return the llama-server binary bytes plus its sibling runtime files.

    Windows llama.cpp release archives ship ``llama-server.exe`` *dynamically*
    linked against DLLs (``ggml.dll``, ``ggml-base.dll``, ``ggml-cpu.dll``,
    ``llama.dll``, …) that live in the same archive directory.  Extracting the
    executable alone yields a binary that cannot start ("the code execution
    cannot proceed because ggml.dll was not found"), so this returns the binary
    bytes together with a ``{basename: bytes}`` map of every *other* file in the
    same directory so the caller can install them alongside the executable.

    Raises RuntimeError when the binary is not found.
    """
    target_names = {"llama-server", "llama-server.exe"}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        server_name: str | None = None
        for name in zf.namelist():
            if Path(name).name.lower() in target_names:
                server_name = name
                break
        if server_name is None:
            raise RuntimeError(
                "llama-server binary not found in the downloaded archive. "
                "The release asset format may have changed."
            )
        server_dir = Path(server_name).parent
        binary_basename = Path(server_name).name
        binary_bytes = zf.read(server_name)
        siblings: dict[str, bytes] = {}
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            candidate = Path(name)
            if candidate.parent != server_dir or candidate.name == binary_basename:
                continue
            siblings[candidate.name] = zf.read(name)
        return binary_bytes, siblings


async def download_binary(
    *,
    dest_dir: Path,
    version: str | None = None,
    platform_string: str | None = None,
    variant: str = "cpu",
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
            ``"linux-x64"`` or ``"win-x64"``.
        variant: Build variant — ``"cpu"`` (default, universally safe) or
            ``"vulkan"`` (GPU acceleration, Windows only).  On Windows, use
            :func:`detect_windows_gpu_variant` to discover the recommended
            variant; on Linux/macOS ``"cpu"`` is the only supported variant
            here.  (``"cuda"`` is not supported — llama.cpp CUDA builds are
            published per toolkit version and need a separate cudart archive.)
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
            mismatch, binary missing from archive, or destination locked.
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
            try:
                release_tag = await fetch_latest_release_tag(client)
            except (httpx.ConnectError, httpx.NetworkError, httpx.TimeoutException) as exc:
                raise RuntimeError(
                    "Cannot reach GitHub to fetch the latest release — "
                    "check your internet connection. "
                    "Engine download requires a network connection (~5 MB)."
                ) from exc
        progress.release_tag = release_tag

        asset_name = build_asset_name(release_tag, platform_string, variant=variant)
        asset_url = build_asset_url(release_tag, asset_name)
        sha256sum_url = build_sha256sum_url(release_tag)

        expected_sha256 = await fetch_expected_sha256(client, sha256sum_url, asset_name)

        _check_cancel()
        progress.state = DownloadState.DOWNLOADING
        if progress_cb:
            progress_cb(progress)

        data = bytearray()
        try:
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
        except (httpx.ConnectError, httpx.NetworkError, httpx.TimeoutException) as exc:
            raise RuntimeError(
                "Network error while downloading engine binary — "
                "check your internet connection and try again. "
                "Engine download requires a network connection (~5 MB)."
            ) from exc

        _check_cancel()
        progress.state = DownloadState.VERIFYING
        if progress_cb:
            progress_cb(progress)

        actual_sha256 = await asyncio.to_thread(_sha256_of_bytes, bytes(data))
        if expected_sha256 is not None and actual_sha256 != expected_sha256:
            progress.state = DownloadState.CHECKSUM_MISMATCH
            if progress_cb:
                progress_cb(progress)
            raise RuntimeError(
                f"SHA-256 checksum mismatch for {asset_name}. "
                f"Expected {expected_sha256}, got {actual_sha256}. "
                "The downloaded file may be corrupted. Try again."
            )

        _check_cancel()
        progress.state = DownloadState.EXTRACTING
        if progress_cb:
            progress_cb(progress)

        dest_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".exe" if sys.platform == "win32" else ""
        dest_path = dest_dir / f"{_BINARY_NAME}{suffix}"
        part_path = dest_dir / f"{_BINARY_NAME}{suffix}.part"

        if sys.platform == "win32":
            # Windows binaries are dynamically linked against sibling DLLs that
            # ship in the same archive directory; install them alongside the
            # executable or it cannot start.
            binary_data, sibling_files = await asyncio.to_thread(
                _extract_runtime_files_from_zip, bytes(data)
            )
        else:
            binary_data = await asyncio.to_thread(_extract_binary_from_zip, bytes(data))
            sibling_files = {}

        def _locked_error(name: str) -> RuntimeError:
            return RuntimeError(
                f"Cannot replace {name}: the file is in use. "
                "Stop the running inference engine before upgrading."
            )

        def _write() -> None:
            try:
                # Install sibling runtime files (DLLs) first so the executable
                # never resolves before its dependencies are present on disk.
                for fname, content in sibling_files.items():
                    sib = dest_dir / fname
                    try:
                        sib.write_bytes(content)
                    except PermissionError as exc:
                        raise _locked_error(sib.name) from exc
                part_path.write_bytes(binary_data)
                if sys.platform != "win32":
                    part_path.chmod(0o755)
                try:
                    os.replace(str(part_path), str(dest_path))
                except PermissionError as exc:
                    raise _locked_error(dest_path.name) from exc
            except BaseException:
                try:
                    part_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise

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
        if progress.state not in (DownloadState.CHECKSUM_MISMATCH, DownloadState.CANCELLED):
            progress.state = DownloadState.FAILED
        progress.error = str(exc)
        if progress_cb:
            progress_cb(progress)
        raise

    finally:
        if own_client:
            await client.aclose()
