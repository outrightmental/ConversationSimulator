# SPDX-License-Identifier: Apache-2.0
"""Tests for the llama.cpp binary downloader and the pin it verifies against.

All HTTP calls are intercepted by mock clients; no real network access or model
weights are required. Issue #530: the downloader fetches the pinned tag, uses
the asset names upstream really publishes on every platform, handles both
archive formats with their symlinks, and refuses an archive whose digest is
missing from the pin or does not match it.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from convsim_core.runtime.llama_cpp_download import (
    DownloadProgress,
    DownloadState,
    _extract_runtime_files_from_tar,
    _extract_runtime_files_from_zip,
    _sha256_of_bytes,
    build_asset_name,
    build_asset_url,
    detect_platform_string,
    detect_windows_gpu_variant,
    download_binary,
)
from convsim_core.runtime.llama_cpp_pin import (
    LlamaCppPin,
    PinError,
    has_variant,
    load_pin,
    parse_pin,
    pin_path,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

# The asset list of the pinned release (gh api repos/ggml-org/llama.cpp/
# releases/tags/b9415 --jq '.assets[].name'), restricted to the archives the
# app can install. If upstream renamed one, this test would say which.
PINNED_RELEASE_ASSETS = {
    "llama-b9415-bin-macos-arm64.tar.gz",
    "llama-b9415-bin-macos-x64.tar.gz",
    "llama-b9415-bin-ubuntu-arm64.tar.gz",
    "llama-b9415-bin-ubuntu-vulkan-arm64.tar.gz",
    "llama-b9415-bin-ubuntu-vulkan-x64.tar.gz",
    "llama-b9415-bin-ubuntu-x64.tar.gz",
    "llama-b9415-bin-win-cpu-arm64.zip",
    "llama-b9415-bin-win-cpu-x64.zip",
    "llama-b9415-bin-win-vulkan-x64.zip",
}

PLATFORMS = ("win-x64", "win-arm64", "linux-x64", "linux-arm64", "macos-arm64", "macos-x64")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _make_tar(files: dict[str, bytes], links: dict[str, str] | None = None, root: str = "llama-b1") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        dir_info = tarfile.TarInfo(root)
        dir_info.type = tarfile.DIRTYPE
        tf.addfile(dir_info)
        for name, content in files.items():
            info = tarfile.TarInfo(f"{root}/{name}")
            info.size = len(content)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(content))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(f"{root}/{name}")
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tf.addfile(info)
    return buf.getvalue()


def _linux_archive() -> bytes:
    return _make_tar(
        {
            "llama-server": b"\x7fELFserver",
            "libllama.so.0.0.1": b"libllama",
            "libggml-base.so.0.13.1": b"libggml-base",
            "libggml-cpu-haswell.so": b"cpu-backend",
            "llama-cli": b"not needed",
            "LICENSE": b"MIT",
        },
        links={
            "libllama.so.0": "libllama.so.0.0.1",
            "libllama.so": "libllama.so.0",
            "libggml-base.so.0": "libggml-base.so.0.13.1",
            "libevil.so": "../../etc/passwd",
        },
    )


def _pin_for(tag: str, data: bytes, *names: str) -> LlamaCppPin:
    digest = _sha256_of_bytes(data)
    return LlamaCppPin(tag=tag, sha256={name: digest for name in names})


def _mock_async_client(
    *,
    asset_data: bytes,
    asset_status: int = 200,
    download_error: Exception | None = None,
) -> Any:
    """A mock httpx.AsyncClient whose stream() serves *asset_data*."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.aclose = AsyncMock()

    stream_ctx = MagicMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=stream_ctx)
    stream_ctx.__aexit__ = AsyncMock(return_value=None)
    stream_ctx.status_code = asset_status
    stream_ctx.headers = {"content-length": str(len(asset_data))}

    async def _aiter_bytes(chunk_size=65536):
        if download_error is not None:
            raise download_error
        offset = 0
        while offset < len(asset_data):
            yield asset_data[offset : offset + chunk_size]
            offset += chunk_size

    stream_ctx.aiter_bytes = _aiter_bytes
    client.stream = MagicMock(return_value=stream_ctx)
    return client


