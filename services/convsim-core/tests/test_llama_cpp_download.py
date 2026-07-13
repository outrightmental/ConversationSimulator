# SPDX-License-Identifier: Apache-2.0
"""Tests for the llama.cpp binary downloader.

All HTTP calls are intercepted by mock clients or in-process fake HTTP servers;
no real network access or model weights are required.  This matches the mock-server
pattern already established in test_sidecar.py for the sidecar integration tests.
"""
from __future__ import annotations

import asyncio
import io
import sys
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from convsim_core.runtime.llama_cpp_download import (
    DownloadProgress,
    DownloadState,
    _extract_binary_from_zip,
    _sha256_of_bytes,
    build_asset_name,
    build_asset_url,
    build_sha256sum_url,
    detect_platform_string,
    detect_windows_gpu_variant,
    download_binary,
    fetch_expected_sha256,
    fetch_latest_release_tag,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zip(filename: str, content: bytes = b"fake-binary") -> bytes:
    """Return a ZIP archive containing a single file *filename* with *content*."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(filename, content)
    return buf.getvalue()


def _mock_async_client(
    *,
    latest_tag: str = "b5000",
    sha256sum_text: str | None = None,
    sha256sum_status: int = 200,
    asset_data: bytes | None = None,
    asset_status: int = 200,
    api_error: Exception | None = None,
    download_error: Exception | None = None,
) -> Any:
    """Build a mock httpx.AsyncClient for download_binary() tests.

    Intercepts:
      GET  <github_api>/releases/latest → ``{"tag_name": latest_tag}``
      GET  .../sha256sum.txt            → sha256sum_text (or 404)
      GET (stream)  .../asset.zip       → asset_data
    """
    import httpx

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.aclose = AsyncMock()

    # API call → latest release tag
    api_resp = MagicMock()
    api_resp.status_code = 200
    api_resp.json = MagicMock(return_value={"tag_name": latest_tag})
    api_resp.raise_for_status = MagicMock()

    # sha256sum.txt response
    sha_resp = MagicMock()
    sha_resp.status_code = sha256sum_status
    sha_resp.text = sha256sum_text or ""
    sha_resp.raise_for_status = MagicMock()
    if sha256sum_status >= 400:
        sha_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {sha256sum_status}",
            request=MagicMock(),
            response=sha_resp,
        )

    async def _get(url, **_kw):
        if api_error is not None:
            raise api_error
        if "api.github.com" in url:
            return api_resp
        return sha_resp

    client.get = _get

    # Streaming download context manager
    stream_ctx = MagicMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=stream_ctx)
    stream_ctx.__aexit__ = AsyncMock(return_value=None)

    data = asset_data or _make_zip("llama-server", b"binary-content")
    stream_ctx.status_code = asset_status
    stream_ctx.headers = {"content-length": str(len(data))}

    async def _aiter_bytes(chunk_size=65536):
        if download_error is not None:
            raise download_error
        offset = 0
        while offset < len(data):
            yield data[offset : offset + chunk_size]
            offset += chunk_size

    stream_ctx.aiter_bytes = _aiter_bytes
    client.stream = MagicMock(return_value=stream_ctx)

    return client


# ---------------------------------------------------------------------------
# detect_platform_string — pure unit tests (monkeypatched sys.platform)
# ---------------------------------------------------------------------------


def test_detect_platform_linux_x86_64(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    assert detect_platform_string() == "linux-x64"


def test_detect_platform_linux_amd64(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("platform.machine", lambda: "amd64")
    assert detect_platform_string() == "linux-x64"


def test_detect_platform_linux_aarch64(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("platform.machine", lambda: "aarch64")
    assert detect_platform_string() == "linux-arm64"


def test_detect_platform_linux_arm64(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    assert detect_platform_string() == "linux-arm64"


def test_detect_platform_macos_arm64(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    assert detect_platform_string() == "macos-arm64"


def test_detect_platform_macos_x86_64(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    assert detect_platform_string() == "macos-x64"


def test_detect_platform_macos_amd64(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "amd64")
    assert detect_platform_string() == "macos-x64"


def test_detect_platform_windows_x64(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("platform.machine", lambda: "amd64")
    assert detect_platform_string() == "win-x64"


def test_detect_platform_windows_x86_64(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    assert detect_platform_string() == "win-x64"


def test_detect_platform_windows_arm64(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    assert detect_platform_string() == "win-arm64"


def test_detect_platform_unsupported_os_raises(monkeypatch):
    monkeypatch.setattr("sys.platform", "freebsd14")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    with pytest.raises(RuntimeError, match="Unsupported platform"):
        detect_platform_string()


def test_detect_platform_unsupported_arch_raises(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("platform.machine", lambda: "riscv64")
    with pytest.raises(RuntimeError, match="Unsupported platform"):
        detect_platform_string()


# ---------------------------------------------------------------------------
# Asset name and URL construction
# ---------------------------------------------------------------------------


def test_build_asset_name():
    name = build_asset_name("b5140", "linux-x64")
    assert name == "llama-b5140-bin-linux-x64-cpu.zip"


def test_build_asset_name_macos():
    name = build_asset_name("b1234", "macos-arm64")
    assert name == "llama-b1234-bin-macos-arm64-cpu.zip"


def test_build_asset_name_windows_x64_cpu():
    name = build_asset_name("b5140", "win-x64")
    assert name == "llama-b5140-bin-win-cpu-x64.zip"


def test_build_asset_name_windows_arm64_cpu():
    name = build_asset_name("b5140", "win-arm64")
    assert name == "llama-b5140-bin-win-cpu-arm64.zip"


def test_build_asset_name_windows_cuda():
    name = build_asset_name("b5140", "win-x64", variant="cuda")
    assert name == "llama-b5140-bin-win-cuda-x64.zip"


def test_build_asset_name_windows_vulkan():
    name = build_asset_name("b5140", "win-x64", variant="vulkan")
    assert name == "llama-b5140-bin-win-vulkan-x64.zip"


def test_build_asset_url():
    url = build_asset_url("b5140", "llama-b5140-bin-linux-x64-cpu.zip")
    assert "ggml-org/llama.cpp" in url
    assert "b5140" in url
    assert "linux-x64" in url
    assert url.startswith("https://")


def test_build_sha256sum_url():
    url = build_sha256sum_url("b5140")
    assert "sha256sum.txt" in url
    assert "b5140" in url


# ---------------------------------------------------------------------------
# fetch_latest_release_tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_latest_release_tag_returns_tag():
    import httpx

    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={"tag_name": "b9999"})
    resp.raise_for_status = MagicMock()

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)

    tag = await fetch_latest_release_tag(client)
    assert tag == "b9999"


@pytest.mark.asyncio
async def test_fetch_latest_release_tag_empty_raises():
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={"tag_name": ""})
    resp.raise_for_status = MagicMock()

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)

    with pytest.raises(RuntimeError, match="tag_name"):
        await fetch_latest_release_tag(client)


# ---------------------------------------------------------------------------
# fetch_expected_sha256
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_expected_sha256_found():
    sha256sum_text = (
        "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890  llama-b5140-bin-linux-x64-cpu.zip\n"
        "0000000000000000000000000000000000000000000000000000000000000000  other.zip\n"
    )
    resp = MagicMock()
    resp.status_code = 200
    resp.text = sha256sum_text
    resp.raise_for_status = MagicMock()

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)

    result = await fetch_expected_sha256(
        client,
        "https://example.com/sha256sum.txt",
        "llama-b5140-bin-linux-x64-cpu.zip",
    )
    assert result == "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"


@pytest.mark.asyncio
async def test_fetch_expected_sha256_star_prefix():
    """GNU checksum format prepends '*' to filenames in binary mode."""
    sha256sum_text = (
        "deadbeef00000000000000000000000000000000000000000000000000000000 *llama-b1-bin-macos-arm64-cpu.zip\n"
    )
    resp = MagicMock()
    resp.status_code = 200
    resp.text = sha256sum_text
    resp.raise_for_status = MagicMock()

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)

    result = await fetch_expected_sha256(
        client,
        "https://example.com/sha256sum.txt",
        "llama-b1-bin-macos-arm64-cpu.zip",
    )
    assert result == "deadbeef00000000000000000000000000000000000000000000000000000000"


@pytest.mark.asyncio
async def test_fetch_expected_sha256_not_in_file_returns_none():
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "aabbcc  other-file.zip\n"
    resp.raise_for_status = MagicMock()

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)

    result = await fetch_expected_sha256(
        client,
        "https://example.com/sha256sum.txt",
        "llama-b9-bin-linux-x64-cpu.zip",
    )
    assert result is None


@pytest.mark.asyncio
async def test_fetch_expected_sha256_404_returns_none():
    import httpx

    resp = MagicMock()
    resp.status_code = 404
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=resp)
    )

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)

    result = await fetch_expected_sha256(
        client,
        "https://example.com/sha256sum.txt",
        "asset.zip",
    )
    assert result is None


# ---------------------------------------------------------------------------
# _extract_binary_from_zip
# ---------------------------------------------------------------------------


def test_extract_binary_from_zip_linux():
    data = _make_zip("llama-server", b"binary-linux")
    result = _extract_binary_from_zip(data)
    assert result == b"binary-linux"


def test_extract_binary_from_zip_windows():
    data = _make_zip("llama-server.exe", b"binary-win")
    result = _extract_binary_from_zip(data)
    assert result == b"binary-win"


def test_extract_binary_from_zip_in_subdirectory():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("build/bin/llama-server", b"binary-in-subdir")
    result = _extract_binary_from_zip(buf.getvalue())
    assert result == b"binary-in-subdir"


def test_extract_binary_from_zip_missing_raises():
    data = _make_zip("some-other-file.txt", b"content")
    with pytest.raises(RuntimeError, match="not found"):
        _extract_binary_from_zip(data)


# ---------------------------------------------------------------------------
# detect_windows_gpu_variant
# ---------------------------------------------------------------------------


def test_detect_windows_gpu_variant_returns_cpu_by_default(monkeypatch):
    """Without nvidia-smi or vulkaninfo, must return 'cpu'."""
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert detect_windows_gpu_variant() == "cpu"


def test_detect_windows_gpu_variant_vulkan_when_nvidia_smi_succeeds(monkeypatch):
    """Returns 'vulkan' when nvidia-smi reports a GPU.

    CUDA is intentionally not recommended: llama.cpp CUDA builds are published
    per toolkit version and need a separate cudart archive, so the single-asset
    downloader can't fetch one. The NVIDIA driver ships the Vulkan runtime, so
    the Vulkan build accelerates on NVIDIA too.
    """
    import subprocess as _subprocess

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = b"NVIDIA GeForce RTX 4090\n"
    monkeypatch.setattr(_subprocess, "run", lambda *a, **kw: fake_result)

    assert detect_windows_gpu_variant() == "vulkan"


def test_detect_windows_gpu_variant_cpu_when_nvidia_smi_fails(monkeypatch):
    """Returns 'cpu' when nvidia-smi is present but returns no GPU name."""
    import subprocess as _subprocess

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)

    fake_result = MagicMock()
    fake_result.returncode = 1
    fake_result.stdout = b""
    monkeypatch.setattr(_subprocess, "run", lambda *a, **kw: fake_result)

    assert detect_windows_gpu_variant() == "cpu"


def test_detect_windows_gpu_variant_vulkan_fallback(monkeypatch):
    """Returns 'vulkan' when vulkaninfo succeeds but nvidia-smi is absent."""
    import subprocess as _subprocess

    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/vulkaninfo" if name == "vulkaninfo" else None,
    )

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = b"GPU info..."
    monkeypatch.setattr(_subprocess, "run", lambda *a, **kw: fake_result)

    assert detect_windows_gpu_variant() == "vulkan"


def test_detect_windows_gpu_variant_never_raises(monkeypatch):
    """detect_windows_gpu_variant() must not propagate exceptions."""
    import subprocess as _subprocess

    monkeypatch.setattr("shutil.which", lambda _: "/fake/nvidia-smi")
    monkeypatch.setattr(_subprocess, "run", MagicMock(side_effect=OSError("no such file")))

    result = detect_windows_gpu_variant()
    assert result in ("cpu", "cuda", "vulkan")


# ---------------------------------------------------------------------------
# download_binary — happy path (mock client)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_binary_success(tmp_path):
    """download_binary() installs the binary and returns its path."""
    binary_content = b"\x7fELFfakebinary"
    zip_data = _make_zip("llama-server", binary_content)
    actual_sha256 = _sha256_of_bytes(zip_data)

    sha256sum_text = f"{actual_sha256}  llama-b5000-bin-linux-x64-cpu.zip\n"
    client = _mock_async_client(
        latest_tag="b5000",
        sha256sum_text=sha256sum_text,
        asset_data=zip_data,
    )

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        result = await download_binary(
            dest_dir=tmp_path / "bin",
            version="b5000",
            platform_string="linux-x64",
        )

    assert result.endswith("llama-server") or result.endswith("llama-server.exe")
    dest = Path(result)
    assert dest.exists()
    assert dest.read_bytes() == binary_content
    assert dest.stat().st_mode & 0o111  # executable bit set


@pytest.mark.asyncio
async def test_download_binary_auto_fetches_latest_tag(tmp_path):
    """When version=None, the latest release tag is fetched from the API."""
    zip_data = _make_zip("llama-server", b"bin")
    client = _mock_async_client(latest_tag="b9999", asset_data=zip_data)

    progress_states: list[str] = []

    def _cb(p: DownloadProgress) -> None:
        progress_states.append(p.state.value)

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        result = await download_binary(
            dest_dir=tmp_path / "bin",
            platform_string="linux-x64",
            progress_cb=_cb,
        )

    assert Path(result).exists()
    assert "fetching_release" in progress_states
    assert "complete" in progress_states


@pytest.mark.asyncio
async def test_download_binary_no_sha256sum_file_still_succeeds(tmp_path):
    """Missing sha256sum.txt does not abort the download."""
    zip_data = _make_zip("llama-server", b"bin")
    client = _mock_async_client(
        latest_tag="b1",
        sha256sum_status=404,
        asset_data=zip_data,
    )

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        result = await download_binary(
            dest_dir=tmp_path / "bin",
            version="b1",
            platform_string="linux-x64",
        )

    assert Path(result).exists()


@pytest.mark.asyncio
async def test_download_binary_checksum_mismatch_raises(tmp_path):
    """A mismatched SHA-256 must raise RuntimeError and leave no binary."""
    zip_data = _make_zip("llama-server", b"bin")
    wrong_sha = "a" * 64
    sha256sum_text = f"{wrong_sha}  llama-b1-bin-linux-x64-cpu.zip\n"
    client = _mock_async_client(
        latest_tag="b1",
        sha256sum_text=sha256sum_text,
        asset_data=zip_data,
    )

    dest = tmp_path / "bin"
    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            await download_binary(
                dest_dir=dest,
                version="b1",
                platform_string="linux-x64",
            )

    # Binary must not have been written
    assert not (dest / "llama-server").exists()


@pytest.mark.asyncio
async def test_download_binary_checksum_mismatch_sets_checksum_mismatch_state(tmp_path):
    """A mismatched SHA-256 must set the progress state to checksum_mismatch."""
    zip_data = _make_zip("llama-server", b"bin")
    wrong_sha = "a" * 64
    sha256sum_text = f"{wrong_sha}  llama-b1-bin-linux-x64-cpu.zip\n"
    client = _mock_async_client(
        latest_tag="b1",
        sha256sum_text=sha256sum_text,
        asset_data=zip_data,
    )

    states: list[str] = []

    def _cb(p: DownloadProgress) -> None:
        states.append(p.state.value)

    dest = tmp_path / "bin"
    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            await download_binary(
                dest_dir=dest,
                version="b1",
                platform_string="linux-x64",
                progress_cb=_cb,
            )

    assert "checksum_mismatch" in states
    assert "failed" not in states  # checksum_mismatch is its own distinct terminal state


@pytest.mark.asyncio
async def test_download_binary_part_file_cleaned_on_checksum_mismatch(tmp_path):
    """The .part file must be removed when a checksum mismatch occurs."""
    zip_data = _make_zip("llama-server", b"bin")
    wrong_sha = "a" * 64
    sha256sum_text = f"{wrong_sha}  llama-b1-bin-linux-x64-cpu.zip\n"
    client = _mock_async_client(
        latest_tag="b1",
        sha256sum_text=sha256sum_text,
        asset_data=zip_data,
    )

    dest = tmp_path / "bin"
    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            await download_binary(
                dest_dir=dest,
                version="b1",
                platform_string="linux-x64",
            )

    # Neither the final binary nor any .part file should remain
    assert not list(dest.glob("*.part"))
    assert not (dest / "llama-server").exists()


@pytest.mark.asyncio
async def test_download_binary_windows_uses_exe_suffix(tmp_path, monkeypatch):
    """On win32, the installed binary must be named llama-server.exe."""
    monkeypatch.setattr("sys.platform", "win32")

    zip_data = _make_zip("llama-server.exe", b"win-binary")
    client = _mock_async_client(latest_tag="b1", asset_data=zip_data)

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        result = await download_binary(
            dest_dir=tmp_path / "bin",
            version="b1",
            platform_string="win-x64",
        )

    assert result.endswith("llama-server.exe")
    assert Path(result).read_bytes() == b"win-binary"


@pytest.mark.asyncio
async def test_download_binary_windows_asset_name(tmp_path):
    """download_binary with win-x64 requests the correct win-cpu-x64 asset."""
    binary_content = b"windows-binary"
    # The asset name for win-x64 default variant is llama-b1-bin-win-cpu-x64.zip
    zip_data = _make_zip("llama-server.exe", binary_content)
    sha256sum_text = f"{_sha256_of_bytes(zip_data)}  llama-b1-bin-win-cpu-x64.zip\n"
    client = _mock_async_client(
        latest_tag="b1",
        sha256sum_text=sha256sum_text,
        asset_data=zip_data,
    )

    captured_stream_url: list[str] = []
    orig_stream = client.stream

    def _recording_stream(method, url, **kw):
        captured_stream_url.append(url)
        return orig_stream(method, url, **kw)

    client.stream = _recording_stream

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        await download_binary(
            dest_dir=tmp_path / "bin",
            version="b1",
            platform_string="win-x64",
        )

    assert len(captured_stream_url) == 1
    assert "win-cpu-x64" in captured_stream_url[0]


@pytest.mark.asyncio
async def test_download_binary_variant_passed_to_asset_name(tmp_path):
    """Passing variant='vulkan' selects the correct Vulkan asset for Windows."""
    binary_content = b"vulkan-binary"
    zip_data = _make_zip("llama-server.exe", binary_content)
    sha256sum_text = f"{_sha256_of_bytes(zip_data)}  llama-b1-bin-win-vulkan-x64.zip\n"
    client = _mock_async_client(
        latest_tag="b1",
        sha256sum_text=sha256sum_text,
        asset_data=zip_data,
    )

    captured_stream_url: list[str] = []
    orig_stream = client.stream

    def _recording_stream(method, url, **kw):
        captured_stream_url.append(url)
        return orig_stream(method, url, **kw)

    client.stream = _recording_stream

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        await download_binary(
            dest_dir=tmp_path / "bin",
            version="b1",
            platform_string="win-x64",
            variant="vulkan",
        )

    assert len(captured_stream_url) == 1
    assert "win-vulkan-x64" in captured_stream_url[0]


@pytest.mark.asyncio
async def test_download_binary_asset_404_raises(tmp_path):
    """HTTP 404 for the asset file must raise RuntimeError with a helpful message."""
    client = _mock_async_client(latest_tag="b1", asset_status=404)

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="Download failed"):
            await download_binary(
                dest_dir=tmp_path / "bin",
                version="b1",
                platform_string="linux-x64",
            )


@pytest.mark.asyncio
async def test_download_binary_offline_fetching_release_raises_friendly(tmp_path):
    """A network error while fetching the latest tag surfaces an offline message."""
    import httpx

    client = _mock_async_client(api_error=httpx.ConnectError("no route to host"))

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="internet connection") as excinfo:
            await download_binary(
                dest_dir=tmp_path / "bin",
                version=None,  # force the latest-release lookup
                platform_string="linux-x64",
            )

    # The raw httpx error must be wrapped, not leaked to the user.
    assert "Cannot reach GitHub" in str(excinfo.value)


@pytest.mark.asyncio
async def test_download_binary_offline_during_download_raises_friendly(tmp_path):
    """A network drop mid-download surfaces an offline message and FAILED state."""
    import httpx

    client = _mock_async_client(
        latest_tag="b1",
        download_error=httpx.ConnectError("connection reset"),
    )

    states: list[str] = []

    def _cb(p: DownloadProgress) -> None:
        states.append(p.state.value)

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="Network error while downloading"):
            await download_binary(
                dest_dir=tmp_path / "bin",
                version="b1",
                platform_string="linux-x64",
                progress_cb=_cb,
            )

    assert states[-1] == "failed"


@pytest.mark.asyncio
async def test_download_binary_locked_destination_raises_and_cleans_part(tmp_path, monkeypatch):
    """A locked destination (PermissionError on replace) is reported and the .part removed."""
    zip_data = _make_zip("llama-server", b"bin")
    client = _mock_async_client(latest_tag="b1", asset_data=zip_data)

    def _raise_locked(src, dst):
        raise PermissionError("[WinError 5] Access is denied")

    monkeypatch.setattr(
        "convsim_core.runtime.llama_cpp_download.os.replace", _raise_locked
    )

    dest = tmp_path / "bin"
    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="in use"):
            await download_binary(
                dest_dir=dest,
                version="b1",
                platform_string="linux-x64",
            )

    # The failed .part write must not leave a stray file behind.
    assert not list(dest.glob("*.part"))
    assert not (dest / "llama-server").exists()


@pytest.mark.asyncio
async def test_download_binary_binary_missing_from_zip_raises(tmp_path):
    """If the ZIP doesn't contain llama-server, RuntimeError must be raised."""
    zip_data = _make_zip("README.txt", b"nope")
    client = _mock_async_client(latest_tag="b1", asset_data=zip_data)

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="not found in the downloaded archive"):
            await download_binary(
                dest_dir=tmp_path / "bin",
                version="b1",
                platform_string="linux-x64",
            )


