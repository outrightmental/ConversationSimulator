# SPDX-License-Identifier: Apache-2.0
"""Tests for the guided voice setup flow (issue #487).

Three concerns, in order of how much damage a regression would do:

1. the registry discloses everything the download policy requires, and never
   ships an unverifiable entry;
2. a download that does not match its checksum leaves nothing installed;
3. the plan and job endpoints describe the machine truthfully, including the
   two engines the app refuses to download.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

import convsim_core.runtime  # noqa: F401 — register built-in adapters
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.services import voice_registry
from convsim_core.services.setup_install_service import StageState
from convsim_core.services.voice_download import (
    ChecksumMismatch,
    DownloadCancelled,
    download_voice_asset,
)
from convsim_core.services.voice_setup_service import (
    get_stt_model_path,
    retire_orphaned_jobs,
    set_stt_model_path,
)
from convsim_core.storage.database import Database

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def voice_paths(tmp_path, monkeypatch):
    """Redirect every voice path at tmp_path.

    Without this the registry resolves install paths under the developer's real
    home directory, so a test could both read their actual install state and —
    far worse — write into it.
    """
    stt_model = tmp_path / "models" / "stt" / "ggml-base.en.bin"
    vad_model = tmp_path / "models" / "vad" / "silero_vad.onnx"
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_MODEL_PATH", str(stt_model))
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    monkeypatch.setenv("CONVSIM_SILERO_VAD_MODEL_PATH", str(vad_model))
    return {"stt_dir": stt_model.parent, "stt_model": stt_model, "vad_model": vad_model}


@pytest.fixture()
def tmp_config(tmp_path):
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        exports_dir=str(tmp_path / "exports"),
        cache_dir=str(tmp_path / "cache"),
        crash_bundles_dir=str(tmp_path / "crashes"),
        models_dir=str(tmp_path / "models" / "llm"),
        official_packs_dir=str(tmp_path / "no-official-packs"),
    )


@pytest.fixture()
def client(tmp_config, voice_paths):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(tmp_path):
    database = Database.open(str(tmp_path / "jobs-db"))
    yield database
    database.close()


# ── Registry: disclosure and verifiability ────────────────────────────────────


def test_every_asset_is_fully_disclosed():
    """No asset may ship without the six fields the confirmation screen shows."""
    assert voice_registry.VOICE_ASSETS, "the registry must not be empty"
    for asset in voice_registry.VOICE_ASSETS:
        assert asset.name
        assert asset.url.startswith("https://"), asset.id
        assert _SHA256_RE.match(asset.sha256), f"{asset.id} has no usable SHA-256"
        assert asset.size_bytes > 0, asset.id
        assert asset.license
        assert asset.license_url.startswith("https://"), asset.id


def test_download_urls_are_revision_pinned():
    """A floating tag could change the bytes under a pinned checksum."""
    for asset in voice_registry.VOICE_ASSETS:
        assert "/resolve/main/" not in asset.url, asset.id
        assert "/raw/master/" not in asset.url, asset.id
        # Both hosts we use carry a 40-char commit sha in the path.
        assert re.search(r"/[0-9a-f]{40}/", asset.url), asset.id


def test_exactly_one_recommended_asset_per_capability():
    for capability in ("stt", "vad"):
        recommended = [a for a in voice_registry.assets_for(capability) if a.recommended]
        assert len(recommended) == 1, capability


def test_engine_commands_cover_every_desktop_platform():
    for engine in voice_registry.VOICE_ENGINES:
        for platform in ("darwin", "linux", "win32"):
            assert voice_registry.engine_command(engine, platform), (engine.id, platform)
    # sys.platform is "linux2"-style on some builds; the lookup must normalise.
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None
    assert voice_registry.engine_command(whisper, "linux2") == whisper.commands["linux"]


def test_whisper_commands_name_packages_that_exist():
    """A command that 404s on the package index is worse than no command.

    The first cut shipped ``winget install --id ggml.whisper-cpp``, which fails
    with "No package found matching input criteria" — winget-pkgs carries only
    ``ggml.llamacpp`` under that publisher. Homebrew is the one package manager
    of the three that ships whisper.cpp, and the formula was renamed, so pin
    both facts rather than re-discovering them from a bug report.
    """
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None

    assert whisper.commands["darwin"] == "brew install whisper.cpp"

    # No winget/apt package exists, so these two must build from source.
    for platform in ("linux", "win32"):
        command = whisper.commands[platform]
        assert "winget" not in command, platform
        assert "cmake --build" in command, platform


def test_the_windows_command_runs_in_the_shell_windows_actually_opens():
    """``&&`` is a parse error in Windows PowerShell 5.1, the stock default shell.

    PowerShell gained ``&&`` in version 7; 5.1 answers "The token '&&' is not a
    valid statement separator in this version" and runs none of the line. A
    command that cannot be pasted into the shell the player has open is the same
    dead end as a package name that does not exist, so the Windows build is
    handed over newline-separated — a statement separator both PowerShell and
    cmd.exe accept.
    """
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None

    windows = whisper.commands["win32"]
    assert "&&" not in windows, windows
    assert windows.count("\n") >= 2, "the three build steps must be separate lines"
    # Nothing in it may depend on a shell-specific variable syntax: %VAR% is
    # cmd.exe only and $env:VAR is PowerShell only, so neither can appear in a
    # string handed to whichever one the player opened.
    assert "%" not in windows, windows
    assert "$env:" not in windows, windows

    # bash has `&&` and expands `~`, so Linux keeps the fail-fast chain.
    assert "&&" in whisper.commands["linux"]


def test_a_source_build_lands_where_the_lookup_will_find_it():
    """The install step must put the binary somewhere ``_find_binary`` resolves.

    ``/usr/local/bin`` needs sudo and is read-only on an immutable SteamOS
    root, and a binary left in the build tree is not installed at all.
    ``~/.convsim/bin`` is resolved on every plan read, so it needs neither sudo
    nor a restart and "Check again" can turn the row green.
    """
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None

    linux = whisper.commands["linux"]
    assert "sudo" not in linux, linux
    assert "~/.convsim/bin" in linux, linux

    from convsim_core.stt.whisper_cpp import _USER_BIN_SUBPATH

    assert _USER_BIN_SUBPATH == (".convsim", "bin"), (
        "the command copies into ~/.convsim/bin; the lookup must search there"
    )


def test_a_build_command_names_the_toolchain_it_needs(monkeypatch):
    """"git: command not found" is the same dead end as a 404 package name.

    Neither Linux nor Windows ships git, cmake and a C++ compiler by default,
    and the app bundles none of them, so the note has to say so — the Docker
    note for Kokoro exists for exactly this reason.
    """
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None

    for platform in ("linux", "win32"):
        note = voice_registry.engine_command_note(whisper, platform)
        assert note is not None, platform
        for tool in ("git", "cmake", "compiler"):
            assert tool in note.lower(), (platform, tool)


def test_a_source_build_produces_a_self_contained_binary():
    """A binary that needs its build tree is not installed, however much PATH says so.

    Upstream defaults BUILD_SHARED_LIBS ON everywhere but MinGW, which drops
    libwhisper/libggml beside the executable in ``build/bin`` and links against
    them through a build-tree rpath. The Linux command copies *only*
    ``whisper-cli`` onto PATH, so deleting the clone — the obvious tidy-up once
    the binary is "installed" — leaves something the PATH lookup still finds
    and ``whisper-cli`` can no longer load. ``find_whisper_binary`` would report
    the engine present, the plan would show the row green, and the player would
    find out mid-conversation: precisely the dead end this flow removes.
    """
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None

    for platform in ("linux", "win32"):
        assert "-DBUILD_SHARED_LIBS=OFF" in whisper.commands[platform], platform


def test_a_command_that_does_not_finish_the_job_carries_a_follow_up_note(monkeypatch):
    """Building on Windows leaves the binary in the build tree, so the note must place it.

    The route it names must be one the running service can observe. A PATH edit
    or a new environment variable is not: both are a snapshot taken when a
    process starts, so "Check again" could never turn green and the note would
    have to ask for a restart. ``~/.convsim/bin`` is re-resolved on every plan
    read, so the note names that instead and the re-check works.
    """
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None

    note = voice_registry.engine_command_note(whisper, "win32")
    assert note is not None
    # Where the build leaves it, and where to put it so the lookup finds it.
    assert "build\\bin\\Release" in note, note
    assert ".convsim\\bin" in note, note
    assert "check again" in note.lower(), note
    assert "no restart" in note.lower(), note

    # macOS needs no follow-up once the command has run: brew puts whisper-cli
    # on PATH itself. Pin which program is consulted, so a machine without
    # Homebrew does not quietly turn this into the brew note below.
    monkeypatch.setattr(voice_registry, "find_tool", lambda name: f"/usr/bin/{name}")
    assert voice_registry.engine_command_note(whisper, "darwin") is None


def test_the_mac_command_says_so_when_homebrew_is_not_there(monkeypatch):
    """`brew install …` on a stock Mac is "command not found" — a dead end.

    Homebrew is not part of macOS, and macOS is the one platform whose command
    is a package-manager one-liner rather than a source build. Handing it over
    unqualified is the same dead end as the winget package that does not exist
    and as Kokoro's docker command on a machine without Docker, both of which
    this flow already names.

    The note must stay off Linux and Windows, whose commands never run brew:
    they have a platform follow-up of their own, and that takes precedence.
    """
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None

    monkeypatch.setattr(voice_registry, "find_tool", lambda _name: None)
    note = voice_registry.engine_command_note(whisper, "darwin")
    assert note is not None, "a brew command on a Mac without brew cannot even start"
    assert "brew" in note.lower(), note
    # It must name the way out, not just the obstacle — and the source build is
    # the route for someone who does not want Homebrew at all.
    assert "brew.sh" in note, note
    assert "source" in note.lower(), note

    # The two build platforms keep their toolchain note, brew or no brew.
    for platform in ("linux", "win32"):
        other = voice_registry.engine_command_note(whisper, platform)
        assert other is not None and "brew" not in other.lower(), (platform, other)

    # With Homebrew present the command is self-contained, so the row is quiet.
    monkeypatch.setattr(voice_registry, "find_tool", lambda name: f"/usr/bin/{name}")
    assert voice_registry.engine_command_note(whisper, "darwin") is None


def test_a_command_that_needs_a_program_this_machine_lacks_says_so(monkeypatch):
    """"docker: command not found" is the same dead end as a 404 package name.

    Kokoro's command *runs* in Docker, so on a machine without Docker it cannot
    start at all. Saying nothing would send the player to a terminal to find
    that out, which is exactly what this screen exists to prevent.
    """
    kokoro = voice_registry.get_engine("kokoro-server")
    assert kokoro is not None
    assert "docker run" in kokoro.commands["win32"]

    monkeypatch.setattr(voice_registry, "find_tool", lambda _name: None)
    note = voice_registry.engine_command_note(kokoro, "win32")
    assert note is not None
    assert "docker" in note.lower()
    # It must name the way out, not just the obstacle.
    assert "docker.com" in note, note

    # Present on PATH: the command is self-contained, so the row stays quiet.
    # This also covers the lookup for an engine that declares no platform notes.
    monkeypatch.setattr(voice_registry, "find_tool", lambda name: f"/usr/bin/{name}")
    assert voice_registry.engine_command_note(kokoro, "win32") is None

    # A platform follow-up still wins over a prerequisite note.
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None
    monkeypatch.setattr(voice_registry, "find_tool", lambda _name: None)
    assert ".convsim\\bin" in (voice_registry.engine_command_note(whisper, "win32") or "")


def test_plan_exposes_the_follow_up_note_for_this_platform(client):
    """The note has to survive the response model, or the UI cannot render it."""
    body = client.get("/api/voice/setup/plan").json()

    engines = {e["id"]: e for e in body["engines"]}
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None
    assert engines["whisper-cli"]["command_note"] == voice_registry.engine_command_note(
        whisper, sys.platform
    )
    # Kokoro's note depends on whether this machine has docker, so compare it
    # against the same resolver rather than pinning one of the two outcomes.
    kokoro = voice_registry.get_engine("kokoro-server")
    assert kokoro is not None
    assert engines["kokoro-server"]["command_note"] == voice_registry.engine_command_note(
        kokoro, sys.platform
    )


def test_a_pip_command_is_only_offered_where_pip_can_reach_this_server(monkeypatch):
    """onnxruntime is the `vad` extra; no shipped binary contains it or a pip.

    The release PyInstaller build installs only ``[build]`` and excludes ``pip``
    outright, so "pip install onnxruntime" cannot close the gap it is offered
    to close in a packaged app — there is no interpreter for it to install
    into. The plan says so, and the UI swaps the command for an explanation.
    """
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert voice_registry.onnxruntime_installable() is True

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert voice_registry.onnxruntime_installable() is False


def test_plan_reports_whether_onnxruntime_can_be_installed_here(client):
    """The flag has to survive the response model, or the UI cannot act on it."""
    body = client.get("/api/voice/setup/plan").json()

    assert body["onnxruntime_installable"] is voice_registry.onnxruntime_installable()
    # Separate from whether it is already there: a packaged build answers
    # "not installed, and not installable" and must not print a command.
    assert "onnxruntime_installed" in body


def test_install_paths_follow_the_engines(voice_paths):
    """A model installed where the engine does not look is not installed at all."""
    base_en = voice_registry.get_asset("whisper-base-en")
    small_en = voice_registry.get_asset("whisper-small-en")
    silero = voice_registry.get_asset("silero-vad")
    assert base_en and small_en and silero

    assert voice_registry.install_path(base_en) == voice_paths["stt_dir"] / "ggml-base.en.bin"
    # An alternative STT model keeps its own filename beside the default one.
    assert voice_registry.install_path(small_en) == voice_paths["stt_dir"] / "ggml-small.en.bin"
    # There is only one VAD model, so it must land on the exact configured path.
    assert voice_registry.install_path(silero) == voice_paths["vad_model"]


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


@pytest.mark.skipif(sys.platform == "win32", reason="chmod +x is a no-op on Windows")
def test_a_bundled_whisper_binary_is_reported_as_installed(tmp_path, monkeypatch):
    """A Steam depot ships whisper-cli in runtimes/ and never touches PATH.

    The shell hands the backend CONVSIM_BUNDLED_RUNTIME_DIR instead
    (publishing/STEAM_DEPOT_CONTENTS.md, docs/sidecar-bundling.md), which is
    how llama-server and the Kokoro server are found. A PATH-only lookup would
    report speech-to-text missing on the one platform that bundles it, and this
    flow would then hand those players a from-source cmake build for a binary
    already installed one directory away.
    """
    monkeypatch.delenv("CONVSIM_WHISPER_CPP_BINARY_PATH", raising=False)
    monkeypatch.setattr(voice_registry, "find_tool", lambda _name: None)
    import convsim_core.stt.whisper_cpp as whisper_cpp

    monkeypatch.setattr(whisper_cpp, "find_tool", lambda _name: None)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    runtimes = tmp_path / "runtimes"
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(runtimes))
    assert voice_registry.find_whisper_binary() is None

    bundled = _make_executable(runtimes / "whisper-cli")
    assert voice_registry.find_whisper_binary() == str(bundled)


@pytest.mark.skipif(sys.platform == "win32", reason="chmod +x is a no-op on Windows")
def test_a_binary_dropped_in_the_user_bin_dir_needs_no_restart(tmp_path, monkeypatch):
    """The destination both build commands name must be resolved per check.

    The Windows note tells the player to copy whisper-cli.exe into
    ~/.convsim/bin and press Check again; the Linux command copies it there
    itself. Either way the lookup has to search that directory on every call,
    or the note is asking for a button press that can never turn the row green.
    """
    monkeypatch.delenv("CONVSIM_WHISPER_CPP_BINARY_PATH", raising=False)
    monkeypatch.delenv("CONVSIM_BUNDLED_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(voice_registry, "find_tool", lambda _name: None)
    import convsim_core.stt.whisper_cpp as whisper_cpp

    monkeypatch.setattr(whisper_cpp, "find_tool", lambda _name: None)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    assert voice_registry.find_whisper_binary() is None
    installed = _make_executable(home / ".convsim" / "bin" / "whisper-cli")
    assert voice_registry.find_whisper_binary() == str(installed)


@pytest.mark.skipif(sys.platform == "win32", reason="chmod +x is a no-op on Windows")
def test_an_explicit_override_still_wins_over_a_bundled_binary(tmp_path, monkeypatch):
    """CONVSIM_WHISPER_CPP_BINARY_PATH is the escape hatch; nothing may outrank it."""
    runtimes = tmp_path / "runtimes"
    _make_executable(runtimes / "whisper-cli")
    monkeypatch.setenv("CONVSIM_BUNDLED_RUNTIME_DIR", str(runtimes))

    override = _make_executable(tmp_path / "elsewhere" / "whisper-cli")
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(override))
    assert voice_registry.find_whisper_binary() == str(override)

    # An override pointing at nothing reports missing rather than silently
    # falling back to the bundled copy the player chose to override.
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "gone"))
    assert voice_registry.find_whisper_binary() is None


# ── Programs the player installed, found where their shell would find them ────


def test_a_homebrew_install_is_found_without_a_path_entry(tmp_path, monkeypatch):
    """The macOS commands this flow hands out install into Homebrew's bin dir.

    A Finder- or Steam-launched build never has that directory on PATH:
    launchd gives GUI apps /usr/bin:/bin:/usr/sbin:/sbin, and the Tauri shell
    passes its environment through to convsim-core untouched. Looking only at
    PATH would have the ffmpeg card quote `brew install ffmpeg` at someone who
    already ran it, with no way to ever clear the row — the dead end the whole
    flow exists to remove.
    """
    brew_bin = tmp_path / "opt" / "homebrew" / "bin"
    brew_bin.mkdir(parents=True)
    monkeypatch.setattr(
        "convsim_core.runtime.toolpath.supplementary_bin_dirs",
        lambda platform=None: (str(brew_bin),),
    )
    monkeypatch.setattr("shutil.which", lambda _name, **_kw: None)

    assert voice_registry.ffmpeg_installed() is False
    _make_executable(brew_bin / "ffmpeg")
    assert voice_registry.ffmpeg_installed() is True, (
        "ffmpeg installed by Homebrew must register, or every recording the "
        "browser makes is undecodable with no row the player can clear"
    )


def test_a_prerequisite_note_is_not_raised_against_a_tool_that_is_installed(
    tmp_path, monkeypatch
):
    """"brew was not found on this machine" must not be said of a machine with brew.

    The note steers the player to brew.sh and to building from source instead.
    Shown to a Homebrew user because the backend inherited launchd's PATH, it
    is simply false — and it talks them out of the one-line install that would
    have worked.
    """
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None

    brew_bin = tmp_path / "opt" / "homebrew" / "bin"
    brew_bin.mkdir(parents=True)
    monkeypatch.setattr(
        "convsim_core.runtime.toolpath.supplementary_bin_dirs",
        lambda platform=None: (str(brew_bin),),
    )
    monkeypatch.setattr("shutil.which", lambda _name, **_kw: None)

    assert voice_registry.engine_command_note(whisper, "darwin") is not None
    _make_executable(brew_bin / "brew")
    assert voice_registry.engine_command_note(whisper, "darwin") is None


def test_path_still_wins_over_the_supplementary_directories(tmp_path, monkeypatch):
    """An explicit PATH entry is the player's choice and must not be second-guessed."""
    from convsim_core.runtime import toolpath

    brew_bin = tmp_path / "homebrew" / "bin"
    brew_bin.mkdir(parents=True)
    _make_executable(brew_bin / "ffmpeg")
    monkeypatch.setattr(toolpath, "supplementary_bin_dirs", lambda platform=None: (str(brew_bin),))
    monkeypatch.setattr("shutil.which", lambda _name, **_kw: "/somewhere/else/ffmpeg")

    assert toolpath.find_tool("ffmpeg") == "/somewhere/else/ffmpeg"


