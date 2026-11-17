# SPDX-License-Identifier: Apache-2.0
"""download-runtime.sh and download-runtime.ps1 refuse what they cannot verify (issue #530).

Each script is run for real against a local HTTP server standing in for the
GitHub release (``LLAMA_CPP_DOWNLOAD_BASE``) and a pin file written by the
test (``LLAMA_CPP_PIN_FILE``). A tampered archive and an archive the pin has
no digest for must both fail and install nothing; the pinned digest must
install. A test is skipped when its shell is not on this machine: bash on
Linux, macOS and Git for Windows; PowerShell on Windows and on the GitHub
Ubuntu runners (``pwsh``).
"""
from __future__ import annotations

import functools
import hashlib
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SH_SCRIPT = REPO_ROOT / "runtimes" / "llama_cpp" / "download-runtime.sh"
PS_SCRIPT = REPO_ROOT / "runtimes" / "llama_cpp" / "download-runtime.ps1"
TAG = "b1"


def _bash() -> str | None:
    if sys.platform == "win32":
        # System32\bash.exe is the WSL launcher; use Git for Windows' bash.
        git = shutil.which("git")
        if git:
            for candidate in (Path(git).parents[1] / "bin" / "bash.exe", Path(git).parent / "bash.exe"):
                if candidate.is_file():
                    return str(candidate)
        return None
    return shutil.which("bash")


def _powershell() -> str | None:
    return shutil.which("pwsh") or (shutil.which("powershell") if sys.platform == "win32" else None)


BASH = _bash()
POWERSHELL = _powershell()


@pytest.fixture
def release(tmp_path):
    """A local stand-in for github.com/ggml-org/llama.cpp/releases/download."""
    root = tmp_path / "release"
    (root / TAG).mkdir(parents=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None  # type: ignore[assignment]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield root, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _publish(release_root: Path, name: str, data: bytes) -> str:
    (release_root / TAG / name).write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _write_pin(tmp_path: Path, digests: dict[str, str]) -> Path:
    pin = tmp_path / "pin.json"
    lines = ["{", f'  "tag": "{TAG}",', '  "sha256": {']
    items = list(digests.items())
    for i, (name, digest) in enumerate(items):
        lines.append(f'    "{name}": "{digest}"' + ("," if i < len(items) - 1 else ""))
    lines += ["  }", "}"]
    pin.write_text("\n".join(lines) + "\n")
    json.loads(pin.read_text())  # the same format the real pin keeps
    return pin


def _tar(files: dict[str, bytes], links: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, content in files.items():
            info = tarfile.TarInfo(f"llama-{TAG}/{name}")
            info.size = len(content)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(content))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(f"llama-{TAG}/{name}")
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tf.addfile(info)
    return buf.getvalue()


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ── download-runtime.sh ───────────────────────────────────────────────────────

needs_bash = pytest.mark.skipif(BASH is None, reason="bash is not available")
LINUX_CPU = f"llama-{TAG}-bin-ubuntu-x64.tar.gz"
LINUX_VULKAN = f"llama-{TAG}-bin-ubuntu-vulkan-x64.tar.gz"


def _run_sh(tmp_path: Path, base: str, pin: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "LLAMA_CPP_PIN_FILE": str(pin),
        "LLAMA_CPP_DOWNLOAD_BASE": base,
        "CONVSIM_LLAMA_CPP_PLATFORM": "ubuntu-x64",
        "HOME": str(tmp_path / "home"),
    })
    env.pop("LLAMA_CPP_DEST", None)
    env.pop("LLAMA_CPP_VARIANT", None)
    env.pop("LLAMA_CPP_VERSION", None)
    assert BASH is not None
    return subprocess.run(
        [BASH, SH_SCRIPT.as_posix(), *args], env=env, capture_output=True, text=True, timeout=120,
    )


def _linux_archive(vulkan: bool = False) -> bytes:
    files = {"llama-server": b"#!/bin/sh\necho fake\n", "libllama.so.0.0.1": b"lib", "LICENSE": b"MIT", "llama-cli": b"x"}
    if vulkan:
        files["libggml-vulkan.so"] = b"vk"
    links = {"libllama.so.0": "libllama.so.0.0.1"} if sys.platform != "win32" else None
    return _tar(files, links)


@needs_bash
def test_sh_installs_a_verified_archive(tmp_path, release):
    root, base = release
    digest = _publish(root, LINUX_CPU, _linux_archive())
    dest = tmp_path / "out"
    result = _run_sh(tmp_path, base, _write_pin(tmp_path, {LINUX_CPU: digest}), "--dest", dest.as_posix())
    assert result.returncode == 0, result.stderr + result.stdout
    assert "checksum verified" in result.stdout
    assert (dest / "llama-server").is_file()
    assert (dest / "libllama.so.0.0.1").is_file()
    assert (dest / "LICENSE-llama.cpp.txt").read_bytes() == b"MIT"
    assert not (dest / "llama-cli").exists()
    if sys.platform != "win32":
        assert os.readlink(dest / "libllama.so.0") == "libllama.so.0.0.1"


@needs_bash
def test_sh_refuses_a_tampered_archive(tmp_path, release):
    root, base = release
    _publish(root, LINUX_CPU, _linux_archive())
    dest = tmp_path / "out"
    result = _run_sh(tmp_path, base, _write_pin(tmp_path, {LINUX_CPU: "0" * 64}), "--dest", dest.as_posix())
    assert result.returncode != 0
    assert "SHA-256 checksum mismatch" in result.stderr
    assert not (dest / "llama-server").exists()