@pytest.mark.asyncio
async def test_download_binary_progress_states_in_order(tmp_path):
    """progress_cb must be called with states in the expected sequence."""
    zip_data = _make_zip("llama-server", b"bin")
    client = _mock_async_client(latest_tag="b1", asset_data=zip_data)

    states: list[str] = []

    def _cb(p: DownloadProgress) -> None:
        states.append(p.state.value)

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        await download_binary(
            dest_dir=tmp_path / "bin",
            version="b1",
            platform_string="linux-x64",
            progress_cb=_cb,
        )

    # Must visit these states in order; deduplicate so repeated "downloading"
    # progress callbacks (one per chunk) don't expand the sequence.
    seen: set[str] = set()
    ordered: list[str] = []
    _key_states = {"fetching_release", "downloading", "verifying", "extracting", "complete"}
    for s in states:
        if s in _key_states and s not in seen:
            ordered.append(s)
            seen.add(s)
    assert ordered == ["fetching_release", "downloading", "verifying", "extracting", "complete"]


@pytest.mark.asyncio
async def test_download_binary_cancelled_mid_download(tmp_path):
    """Setting cancel_event during the download must raise CancelledError."""
    zip_data = _make_zip("llama-server", b"bin")

    cancel = asyncio.Event()
    chunk_count = 0

    client = _mock_async_client(latest_tag="b1", asset_data=zip_data)

    orig_stream = client.stream

    # Wrap the stream context manager so we set the cancel event after the first chunk
    stream_ctx = client.stream.return_value

    orig_aiter = stream_ctx.aiter_bytes

    async def _aiter_with_cancel(chunk_size=65536):
        nonlocal chunk_count
        async for chunk in orig_aiter(chunk_size):
            chunk_count += 1
            if chunk_count == 1:
                cancel.set()
            yield chunk

    stream_ctx.aiter_bytes = _aiter_with_cancel

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        with pytest.raises(asyncio.CancelledError):
            await download_binary(
                dest_dir=tmp_path / "bin",
                version="b1",
                platform_string="linux-x64",
                cancel_event=cancel,
            )


