# SPDX-License-Identifier: Apache-2.0
"""Registry of the downloadable assets and engines the voice stack needs.

Voice is optional: the app is fully playable in text-only mode.  Turning it on
needs two different kinds of thing, and they are listed separately here because
the app can only automate one of them:

``VOICE_ASSETS``
    Weight files the app downloads itself — a whisper.cpp GGML model for
    speech-to-text, the Silero VAD ONNX model for hands-free turn-taking.  Each
    entry carries a revision-pinned URL, a mandatory SHA-256, a licence and an
    exact byte size, so the confirmation screen can disclose everything
    ``docs/model-download-policy.md`` §4 requires before a single byte moves.

``VOICE_ENGINES``
    Native programs the app cannot fetch safely — ``whisper-cli`` and the Kokoro
    TTS server.  Neither publishes a checksummed cross-platform release the way
    llama.cpp does, so onboarding *guides* the player through installing them
    (per-platform commands, a docs link, a re-check button) instead of
    pretending to automate it.  Once the binary exists the app can take over
    again: a present-but-stopped Kokoro server is started with one click.

The SHA-256 values are the Hugging Face / upstream LFS object ids for the exact
pinned revision.  A file that does not match is deleted, never installed.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Capability = Literal["stt", "tts", "vad"]

# Hugging Face repo revision the whisper.cpp GGML weights are pinned to.
# (The repo is append-only; the per-file SHA-256 below is the real integrity
# gate, the revision pin just stops a moved tag from silently changing what the
# URL points at.)
_WHISPER_REPO_REV = "5359861c739e955e79d9a303bcbc70fb988958b1"
_WHISPER_BASE_URL = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/{_WHISPER_REPO_REV}"

# Commit of snakers4/silero-vad the VAD weights are pinned to. This revision
# ships the v5 model — the one convsim_core/vad/silero.py drives with its
# (input, state, sr) signature — so the pin is load-bearing, not cosmetic.
_SILERO_COMMIT = "bfdc0193023f121ea5b3cc7b176dbed570a68a59"

_MIT_URL = "https://opensource.org/licenses/MIT"


@dataclass(frozen=True)
class VoiceAsset:
    """One downloadable weight file, with everything needed to disclose it."""

    id: str
    capability: Capability
    name: str
    description: str
    filename: str
    url: str
    sha256: str
    size_bytes: int
    license: str
    license_url: str
    # Exactly one asset per capability is the one-click default.
    recommended: bool = False
    # Shown next to the name in the picker, e.g. "English only".
    language_note: str = ""


@dataclass(frozen=True)
class VoiceEngine:
    """A native program voice needs that the app cannot download for the user."""

    id: str
    capability: Capability
    name: str
    # Why the app does not just fetch it — shown verbatim in the UI.
    why_manual: str
    docs_url: str
    # Per-platform install command, keyed by sys.platform value.
    commands: dict[str, str]
    # True when the app can start it once the binary exists (Kokoro's server).
    startable: bool = False


VOICE_ASSETS: tuple[VoiceAsset, ...] = (
    VoiceAsset(
        id="whisper-tiny-en",
        capability="stt",
        name="Whisper tiny.en",
        description="Fastest and smallest. Noticeably less accurate on accents and noise.",
        filename="ggml-tiny.en.bin",
        url=f"{_WHISPER_BASE_URL}/ggml-tiny.en.bin",
        sha256="921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f",
        size_bytes=77_704_715,
        license="MIT",
        license_url=_MIT_URL,
        language_note="English only",
    ),
    VoiceAsset(
        id="whisper-base-en",
        capability="stt",
        name="Whisper base.en",
        description="The recommended balance of accuracy and speed for spoken practice.",
        filename="ggml-base.en.bin",
        url=f"{_WHISPER_BASE_URL}/ggml-base.en.bin",
        sha256="a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002",
        size_bytes=147_964_211,
        license="MIT",
        license_url=_MIT_URL,
        recommended=True,
        language_note="English only",
    ),
    VoiceAsset(
        id="whisper-base",
        capability="stt",
        name="Whisper base (multilingual)",
        description="Same size as base.en, but transcribes every language Whisper supports.",
        filename="ggml-base.bin",
        url=f"{_WHISPER_BASE_URL}/ggml-base.bin",
        sha256="60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
        size_bytes=147_951_465,
        license="MIT",
        license_url=_MIT_URL,
        language_note="Multilingual",
    ),
    VoiceAsset(
        id="whisper-small-en",
        capability="stt",
        name="Whisper small.en",
        description="Most accurate of the three. Slower, and wants a bit more memory.",
        filename="ggml-small.en.bin",
        url=f"{_WHISPER_BASE_URL}/ggml-small.en.bin",
        sha256="c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d",
        size_bytes=487_614_201,
        license="MIT",
        license_url=_MIT_URL,
        language_note="English only",
    ),
    VoiceAsset(
        id="silero-vad",
        capability="vad",
        name="Silero VAD",
        description=(
            "Detects when you have stopped speaking, so hands-free mode can take "
            "its turn without a push-to-talk key."
        ),
        filename="silero_vad.onnx",
        url=(
            "https://raw.githubusercontent.com/snakers4/silero-vad/"
            f"{_SILERO_COMMIT}/src/silero_vad/data/silero_vad.onnx"
        ),
        sha256="1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3",
        size_bytes=2_327_524,
        license="MIT",
        license_url="https://github.com/snakers4/silero-vad/blob/master/LICENSE",
        recommended=True,
    ),
)


_WHISPER_DOCS = "https://github.com/ggml-org/whisper.cpp#quick-start"
_KOKORO_DOCS = "https://github.com/remsky/Kokoro-FastAPI#readme"

VOICE_ENGINES: tuple[VoiceEngine, ...] = (
    VoiceEngine(
        id="whisper-cli",
        capability="stt",
        name="whisper.cpp",
        why_manual=(
            "whisper.cpp publishes no checksummed binary for every platform, so the "
            "app will not download one for you. One command installs it."
        ),
        docs_url=_WHISPER_DOCS,
        commands={
            "darwin": "brew install whisper-cpp",
            "linux": (
                "git clone https://github.com/ggml-org/whisper.cpp && "
                "cmake -B build -S whisper.cpp && cmake --build build --config Release && "
                "sudo cp build/bin/whisper-cli /usr/local/bin/"
            ),
            "win32": "winget install --id ggml.whisper-cpp",
        },
    ),
    VoiceEngine(
        id="kokoro-server",
        capability="tts",
        name="Kokoro TTS server",
        why_manual=(
            "The NPC voice runs in a small local server. Steam builds ship it; "
            "elsewhere the quickest route is the official container image."
        ),
        docs_url=_KOKORO_DOCS,
        commands={
            "darwin": "docker run --rm -p 7358:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest",
            "linux": "docker run --rm -p 7358:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest",
            "win32": "docker run --rm -p 7358:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest",
        },
        startable=True,
    ),
)


def get_asset(asset_id: str) -> VoiceAsset | None:
    """Return the asset with *asset_id*, or None when it is not in the registry."""
    for asset in VOICE_ASSETS:
        if asset.id == asset_id:
            return asset
    return None


def assets_for(capability: Capability) -> list[VoiceAsset]:
    """Return every registry asset that serves *capability*, in display order."""
    return [a for a in VOICE_ASSETS if a.capability == capability]


def recommended_asset(capability: Capability) -> VoiceAsset | None:
    """Return the one-click default asset for *capability*."""
    for asset in assets_for(capability):
        if asset.recommended:
            return asset
    return None


def get_engine(engine_id: str) -> VoiceEngine | None:
    """Return the engine with *engine_id*, or None when it is not in the registry."""
    for engine in VOICE_ENGINES:
        if engine.id == engine_id:
            return engine
    return None


def engine_command(engine: VoiceEngine, platform: str) -> str | None:
    """Return the install command for *platform*, or None when none is listed."""
    if platform.startswith("linux"):
        platform = "linux"
    return engine.commands.get(platform)


def find_whisper_binary() -> str | None:
    """Return the resolved ``whisper-cli`` path, honouring the configured override.

    Mirrors the lookup ``WhisperCppWorker`` performs so onboarding never reports
    an engine as present that the worker would then fail to find.
    """
    from convsim_core.stt.whisper_cpp import WhisperCppConfig, _find_binary

    explicit = WhisperCppConfig().binary_path
    if explicit:
        return explicit if os.path.isfile(explicit) and os.access(explicit, os.X_OK) else None
    return _find_binary(None)


def onnxruntime_installed() -> bool:
    """Return True when the optional ``onnxruntime`` dependency can be imported."""
    from importlib.util import find_spec

    try:
        return find_spec("onnxruntime") is not None
    except (ImportError, ValueError):  # pragma: no cover - broken import machinery
        return False


def ffmpeg_installed() -> bool:
    """Return True when ffmpeg is on PATH (needed to decode browser audio)."""
    return shutil.which("ffmpeg") is not None


def stt_model_dir() -> Path:
    """Directory the STT worker reads its model from."""
    from convsim_core.stt.whisper_cpp import WhisperCppConfig

    return Path(WhisperCppConfig().model_path).expanduser().parent


def vad_model_path() -> Path:
    """Exact path the VAD worker reads its ONNX model from."""
    from convsim_core.vad.silero import SileroVadConfig

    return Path(SileroVadConfig().model_path).expanduser()


def install_path(asset: VoiceAsset) -> Path:
    """Where *asset* must land for the engine that consumes it to find it.

    VAD resolves to the worker's exact configured path (there is only one VAD
    model, so an alternative filename would simply never be read). STT keeps the
    upstream filename inside the worker's model directory, because the player
    may install more than one and switch between them.

    Raises ValueError for a capability with no file-backed engine, so adding a
    downloadable TTS asset fails loudly here rather than quietly dropping the
    file into the speech-to-text directory.
    """
    if asset.capability == "vad":
        return vad_model_path()
    if asset.capability == "stt":
        return stt_model_dir() / asset.filename
    raise ValueError(
        f"No install path is defined for {asset.capability!r} assets "
        f"(asset {asset.id!r}); teach install_path() where its engine reads from."
    )


def configured_stt_model_path() -> Path:
    """The model file the STT worker reads when nothing has been chosen."""
    from convsim_core.stt.whisper_cpp import WhisperCppConfig

    return Path(WhisperCppConfig().model_path).expanduser()
