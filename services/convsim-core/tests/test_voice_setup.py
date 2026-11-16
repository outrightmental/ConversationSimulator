# SPDX-License-Identifier: Apache-2.0
"""One-click voice install: catalog, installer, engine runner, jobs and API.

Nothing here touches the network or runs the real engine. Downloads are
served by an ``httpx.MockTransport`` from bytes built in the test, and the
engine is replaced by a function that plays its part.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import sys
import tarfile
import time
import wave
from pathlib import Path
from typing import Callable, Optional

import httpx
import pytest
from fastapi.testclient import TestClient

import convsim_core.network_policy as network_policy
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.stt.sherpa_whisper import SherpaWhisperWorker
from convsim_core.tts.sherpa_kokoro import SherpaKokoroTtsWorker
from convsim_core.tts.voices import APPROVED_VOICES
from convsim_core.voice import catalog
from convsim_core.voice import engine as engine_mod
from convsim_core.voice.catalog import VoiceAsset, VoiceDownload
from convsim_core.voice.engine import EngineError, EngineResult
from convsim_core.voice.installer import (
    ERROR_CODE_CHECKSUM,
    VoiceInstallCancelled,
    VoiceInstallError,
    _member_target,
    install_asset,
)
from convsim_core.voice.jobs import VoiceInstallManager
from convsim_core.voice.layout import VoiceLayout
from convsim_core.voice.workers import apply_voice_workers


# ── Builders ──────────────────────────────────────────────────────────────────


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tar_bz2(members: dict[str, bytes], *, extra: Optional[list[tarfile.TarInfo]] = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(data))
        for info in extra or []:
            archive.addfile(info)
    return buffer.getvalue()


def _file_download(url: str, data: bytes, dest: str) -> VoiceDownload:
    return VoiceDownload(url=url, sha256=_sha256(data), size_bytes=len(data), dest=dest)


def _asset(asset_id: str, install_dir: str, downloads, required) -> VoiceAsset:
    return VoiceAsset(
        id=asset_id,
        label=f"Test {asset_id}",
        version="test-1",
        install_dir=install_dir,
        license="Apache-2.0",
        license_note=None,
        source_name="test",
        source_url="https://example.test/source",
        downloads=tuple(downloads),
        required_files=tuple(required),
    )


class _Server:
    """Serves fixed bodies, honours Range, and records what was asked."""

    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.bodies = dict(bodies)
        self.requests: list[httpx.Request] = []
        self.before_respond: Optional[Callable[[httpx.Request], None]] = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.before_respond is not None:
            self.before_respond(request)
        body = self.bodies.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        range_header = request.headers.get("range")
        if range_header:
            start = int(re.match(r"bytes=(\d+)-", range_header).group(1))
            return httpx.Response(
                206,
                content=body[start:],
                headers={"content-range": f"bytes {start}-{len(body) - 1}/{len(body)}"},
            )
        return httpx.Response(200, content=body)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


@pytest.fixture(autouse=True)
def _allow_explicit_downloads(monkeypatch):
    monkeypatch.setattr(network_policy, "LOCAL_MODE", False)


# ── Catalog ───────────────────────────────────────────────────────────────────


def _all_assets() -> list[VoiceAsset]:
    engines = [catalog.engine_asset(key) for key in catalog.engine_platform_keys()]
    return [e for e in engines if e is not None] + list(catalog.MODEL_ASSETS.values())


def test_every_download_is_pinned_and_disclosable():
    """No file ships without an HTTPS source, an exact size and a SHA-256."""
    for asset in _all_assets():
        assert asset.license, asset.id
        assert asset.source_url.startswith("https://"), asset.id
        assert asset.downloads, asset.id
        for download in asset.downloads:
            assert download.url.startswith("https://"), download.url
            assert re.fullmatch(r"[0-9a-f]{64}", download.sha256), download.url
            assert download.size_bytes > 0, download.url
            assert download.unpack or download.dest, download.url


def test_model_files_are_pinned_to_an_immutable_revision():
    """Hugging Face URLs name a commit, never a branch that can move."""
    for asset in catalog.MODEL_ASSETS.values():
        for download in asset.downloads:
            if "huggingface.co" in download.url:
                assert re.search(r"/resolve/[0-9a-f]{40}/", download.url), download.url


def test_engine_is_pinned_for_every_platform_the_app_ships_on():
    assert set(catalog.engine_platform_keys()) >= {
        "win-x64", "osx-arm64", "osx-x64", "linux-x64", "linux-aarch64",
    }
    for key in catalog.engine_platform_keys():
        asset = catalog.engine_asset(key)
        assert asset is not None
        assert catalog.ENGINE_VERSION in asset.downloads[0].url
        suffix = ".exe" if key.startswith("win-") else ""
        assert f"bin/sherpa-onnx-offline{suffix}" in asset.required_files
        assert f"bin/sherpa-onnx-offline-tts{suffix}" in asset.required_files


def test_engine_stays_on_the_release_line_that_speaks_every_word():
    """2.x dropped eSpeak NG and skips words missing from the lexicon."""
    assert catalog.ENGINE_VERSION.startswith("1.")


def test_unknown_platform_has_no_engine():
    assert catalog.engine_asset("plan9-mips") is None


def test_this_machine_resolves_to_a_pinned_engine():
    assert catalog.detect_platform_key() in catalog.engine_platform_keys()


def test_platform_lookup_starts_no_process_on_windows(monkeypatch):
    """``platform.machine()`` runs ``ver`` in a ``cmd`` child on Windows with
    Python 3.11, which flashes a console window over the packaged app at every
    start. The lookup reads the environment instead."""
    import platform
    import subprocess

    def _forbidden(*args, **kwargs):
        raise AssertionError("the platform lookup must not start a process or call uname()")

    monkeypatch.setattr(subprocess, "check_output", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    monkeypatch.setattr(platform, "uname", _forbidden)
    monkeypatch.setattr(platform, "machine", _forbidden)
    monkeypatch.setattr(sys, "platform", "win32")

    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "AMD64")
    monkeypatch.delenv("PROCESSOR_ARCHITEW6432", raising=False)
    assert catalog.detect_platform_key() == "win-x64"

    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "ARM64")
    assert catalog.detect_platform_key() == "win-arm64"

    # A 32-bit process on a 64-bit system reports the real architecture here.
    monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "x86")
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", "AMD64")
    assert catalog.detect_platform_key() == "win-x64"

    # Plain 32-bit Windows has no engine build.
    monkeypatch.delenv("PROCESSOR_ARCHITEW6432")
    assert catalog.detect_platform_key() is None


def test_every_approved_voice_has_a_speaker_id():
    assert set(catalog.KOKORO_SPEAKER_IDS) == set(APPROVED_VOICES)
    assert len(set(catalog.KOKORO_SPEAKER_IDS.values())) == len(APPROVED_VOICES)


def test_install_folders_are_plain_ascii():
    """The engine is handed these as relative paths on its command line."""
    for asset in _all_assets():
        assert asset.install_dir.isascii() and " " not in asset.install_dir


# ── Installer ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_install_places_files_unpacks_archives_and_writes_the_marker(tmp_path):
    model = b"model-bytes" * 1000
    archive = _tar_bz2({
        "pkg/bin/tool": b"#!tool",
        "pkg/bin/other-tool": b"#!other",
        "pkg/include/header.h": b"//",
    })
    asset = _asset(
        "thing", "thing",
        [
            _file_download("https://example.test/model.onnx", model, "model.onnx"),
            VoiceDownload(
                url="https://example.test/pkg.tar.bz2", sha256=_sha256(archive),
                size_bytes=len(archive), unpack=True, strip_components=1, keep=("bin/tool",),
            ),
        ],
        ["model.onnx", "bin/tool"],
    )
    server = _Server({
        "https://example.test/model.onnx": model,
        "https://example.test/pkg.tar.bz2": archive,
    })
    layout = VoiceLayout(tmp_path / "voice")
    progress: list[tuple[int, int]] = []
    phases: list[str] = []

    async with server.client() as client:
        await install_asset(
            asset, layout, client=client,
            on_progress=lambda done, total: progress.append((done, total)),
            on_phase=phases.append,
        )

    installed = layout.asset_dir(asset)
    assert (installed / "model.onnx").read_bytes() == model
    assert (installed / "bin" / "tool").read_bytes() == b"#!tool"
    # Only what the catalog asks for is unpacked.
    assert not (installed / "bin" / "other-tool").exists()
    assert not (installed / "include").exists()
    assert layout.is_installed(asset)
    assert not layout.staging_dir(asset).exists()
    assert progress[-1] == (asset.download_bytes, asset.download_bytes)
    assert phases == ["downloading", "unpacking"]
    assert (layout.root / ".nosteamcloudpath").exists()


@pytest.mark.asyncio
async def test_checksum_mismatch_installs_nothing(tmp_path):
    good = b"the real file"
    asset = _asset(
        "thing", "thing",
        [_file_download("https://example.test/f", good, "f")],
        ["f"],
    )
    server = _Server({"https://example.test/f": b"a tampered file"})
    layout = VoiceLayout(tmp_path / "voice")

    async with server.client() as client:
        with pytest.raises(VoiceInstallError) as excinfo:
            await install_asset(asset, layout, client=client)

    assert excinfo.value.code == ERROR_CODE_CHECKSUM
    assert not layout.is_installed(asset)
    assert not layout.asset_dir(asset).exists()
    # The rejected bytes are gone too: a retry starts clean.
    assert not list(layout.staging_dir(asset).rglob("*.part"))


@pytest.mark.asyncio
async def test_cancel_leaves_nothing_behind(tmp_path):
    data = b"x" * 500_000
    asset = _asset(
        "thing", "thing", [_file_download("https://example.test/f", data, "f")], ["f"]
    )
    server = _Server({"https://example.test/f": data})
    layout = VoiceLayout(tmp_path / "voice")
    cancel_event = asyncio.Event()
    cancel_event.set()

    async with server.client() as client:
        with pytest.raises(VoiceInstallCancelled):
            await install_asset(asset, layout, client=client, cancel_event=cancel_event)

    assert not layout.staging_dir(asset).exists()
    assert not layout.asset_dir(asset).exists()


@pytest.mark.asyncio
async def test_interrupted_download_resumes_from_its_part_file(tmp_path):
    data = bytes(range(256)) * 400
    asset = _asset(
        "thing", "thing", [_file_download("https://example.test/f", data, "f")], ["f"]
    )
    server = _Server({"https://example.test/f": data})
    layout = VoiceLayout(tmp_path / "voice")
    downloads = layout.staging_dir(asset) / "downloads"
    downloads.mkdir(parents=True)
    (downloads / "00-f.part").write_bytes(data[:30_000])

    async with server.client() as client:
        await install_asset(asset, layout, client=client)

    assert server.requests[0].headers["range"] == "bytes=30000-"
    assert (layout.asset_dir(asset) / "f").read_bytes() == data


@pytest.mark.asyncio
async def test_reinstall_replaces_the_previous_copy(tmp_path):
    layout = VoiceLayout(tmp_path / "voice")
    old = _asset("thing", "thing", [_file_download("https://example.test/a", b"old", "a")], ["a"])
    new = _asset("thing", "thing", [_file_download("https://example.test/b", b"new", "b")], ["b"])
    server = _Server({"https://example.test/a": b"old", "https://example.test/b": b"new"})

    async with server.client() as client:
        await install_asset(old, layout, client=client)
        await install_asset(new, layout, client=client)

    assert not (layout.asset_dir(new) / "a").exists()
    assert (layout.asset_dir(new) / "b").read_bytes() == b"new"


@pytest.mark.asyncio
async def test_archive_cannot_write_outside_its_folder(tmp_path):
    link = tarfile.TarInfo("pkg/link")
    link.type = tarfile.SYMTYPE
    link.linkname = "../../../outside"
    archive = _tar_bz2(
        {"pkg/ok.txt": b"ok", "pkg/../../escape.txt": b"no", "/abs.txt": b"no"},
        extra=[link],
    )
    asset = _asset(
        "thing", "thing",
        [VoiceDownload(
            url="https://example.test/a.tar.bz2", sha256=_sha256(archive),
            size_bytes=len(archive), unpack=True, strip_components=1,
        )],
        ["ok.txt"],
    )
    server = _Server({"https://example.test/a.tar.bz2": archive})
    layout = VoiceLayout(tmp_path / "voice")

    async with server.client() as client:
        await install_asset(asset, layout, client=client)

    assert (layout.asset_dir(asset) / "ok.txt").read_bytes() == b"ok"
    written = {p.name for p in tmp_path.rglob("*") if p.is_file()}
    assert "escape.txt" not in written and "abs.txt" not in written
    assert not (layout.asset_dir(asset) / "link").exists()


def test_member_target_rules():
    download = VoiceDownload(
        url="https://x", sha256="0" * 64, size_bytes=1, unpack=True,
        strip_components=1, keep=("bin/*.dll", "bin/tool"),
    )
    assert _member_target("pkg/bin/tool", download) == "bin/tool"
    assert _member_target("pkg/bin/a.dll", download) == "bin/a.dll"
    assert _member_target("pkg/bin/unwanted", download) is None
    assert _member_target("pkg/../bin/tool", download) is None
    assert _member_target("pkg", download) is None


@pytest.mark.asyncio
async def test_missing_required_file_fails_the_install(tmp_path):
    asset = _asset(
        "thing", "thing",
        [_file_download("https://example.test/a", b"a", "a")],
        ["a", "never-downloaded"],
    )
    server = _Server({"https://example.test/a": b"a"})
    layout = VoiceLayout(tmp_path / "voice")
    async with server.client() as client:
        with pytest.raises(VoiceInstallError):
            await install_asset(asset, layout, client=client)
    assert not layout.is_installed(asset)


def test_a_marker_without_its_files_is_not_installed(tmp_path):
    layout = VoiceLayout(tmp_path / "voice")
    asset = catalog.WHISPER_ASSET
    folder = layout.asset_dir(asset)
    folder.mkdir(parents=True)
    layout.write_marker(asset, folder)
    assert not layout.is_installed(asset)


# ── Text handed to the engine ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, spoken",
    [
        ("I don’t think that’s fair.", "I don't think that's fair."),
        ("She said “no”.", 'She said "no".'),
        ("Wait — what?", "Wait , what?"),
        ("Well… I suppose so.", "Well, I suppose so."),
        ("Hmm...", "Hmm."),
        ("...and then it broke.", "and then it broke."),
        ("--help me", "help me"),
        ("two\n\nlines\there", "two lines here"),
    ],
)
def test_spoken_text_is_normalised(raw, spoken):
    assert engine_mod.normalize_spoken_text(raw) == spoken


def test_text_passes_through_unchanged_off_windows():
    assert engine_mod.text_for_argv("café ¿Qué?", platform="linux") == "café ¿Qué?"


@pytest.mark.skipif(sys.platform != "win32", reason="ANSI command lines are a Windows matter")
def test_windows_text_arrives_as_utf8():
    """The string passed is the one whose ANSI encoding is the wanted UTF-8."""
    text = "café ¿Qué?"
    carried = engine_mod.text_for_argv(text, platform="win32")
    try:
        delivered = carried.encode("mbcs")
    except UnicodeError:
        pytest.skip("this machine's code page cannot carry the text")
    # Either the engine receives the exact UTF-8, or accents were dropped
    # (double-byte code pages) and what it receives is plain ASCII.
    assert delivered == text.encode("utf-8") or carried.isascii()


def test_ascii_text_is_never_rewritten_for_windows():
    assert engine_mod.text_for_argv("Plain words.", platform="win32") == "Plain words."


# ── Whisper worker ────────────────────────────────────────────────────────────


def _wav(seconds: float, *, rate: int = 16000, quiet_at: Optional[float] = None) -> bytes:
    """A loud WAV, optionally with half a second of silence at *quiet_at*."""
    import array

    count = int(seconds * rate)
    samples = array.array("h", [8000 if i % 2 else -8000 for i in range(count)])
    if quiet_at is not None:
        begin = int(quiet_at * rate)
        for i in range(begin, min(count, begin + rate // 2)):
            samples[i] = 0
    if sys.byteorder == "big":
        samples.byteswap()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(samples.tobytes())
    return buffer.getvalue()


def _frames(data: bytes) -> int:
    with wave.open(io.BytesIO(data)) as reader:
        return reader.getnframes()


def test_short_recording_is_not_split():
    from convsim_core.stt.sherpa_whisper import split_wav

    data = _wav(12.0)
    assert split_wav(data) == [data]


def test_long_recording_is_split_at_a_quiet_moment_and_loses_nothing():
    from convsim_core.stt.sherpa_whisper import split_wav

    data = _wav(65.0, quiet_at=25.0)
    pieces = split_wav(data)

    assert len(pieces) == 3
    assert sum(_frames(p) for p in pieces) == _frames(data)
    assert all(_frames(p) / 16000 <= 28.5 for p in pieces)
    # The first cut lands inside the silence, not at the 28 s limit.
    assert 25.0 <= _frames(pieces[0]) / 16000 <= 25.5


def test_unreadable_audio_is_passed_through_for_the_engine_to_judge():
    from convsim_core.stt.sherpa_whisper import split_wav

    assert split_wav(b"RIFFxxxxWAVEnot really") == [b"RIFFxxxxWAVEnot really"]


@pytest.mark.parametrize(
    "language, expected",
    [("en", "en"), ("es-MX", "es"), ("EN_us", "en"), (None, ""), ("", ""), ("tlh", "")],
)
def test_whisper_language_codes(language, expected):
    from convsim_core.stt.sherpa_whisper import whisper_language

    assert whisper_language(language) == expected


def _install_markers(voice_dir: Path, monkeypatch) -> VoiceLayout:
    """Make the engine, Whisper and Kokoro look installed without downloading."""
    layout = VoiceLayout(voice_dir)
    engine = catalog.engine_asset() or catalog.engine_asset("linux-x64")
    monkeypatch.setattr(catalog, "engine_asset", lambda platform_key=None: engine)
    for asset in (engine, catalog.WHISPER_ASSET, catalog.KOKORO_ASSET):
        folder = layout.asset_dir(asset)
        for rel in asset.required_files:
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            (folder / rel).write_bytes(b"x")
        layout.write_marker(asset, folder)
    return layout


class _FakeEngine:
    """Stands in for ``run_engine`` and records each call."""

    def __init__(self, respond: Callable[[VoiceLayout, str, list[str]], EngineResult]) -> None:
        self.respond = respond
        self.calls: list[tuple[str, list[str]]] = []

    async def __call__(self, layout, program, args, *, timeout):
        self.calls.append((program, list(args)))
        return self.respond(layout, program, list(args))


@pytest.mark.asyncio
async def test_whisper_worker_transcribes_and_cleans_up(tmp_path, monkeypatch):
    from convsim_core.stt import sherpa_whisper
    from convsim_core.stt.types import SttRequest

    layout = _install_markers(tmp_path / "voice", monkeypatch)
    seen_files: list[Path] = []

    def respond(layout_, program, args):
        seen_files.extend(layout_.root / a for a in args if a.endswith(".wav"))
        assert all(p.is_file() for p in seen_files)
        line = json.dumps({"lang": "es", "text": " Hola, ¿qué tal? "})
        return EngineResult(0, "", f"noise\n{line}\n")

    fake = _FakeEngine(respond)
    monkeypatch.setattr(sherpa_whisper, "run_engine", fake)

    worker = SherpaWhisperWorker(layout.root)
    result = await worker.transcribe(SttRequest(audio=_wav(3.0), audio_format="wav", language="es"))

    assert result.transcript == "Hola, ¿qué tal?"
    assert result.language == "es"
    assert result.duration_ms == pytest.approx(3000.0)
    program, args = fake.calls[0]
    assert program == catalog.ENGINE_STT_PROGRAM
    assert "--whisper-language=es" in args
    # Every path the engine sees is relative to the voice root.
    assert all(not Path(a.split("=", 1)[-1]).is_absolute() for a in args)
    assert seen_files and not any(p.exists() for p in seen_files)


@pytest.mark.asyncio
async def test_whisper_worker_joins_the_pieces_of_a_long_recording(tmp_path, monkeypatch):
    from convsim_core.stt import sherpa_whisper
    from convsim_core.stt.types import SttRequest

    layout = _install_markers(tmp_path / "voice", monkeypatch)

    def respond(layout_, program, args):
        files = [a for a in args if a.endswith(".wav")]
        lines = [json.dumps({"lang": "en", "text": f"part {i}."}) for i in range(len(files))]
        return EngineResult(0, "\n".join(lines), "")

    fake = _FakeEngine(respond)
    monkeypatch.setattr(sherpa_whisper, "run_engine", fake)

    result = await SherpaWhisperWorker(layout.root).transcribe(
        SttRequest(audio=_wav(40.0), audio_format="wav")
    )
    assert result.transcript == "part 0. part 1."
    assert len(fake.calls) == 1  # one engine run, one model load


@pytest.mark.asyncio
async def test_whisper_worker_is_unavailable_until_installed(tmp_path):
    from convsim_core.runtime.types import RuntimeStatus
    from convsim_core.stt.types import SttRequest, SttUnavailableError

    worker = SherpaWhisperWorker(tmp_path / "voice")
    assert (await worker.health()).status == RuntimeStatus.UNAVAILABLE
    with pytest.raises(SttUnavailableError):
        await worker.transcribe(SttRequest(audio=_wav(1.0)))


@pytest.mark.asyncio
async def test_whisper_worker_refuses_audio_it_cannot_convert(tmp_path, monkeypatch):
    from convsim_core.stt import sherpa_whisper
    from convsim_core.stt.types import SttError, SttRequest, SttUnavailableError

    layout = _install_markers(tmp_path / "voice", monkeypatch)
    monkeypatch.setattr(sherpa_whisper.shutil, "which", lambda name: None)
    with pytest.raises(SttError) as excinfo:
        await SherpaWhisperWorker(layout.root).transcribe(
            SttRequest(audio=b"\x1aE\xdf\xa3webm", audio_format="webm")
        )
    assert not isinstance(excinfo.value, SttUnavailableError)


@pytest.mark.asyncio
async def test_whisper_worker_reports_an_engine_failure(tmp_path, monkeypatch):
    from convsim_core.stt import sherpa_whisper
    from convsim_core.stt.types import SttError, SttRequest

    layout = _install_markers(tmp_path / "voice", monkeypatch)
    monkeypatch.setattr(
        sherpa_whisper, "run_engine",
        _FakeEngine(lambda *_: EngineResult(1, "", "model file is corrupt")),
    )
    with pytest.raises(SttError, match="model file is corrupt"):
        await SherpaWhisperWorker(layout.root).transcribe(SttRequest(audio=_wav(1.0)))


# ── Kokoro worker ─────────────────────────────────────────────────────────────


def _synth_engine(layout_, program, args):
    out = next(a.split("=", 1)[1] for a in args if a.startswith("--output-filename="))
    (layout_.root / out).write_bytes(b"RIFF" + b"\0" * 100)
    return EngineResult(0, "", "")


@pytest.mark.asyncio
async def test_kokoro_worker_synthesises_then_serves_from_cache(tmp_path, monkeypatch):
    from convsim_core.tts import sherpa_kokoro
    from convsim_core.tts.types import TtsRequest

    layout = _install_markers(tmp_path / "voice", monkeypatch)
    fake = _FakeEngine(_synth_engine)
    monkeypatch.setattr(sherpa_kokoro, "run_engine", fake)
    worker = SherpaKokoroTtsWorker(layout.root, tmp_path / "cache" / "tts")

    first = await worker.synthesize(TtsRequest(text="Hello there.", voice_id="af_heart"))
    second = await worker.synthesize(TtsRequest(text="Hello there.", voice_id="af_heart"))

    assert Path(first.audio_path).is_file()
    assert Path(first.audio_path).parent == tmp_path / "cache" / "tts"
    assert re.fullmatch(r"[a-f0-9]{32}\.wav", Path(first.audio_path).name)
    assert second.audio_path == first.audio_path
    assert len(fake.calls) == 1
    program, args = fake.calls[0]
    assert program == catalog.ENGINE_TTS_PROGRAM
    assert f"--sid={catalog.KOKORO_SPEAKER_IDS['af_heart']}" in args
    assert "--kokoro-lang=en" in args
    assert "--kokoro-lexicon=tts/lexicon-us-en.txt" in args
    assert args[-1] == "Hello there."
    assert not list(layout.tmp_dir.glob("*"))
    assert await worker.cache_size() == {"files": 1, "size_bytes": 104}
    assert await worker.clear_cache() == 1


@pytest.mark.asyncio
async def test_british_voices_use_the_british_lexicon(tmp_path, monkeypatch):
    from convsim_core.tts import sherpa_kokoro
    from convsim_core.tts.types import TtsRequest

    layout = _install_markers(tmp_path / "voice", monkeypatch)
    fake = _FakeEngine(_synth_engine)
    monkeypatch.setattr(sherpa_kokoro, "run_engine", fake)
    worker = SherpaKokoroTtsWorker(layout.root, tmp_path / "cache")

    await worker.synthesize(TtsRequest(text="Right then.", voice_id="bm_george"))
    assert "--kokoro-lexicon=tts/lexicon-gb-en.txt" in fake.calls[0][1]


@pytest.mark.asyncio
async def test_spanish_is_spoken_as_spanish(tmp_path, monkeypatch):
    from convsim_core.tts import sherpa_kokoro
    from convsim_core.tts.types import TtsRequest

    layout = _install_markers(tmp_path / "voice", monkeypatch)
    fake = _FakeEngine(_synth_engine)
    monkeypatch.setattr(sherpa_kokoro, "run_engine", fake)
    worker = SherpaKokoroTtsWorker(layout.root, tmp_path / "cache")

    await worker.synthesize(TtsRequest(text="Hola.", voice_id="af_heart", language="es-ES"))
    args = fake.calls[0][1]
    assert "--kokoro-lang=es" in args
    # The English lexicon would mispronounce it; eSpeak NG does all of it.
    assert not any(a.startswith("--kokoro-lexicon=") for a in args)


@pytest.mark.asyncio
async def test_a_language_the_voices_cannot_speak_falls_back_to_text(tmp_path, monkeypatch):
    from convsim_core.tts import sherpa_kokoro
    from convsim_core.tts.types import TtsRequest, TtsUnavailableError

    layout = _install_markers(tmp_path / "voice", monkeypatch)
    fake = _FakeEngine(_synth_engine)
    monkeypatch.setattr(sherpa_kokoro, "run_engine", fake)
    worker = SherpaKokoroTtsWorker(layout.root, tmp_path / "cache")

    with pytest.raises(TtsUnavailableError):
        await worker.synthesize(TtsRequest(text="Konnichiwa.", voice_id="af_heart", language="ja"))
    assert fake.calls == []


@pytest.mark.asyncio
async def test_same_text_in_two_languages_is_cached_separately(tmp_path, monkeypatch):
    from convsim_core.tts import sherpa_kokoro
    from convsim_core.tts.types import TtsRequest

    layout = _install_markers(tmp_path / "voice", monkeypatch)
    monkeypatch.setattr(sherpa_kokoro, "run_engine", _FakeEngine(_synth_engine))
    worker = SherpaKokoroTtsWorker(layout.root, tmp_path / "cache")

    english = await worker.synthesize(TtsRequest(text="No.", voice_id="af_heart", language="en"))
    spanish = await worker.synthesize(TtsRequest(text="No.", voice_id="af_heart", language="es"))
    assert english.audio_path != spanish.audio_path


@pytest.mark.asyncio
async def test_kokoro_worker_rejects_unapproved_voices_and_missing_install(tmp_path, monkeypatch):
    from convsim_core.tts.types import TtsRequest, TtsUnavailableError, TtsVoiceValidationError

    worker = SherpaKokoroTtsWorker(tmp_path / "voice", tmp_path / "cache")
    with pytest.raises(TtsVoiceValidationError):
        await worker.synthesize(TtsRequest(text="Hi.", voice_id="cloned_celebrity"))
    with pytest.raises(TtsUnavailableError):
        await worker.synthesize(TtsRequest(text="Hi.", voice_id="af_heart"))


@pytest.mark.asyncio
async def test_kokoro_worker_reports_an_engine_that_wrote_no_audio(tmp_path, monkeypatch):
    from convsim_core.tts import sherpa_kokoro
    from convsim_core.tts.types import TtsError, TtsRequest

    layout = _install_markers(tmp_path / "voice", monkeypatch)
    monkeypatch.setattr(
        sherpa_kokoro, "run_engine",
        _FakeEngine(lambda *_: EngineResult(1, "", "Error in generating audio.")),
    )
    worker = SherpaKokoroTtsWorker(layout.root, tmp_path / "cache")
    with pytest.raises(TtsError, match="Error in generating audio"):
        await worker.synthesize(TtsRequest(text="Hi.", voice_id="af_heart"))


# ── Sentence queue ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_queue_synthesises_side_by_side_but_answers_in_order(tmp_path):
    from convsim_core.services.tts_queue import synthesize_utterance
    from convsim_core.tts.types import TtsRequest, TtsResult

    class _Worker:
        max_concurrency = 2

        def __init__(self) -> None:
            self.running = 0
            self.peak = 0
            self.languages: list[Optional[str]] = []

        async def synthesize(self, request: TtsRequest) -> TtsResult:
            self.running += 1
            self.peak = max(self.peak, self.running)
            self.languages.append(request.language)
            # The first sentence takes longest, so it finishes last.
            await asyncio.sleep(0.05 if request.text.startswith("One") else 0.01)
            self.running -= 1
            return TtsResult(audio_path=f"/x/{request.text}", voice_id=request.voice_id)

    worker = _Worker()
    chunks = await synthesize_utterance(
        "One. Two. Three. Four.", "af_heart", worker, language="es"
    )

    assert [c.text for c in chunks] == ["One.", "Two.", "Three.", "Four."]
    assert [c.chunk_index for c in chunks] == [0, 1, 2, 3]
    assert worker.peak == 2
    assert worker.languages == ["es"] * 4


# ── Jobs and API ──────────────────────────────────────────────────────────────


_FAKE_BODIES = {
    "https://example.test/engine.tar.bz2": _tar_bz2({
        "pkg/bin/sherpa-onnx-offline": b"stt",
        "pkg/bin/sherpa-onnx-offline-tts": b"tts",
        "pkg/bin/sherpa-onnx-version": b"version",
        "pkg/bin/unneeded": b"-",
    }),
    "https://example.test/encoder": b"encoder" * 50,
    "https://example.test/kokoro": b"kokoro" * 80,
}


def _fake_catalog(monkeypatch) -> None:
    """Swap the pinned downloads for tiny ones, keeping ids and folders."""
    bodies = _FAKE_BODIES
    engine_body = bodies["https://example.test/engine.tar.bz2"]
    engine = _asset(
        "engine", "engine",
        [VoiceDownload(
            url="https://example.test/engine.tar.bz2", sha256=_sha256(engine_body),
            size_bytes=len(engine_body), unpack=True, strip_components=1,
            keep=("bin/sherpa-onnx-*",),
        )],
        ["bin/sherpa-onnx-offline", "bin/sherpa-onnx-offline-tts", "bin/sherpa-onnx-version"],
    )
    whisper = _asset(
        "whisper-base", "stt",
        [_file_download("https://example.test/encoder", bodies["https://example.test/encoder"], "enc")],
        ["enc"],
    )
    kokoro = _asset(
        "kokoro-v1", "tts",
        [_file_download("https://example.test/kokoro", bodies["https://example.test/kokoro"], "model")],
        ["model"],
    )
    monkeypatch.setattr(catalog, "engine_asset", lambda platform_key=None: engine)
    monkeypatch.setattr(catalog, "MODEL_ASSETS", {"whisper-base": whisper, "kokoro-v1": kokoro})


def _config(tmp_path, **overrides) -> ServiceConfig:
    base = dict(
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
    base.update(overrides)
    return ServiceConfig(**base)


def _voice_client(tmp_path, monkeypatch, **overrides):
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    _fake_catalog(monkeypatch)
    server = _Server(_FAKE_BODIES)
    app = create_app(_config(tmp_path, **overrides))
    client = TestClient(app)
    client.__enter__()
    manager: VoiceInstallManager = app.state.voice_install
    manager._client_factory = server.client

    async def _probe(layout):
        return catalog.ENGINE_VERSION

    manager._probe = _probe
    return client, app, server


def _wait_for(client: TestClient, job_id: int, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/voice/setup/install/{job_id}").json()
        if job["status"] in ("complete", "failed", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"voice install job {job_id} did not finish: {job}")


@pytest.fixture()
def voice_app(tmp_path, monkeypatch):
    client, app, server = _voice_client(tmp_path, monkeypatch)
    try:
        yield client, app, server
    finally:
        client.__exit__(None, None, None)


def test_voice_dir_defaults_beside_the_models_folder(tmp_path):
    config = _config(tmp_path)
    assert Path(config.voice_dir) == tmp_path / "models" / "voice"
    assert _config(tmp_path, voice_dir=str(tmp_path / "v")).voice_dir == str(tmp_path / "v")


def test_plan_states_what_will_be_downloaded_and_downloads_nothing(voice_app):
    client, app, server = voice_app

    plan = client.get("/api/voice/setup").json()

    assert plan["supported"] is True
    assert plan["job"] is None
    assert {c["id"] for c in plan["components"]} == {"stt", "tts"}
    assert all(not c["ready"] and not c["installed"] for c in plan["components"])
    total = sum(len(b) for b in _FAKE_BODIES.values())
    assert plan["download_bytes"] == total
    # The engine is counted once, not once per direction.
    stt, tts = (next(c for c in plan["components"] if c["id"] == i) for i in ("stt", "tts"))
    assert stt["download_bytes"] + tts["download_bytes"] > total
    for asset in plan["assets"]:
        assert asset["license"] and asset["source_url"].startswith("https://")
        for download in asset["downloads"]:
            assert download["url"] and download["size_bytes"] > 0
            assert re.fullmatch(r"[0-9a-f]{64}", download["sha256"])
    # Reading the plan is not consent: nothing was fetched or created.
    assert server.requests == []
    assert not Path(plan["install_dir"]).exists()


def test_install_downloads_everything_and_switches_voice_on(voice_app):
    client, app, server = voice_app
    assert client.get("/api/health").json()["runtime"]["stt_ready"] is False

    started = client.post("/api/voice/setup/install", json={}).json()
    assert started["status"] in ("pending", "running", "complete")
    assert [s["id"] for s in started["stages"]] == ["engine", "whisper-base", "kokoro-v1", "check"]
    # Every download states its size before it starts, so overall progress is
    # out of the whole install from the first moment.
    assert sum(s["bytes_total"] or 0 for s in started["stages"]) == sum(
        len(body) for body in _FAKE_BODIES.values()
    )
    job = _wait_for(client, started["id"])

    assert job["status"] == "complete", job
    assert all(s["state"] == "complete" for s in job["stages"])
    assert sorted(str(r.url) for r in server.requests) == sorted(_FAKE_BODIES)

    # Voice is on without a restart: the workers changed under the running app.
    health = client.get("/api/health").json()
    assert health["runtime"]["stt_ready"] is True
    assert health["runtime"]["tts_ready"] is True
    assert health["stt"]["worker_id"] == "sherpa_whisper"
    assert health["tts"]["worker_id"] == "sherpa_kokoro"

    plan = client.get("/api/voice/setup").json()
    assert plan["download_bytes"] == 0
    assert all(c["ready"] and c["installed"] for c in plan["components"])
    assert plan["job"]["status"] == "complete"
    voice_root = Path(plan["install_dir"])
    assert (voice_root / "engine" / "bin" / "sherpa-onnx-offline").is_file()
    assert not (voice_root / "engine" / "bin" / "unneeded").exists()
    assert not (voice_root / ".staging").exists()


def test_one_direction_can_be_installed_alone(voice_app):
    client, app, server = voice_app

    job = _wait_for(client, client.post(
        "/api/voice/setup/install", json={"components": ["stt"]}
    ).json()["id"])

    assert job["status"] == "complete"
    assert [s["id"] for s in job["stages"]] == ["engine", "whisper-base", "check"]
    health = client.get("/api/health").json()
    assert health["runtime"]["stt_ready"] is True
    assert health["runtime"]["tts_ready"] is False
    # The second direction reuses the engine that is already there.
    plan = client.get("/api/voice/setup").json()
    tts = next(c for c in plan["components"] if c["id"] == "tts")
    assert tts["download_bytes"] == len(_FAKE_BODIES["https://example.test/kokoro"])


def test_installed_voice_is_picked_up_at_startup(tmp_path, monkeypatch):
    client, app, server = _voice_client(tmp_path, monkeypatch)
    try:
        _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])
    finally:
        client.__exit__(None, None, None)

    restarted = create_app(_config(tmp_path))
    with TestClient(restarted) as again:
        health = again.get("/api/health").json()
    assert health["stt"]["worker_id"] == "sherpa_whisper"
    assert health["tts"]["worker_id"] == "sherpa_kokoro"


def test_a_corrupt_download_fails_the_job_and_can_be_retried(voice_app):
    client, app, server = voice_app
    good = server.bodies["https://example.test/kokoro"]
    server.bodies["https://example.test/kokoro"] = b"tampered"

    failed = _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])

    assert failed["status"] == "failed"
    assert failed["error_code"] == "CHECKSUM"
    assert next(s for s in failed["stages"] if s["id"] == "kokoro-v1")["state"] == "failed"
    health = client.get("/api/health").json()
    assert health["runtime"]["tts_ready"] is False
    # What verified before the failure is installed and already usable.
    assert health["runtime"]["stt_ready"] is False or health["stt"]["worker_id"] == "sherpa_whisper"

    server.bodies["https://example.test/kokoro"] = good
    retried = _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])
    assert retried["status"] == "complete"
    assert retried["id"] != failed["id"]
    # Only the piece that failed is fetched again.
    assert [s["id"] for s in retried["stages"]] == ["kokoro-v1", "check"]


def test_a_network_failure_is_reported_as_retryable(voice_app):
    client, app, server = voice_app

    def refuse(request: httpx.Request) -> None:
        raise httpx.ConnectError("no route to host", request=request)

    server.before_respond = refuse
    job = _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])
    assert job["status"] == "failed"
    assert job["error_code"] == "NETWORK"
    assert job["error_message"]


def test_an_engine_that_will_not_start_fails_the_install(voice_app):
    client, app, server = voice_app

    async def _broken(layout):
        raise EngineError("The speech engine was installed but did not start (bad CPU).")

    app.state.voice_install._probe = _broken
    job = _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])
    assert job["status"] == "failed"
    assert job["error_code"] == "ENGINE"
    assert next(s for s in job["stages"] if s["id"] == "check")["state"] == "failed"


def test_second_request_reattaches_to_the_running_job(voice_app):
    client, app, server = voice_app
    release = False

    def hold(request: httpx.Request) -> None:
        deadline = time.monotonic() + 10
        while not release and time.monotonic() < deadline:
            time.sleep(0.01)

    server.before_respond = hold
    first = client.post("/api/voice/setup/install", json={}).json()
    second = client.post("/api/voice/setup/install", json={"components": ["tts"]}).json()
    plan = client.get("/api/voice/setup").json()
    release = True

    assert second["id"] == first["id"]
    assert plan["job"]["id"] == first["id"]
    assert _wait_for(client, first["id"])["status"] == "complete"


def test_cancel_stops_the_job_and_removes_the_partial_download(voice_app):
    client, app, server = voice_app
    release = False

    def hold(request: httpx.Request) -> None:
        deadline = time.monotonic() + 10
        while not release and time.monotonic() < deadline:
            time.sleep(0.01)

    server.before_respond = hold
    started = client.post("/api/voice/setup/install", json={}).json()
    assert client.delete(f"/api/voice/setup/install/{started['id']}").status_code == 204
    release = True
    job = _wait_for(client, started["id"])

    assert job["status"] == "cancelled"
    voice_root = Path(client.get("/api/voice/setup").json()["install_dir"])
    assert not (voice_root / ".staging").exists()
    assert client.get("/api/health").json()["runtime"]["tts_ready"] is False
    # A finished job cannot be cancelled again.
    assert client.delete(f"/api/voice/setup/install/{started['id']}").status_code == 409


def test_unknown_component_and_unknown_job_are_refused(voice_app):
    client, app, server = voice_app
    response = client.post("/api/voice/setup/install", json={"components": ["telepathy"]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VOICE_COMPONENT_UNKNOWN"
    assert client.get("/api/voice/setup/install/999").status_code == 404
    assert client.delete("/api/voice/setup/install/999").status_code == 404
    assert server.requests == []


def test_unsupported_platform_offers_no_install(voice_app, monkeypatch):
    client, app, server = voice_app
    monkeypatch.setattr(catalog, "engine_asset", lambda platform_key=None: None)

    plan = client.get("/api/voice/setup").json()
    assert plan["supported"] is False
    assert plan["unsupported_reason"]
    assert plan["download_bytes"] == 0

    response = client.post("/api/voice/setup/install", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VOICE_UNSUPPORTED"


def test_demo_edition_can_install_voice(tmp_path, monkeypatch):
    """Voice is the one extra download a demo player may choose."""
    client, app, server = _voice_client(tmp_path, monkeypatch, edition="demo")
    try:
        assert client.get("/api/health").json()["edition"] == "demo"
        assert client.get("/api/voice/setup").status_code == 200
        job = _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])
        assert job["status"] == "complete"
        assert client.get("/api/health").json()["runtime"]["stt_ready"] is True
    finally:
        client.__exit__(None, None, None)


def test_explicitly_chosen_workers_are_left_alone(tmp_path, monkeypatch):
    """Only the defaults give way; ``fake`` in a test stays ``fake``."""
    client, app, server = _voice_client(
        tmp_path, monkeypatch, stt_worker_id="fake", tts_worker_id="fake"
    )
    try:
        _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])
        health = client.get("/api/health").json()
        assert health["stt"]["worker_id"] == "fake"
        assert health["tts"]["worker_id"] == "fake"
    finally:
        client.__exit__(None, None, None)


def test_workers_fall_back_when_the_install_is_removed(tmp_path, monkeypatch):
    import shutil

    client, app, server = _voice_client(tmp_path, monkeypatch)
    try:
        _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])
        assert isinstance(app.state.stt_worker, SherpaWhisperWorker)
        shutil.rmtree(Path(app.state.service_config.voice_dir))
        apply_voice_workers(app)
        assert app.state.stt_worker.id == "whisper_cpp"
        assert app.state.tts_worker.id == "kokoro"
    finally:
        client.__exit__(None, None, None)


# ── Removing voice ────────────────────────────────────────────────────────────


def test_removing_voice_frees_the_folder_and_switches_back_to_text(voice_app):
    client, app, server = voice_app
    _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])
    plan = client.get("/api/voice/setup").json()
    assert plan["installed_bytes"] > 0
    voice_root = Path(plan["install_dir"])

    response = client.delete("/api/voice/setup")

    assert response.status_code == 200
    assert response.json()["freed_bytes"] == plan["installed_bytes"]
    for name in ("engine", "stt", "tts"):
        assert not (voice_root / name).exists()
    health = client.get("/api/health").json()
    assert health["runtime"]["stt_ready"] is False
    assert health["runtime"]["tts_ready"] is False
    assert health["stt"]["worker_id"] == "whisper_cpp"
    after = client.get("/api/voice/setup").json()
    assert after["installed_bytes"] == 0
    assert after["job"] is None
    assert all(not c["installed"] for c in after["components"])


def test_voice_can_be_installed_again_after_removal(voice_app):
    client, app, server = voice_app
    _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])
    assert client.delete("/api/voice/setup").status_code == 200
    job = _wait_for(client, client.post("/api/voice/setup/install", json={}).json()["id"])
    assert job["status"] == "complete"
    assert client.get("/api/health").json()["runtime"]["tts_ready"] is True


def test_removing_with_nothing_installed_frees_nothing(voice_app):
    client, app, server = voice_app
    response = client.delete("/api/voice/setup")
    assert response.status_code == 200
    assert response.json()["freed_bytes"] == 0


def test_voice_cannot_be_removed_while_it_installs(voice_app):
    client, app, server = voice_app
    release = False

    def hold(request: httpx.Request) -> None:
        deadline = time.monotonic() + 10
        while not release and time.monotonic() < deadline:
            time.sleep(0.01)

    server.before_respond = hold
    started = client.post("/api/voice/setup/install", json={}).json()
    response = client.delete("/api/voice/setup")
    release = True
    _wait_for(client, started["id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VOICE_BUSY"