@pytest.mark.asyncio
async def test_download_binary_creates_dest_dir(tmp_path):
    """download_binary() must create dest_dir if it doesn't exist."""
    zip_data = _make_zip("llama-server", b"bin")
    client = _mock_async_client(latest_tag="b1", asset_data=zip_data)

    nested = tmp_path / "a" / "b" / "c"
    assert not nested.exists()

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        await download_binary(
            dest_dir=nested,
            version="b1",
            platform_string="linux-x64",
        )

    assert nested.is_dir()


@pytest.mark.asyncio
async def test_download_binary_progress_includes_release_tag(tmp_path):
    """The progress snapshot must include the resolved release tag."""
    zip_data = _make_zip("llama-server", b"bin")
    client = _mock_async_client(latest_tag="b9876", asset_data=zip_data)

    final_progress: list[DownloadProgress] = []

    def _cb(p: DownloadProgress) -> None:
        final_progress.append(p)

    with patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client):
        await download_binary(
            dest_dir=tmp_path / "bin",
            version="b9876",
            platform_string="linux-x64",
            progress_cb=_cb,
        )

    complete = next(p for p in reversed(final_progress) if p.state == DownloadState.COMPLETE)
    assert complete.release_tag == "b9876"
    assert complete.binary_path is not None


# ---------------------------------------------------------------------------
# API endpoint tests via TestClient
# ---------------------------------------------------------------------------