def test_only_the_platforms_that_need_a_supplement_get_one():
    """Windows puts the machine PATH in every process environment, GUI ones included."""
    from convsim_core.runtime.toolpath import supplementary_bin_dirs

    assert "/opt/homebrew/bin" in supplementary_bin_dirs("darwin")
    # linux2-style legacy values must fold onto the same key.
    assert supplementary_bin_dirs("linux") == supplementary_bin_dirs("linux2")
    assert supplementary_bin_dirs("win32") == ()


# ── Downloader ────────────────────────────────────────────────────────────────


def _mock_client(content: bytes, *, status_code: int = 200, headers: dict | None = None):
    async def _aiter_bytes(chunk_size=None):
        yield content

    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    response.headers = {"content-length": str(len(content)), **(headers or {})}
    response.aiter_bytes = _aiter_bytes

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=None)

    client = MagicMock(spec=httpx.AsyncClient)
    client.stream = MagicMock(return_value=cm)
    client.aclose = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_download_verifies_and_installs(tmp_path):
    content = b"pretend ggml weights"
    dest = tmp_path / "stt" / "ggml-base.en.bin"
    seen: list[tuple[int, int | None]] = []

    written = await download_voice_asset(
        url="https://example.test/m.bin",
        dest_path=dest,
        expected_sha256=_sha256_of(content),
        progress_cb=lambda done, total: seen.append((done, total)),
        _client=_mock_client(content),
    )

    assert written == len(content)
    assert dest.read_bytes() == content
    assert not dest.with_name(dest.name + ".part").exists()
    assert seen[-1][0] == len(content)