def _patched(client: Any):
    return patch("convsim_core.runtime.llama_cpp_download.httpx.AsyncClient", return_value=client)


# ---------------------------------------------------------------------------
# The pin
# ---------------------------------------------------------------------------


def test_the_pin_is_one_file_in_the_repository():
    assert pin_path() == REPO_ROOT / "runtimes" / "llama_cpp" / "pin.json"
    pin = load_pin()
    assert pin.tag == "b9415"


def test_every_installable_asset_name_matches_the_pinned_release():
    pin = load_pin()
    names = set()
    for platform_string in PLATFORMS:
        for variant in ("cpu", "vulkan"):
            if has_variant(platform_string, variant):
                names.add(build_asset_name(pin.tag, platform_string, variant=variant))
    assert names == PINNED_RELEASE_ASSETS
    # ... and the pin has a digest for every one of them, and nothing else.
    assert set(pin.sha256) == PINNED_RELEASE_ASSETS


@pytest.mark.parametrize(
    ("platform_string", "variant", "expected"),
    [
        ("win-x64", "cpu", "llama-b9415-bin-win-cpu-x64.zip"),
        ("win-x64", "vulkan", "llama-b9415-bin-win-vulkan-x64.zip"),
        ("win-arm64", "cpu", "llama-b9415-bin-win-cpu-arm64.zip"),
        ("linux-x64", "cpu", "llama-b9415-bin-ubuntu-x64.tar.gz"),
        ("linux-x64", "vulkan", "llama-b9415-bin-ubuntu-vulkan-x64.tar.gz"),
        ("linux-arm64", "cpu", "llama-b9415-bin-ubuntu-arm64.tar.gz"),
        ("linux-arm64", "vulkan", "llama-b9415-bin-ubuntu-vulkan-arm64.tar.gz"),
        ("macos-arm64", "cpu", "llama-b9415-bin-macos-arm64.tar.gz"),
        ("macos-x64", "cpu", "llama-b9415-bin-macos-x64.tar.gz"),
    ],
)
def test_asset_names(platform_string, variant, expected):
    assert build_asset_name("b9415", platform_string, variant=variant) == expected


@pytest.mark.parametrize("platform_string", ["macos-arm64", "macos-x64", "win-arm64"])
def test_no_vulkan_build_where_upstream_publishes_none(platform_string):
    assert not has_variant(platform_string, "vulkan")
    with pytest.raises(ValueError):
        build_asset_name("b9415", platform_string, variant="vulkan")


def test_cuda_is_not_a_variant():
    with pytest.raises(ValueError):
        build_asset_name("b9415", "win-x64", variant="cuda")


def test_pin_file_keeps_one_entry_per_line_for_the_shell_script():
    """download-runtime.sh reads the pin with sed, one key per line."""
    lines = (REPO_ROOT / "runtimes" / "llama_cpp" / "pin.json").read_text().splitlines()
    pin = load_pin()
    assert any(re.fullmatch(r'\s*"tag": "b9415",', line) for line in lines)
    for name, digest in pin.sha256.items():
        assert any(re.fullmatch(rf'\s*"{re.escape(name)}": "{digest}",?', line) for line in lines), name


def test_the_pinned_digests_are_github_release_digests():
    """Each digest is 64 hex digits; parse_pin refuses anything else."""
    with pytest.raises(PinError):
        parse_pin(json.dumps({"tag": "b1", "sha256": {"a.zip": "XYZ"}}))
    with pytest.raises(PinError):
        parse_pin(json.dumps({"sha256": {}}))


