# SPDX-License-Identifier: Apache-2.0
"""Platform-aware downloader for the llama-server binary.

Downloads the pinned llama.cpp release archive for this platform, verifies its
SHA-256 against the digest pinned in ``runtimes/llama_cpp/pin.json``, and
installs ``llama-server`` with the shared libraries it links against.

This is the programmatic equivalent of ``runtimes/llama_cpp/download-runtime.sh``
and ``download-runtime.ps1``, so the app can install an engine without the
player running a script. It is only reached when no engine is bundled, which in
practice means a build from source: every Steam build bundles both engines
(issue #530).

Verification is not optional. Upstream publishes no checksum file, so the pin is
the only source of an expected digest; an archive the pin has no digest for, or
one whose digest does not match, is never installed (issue #530).

Supported platforms (see ``llama_cpp_pin`` for the exact asset names)
--------------------------------------------------------------------
  Linux  x86_64  → linux-x64    (cpu / vulkan)
  Linux  aarch64 → linux-arm64  (cpu / vulkan)
  macOS  arm64   → macos-arm64  (the default build uses Metal)
  macOS  x86_64  → macos-x64
  Windows x86_64 → win-x64      (cpu / vulkan)
  Windows arm64  → win-arm64    (cpu)

Usage
-----
::

    from pathlib import Path
    from convsim_core.runtime.llama_cpp_download import download_binary

    binary_path = await download_binary(dest_dir=Path.home() / ".convsim" / "bin")
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
import tarfile
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Callable

import httpx

from convsim_core.runtime.llama_cpp_pin import (
    LlamaCppPin,
    PinError,
    asset_name as _pinned_asset_name,
    is_zip,
    load_pin,
)

_GITHUB_REPO = "ggml-org/llama.cpp"
_GITHUB_RELEASES = "https://github.com"
_BINARY_NAME = "llama-server"
_CHUNK_SIZE = 65_536  # 64 KB
#: Name the upstream licence is installed under, as download-runtime.sh does.
_LICENSE_NAME = "LICENSE-llama.cpp.txt"


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


@dataclass
class RuntimeFiles:
    """What an archive contributes to an install directory.

    ``files`` maps a basename to its bytes; ``symlinks`` maps a basename to the
    basename it points at (the versioned ``libX.so -> libX.so.0`` chain the
    engine links against by its symlink name).
    """

    binary: bytes
    files: dict[str, bytes] = field(default_factory=dict)
    symlinks: dict[str, str] = field(default_factory=dict)


def detect_platform_string() -> str:
    """Return the engine platform id for this machine.

    One of ``win-x64``, ``win-arm64``, ``linux-x64``, ``linux-arm64``,
    ``macos-arm64``, ``macos-x64``. :func:`build_asset_name` maps it to the
    name upstream publishes (Linux builds are named ``ubuntu-*`` there).

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
    """Probe for a graphics driver on Windows; return ``"vulkan"`` or ``"cpu"``.

    Kept for ``GET /api/sidecar/gpu-variant``. Which engine actually runs is
    decided by the engine itself (``llama-server --list-devices`` from the
    Vulkan build; see ``runtime/engine_variant.py``), not by this probe.

    Never raises — detection failures always fall back to ``"cpu"``. CUDA is
    deliberately never returned: llama.cpp publishes CUDA builds per toolkit
    version plus a separate cudart archive, and the Vulkan build accelerates
    NVIDIA cards too (the NVIDIA driver ships the Vulkan runtime).
    """
    # Suppress the console window Windows would otherwise flash for each probe;
    # this runs behind a GUI Tauri app with no attached console. The flag only
    # exists on Windows, so fall back to 0 (no-op) everywhere else.
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        if shutil.which("nvidia-smi"):
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                timeout=5,
                creationflags=no_window,
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
                creationflags=no_window,
            )
            if result.returncode == 0:
                return "vulkan"
    except Exception:  # noqa: BLE001
        pass

    return "cpu"


def build_asset_name(release_tag: str, platform_string: str, *, variant: str = "cpu") -> str:
    """Return the upstream archive name for a llama.cpp release.

    Windows: ``llama-{tag}-bin-win-{cpu|vulkan}-{arch}.zip``.
    Linux: ``llama-{tag}-bin-ubuntu[-vulkan]-{arch}.tar.gz``.
    macOS: ``llama-{tag}-bin-macos-{arch}.tar.gz``.

    Raises ValueError for a platform or variant upstream does not publish.
    """
    return _pinned_asset_name(release_tag, platform_string, variant)