@pytest.mark.asyncio
async def test_download_rejects_a_checksum_mismatch(tmp_path):
    dest = tmp_path / "stt" / "ggml-base.en.bin"

    with pytest.raises(ChecksumMismatch):
        await download_voice_asset(
            url="https://example.test/m.bin",
            dest_path=dest,
            expected_sha256="b" * 64,
            _client=_mock_client(b"tampered"),
        )

    # Neither the final file nor the partial may survive a failed verification.
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


@pytest.mark.asyncio
async def test_download_cancel_leaves_nothing_behind(tmp_path):
    dest = tmp_path / "stt" / "ggml-base.en.bin"
    cancel = asyncio.Event()
    cancel.set()

    with pytest.raises(DownloadCancelled):
        await download_voice_asset(
            url="https://example.test/m.bin",
            dest_path=dest,
            expected_sha256=_sha256_of(b"anything"),
            cancel_event=cancel,
            _client=_mock_client(b"anything"),
        )

    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


@pytest.mark.asyncio
async def test_download_resumes_from_a_partial_file(tmp_path):
    """A .part left by a killed process continues instead of restarting."""
    content = b"0123456789abcdef"
    dest = tmp_path / "stt" / "ggml-base.en.bin"
    dest.parent.mkdir(parents=True)
    part = dest.with_name(dest.name + ".part")
    part.write_bytes(content[:6])

    client = _mock_client(
        content[6:],
        status_code=206,
        headers={"content-range": f"bytes 6-{len(content) - 1}/{len(content)}"},
    )

    written = await download_voice_asset(
        url="https://example.test/m.bin",
        dest_path=dest,
        expected_sha256=_sha256_of(content),
        _client=client,
    )

    assert written == len(content)
    assert dest.read_bytes() == content
    assert client.stream.call_args.kwargs["headers"] == {"Range": "bytes=6-"}