def test_the_packaged_core_embeds_the_pin():
    spec = (REPO_ROOT / "services" / "convsim-core" / "convsim-core.spec").read_text()
    assert "'runtimes' / 'llama_cpp' / 'pin.json'" in spec


def test_build_asset_url():
    url = build_asset_url("b9415", "llama-b9415-bin-win-cpu-x64.zip")
    assert url == (
        "https://github.com/ggml-org/llama.cpp/releases/download/b9415/llama-b9415-bin-win-cpu-x64.zip"
    )


# ---------------------------------------------------------------------------
# detect_platform_string — pure unit tests (monkeypatched sys.platform)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("linux", "x86_64", "linux-x64"),
        ("linux", "amd64", "linux-x64"),
        ("linux", "aarch64", "linux-arm64"),
        ("linux", "arm64", "linux-arm64"),
        ("darwin", "arm64", "macos-arm64"),
        ("darwin", "x86_64", "macos-x64"),
        ("win32", "amd64", "win-x64"),
        ("win32", "x86_64", "win-x64"),
        ("win32", "arm64", "win-arm64"),
    ],
)
def test_detect_platform(monkeypatch, system, machine, expected):
    monkeypatch.setattr("sys.platform", system)
    monkeypatch.setattr("platform.machine", lambda: machine)
    assert detect_platform_string() == expected


def test_detect_platform_unsupported_raises(monkeypatch):
    monkeypatch.setattr("sys.platform", "freebsd14")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    with pytest.raises(RuntimeError, match="Unsupported platform"):
        detect_platform_string()


# ---------------------------------------------------------------------------
# Archive extraction
# ---------------------------------------------------------------------------


def test_zip_extraction_returns_the_binary_and_every_sibling():
    data = _make_zip({
        "llama-server.exe": b"exe",
        "ggml.dll": b"ggml",
        "ggml-vulkan.dll": b"vk",
        "docs/README.txt": b"elsewhere",
    })
    files = _extract_runtime_files_from_zip(data)
    assert files.binary == b"exe"
    assert files.files == {"ggml.dll": b"ggml", "ggml-vulkan.dll": b"vk"}


def test_zip_without_the_binary_raises():
    with pytest.raises(RuntimeError, match="not found"):
        _extract_runtime_files_from_zip(_make_zip({"ggml.dll": b"ggml"}))


def test_tar_extraction_keeps_libraries_and_their_symlinks():
    files = _extract_runtime_files_from_tar(_linux_archive())
    assert files.binary == b"\x7fELFserver"
    assert set(files.files) == {
        "libllama.so.0.0.1", "libggml-base.so.0.13.1", "libggml-cpu-haswell.so", "LICENSE-llama.cpp.txt",
    }
    assert files.symlinks == {
        "libllama.so.0": "libllama.so.0.0.1",
        "libllama.so": "libllama.so.0",
        "libggml-base.so.0": "libggml-base.so.0.13.1",
    }  # the link out of the install directory is dropped
    assert "llama-cli" not in files.files


def test_tar_without_the_binary_raises():
    with pytest.raises(RuntimeError, match="not found"):
        _extract_runtime_files_from_tar(_make_tar({"libllama.so": b"x"}))


# ---------------------------------------------------------------------------
# download_binary — verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downloads_the_pinned_tag_by_default(tmp_path):
    data = _make_zip({"llama-server.exe": b"win", "ggml.dll": b"g"})
    pin = _pin_for("b7777", data, "llama-b7777-bin-win-cpu-x64.zip")
    client = _mock_async_client(asset_data=data)
    with _patched(client):
        result = await download_binary(dest_dir=tmp_path / "bin", platform_string="win-x64", pin=pin)
    url = client.stream.call_args.args[1]
    assert url.endswith("/b7777/llama-b7777-bin-win-cpu-x64.zip")
    assert Path(result).name == "llama-server.exe"
    assert (tmp_path / "bin" / "ggml.dll").read_bytes() == b"g"