def test_download_runtime_status_idle(client):
    """GET /api/sidecar/download-runtime returns idle state when no download started."""
    from convsim_core.routers import sidecar as sidecar_mod
    sidecar_mod._reset_download_state()

    resp = client.get("/api/sidecar/download-runtime")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "idle"
    assert data["bytes_downloaded"] == 0
    assert data["binary_path"] is None


def test_download_runtime_409_when_already_running(client):
    """POST /api/sidecar/download-runtime returns 409 when a download is in progress."""
    import convsim_core.routers.sidecar as sidecar_mod
    from unittest.mock import MagicMock

    sidecar_mod._reset_download_state()

    # Plant a sentinel task object that reports done=False without actually
    # running a coroutine, so we avoid the "coroutine never awaited" warning.
    fake_task = MagicMock()
    fake_task.done.return_value = False
    sidecar_mod._download_task = fake_task
    sidecar_mod._download_progress = DownloadProgress(state=DownloadState.DOWNLOADING)

    try:
        with patch(
            "convsim_core.routers.sidecar.detect_platform_string",
            return_value="linux-x64",
        ):
            resp = client.post(
                "/api/sidecar/download-runtime",
                json={"version": "b1"},
            )

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DOWNLOAD_ALREADY_IN_PROGRESS"
    finally:
        sidecar_mod._reset_download_state()