@pytest.mark.asyncio
async def test_download_requires_the_explicit_download_network_mode(tmp_path, monkeypatch):
    """Nothing here may be reachable from play-mode code."""
    seen: list = []
    monkeypatch.setattr(
        "convsim_core.services.voice_download.require_network",
        lambda mode: seen.append(mode),
    )
    await download_voice_asset(
        url="https://example.test/m.bin",
        dest_path=tmp_path / "m.bin",
        expected_sha256=_sha256_of(b"x"),
        _client=_mock_client(b"x"),
    )
    from convsim_core.network_policy import NetworkMode

    assert seen == [NetworkMode.EXPLICIT_DOWNLOAD]


# ── Plan endpoint ─────────────────────────────────────────────────────────────


def test_plan_reports_both_capabilities_as_not_ready(client):
    body = client.get("/api/voice/setup/plan").json()

    ids = {c["id"] for c in body["capabilities"]}
    assert ids == {"stt", "tts", "vad"}
    assert all(not c["ready"] for c in body["capabilities"])
    assert body["active_job_id"] is None


def test_plan_names_the_engines_it_will_not_download(client):
    body = client.get("/api/voice/setup/plan").json()

    engines = {e["id"]: e for e in body["engines"]}
    assert set(engines) == {"whisper-cli", "kokoro-server"}
    for engine in engines.values():
        assert engine["installed"] is False
        assert engine["why_manual"]
        # The player gets a command for their own platform, not a generic link.
        assert engine["command"]
        assert engine["docs_url"].startswith("https://")
    # Only the Kokoro server is something the app can launch itself.
    assert engines["kokoro-server"]["startable"] is True
    assert engines["whisper-cli"]["startable"] is False