@pytest.mark.asyncio
async def test_a_tampered_archive_is_refused(tmp_path):
    data = _make_zip({"llama-server.exe": b"win"})
    pin = LlamaCppPin(tag="b1", sha256={"llama-b1-bin-win-cpu-x64.zip": "a" * 64})
    states: list[str] = []
    with _patched(_mock_async_client(asset_data=data)):
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            await download_binary(
                dest_dir=tmp_path / "bin", platform_string="win-x64", pin=pin,
                progress_cb=lambda p: states.append(p.state.value),
            )
    assert "checksum_mismatch" in states and "failed" not in states
    assert not (tmp_path / "bin").exists() or not list((tmp_path / "bin").iterdir())


@pytest.mark.asyncio
async def test_an_archive_with_no_pinned_digest_is_refused(tmp_path):
    data = _make_zip({"llama-server.exe": b"win"})
    pin = LlamaCppPin(tag="b1", sha256={})
    client = _mock_async_client(asset_data=data)
    with _patched(client):
        with pytest.raises(RuntimeError, match="No pinned SHA-256"):
            await download_binary(dest_dir=tmp_path / "bin", platform_string="win-x64", pin=pin)
    client.stream.assert_not_called()  # nothing is even downloaded
    assert not (tmp_path / "bin" / "llama-server.exe").exists()


@pytest.mark.asyncio
async def test_another_tag_needs_its_digest_passed(tmp_path):
    data = _make_zip({"llama-server.exe": b"win"})
    pin = _pin_for("b1", data, "llama-b1-bin-win-cpu-x64.zip")
    with _patched(_mock_async_client(asset_data=data)):
        with pytest.raises(RuntimeError, match="not the pinned release"):
            await download_binary(dest_dir=tmp_path / "a", version="b2", platform_string="win-x64", pin=pin)
    with _patched(_mock_async_client(asset_data=data)):
        result = await download_binary(
            dest_dir=tmp_path / "b", version="b2", platform_string="win-x64", pin=pin,
            sha256=_sha256_of_bytes(data),
        )
    assert Path(result).exists()


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
async def test_linux_install_recreates_the_library_symlinks(tmp_path):
    data = _linux_archive()
    pin = _pin_for("b1", data, "llama-b1-bin-ubuntu-vulkan-x64.tar.gz")
    dest = tmp_path / "bin" / "vulkan"
    with _patched(_mock_async_client(asset_data=data)):
        result = await download_binary(dest_dir=dest, platform_string="linux-x64", variant="vulkan", pin=pin)
    assert Path(result) == dest / "llama-server"
    assert os.access(result, os.X_OK)
    assert os.readlink(dest / "libllama.so.0") == "libllama.so.0.0.1"
    assert (dest / "libllama.so").read_bytes() == b"libllama"
    assert (dest / "LICENSE-llama.cpp.txt").read_bytes() == b"MIT"
    assert not (dest / "libevil.so").exists()
    assert not (dest / "llama-cli").exists()


@pytest.mark.asyncio
async def test_vulkan_variant_downloads_the_vulkan_archive(tmp_path):
    data = _make_zip({"llama-server.exe": b"vk", "ggml-vulkan.dll": b"v"})
    pin = _pin_for("b1", data, "llama-b1-bin-win-vulkan-x64.zip")
    client = _mock_async_client(asset_data=data)
    with _patched(client):
        await download_binary(dest_dir=tmp_path / "vulkan", platform_string="win-x64", variant="vulkan", pin=pin)
    assert "win-vulkan-x64" in client.stream.call_args.args[1]
    assert (tmp_path / "vulkan" / "ggml-vulkan.dll").exists()


@pytest.mark.asyncio
async def test_a_variant_upstream_does_not_publish_fails_before_downloading(tmp_path):
    client = _mock_async_client(asset_data=b"")
    with _patched(client):
        with pytest.raises(RuntimeError, match="no vulkan build"):
            await download_binary(
                dest_dir=tmp_path, platform_string="macos-arm64", variant="vulkan",
                pin=LlamaCppPin(tag="b1", sha256={}),
            )
    client.stream.assert_not_called()


