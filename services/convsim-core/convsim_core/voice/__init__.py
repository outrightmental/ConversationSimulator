# SPDX-License-Identifier: Apache-2.0
"""One-click voice: the speech engine and models the app can install for itself.

Voice used to mean a ``whisper-cli`` the player compiled and a Kokoro server
the player ran. This package replaces that with a download the app does on
the player's request, the same way it fetches the LLM:

* :mod:`convsim_core.voice.catalog` pins every file: URL, size, SHA-256,
  licence. Nothing is fetched that is not listed there.
* :mod:`convsim_core.voice.installer` downloads, verifies and unpacks them
  under the voice folder.
* :mod:`convsim_core.voice.jobs` runs an install as a cancellable job with
  per-stage progress.
* :mod:`convsim_core.voice.engine` runs the installed engine, a separate
  program, one short-lived process per request.
* :mod:`convsim_core.voice.workers` points the app's STT and TTS workers at
  the installed engine once it is there.

See ``docs/voice-setup.md``.
"""