def test_an_externally_run_engine_is_not_reported_as_missing(voice_paths):
    """A Kokoro server run from Docker leaves no binary for the app to find.

    The Docker command is the one this very plan hands out, so resolving the row
    from ``find_kokoro_executable`` alone would re-offer a command the player has
    already run — behind a "Check again" that can never turn green — right next
    to a capability the worker reports as ready.
    """
    from convsim_core.services.voice_setup_service import build_plan
    from convsim_core.storage.database import Database

    database = Database.open(str(voice_paths["stt_dir"].parent / "serving-db"))
    try:
        plan = build_plan(database.connection(), stt_ready=False, tts_ready=True)
    finally:
        database.close()

    kokoro = next(e for e in plan["engines"] if e["id"] == "kokoro-server")
    assert kokoro["serving"] is True
    assert kokoro["installed"] is True
    # Nothing was located, so no path may be claimed.
    assert kokoro["found_at"] is None

    # Speech-to-text is not ready here, so its engine row stays honest.
    whisper = next(e for e in plan["engines"] if e["id"] == "whisper-cli")
    assert whisper["serving"] is False
    assert whisper["installed"] is False


def test_an_engine_the_app_cannot_see_is_not_offered_as_startable(client):
    """``serving`` must survive the response model — the UI hides Start on it."""
    body = client.get("/api/voice/setup/plan").json()
    kokoro = next(e for e in body["engines"] if e["id"] == "kokoro-server")
    # Nothing is running in this fixture, so the row is a genuine gap.
    assert kokoro["serving"] is False
    assert kokoro["installed"] is False


def test_plan_discloses_source_licence_checksum_and_destination(client):
    body = client.get("/api/voice/setup/plan").json()

    assert body["assets"], "the plan must list the downloadable assets"
    for asset in body["assets"]:
        assert asset["source_url"].startswith("https://")
        assert asset["license"] and asset["license_url"]
        assert _SHA256_RE.match(asset["sha256"])
        assert asset["size_bytes"] > 0
        assert asset["install_path"]
        assert asset["installed"] is False


def test_plan_marks_an_asset_installed_once_the_file_exists(client, voice_paths):
    voice_paths["vad_model"].parent.mkdir(parents=True, exist_ok=True)
    voice_paths["vad_model"].write_bytes(b"onnx")

    body = client.get("/api/voice/setup/plan").json()
    silero = next(a for a in body["assets"] if a["id"] == "silero-vad")
    assert silero["installed"] is True


def test_plan_default_download_size_excludes_installed_assets(client, voice_paths):
    before = client.get("/api/voice/setup/plan").json()
    assert before["default_asset_ids"] == ["whisper-base-en", "silero-vad"]

    voice_paths["vad_model"].parent.mkdir(parents=True, exist_ok=True)
    voice_paths["vad_model"].write_bytes(b"onnx")

    after = client.get("/api/voice/setup/plan").json()
    silero = voice_registry.get_asset("silero-vad")
    assert silero is not None
    assert after["default_download_bytes"] == before["default_download_bytes"] - silero.size_bytes