@needs_bash
def test_sh_refuses_an_archive_with_no_pinned_digest(tmp_path, release):
    root, base = release
    _publish(root, LINUX_CPU, _linux_archive())
    dest = tmp_path / "out"
    result = _run_sh(tmp_path, base, _write_pin(tmp_path, {"some-other.tar.gz": "1" * 64}), "--dest", dest.as_posix())
    assert result.returncode != 0
    assert "No pinned SHA-256" in result.stderr
    assert not (dest / "llama-server").exists()


@needs_bash
def test_sh_refuses_an_unpinned_tag_without_a_digest(tmp_path, release):
    root, base = release
    _publish(root, LINUX_CPU, _linux_archive())
    result = _run_sh(tmp_path, base, _write_pin(tmp_path, {}), "--version", "b2", "--dest", (tmp_path / "o").as_posix())
    assert result.returncode != 0
    assert "not the pinned release" in result.stderr


@needs_bash
def test_sh_vulkan_variant_installs_into_its_own_directory(tmp_path, release):
    root, base = release
    digest = _publish(root, LINUX_VULKAN, _linux_archive(vulkan=True))
    result = _run_sh(tmp_path, base, _write_pin(tmp_path, {LINUX_VULKAN: digest}), "--variant", "vulkan")
    assert result.returncode == 0, result.stderr + result.stdout
    vulkan_dir = tmp_path / "home" / ".convsim" / "bin" / "vulkan"
    assert (vulkan_dir / "llama-server").is_file()
    assert (vulkan_dir / "libggml-vulkan.so").is_file()
    assert not (tmp_path / "home" / ".convsim" / "bin" / "llama-server").exists()


@needs_bash
def test_sh_refuses_a_vulkan_build_for_macos(tmp_path, release):
    _, base = release
    env_pin = _write_pin(tmp_path, {})
    env = dict(os.environ, LLAMA_CPP_PIN_FILE=str(env_pin), LLAMA_CPP_DOWNLOAD_BASE=base,
               CONVSIM_LLAMA_CPP_PLATFORM="macos-arm64", HOME=str(tmp_path / "home"))
    result = subprocess.run([BASH, SH_SCRIPT.as_posix(), "--variant", "vulkan"], env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert "no Vulkan build for macOS" in result.stderr


# ── download-runtime.ps1 ──────────────────────────────────────────────────────

needs_powershell = pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
WIN_CPU = f"llama-{TAG}-bin-win-cpu-x64.zip"
WIN_VULKAN = f"llama-{TAG}-bin-win-vulkan-x64.zip"


def _run_ps(tmp_path: Path, base: str, pin: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({"LLAMA_CPP_PIN_FILE": str(pin), "LLAMA_CPP_DOWNLOAD_BASE": base})
    assert POWERSHELL is not None
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(PS_SCRIPT), *args],
        env=env, capture_output=True, text=True, timeout=180,
    )


def _windows_archive(vulkan: bool = False) -> bytes:
    files = {"llama-server.exe": b"MZfake", "ggml.dll": b"ggml", "llama.dll": b"llama"}
    if vulkan:
        files["ggml-vulkan.dll"] = b"vk"
    return _zip(files)


@needs_powershell
def test_ps1_installs_a_verified_archive(tmp_path, release):
    root, base = release
    digest = _publish(root, WIN_CPU, _windows_archive())
    dest = tmp_path / "out"
    result = _run_ps(tmp_path, base, _write_pin(tmp_path, {WIN_CPU: digest}), "-Dest", str(dest))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "checksum verified" in result.stdout
    assert (dest / "llama-server.exe").read_bytes() == b"MZfake"
    assert (dest / "ggml.dll").is_file()


@needs_powershell
def test_ps1_refuses_a_tampered_archive(tmp_path, release):
    root, base = release
    _publish(root, WIN_CPU, _windows_archive())
    dest = tmp_path / "out"
    result = _run_ps(tmp_path, base, _write_pin(tmp_path, {WIN_CPU: "0" * 64}), "-Dest", str(dest))
    assert result.returncode != 0
    assert "SHA-256 checksum mismatch" in result.stderr + result.stdout
    assert not (dest / "llama-server.exe").exists()


@needs_powershell
def test_ps1_refuses_an_archive_with_no_pinned_digest(tmp_path, release):
    root, base = release
    _publish(root, WIN_CPU, _windows_archive())
    dest = tmp_path / "out"
    result = _run_ps(tmp_path, base, _write_pin(tmp_path, {"some-other.zip": "1" * 64}), "-Dest", str(dest))
    assert result.returncode != 0
    assert "No pinned SHA-256" in result.stderr + result.stdout
    assert not (dest / "llama-server.exe").exists()


@needs_powershell
def test_ps1_vulkan_variant(tmp_path, release):
    root, base = release
    digest = _publish(root, WIN_VULKAN, _windows_archive(vulkan=True))
    dest = tmp_path / "runtimes" / "vulkan"
    result = _run_ps(tmp_path, base, _write_pin(tmp_path, {WIN_VULKAN: digest}), "-Variant", "vulkan", "-Dest", str(dest))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (dest / "ggml-vulkan.dll").is_file()


@needs_powershell
def test_ps1_cpu_build_refuses_to_sit_beside_the_vulkan_backend(tmp_path, release):
    root, base = release
    # A CPU archive that (wrongly) carries the Vulkan backend must not install
    # as the CPU build.
    digest = _publish(root, WIN_CPU, _windows_archive(vulkan=True))
    result = _run_ps(tmp_path, base, _write_pin(tmp_path, {WIN_CPU: digest}), "-Dest", str(tmp_path / "out"))
    assert result.returncode != 0
    assert "ggml-vulkan.dll" in result.stderr + result.stdout
