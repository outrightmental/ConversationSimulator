# SPDX-License-Identifier: Apache-2.0
"""Point the app's STT and TTS workers at the installed voice engine.

The app is configured with a worker id for each direction
(``CONVSIM_STT_WORKER_ID``, ``CONVSIM_TTS_WORKER_ID``). Their defaults,
``whisper_cpp`` and ``kokoro``, are the set-it-up-yourself workers: a
``whisper-cli`` on the PATH, a Kokoro server on port 7358. Once the player
has installed voice from inside the app, those defaults give way to the
built-in engine. Anything set explicitly (``fake`` in tests, a developer's
own choice) is left alone.

Called at startup and again whenever an install finishes, so voice switches
on without restarting the app.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from convsim_core.stt import build_stt_worker
from convsim_core.stt.sherpa_whisper import SherpaWhisperWorker
from convsim_core.tts import build_tts_worker
from convsim_core.tts.sherpa_kokoro import SherpaKokoroTtsWorker
from convsim_core.voice.layout import VoiceLayout

logger = logging.getLogger(__name__)

# The worker ids that mean "nothing was chosen": the ones a voice install
# may take over from.
_DEFAULT_STT_WORKER_ID = "whisper_cpp"
_DEFAULT_TTS_WORKER_ID = "kokoro"


def apply_voice_workers(app: Any) -> None:
    """Select the STT and TTS workers for the current install state."""
    config = app.state.service_config
    layout = VoiceLayout(config.voice_dir)

    if config.stt_worker_id == _DEFAULT_STT_WORKER_ID:
        want_builtin = layout.stt_installed()
        have_builtin = isinstance(app.state.stt_worker, SherpaWhisperWorker)
        if want_builtin and not have_builtin:
            app.state.stt_worker = SherpaWhisperWorker(config.voice_dir)
            logger.info("voice: speech-to-text now uses the built-in engine")
        elif have_builtin and not want_builtin:
            app.state.stt_worker = build_stt_worker(config.stt_worker_id)

    if config.tts_worker_id == _DEFAULT_TTS_WORKER_ID:
        want_builtin = layout.tts_installed()
        have_builtin = isinstance(app.state.tts_worker, SherpaKokoroTtsWorker)
        if want_builtin and not have_builtin:
            app.state.tts_worker = SherpaKokoroTtsWorker(
                config.voice_dir, Path(config.cache_dir) / "tts"
            )
            logger.info("voice: text-to-speech now uses the built-in engine")
        elif have_builtin and not want_builtin:
            app.state.tts_worker = build_tts_worker(config.tts_worker_id)