def test_plan_marks_the_configured_default_as_selected(client, voice_paths):
    """With no recorded choice, the file the worker is configured to read wins."""
    voice_paths["stt_model"].parent.mkdir(parents=True, exist_ok=True)
    voice_paths["stt_model"].write_bytes(b"ggml")

    assets = {a["id"]: a for a in client.get("/api/voice/setup/plan").json()["assets"]}
    assert assets["whisper-base-en"]["selected"] is True
    assert assets["whisper-small-en"]["selected"] is False


def test_plan_follows_a_recorded_choice_over_the_default(client, voice_paths):
    """Installing small.en makes it the selected model, not base.en."""
    from convsim_core.services.voice_setup_service import set_stt_model_path

    for name in ("ggml-base.en.bin", "ggml-small.en.bin"):
        path = voice_paths["stt_dir"] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ggml")
    set_stt_model_path(
        client.app.state.db.connection(), str(voice_paths["stt_dir"] / "ggml-small.en.bin")
    )

    assets = {a["id"]: a for a in client.get("/api/voice/setup/plan").json()["assets"]}
    assert assets["whisper-small-en"]["selected"] is True
    assert assets["whisper-base-en"]["selected"] is False


def test_an_uninstalled_asset_is_never_selected(client):
    for asset in client.get("/api/voice/setup/plan").json()["assets"]:
        assert asset["selected"] is False


def test_install_path_refuses_a_capability_with_no_engine_directory():
    """A future downloadable TTS asset must fail loudly, not land in the STT dir."""
    from dataclasses import replace

    base_en = voice_registry.get_asset("whisper-base-en")
    assert base_en is not None
    with pytest.raises(ValueError, match="tts"):
        voice_registry.install_path(replace(base_en, capability="tts"))


# ── Install job endpoints ─────────────────────────────────────────────────────


def _stub_downloads(monkeypatch, *, fail_with: Exception | None = None) -> list[Path]:
    """Replace the network download with a local file write; returns written paths."""
    written: list[Path] = []

    async def _fake_download(*, url, dest_path, expected_sha256, progress_cb=None, cancel_event=None, **_):
        if fail_with is not None:
            raise fail_with
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"downloaded")
        written.append(dest_path)
        if progress_cb is not None:
            progress_cb(10, 10)
        return 10

    monkeypatch.setattr(
        "convsim_core.routers.voice_setup.download_voice_asset", _fake_download
    )
    return written


def _await_terminal(client: TestClient, job_id: int) -> dict:
    for _ in range(100):
        body = client.get(f"/api/voice/setup/install/{job_id}").json()
        if body["status"] in ("complete", "failed", "cancelled"):
            return body
        import time

        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached a terminal state")


def test_install_downloads_the_requested_assets(client, monkeypatch, voice_paths):
    written = _stub_downloads(monkeypatch)

    started = client.post(
        "/api/voice/setup/install", json={"asset_ids": ["whisper-base-en", "silero-vad"]}
    )
    assert started.status_code == 200
    job = _await_terminal(client, started.json()["id"])

    assert job["status"] == "complete"
    assert [s["state"] for s in job["stages"]] == ["complete", "complete"]
    assert set(written) == {voice_paths["stt_model"], voice_paths["vad_model"]}


def test_install_points_the_stt_worker_at_the_model_it_fetched(client, monkeypatch, voice_paths):
    """Choosing small.en must actually switch the worker, not just drop a file."""
    _stub_downloads(monkeypatch)

    started = client.post("/api/voice/setup/install", json={"asset_ids": ["whisper-small-en"]})
    job = _await_terminal(client, started.json()["id"])
    assert job["status"] == "complete"

    expected = str(voice_paths["stt_dir"] / "ggml-small.en.bin")
    conn = client.app.state.db.connection()
    assert get_stt_model_path(conn) == expected
    assert client.app.state.stt_worker.model_path == expected


def test_install_skips_an_asset_that_is_already_present(client, monkeypatch, voice_paths):
    voice_paths["vad_model"].parent.mkdir(parents=True, exist_ok=True)
    voice_paths["vad_model"].write_bytes(b"onnx")
    written = _stub_downloads(monkeypatch)

    started = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]})
    job = _await_terminal(client, started.json()["id"])

    assert job["stages"][0]["state"] == "skipped"
    assert written == []


def test_installing_an_already_present_stt_model_switches_the_worker(
    client, monkeypatch, voice_paths
):
    """Switching between two installed models needs no download, only a re-point."""
    small = voice_paths["stt_dir"] / "ggml-small.en.bin"
    small.parent.mkdir(parents=True, exist_ok=True)
    small.write_bytes(b"ggml")
    written = _stub_downloads(monkeypatch)

    started = client.post("/api/voice/setup/install", json={"asset_ids": ["whisper-small-en"]})
    job = _await_terminal(client, started.json()["id"])

    assert job["status"] == "complete"
    assert job["stages"][0]["state"] == "skipped"
    assert written == []
    assert client.app.state.stt_worker.model_path == str(small)


def test_a_restart_re_applies_the_model_the_player_chose(tmp_config, voice_paths):
    """A choice that does not survive a restart is not a choice.

    The install endpoint re-points the live worker, but that lives in memory.
    Startup has to read the recorded path back, or the first utterance after a
    restart transcribes with the configured default — a model the player may
    never have installed. ``apply_stt_model_path`` finds ``set_model_path`` by
    ``getattr``, so a rename on either side would no-op in silence; only an
    end-to-end restart catches it.
    """
    chosen = str(voice_paths["stt_dir"] / "ggml-small.en.bin")

    with TestClient(create_app(tmp_config)) as first:
        # Nothing has re-pointed this worker yet: it reads the configured default.
        assert first.app.state.stt_worker.model_path == str(voice_paths["stt_model"])
        set_stt_model_path(first.app.state.db.connection(), chosen)

    with TestClient(create_app(tmp_config)) as restarted:
        assert restarted.app.state.stt_worker.model_path == chosen