def build_asset_url(release_tag: str, asset_name: str) -> str:
    """Return the GitHub download URL for *asset_name* in *release_tag*."""
    return f"{_GITHUB_RELEASES}/{_GITHUB_REPO}/releases/download/{release_tag}/{asset_name}"


def expected_sha256(asset_name: str, *, release_tag: str, pin: LlamaCppPin) -> str:
    """The digest *asset_name* must have. Raises PinError when none is pinned.

    Only the pinned tag has digests. Another tag needs its digest passed
    explicitly (``download_binary(sha256=...)``).
    """
    if release_tag != pin.tag:
        raise PinError(
            f"llama.cpp {release_tag} is not the pinned release ({pin.tag}), so there is no "
            "pinned SHA-256 to verify it against. Pass its digest explicitly."
        )
    return pin.digest_for(asset_name)


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def _is_server_name(name: str) -> bool:
    return PurePosixPath(name).name.lower() in {"llama-server", "llama-server.exe"}


def _is_shared_library(name: str) -> bool:
    return name.endswith(".so") or ".so." in name or name.endswith(".dylib")


def _extract_runtime_files_from_zip(data: bytes) -> RuntimeFiles:
    """The engine and every other file beside it in a Windows ``.zip``.

    Windows archives ship ``llama-server.exe`` dynamically linked against DLLs
    (``ggml.dll``, ``ggml-base.dll``, ``ggml-cpu-*.dll``, ``llama.dll``, …) in
    the same directory; the executable alone cannot start ("ggml.dll was not
    found"). Every file in that directory is returned, exactly as
    ``download-runtime.ps1`` copies them.

    Raises RuntimeError when the binary is not found.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        server_name = next((n for n in names if _is_server_name(n)), None)
        if server_name is None:
            raise RuntimeError(
                "llama-server binary not found in the downloaded archive. "
                "The release asset format may have changed."
            )
        server_dir = PurePosixPath(server_name).parent
        result = RuntimeFiles(binary=zf.read(server_name))
        for name in names:
            if name.endswith("/") or name == server_name:
                continue
            candidate = PurePosixPath(name)
            if candidate.parent != server_dir:
                continue
            result.files[candidate.name] = zf.read(name)
        return result


def _extract_runtime_files_from_tar(data: bytes) -> RuntimeFiles:
    """The engine, its shared libraries (symlinks kept) and LICENSE from a ``.tar.gz``.

    Linux and macOS archives put everything under ``llama-<tag>/``.
    ``llama-server`` links its libraries by their SONAME, which is a symlink in
    a versioned chain (``libllama.so -> libllama.so.0 -> libllama.so.0.0.9415``),
    so the links are recreated rather than dropped or duplicated — the same
    selection ``download-runtime.sh`` makes with ``find -type f -o -type l``
    and ``cp -a``. The other command-line tools in the archive are not needed.

    A link is only kept when it points at a sibling by bare name: an archive
    cannot use one to write outside the install directory.

    Raises RuntimeError when the binary is not found.
    """
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        members = tf.getmembers()
        server = next(
            (m for m in members if m.isfile() and _is_server_name(m.name)),
            None,
        )
        if server is None:
            raise RuntimeError(
                "llama-server binary not found in the downloaded archive. "
                "The release asset format may have changed."
            )
        server_dir = PurePosixPath(server.name).parent
        fh = tf.extractfile(server)
        assert fh is not None
        result = RuntimeFiles(binary=fh.read())
        for member in members:
            path = PurePosixPath(member.name)
            if path.parent != server_dir or member.name == server.name:
                continue
            base = path.name
            if member.issym():
                target = member.linkname
                if _is_shared_library(base) and target and "/" not in target and target not in (".", ".."):
                    result.symlinks[base] = target
                continue
            if not member.isfile():
                continue
            if _is_shared_library(base):
                fh = tf.extractfile(member)
                if fh is not None:
                    result.files[base] = fh.read()
            elif base == "LICENSE":
                fh = tf.extractfile(member)
                if fh is not None:
                    result.files[_LICENSE_NAME] = fh.read()
        return result


def extract_runtime_files(data: bytes, asset_name: str) -> RuntimeFiles:
    """Read the files to install out of a downloaded archive."""
    if is_zip(asset_name):
        return _extract_runtime_files_from_zip(data)
    return _extract_runtime_files_from_tar(data)


async def download_binary(
    *,
    dest_dir: Path,
    version: str | None = None,
    platform_string: str | None = None,
    variant: str = "cpu",
    sha256: str | None = None,
    pin: LlamaCppPin | None = None,
    cancel_event: asyncio.Event | None = None,
    progress_cb: Callable[[DownloadProgress], None] | None = None,
    _client: httpx.AsyncClient | None = None,
    _timeout: float = 120.0,
) -> str:
    """Download, verify, and install the llama-server binary.

    Args:
        dest_dir: Directory where the engine is installed. The Vulkan build
            belongs in its own directory (``~/.convsim/bin/vulkan``), so that
            the default engine never sits beside the Vulkan backend library.
        version: Release tag. Omit for the pinned tag, which is the only one
            with pinned digests.
        platform_string: Override the auto-detected platform id (tests).
        variant: ``"cpu"`` (the default build; on macOS it uses Metal) or
            ``"vulkan"`` (Windows x64 and Linux).
        sha256: The expected digest, for a tag that is not pinned. Ignored
            when it is None and the tag is pinned.
        pin: The pin to verify against (tests). Defaults to the shipped pin.
        cancel_event: When set, the download stops cleanly and
            ``asyncio.CancelledError`` is raised. Checked between chunks.
        progress_cb: Called after each significant state or byte-count change
            with a ``DownloadProgress`` snapshot.
        _client: Injected ``httpx.AsyncClient`` for tests.
        _timeout: HTTP request timeout in seconds.

    Returns:
        Absolute path string of the installed binary.

    Raises:
        RuntimeError: Platform not supported, no pinned digest, download
            failed, checksum mismatch, binary missing from the archive, or
            destination locked.
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
        if pin is None:
            pin = load_pin()
        release_tag = version or pin.tag
        progress.release_tag = release_tag

        try:
            asset_name = build_asset_name(release_tag, platform_string, variant=variant)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        asset_url = build_asset_url(release_tag, asset_name)
        wanted_sha256 = (sha256 or "").strip().lower() or expected_sha256(
            asset_name, release_tag=release_tag, pin=pin
        )

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
                "Engine download requires a network connection."
            ) from exc

        _check_cancel()
        progress.state = DownloadState.VERIFYING
        if progress_cb:
            progress_cb(progress)

        actual_sha256 = await asyncio.to_thread(_sha256_of_bytes, bytes(data))
        if actual_sha256 != wanted_sha256:
            progress.state = DownloadState.CHECKSUM_MISMATCH
            if progress_cb:
                progress_cb(progress)
            raise RuntimeError(
                f"SHA-256 checksum mismatch for {asset_name}. "
                f"Expected {wanted_sha256}, got {actual_sha256}. "
                "The downloaded file may be corrupted. Try again."
            )

        _check_cancel()
        progress.state = DownloadState.EXTRACTING
        if progress_cb:
            progress_cb(progress)

        runtime_files = await asyncio.to_thread(extract_runtime_files, bytes(data), asset_name)

        dest_dir.mkdir(parents=True, exist_ok=True)
        windows_build = platform_string.startswith("win-")
        suffix = ".exe" if windows_build else ""
        dest_path = dest_dir / f"{_BINARY_NAME}{suffix}"
        part_path = dest_dir / f"{_BINARY_NAME}{suffix}.part"

        def _locked_error(name: str) -> RuntimeError:
            return RuntimeError(
                f"Cannot replace {name}: the file is in use. "
                "Stop the running inference engine before upgrading."
            )

        def _write() -> None:
            try:
                # Libraries first, so the executable never resolves before its
                # dependencies are on disk; then the links that name them.
                for fname, content in runtime_files.files.items():
                    target = dest_dir / fname
                    try:
                        target.write_bytes(content)
                        if not windows_build and _is_shared_library(fname):
                            target.chmod(0o755)
                    except PermissionError as exc:
                        raise _locked_error(target.name) from exc
                for link, points_to in runtime_files.symlinks.items():
                    link_path = dest_dir / link
                    try:
                        if link_path.is_symlink() or link_path.exists():
                            link_path.unlink()
                        os.symlink(points_to, link_path)
                    except PermissionError as exc:
                        raise _locked_error(link_path.name) from exc
                part_path.write_bytes(runtime_files.binary)
                if not windows_build:
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

    except PinError as exc:
        progress.state = DownloadState.FAILED
        progress.error = str(exc)
        if progress_cb:
            progress_cb(progress)
        raise RuntimeError(str(exc)) from exc

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
