#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install voice for real and prove it works on this machine.

Downloads the pinned speech engine and models for this platform into a
scratch folder, exactly as the app's own installer does (same catalog, same
checksum checks), then round-trips speech: a sentence is synthesised with a
Kokoro voice, the audio is transcribed with Whisper, and the words that come
back are compared with the words that went in.

This is the check a unit test cannot make. The unit tests replace the engine
with a stand-in; this runs the engine the catalog pins, so it catches an
engine build that does not start on a platform, a pin that has moved at its
source, and a pronunciation change that drops words.

Usage::

    python scripts/voice-smoke.py                 # full round trip (~560 MB)
    python scripts/voice-smoke.py --engine-only   # engine download + start (~25 MB)
    python scripts/voice-smoke.py --voice-dir D   # keep the install in D

Run from the repo root with convsim-core importable (``pip install -e
services/convsim-core``). Exit status 0 means every check passed.
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

import httpx

from convsim_core.stt.sherpa_whisper import SherpaWhisperWorker
from convsim_core.stt.types import SttRequest
from convsim_core.tts.sherpa_kokoro import SherpaKokoroTtsWorker
from convsim_core.tts.types import TtsRequest
from convsim_core.voice import catalog
from convsim_core.voice.engine import probe_engine
from convsim_core.voice.installer import install_asset
from convsim_core.voice.layout import VoiceLayout

# What goes in must come back at least this alike, word for word. The English
# sentences round-trip exactly on the reference machine; the margin is for a
# homophone or a number written differently, not for a missing clause.
_MIN_SIMILARITY = 0.9

# (voice, language, text). Chosen to exercise what has broken before:
#   1. words absent from the Kokoro lexicon ("reasons", "noticed", "that's"),
#      which engine 2.x skipped without a sound;
#   2. typographic punctuation and an ellipsis, which reached the engine as
#      noise on Windows and cost the last word of the sentence;
#   3. a British voice, which takes the British lexicon;
#   4. Spanish with its accents and inverted marks, spoken as Spanish.
_ROUND_TRIPS: list[tuple[str, str, str]] = [
    (
        "af_heart",
        "en",
        "One morning the pipeline began failing for reasons nobody could explain. "
        "I noticed the failures, and that's my final number.",
    ),
    (
        "am_michael",
        "en",
        "I don’t think that’s fair — the café was “closed”… wasn’t it?",
    ),
    ("bm_george", "en", "Right then, shall we have a look at the numbers?"),
    ("af_heart", "es", "Hola, bienvenido al café. ¿Qué te gustaría tomar hoy?"),
]


def _words(text: str) -> list[str]:
    """Lower-case words with accents, apostrophes and punctuation removed.

    Apostrophes go before anything else, straight or curly, so "don't" and
    "don’t" are the same word and neither becomes two.
    """
    joined = re.sub(r"['‘’]", "", text)
    folded = unicodedata.normalize("NFKD", joined).encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[a-z0-9]+", folded.lower())


def _similarity(expected: str, heard: str) -> float:
    return difflib.SequenceMatcher(None, _words(expected), _words(heard)).ratio()


async def _install(layout: VoiceLayout, assets: list[catalog.VoiceAsset]) -> None:
    timeout = httpx.Timeout(connect=30.0, read=120.0, write=120.0, pool=30.0)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        for asset in assets:
            if layout.is_installed(asset):
                print(f"  {asset.id}: already installed")
                continue
            started = time.monotonic()
            await install_asset(asset, layout, client=client)
            megabytes = asset.download_bytes / 1e6
            print(f"  {asset.id}: {megabytes:.0f} MB in {time.monotonic() - started:.0f} s")


async def _run(voice_dir: Path, engine_only: bool) -> int:
    key = catalog.detect_platform_key()
    engine = catalog.engine_asset()
    if engine is None:
        print(f"FAIL: no speech engine build is pinned for this platform ({key}).")
        return 1
    print(f"Platform: {key}   voice folder: {voice_dir}")

    layout = VoiceLayout(voice_dir)
    assets = [engine] if engine_only else [engine, catalog.WHISPER_ASSET, catalog.KOKORO_ASSET]
    print("Installing (checksum-verified):")
    await _install(layout, assets)

    version = await probe_engine(layout)
    print(f"Engine starts: sherpa-onnx {version}")
    if version != catalog.ENGINE_VERSION:
        print(f"FAIL: the engine reports {version}, the catalog pins {catalog.ENGINE_VERSION}.")
        return 1
    if engine_only:
        print("PASS (engine only)")
        return 0

    tts = SherpaKokoroTtsWorker(voice_dir, voice_dir / "smoke-cache")
    stt = SherpaWhisperWorker(voice_dir)
    failures = 0
    for voice_id, language, text in _ROUND_TRIPS:
        started = time.monotonic()
        spoken = await tts.synthesize(TtsRequest(text=text, voice_id=voice_id, language=language))
        synth_s = time.monotonic() - started
        audio = Path(spoken.audio_path).read_bytes()

        started = time.monotonic()
        heard = await stt.transcribe(SttRequest(audio=audio, audio_format="wav", language=language))
        stt_s = time.monotonic() - started

        score = _similarity(text, heard.transcript)
        verdict = "ok  " if score >= _MIN_SIMILARITY else "FAIL"
        # ASCII only: a Windows runner's console cannot print every character.
        print(f"  {verdict} {voice_id} [{language}] similarity {score:.2f}  "
              f"synthesis {synth_s:.1f} s, transcription {stt_s:.1f} s")
        print(f"       said : {ascii(text)}")
        print(f"       heard: {ascii(heard.transcript)}")
        if score < _MIN_SIMILARITY:
            failures += 1

    if failures:
        print(f"FAIL: {failures} of {len(_ROUND_TRIPS)} round trips did not come back intact.")
        return 1
    print(f"PASS: {len(_ROUND_TRIPS)} round trips came back intact.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--engine-only", action="store_true",
                        help="download and start the engine only; skip the models")
    parser.add_argument("--voice-dir", type=Path, default=None,
                        help="install here and keep it (default: a temporary folder)")
    args = parser.parse_args()

    if args.voice_dir is not None:
        args.voice_dir.mkdir(parents=True, exist_ok=True)
        return asyncio.run(_run(args.voice_dir.resolve(), args.engine_only))
    with tempfile.TemporaryDirectory(prefix="convsim-voice-smoke-") as scratch:
        return asyncio.run(_run(Path(scratch).resolve(), args.engine_only))


if __name__ == "__main__":
    sys.exit(main())