# ---------------------------------------------------------------------------
# download_binary — failure handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asset_404_raises(tmp_path):
    data = _make_zip({"llama-server": b"x"})
    pin = _pin_for("b1", data, "llama-b1-bin-ubuntu-x64.tar.gz")
    with _patched(_mock_async_client(asset_data=data, asset_status=404)):
        with pytest.raises(RuntimeError, match="Download failed"):
            await download_binary(dest_dir=tmp_path, platform_string="linux-x64", pin=pin)


@pytest.mark.asyncio
async def test_offline_during_download_raises_friendly(tmp_path):
    import httpx

    data = _linux_archive()
    pin = _pin_for("b1", data, "llama-b1-bin-ubuntu-x64.tar.gz")
    states: list[str] = []
    with _patched(_mock_async_client(asset_data=data, download_error=httpx.ConnectError("reset"))):
        with pytest.raises(RuntimeError, match="Network error while downloading"):
            await download_binary(
                dest_dir=tmp_path, platform_string="linux-x64", pin=pin,
                progress_cb=lambda p: states.append(p.state.value),
            )
    assert states[-1] == "failed"


@pytest.mark.asyncio
async def test_locked_destination_raises_and_cleans_part(tmp_path, monkeypatch):
    data = _make_zip({"llama-server.exe": b"x"})
    pin = _pin_for("b1", data, "llama-b1-bin-win-cpu-x64.zip")

    def _raise_locked(src, dst):
        raise PermissionError("[WinError 5] Access is denied")

    monkeypatch.setattr("convsim_core.runtime.llama_cpp_download.os.replace", _raise_locked)
    dest = tmp_path / "bin"
    with _patched(_mock_async_client(asset_data=data)):
        with pytest.raises(RuntimeError, match="in use"):
            await download_binary(dest_dir=dest, platform_string="win-x64", pin=pin)
    assert not list(dest.glob("*.part"))
    assert not (dest / "llama-server.exe").exists()


@pytest.mark.asyncio
async def test_progress_states_in_order(tmp_path):
    data = _make_zip({"llama-server.exe": b"x"})
    pin = _pin_for("b1", data, "llama-b1-bin-win-cpu-x64.zip")
    states: list[str] = []
    with _patched(_mock_async_client(asset_data=data)):
        await download_binary(
            dest_dir=tmp_path, platform_string="win-x64", pin=pin,
            progress_cb=lambda p: states.append(p.state.value),
        )
    ordered: list[str] = []
    for s in states:
        if not ordered or ordered[-1] != s:
            ordered.append(s)
    assert ordered == ["fetching_release", "downloading", "verifying", "extracting", "complete"]


@pytest.mark.asyncio
async def test_cancelled_mid_download(tmp_path):
    data = _make_zip({"llama-server.exe": b"x" * 200_000})
    pin = _pin_for("b1", data, "llama-b1-bin-win-cpu-x64.zip")
    cancel = asyncio.Event()
    client = _mock_async_client(asset_data=data)
    stream_ctx = client.stream.return_value
    original = stream_ctx.aiter_bytes

    async def _cancel_after_first(chunk_size=65536):
        async for chunk in original(chunk_size):
            cancel.set()
            yield chunk

    stream_ctx.aiter_bytes = _cancel_after_first
    with _patched(client):
        with pytest.raises(asyncio.CancelledError):
            await download_binary(dest_dir=tmp_path, platform_string="win-x64", pin=pin, cancel_event=cancel)


# ---------------------------------------------------------------------------
# detect_windows_gpu_variant
# ---------------------------------------------------------------------------