def test_download_runtime_cancel_no_download_returns_409(client):
    """DELETE /api/sidecar/download-runtime when idle returns 409."""
    import convsim_core.routers.sidecar as sidecar_mod
    sidecar_mod._reset_download_state()

    resp = client.delete("/api/sidecar/download-runtime")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "NO_DOWNLOAD_IN_PROGRESS"


def test_download_runtime_unsupported_platform_returns_400(client, monkeypatch):
    """POST /api/sidecar/download-runtime returns 400 on an unsupported platform."""
    import convsim_core.routers.sidecar as sidecar_mod
    sidecar_mod._reset_download_state()

    with patch(
        "convsim_core.routers.sidecar.detect_platform_string",
        side_effect=RuntimeError("Unsupported platform: win32/amd64"),
    ):
        resp = client.post("/api/sidecar/download-runtime", json={})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PLATFORM_NOT_SUPPORTED"


# ---------------------------------------------------------------------------
# Runtime capabilities endpoint
# ---------------------------------------------------------------------------


def test_runtime_capabilities_endpoint_llama_cpp(client, monkeypatch):
    """GET /api/runtime/capabilities returns llama_cpp flags."""
    monkeypatch.setenv("CONVSIM_RUNTIME", "llama_cpp")
    resp = client.get("/api/runtime/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert "streaming" in data
    assert "json_schema" in data
    assert "grammar" in data
    assert "tool_calling" in data
    assert "embeddings" in data
    assert "runtime_id" in data


def test_runtime_capabilities_streaming_true_for_llama_cpp(client):
    """llama_cpp runtime must advertise streaming=True."""
    from convsim_core.runtime.llama_cpp import LlamaCppRuntime
    if not isinstance(client.app.state.runtime, LlamaCppRuntime):
        pytest.skip("Active runtime is not llama_cpp in this test config")
    resp = client.get("/api/runtime/capabilities")
    assert resp.json()["streaming"] is True


def test_runtime_capabilities_runtime_id_matches_active(client):
    """The runtime_id in the response must match the active runtime."""
    runtime = client.app.state.runtime
    resp = client.get("/api/runtime/capabilities")
    assert resp.json()["runtime_id"] == runtime.id