def test_install_surfaces_a_checksum_mismatch_as_a_failed_job(client, monkeypatch):
    _stub_downloads(monkeypatch, fail_with=ChecksumMismatch("SHA-256 did not match."))

    started = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]})
    job = _await_terminal(client, started.json()["id"])

    assert job["status"] == "failed"
    assert "SHA-256" in (job["error_message"] or "")
    assert job["stages"][0]["state"] == "failed"


def test_install_rejects_an_unknown_asset(client):
    r = client.post("/api/voice/setup/install", json={"asset_ids": ["not-a-model"]})
    assert r.status_code == 404
    assert "not-a-model" in r.json()["error"]["message"]


def test_install_defaults_to_the_recommended_assets(client, monkeypatch):
    _stub_downloads(monkeypatch)
    started = client.post("/api/voice/setup/install", json={})
    assert started.json()["asset_ids"] == ["whisper-base-en", "silero-vad"]


def test_install_reattaches_instead_of_starting_a_second_job(client, monkeypatch):
    release = asyncio.Event()

    async def _slow_download(*, dest_path, progress_cb=None, **_):
        await release.wait()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"x")
        return 1

    monkeypatch.setattr(
        "convsim_core.routers.voice_setup.download_voice_asset", _slow_download
    )

    first = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]}).json()
    second = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]}).json()
    assert second["id"] == first["id"]

    # The plan hands the same job back so a reopened screen rejoins the download.
    assert client.get("/api/voice/setup/plan").json()["active_job_id"] == first["id"]

    client.delete(f"/api/voice/setup/install/{first['id']}")


def test_cancel_marks_the_job_cancelled_not_failed(client, monkeypatch):
    """A user abort must be distinguishable from a real error."""

    async def _watch_cancel(*, cancel_event=None, **_):
        assert cancel_event is not None
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)
        raise DownloadCancelled()

    monkeypatch.setattr(
        "convsim_core.routers.voice_setup.download_voice_asset", _watch_cancel
    )

    job_id = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]}).json()["id"]
    assert client.delete(f"/api/voice/setup/install/{job_id}").status_code == 204

    assert _await_terminal(client, job_id)["status"] == "cancelled"


def test_cancel_between_assets_is_not_reported_as_complete(client, monkeypatch, voice_paths):
    """A cancel that lands between two assets must not finish the job 'complete'.

    download_voice_asset notices the event on its first chunk, so cancelling
    mid-transfer was always handled. An asset already on disk takes the skip
    branch instead, which never looks at the event — so a cancel arriving in the
    gap between two assets ran the loop out and reported success, after the
    client had already been told 204.
    """
    # Present on disk, so this asset's stage skips rather than downloading —
    # the path that ignored the cancel.
    voice_paths["vad_model"].parent.mkdir(parents=True, exist_ok=True)
    voice_paths["vad_model"].write_bytes(b"onnx")

    async def _download_then_cancel(*, dest_path, cancel_event=None, **_):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"downloaded")
        # Stands in for the player pressing Cancel as this file lands.
        assert cancel_event is not None
        cancel_event.set()
        return 10

    monkeypatch.setattr(
        "convsim_core.routers.voice_setup.download_voice_asset", _download_then_cancel
    )

    job_id = client.post(
        "/api/voice/setup/install",
        json={"asset_ids": ["whisper-base-en", "silero-vad"]},
    ).json()["id"]

    job = _await_terminal(client, job_id)
    assert job["status"] == "cancelled"
    # The asset that finished before the cancel keeps its real outcome; the one
    # that never started stays pending rather than claiming to have failed.
    assert job["stages"][0]["state"] == "complete"
    assert job["stages"][1]["state"] == "pending"
    assert job["stages"][1]["error"] is None


@pytest.mark.asyncio
async def test_cancel_is_honoured_when_every_asset_is_already_present(db, voice_paths):
    """The variant with no download call at all, so no exception path exists.

    Re-pointing the worker at an installed model posts the same install, which
    skips every stage. Driving ``_run_install`` directly is the only way to open
    the cancel window deterministically: through the API the task would finish
    before a DELETE could land.
    """
    from convsim_core.routers.voice_setup import _run_install
    from convsim_core.services.voice_setup_service import create_job, get_job, stage_label

    for path in (voice_paths["stt_model"], voice_paths["vad_model"]):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"present")

    conn = db.connection()
    asset_ids = ["whisper-base-en", "silero-vad"]
    assets = [voice_registry.get_asset(i) for i in asset_ids]
    job_id = create_job(
        conn,
        asset_ids=asset_ids,
        stages=[StageState(id=a.id, label=stage_label(a), state="pending") for a in assets],
    )

    cancel = asyncio.Event()
    cancel.set()
    await _run_install(
        job_id=job_id,
        asset_ids=asset_ids,
        conn=conn,
        stt_worker=MagicMock(),
        cancel_event=cancel,
    )

    job = get_job(conn, job_id)
    assert job is not None
    assert job["status"] == "cancelled"
    assert [s["state"] for s in job["stages"]] == ["pending", "pending"]
    # A cancelled job must not re-point the worker at anything.
    assert get_stt_model_path(conn) is None