def test_detect_windows_gpu_variant_returns_cpu_by_default(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert detect_windows_gpu_variant() == "cpu"


def test_detect_windows_gpu_variant_never_raises(monkeypatch):
    import subprocess as _subprocess

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(_subprocess, "run", MagicMock(side_effect=OSError("no such file")))
    assert detect_windows_gpu_variant() in ("cpu", "vulkan")


# ---------------------------------------------------------------------------
# API endpoint tests via TestClient
# ---------------------------------------------------------------------------


def test_download_runtime_status_idle(client):
    from convsim_core.routers import sidecar as sidecar_mod

    sidecar_mod._reset_download_state()
    resp = client.get("/api/sidecar/download-runtime")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "idle"
    assert data["binary_path"] is None


def test_download_runtime_409_when_already_running(client):
    import convsim_core.routers.sidecar as sidecar_mod

    sidecar_mod._reset_download_state()
    fake_task = MagicMock()
    fake_task.done.return_value = False
    sidecar_mod._download_task = fake_task
    sidecar_mod._download_progress = DownloadProgress(state=DownloadState.DOWNLOADING)
    try:
        with patch("convsim_core.routers.sidecar.detect_platform_string", return_value="linux-x64"):
            resp = client.post("/api/sidecar/download-runtime", json={})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DOWNLOAD_ALREADY_IN_PROGRESS"
    finally:
        sidecar_mod._reset_download_state()


def test_download_runtime_rejects_an_unknown_variant(client):
    import convsim_core.routers.sidecar as sidecar_mod

    sidecar_mod._reset_download_state()
    with patch("convsim_core.routers.sidecar.detect_platform_string", return_value="linux-x64"):
        resp = client.post("/api/sidecar/download-runtime", json={"variant": "cuda"})
    assert resp.status_code == 422


def test_download_runtime_puts_the_vulkan_build_in_its_own_directory(client, monkeypatch, tmp_path):
    import convsim_core.routers.sidecar as sidecar_mod

    sidecar_mod._reset_download_state()
    monkeypatch.setattr(sidecar_mod, "user_install_dir", lambda: tmp_path / "bin")
    seen: dict[str, Any] = {}

    async def _fake_download(**kwargs):
        seen.update(kwargs)
        return str(kwargs["dest_dir"] / "llama-server")

    monkeypatch.setattr(sidecar_mod, "download_binary", _fake_download)
    with patch("convsim_core.routers.sidecar.detect_platform_string", return_value="linux-x64"):
        resp = client.post("/api/sidecar/download-runtime", json={"variant": "vulkan"})
    assert resp.status_code == 200
    for _ in range(50):
        if seen:
            break
        import time

        time.sleep(0.02)
    assert seen["dest_dir"] == tmp_path / "bin" / "vulkan"
    assert seen["variant"] == "vulkan"
    sidecar_mod._reset_download_state()


def test_download_runtime_cancel_no_download_returns_409(client):
    import convsim_core.routers.sidecar as sidecar_mod

    sidecar_mod._reset_download_state()
    resp = client.delete("/api/sidecar/download-runtime")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "NO_DOWNLOAD_IN_PROGRESS"


def test_download_runtime_unsupported_platform_returns_400(client):
    import convsim_core.routers.sidecar as sidecar_mod

    sidecar_mod._reset_download_state()
    with patch(
        "convsim_core.routers.sidecar.detect_platform_string",
        side_effect=RuntimeError("Unsupported platform: freebsd/amd64"),
    ):
        resp = client.post("/api/sidecar/download-runtime", json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PLATFORM_NOT_SUPPORTED"


# ---------------------------------------------------------------------------
# Runtime capabilities endpoint
# ---------------------------------------------------------------------------


def test_runtime_capabilities_runtime_id_matches_active(client):
    runtime = client.app.state.runtime
    resp = client.get("/api/runtime/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["runtime_id"] == runtime.id
    for key in ("streaming", "json_schema", "grammar", "tool_calling", "embeddings"):
        assert key in data
