# SPDX-License-Identifier: Apache-2.0
"""The pinned list of everything a voice install downloads.

Three assets make up voice:

``engine``
    sherpa-onnx, a prebuilt speech engine published by its authors for every
    platform the app ships on. It runs both directions: Whisper models for
    speech-to-text and Kokoro models for text-to-speech.
``whisper-base``
    The multilingual Whisper *base* model, in the engine's ONNX format.
``kokoro-v1``
    The Kokoro v1.0 voices, plus the eSpeak NG pronunciation data the engine
    uses for words the Kokoro lexicon does not list.

Every download is pinned to an immutable address where one exists (a Hugging
Face commit, a versioned GitHub release) and always to an exact size and
SHA-256, per ``docs/model-download-policy.md``. A file that does not match is
discarded, never installed.

Why engine 1.13.8 and not the 2.x line: 2.0 removed eSpeak NG, and with it
any pronunciation for a word missing from the lexicon. Such words are skipped
in silence ("reasons", "noticed", "that's" are all missing), which is not
acceptable for conversational speech. 1.13.8 is the last release that speaks
every word. ``docs/voice-setup.md`` records the measurements.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

ENGINE_VERSION = "1.13.8"

_ENGINE_RELEASE = (
    f"https://github.com/k2-fsa/sherpa-onnx/releases/download/v{ENGINE_VERSION}"
)
_WHISPER_REVISION = "bb53ee204431c90d314c1cc08d28d23e5b7927cc"
_WHISPER_BASE = (
    f"https://huggingface.co/csukuangfj/sherpa-onnx-whisper-base/resolve/{_WHISPER_REVISION}"
)
_KOKORO_REVISION = "f7b96bb6bef5c5da4d3aa4f4e0498fbbf62dc78b"
_KOKORO_BASE = (
    f"https://huggingface.co/csukuangfj/kokoro-multi-lang-v1_0/resolve/{_KOKORO_REVISION}"
)
_ESPEAK_DATA_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/espeak-ng-data.tar.bz2"
)

# File written last into an asset's folder. Its presence, with the catalog's
# current version inside, is what "installed" means.
INSTALL_MARKER = ".installed.json"


@dataclass(frozen=True)
class VoiceDownload:
    """One file fetched over the network."""

    url: str
    sha256: str
    size_bytes: int
    # Where the file lands, relative to the asset folder. Ignored for an archive.
    dest: str = ""
    # An archive is unpacked into the asset folder instead of being stored.
    unpack: bool = False
    # Leading path components dropped from each archive member.
    strip_components: int = 0
    # ``fnmatch`` patterns, matched after stripping; only matching members are
    # unpacked. Empty means every member.
    keep: tuple[str, ...] = ()


@dataclass(frozen=True)
class VoiceAsset:
    """A unit that is installed, replaced and reported on as a whole."""

    id: str
    label: str
    version: str
    # Folder under the voice root. Deliberately plain ASCII: the engine is
    # handed these as relative paths (see ``voice.engine``).
    install_dir: str
    license: str
    license_note: Optional[str]
    source_name: str
    source_url: str
    downloads: tuple[VoiceDownload, ...]
    # Paths, relative to the asset folder, that must exist for it to count as
    # installed. A marker without them is a damaged install.
    required_files: tuple[str, ...]

    @property
    def download_bytes(self) -> int:
        return sum(d.size_bytes for d in self.downloads)


@dataclass(frozen=True)
class VoiceComponent:
    """Something the player gets: a way to speak, or a way to hear."""

    id: str
    label: str
    description: str
    # The model assets it needs. The engine is shared by both and implied.
    asset_ids: tuple[str, ...]
    # Languages it can handle (primary subtags), or None for "any".
    languages: Optional[tuple[str, ...]]


# ── Engine ────────────────────────────────────────────────────────────────────

# platform key → (asset file name, size in bytes, SHA-256). The digests are the
# ones GitHub publishes for each release asset. The Windows builds are the
# ``MT`` variant: the C runtime is linked in, so a player needs no Visual C++
# redistributable.
_ENGINE_BUILDS: dict[str, tuple[str, int, str]] = {
    "win-x64": (
        f"sherpa-onnx-v{ENGINE_VERSION}-win-x64-shared-MT-Release.tar.bz2",
        24_805_859,
        "6dffdc715a4465b989446a6105265d2cb345e7101591a17d35534b6758f6e8df",
    ),
    "win-arm64": (
        f"sherpa-onnx-v{ENGINE_VERSION}-win-arm64-shared-MT-Release.tar.bz2",
        23_341_583,
        "455ea18dc44aea188b4f7976037dea3d77e3f8d7afe0760f34244a7a0db53c4c",
    ),
    "osx-arm64": (
        f"sherpa-onnx-v{ENGINE_VERSION}-osx-arm64-shared.tar.bz2",
        20_314_448,
        "b10e5c7e2c30ea03de9c442655d14860d9edc475c6251d58a8f5f06e913a1d56",
    ),
    "osx-x64": (
        f"sherpa-onnx-v{ENGINE_VERSION}-osx-x64-shared.tar.bz2",
        22_846_038,
        "54aad64acee9d2d596535a6080d6f22602a720af5460e1d50461b1e1b06bee40",
    ),
    "linux-x64": (
        f"sherpa-onnx-v{ENGINE_VERSION}-linux-x64-shared.tar.bz2",
        28_156_791,
        "c0bdb7907d3a74bba1d55d22bf4d9fa75586cf1530614ebe88a27b9118e015c4",
    ),
    "linux-aarch64": (
        f"sherpa-onnx-v{ENGINE_VERSION}-linux-aarch64-shared-cpu.tar.bz2",
        28_091_778,
        "4e3734f82bc1379fd91f219f5869c7e9d03b7a4f7561907d8abca4849c51a789",
    ),
}

# The three programs the app runs, out of the two dozen in the archive.
ENGINE_STT_PROGRAM = "sherpa-onnx-offline"
ENGINE_TTS_PROGRAM = "sherpa-onnx-offline-tts"
ENGINE_VERSION_PROGRAM = "sherpa-onnx-version"
_ENGINE_PROGRAMS = (ENGINE_STT_PROGRAM, ENGINE_TTS_PROGRAM, ENGINE_VERSION_PROGRAM)


def _machine() -> str:
    """This process's processor architecture, lower-cased.

    Not ``platform.machine()``. On Windows that goes through
    ``platform.uname()``, which on Python 3.11 runs ``ver`` in a ``cmd``
    child. This is asked every time the core starts, and the packaged core
    has no console of its own, so that child would flash a console window
    over the app. The environment answers the same question for free.
    """
    if sys.platform == "win32":
        # PROCESSOR_ARCHITEW6432 is set only for a 32-bit process on a 64-bit
        # system, where it names the real architecture.
        return (
            os.environ.get("PROCESSOR_ARCHITEW6432")
            or os.environ.get("PROCESSOR_ARCHITECTURE", "")
        ).lower()
    return os.uname().machine.lower()


def detect_platform_key() -> Optional[str]:
    """The engine build for this machine, or None when there is none."""
    machine = _machine()
    arm = machine in ("arm64", "aarch64")
    x64 = machine in ("x86_64", "amd64")
    if sys.platform == "win32":
        return "win-arm64" if arm else "win-x64" if x64 else None
    if sys.platform == "darwin":
        return "osx-arm64" if arm else "osx-x64" if x64 else None
    if sys.platform.startswith("linux"):
        return "linux-aarch64" if arm else "linux-x64" if x64 else None
    return None


def engine_program_filename(program: str, platform_key: Optional[str] = None) -> str:
    """File name of an engine program on this (or the given) platform."""
    key = platform_key if platform_key is not None else detect_platform_key()
    return f"{program}.exe" if key and key.startswith("win-") else program


def engine_asset(platform_key: Optional[str] = None) -> Optional[VoiceAsset]:
    """The engine asset for a platform, or None where no build is published."""
    key = platform_key if platform_key is not None else detect_platform_key()
    if key is None or key not in _ENGINE_BUILDS:
        return None
    filename, size, sha256 = _ENGINE_BUILDS[key]
    programs = tuple(engine_program_filename(p, key) for p in _ENGINE_PROGRAMS)
    keep = tuple(f"bin/{p}" for p in programs) + (
        # Windows keeps its libraries beside the programs; macOS and Linux
        # keep them in lib/, which the programs find by relative path.
        "bin/*.dll",
        "lib/*.so",
        "lib/*.so.*",
        "lib/*.dylib",
    )
    return VoiceAsset(
        id="engine",
        label="Speech engine",
        version=f"{ENGINE_VERSION}-{key}",
        install_dir="engine",
        license="Apache-2.0",
        license_note="Includes ONNX Runtime (MIT) and eSpeak NG (GPL-3.0-or-later).",
        source_name="sherpa-onnx",
        source_url=f"https://github.com/k2-fsa/sherpa-onnx/releases/tag/v{ENGINE_VERSION}",
        downloads=(
            VoiceDownload(
                url=f"{_ENGINE_RELEASE}/{filename}",
                sha256=sha256,
                size_bytes=size,
                unpack=True,
                strip_components=1,
                keep=keep,
            ),
        ),
        required_files=tuple(f"bin/{p}" for p in programs),
    )


def engine_platform_keys() -> tuple[str, ...]:
    """Every platform an engine build is pinned for."""
    return tuple(_ENGINE_BUILDS)


# ── Models ────────────────────────────────────────────────────────────────────

WHISPER_ASSET = VoiceAsset(
    id="whisper-base",
    label="Listening model (Whisper base)",
    version=f"base-int8-{_WHISPER_REVISION[:12]}",
    install_dir="stt",
    license="MIT",
    license_note=None,
    source_name="OpenAI Whisper, converted for sherpa-onnx",
    source_url="https://huggingface.co/csukuangfj/sherpa-onnx-whisper-base",
    downloads=(
        VoiceDownload(
            url=f"{_WHISPER_BASE}/base-encoder.int8.onnx",
            sha256="0b8fb1304b6109976038efff5ace81720e00386f3ff6b54ee8c75291ca0a1e11",
            size_bytes=29_120_534,
            dest="base-encoder.int8.onnx",
        ),
        VoiceDownload(
            url=f"{_WHISPER_BASE}/base-decoder.int8.onnx",
            sha256="9759d217388a01b3a4c7c15533201067b48ae819c4daafc8624e64b9409dc02d",
            size_bytes=130_672_026,
            dest="base-decoder.int8.onnx",
        ),
        VoiceDownload(
            url=f"{_WHISPER_BASE}/base-tokens.txt",
            sha256="b34b360dbb493e781e479794586d661700670d65564001f23024971d1f2fa126",
            size_bytes=816_730,
            dest="base-tokens.txt",
        ),
    ),
    required_files=("base-encoder.int8.onnx", "base-decoder.int8.onnx", "base-tokens.txt"),
)

KOKORO_ASSET = VoiceAsset(
    id="kokoro-v1",
    label="Voices (Kokoro v1.0)",
    version=f"v1_0-{_KOKORO_REVISION[:12]}",
    install_dir="tts",
    license="Apache-2.0",
    license_note="Pronunciation data from eSpeak NG (GPL-3.0-or-later).",
    source_name="Kokoro-82M, converted for sherpa-onnx",
    source_url="https://huggingface.co/csukuangfj/kokoro-multi-lang-v1_0",
    downloads=(
        # The full-precision model, not the 114 MB int8 one: measured on the
        # same machine it synthesised three to five times faster.
        VoiceDownload(
            url=f"{_KOKORO_BASE}/model.onnx",
            sha256="b40f62b166ac8164b0627ef48a0b358eda0985e272fb03ef5252e7206305da11",
            size_bytes=325_560_556,
            dest="model.onnx",
        ),
        VoiceDownload(
            url=f"{_KOKORO_BASE}/voices.bin",
            sha256="1c5a5b983d3d50d8586d437a51f3faa2da7919ce76a013c081e65671a3447c29",
            size_bytes=28_200_960,
            dest="voices.bin",
        ),
        VoiceDownload(
            url=f"{_KOKORO_BASE}/tokens.txt",
            sha256="6ebb6bb288f20f3ae8d004d3c2ca27697da27c037d75e81a60e2a6a663f95425",
            size_bytes=687,
            dest="tokens.txt",
        ),
        VoiceDownload(
            url=f"{_KOKORO_BASE}/lexicon-us-en.txt",
            sha256="7daaab53a181be9885b853a8582bf1838186317e5dadacbcef9c426d6fa0da14",
            size_bytes=5_956_885,
            dest="lexicon-us-en.txt",
        ),
        VoiceDownload(
            url=f"{_KOKORO_BASE}/lexicon-gb-en.txt",
            sha256="c4cbb37316f62210dff52718a7afcaae24f50c032cc75ab47ae67b831d1049e7",
            size_bytes=6_366_635,
            dest="lexicon-gb-en.txt",
        ),
        VoiceDownload(
            url=f"{_KOKORO_BASE}/LICENSE",
            sha256="cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
            size_bytes=11_358,
            dest="LICENSE",
        ),
        # The archive's single top-level folder is espeak-ng-data/, which is
        # where the engine is told to look, so nothing is stripped.
        VoiceDownload(
            url=_ESPEAK_DATA_URL,
            sha256="4135ccf82e1f40613491c0874d4945ae9e9c7840933d8e25a6f9e003d9ebf533",
            size_bytes=7_252_012,
            unpack=True,
            keep=("espeak-ng-data/*",),
        ),
    ),
    required_files=(
        "model.onnx",
        "voices.bin",
        "tokens.txt",
        "lexicon-us-en.txt",
        "lexicon-gb-en.txt",
        "espeak-ng-data/phontab",
    ),
)

MODEL_ASSETS: dict[str, VoiceAsset] = {
    WHISPER_ASSET.id: WHISPER_ASSET,
    KOKORO_ASSET.id: KOKORO_ASSET,
}

# Languages the Kokoro voices can speak through the engine's eSpeak NG
# phonemiser: session language (primary subtag) → the engine's language name.
KOKORO_LANGUAGES: dict[str, str] = {
    "en": "en",
    "es": "es",
    "fr": "fr",
    "it": "it",
    "pt": "pt-br",
    "hi": "hi",
}

# Speaker index of each approved voice inside the Kokoro v1.0 voice table
# (the model's own ``speaker2id`` metadata). Must cover
# ``convsim_core.tts.voices.APPROVED_VOICES`` exactly; a test pins that.
KOKORO_SPEAKER_IDS: dict[str, int] = {
    "af_bella": 2,
    "af_heart": 3,
    "af_nicole": 6,
    "af_sky": 10,
    "am_adam": 11,
    "am_michael": 16,
    "bf_emma": 21,
    "bf_isabella": 22,
    "bm_george": 26,
    "bm_lewis": 27,
}

STT_COMPONENT = VoiceComponent(
    id="stt",
    label="Voice input",
    description="Speak your turns instead of typing them.",
    asset_ids=(WHISPER_ASSET.id,),
    languages=None,
)

TTS_COMPONENT = VoiceComponent(
    id="tts",
    label="Character voice",
    description="Hear the other person's replies out loud.",
    asset_ids=(KOKORO_ASSET.id,),
    languages=tuple(KOKORO_LANGUAGES),
)

COMPONENTS: dict[str, VoiceComponent] = {
    STT_COMPONENT.id: STT_COMPONENT,
    TTS_COMPONENT.id: TTS_COMPONENT,
}