def test_cancelling_a_finished_job_is_a_conflict(client, monkeypatch):
    _stub_downloads(monkeypatch)
    job_id = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]}).json()["id"]
    _await_terminal(client, job_id)

    r = client.delete(f"/api/voice/setup/install/{job_id}")
    assert r.status_code == 409


def test_unknown_job_is_a_404(client):
    assert client.get("/api/voice/setup/install/9999").status_code == 404
    assert client.delete("/api/voice/setup/install/9999").status_code == 404


def test_retire_orphaned_jobs_fails_rows_no_task_is_driving(db):
    conn = db.connection()
    conn.execute("INSERT INTO voice_install_jobs (status) VALUES ('running')")
    conn.execute("INSERT INTO voice_install_jobs (status) VALUES ('complete')")
    conn.commit()

    assert retire_orphaned_jobs(conn) == 1

    statuses = [r[0] for r in conn.execute("SELECT status FROM voice_install_jobs ORDER BY id")]
    assert statuses == ["failed", "complete"]


# ── Engine start ──────────────────────────────────────────────────────────────


def test_only_the_kokoro_server_is_startable(client):
    assert client.post("/api/voice/setup/engine/whisper-cli/start").status_code == 404
    assert client.post("/api/voice/setup/engine/nope/start").status_code == 404


def test_starting_kokoro_without_the_binary_explains_why(client):
    r = client.post("/api/voice/setup/engine/kokoro-server/start")
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is False
    assert "kokoro" in body["message"].lower()


def test_starting_kokoro_runs_the_sidecar(client, monkeypatch):
    from convsim_core.runtime.sidecar import SidecarState

    sidecar = client.app.state.kokoro_sidecar
    started = {"called": False}

    async def _start(**_kwargs):
        started["called"] = True
        monkeypatch.setattr(
            type(sidecar), "state", property(lambda self: SidecarState.RUNNING)
        )

    monkeypatch.setattr(sidecar, "start", _start)

    body = client.post("/api/voice/setup/engine/kokoro-server/start").json()
    assert started["called"] is True
    assert body["started"] is True
    assert body["state"] == "running"


def test_a_model_that_landed_is_still_used_when_a_later_asset_fails(
    client, monkeypatch, voice_paths
):
    """A speech model that downloaded must be the one in use, even if the job fails.

    The player picks small.en and it verifies; then the 2 MB VAD model fails —
    its host is ``raw.githubusercontent.com``, which some networks block while
    Hugging Face answers fine. Persisting only at the end of the job left
    small.en on disk with the worker still pointed at ``ggml-base.en.bin``, a
    file that may never have been installed: the screen then read "Speak your
    turns — Not yet" with every row beneath it green and nothing naming the
    gap. A failure is not a request to leave the setup unchanged.
    """
    small = voice_paths["stt_dir"] / "ggml-small.en.bin"

    async def _download(*, dest_path, **_):
        if dest_path == voice_paths["vad_model"]:
            raise RuntimeError("connection reset by peer")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"ggml")
        return 4

    monkeypatch.setattr(
        "convsim_core.routers.voice_setup.download_voice_asset", _download
    )

    job_id = client.post(
        "/api/voice/setup/install",
        json={"asset_ids": ["whisper-small-en", "silero-vad"]},
    ).json()["id"]
    job = _await_terminal(client, job_id)

    assert job["status"] == "failed"
    assert job["stages"][0]["state"] == "complete"
    assert job["stages"][1]["state"] == "failed"

    conn = client.app.state.db.connection()
    assert get_stt_model_path(conn) == str(small)
    assert client.app.state.stt_worker.model_path == str(small)
    # The plan has to agree, or the picker would offer a download for a model
    # the player has already waited for.
    assets = {a["id"]: a for a in client.get("/api/voice/setup/plan").json()["assets"]}
    assert assets["whisper-small-en"]["selected"] is True


def test_a_start_that_only_joined_one_in_flight_is_not_called_a_success(client, monkeypatch):
    """``start()`` is a no-op while a start is already in flight, and returns None.

    The sidecar waits on /health for up to two minutes, so a second press —
    another tab, or a player who came back to the screen — reaches a sidecar in
    state STARTING, where ``start()`` returns immediately without raising.
    Reading that as success announced "The voice server is running" in success
    green above the amber row saying it was not.
    """
    from convsim_core.runtime.sidecar import SidecarState

    sidecar = client.app.state.kokoro_sidecar
    monkeypatch.setattr(
        type(sidecar), "state", property(lambda self: SidecarState.STARTING)
    )

    async def _already_starting(**_kwargs):
        return None

    monkeypatch.setattr(sidecar, "start", _already_starting)

    body = client.post("/api/voice/setup/engine/kokoro-server/start").json()
    assert body["started"] is False
    assert body["state"] == "starting"
    assert "starting" in body["message"].lower()


def test_a_server_that_died_the_moment_it_came_up_is_not_called_a_success(client, monkeypatch):
    """The state property re-reads the child process, so RUNNING can go CRASHED.

    ``start()`` returns once /health answers 200; a server that exits straight
    afterwards leaves the next state read CRASHED. The reason the sidecar
    recorded is what the player needs, not a success line.
    """
    from convsim_core.runtime.sidecar import SidecarState

    sidecar = client.app.state.kokoro_sidecar
    monkeypatch.setattr(
        type(sidecar), "state", property(lambda self: SidecarState.CRASHED)
    )
    monkeypatch.setattr(
        sidecar, "get_status", lambda: {"state": "crashed", "error": "exited with code 1"}
    )

    async def _start(**_kwargs):
        return None

    monkeypatch.setattr(sidecar, "start", _start)

    body = client.post("/api/voice/setup/engine/kokoro-server/start").json()
    assert body["started"] is False
    assert body["state"] == "crashed"
    assert body["message"] == "exited with code 1"
