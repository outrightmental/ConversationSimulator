# SPDX-License-Identifier: Apache-2.0
"""Run the installed speech engine.

The engine is a set of command-line programs published by the sherpa-onnx
project. The app runs one short-lived process per request: about a second to
load a model, then the work. Nothing of the engine is linked into the app.

Two things about its command line are handled here so the workers do not
have to think about them:

* **Paths.** The process is started with the voice root as its working
  directory and given paths relative to it. Those are plain ASCII (see
  :mod:`convsim_core.voice.layout`), so the absolute path, which contains the
  player's user name, never has to survive the command line.
* **Text.** On Windows the engine reads its arguments in the machine's legacy
  "ANSI" code page and then treats them as UTF-8. A curly apostrophe or an
  accented letter passed as-is comes out as noise ("I don't think" was spoken
  as "I don't know how to"). :func:`text_for_argv` hands over a string that
  arrives as the UTF-8 the engine expects.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import Optional, Sequence

from convsim_core.runtime.procflags import CREATE_NO_WINDOW
from convsim_core.voice import catalog
from convsim_core.voice.layout import VoiceLayout

# Longest text handed to the engine in one argument. A sentence is far
# shorter; this only bounds a pathological input.
_MAX_TEXT_CHARS = 2000

# Typographic characters that carry no pronunciation of their own, mapped to
# the plain form every phonemiser understands.
_PLAIN_PUNCTUATION = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "«": '"', "»": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "−": "-",
    # A dash used as a break in the sentence is spoken as a pause.
    "—": ", ", "―": ", ",
    "…": "...",
    " ": " ", " ": " ", " ": " ", " ": " ",
    "​": "", "‌": "", "‍": "", "﻿": "",
}
_PLAIN_PUNCTUATION_TABLE = str.maketrans(_PLAIN_PUNCTUATION)
_WHITESPACE = re.compile(r"\s+")
_TRAILING_ELLIPSIS = re.compile(r"\s*\.{2,}$")
_ELLIPSIS = re.compile(r"\s*\.{2,}\s*")


class EngineError(Exception):
    """The engine could not be run, or reported a failure."""


@dataclass(frozen=True)
class EngineResult:
    returncode: int
    stdout: str
    stderr: str


def default_threads() -> int:
    """Threads per engine process: half the cores, between one and four.

    Four is where synthesis stops getting faster; more was measurably slower.
    """
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def normalize_spoken_text(text: str) -> str:
    """Plain punctuation, single spaces, no leading dash, bounded length.

    An ellipsis becomes the pause it stands for: a comma inside a sentence, a
    full stop at its end. Left as dots, the engine was heard to drop the word
    after it ("closed... wasn't it?" lost its "it").
    """
    plain = text.translate(_PLAIN_PUNCTUATION_TABLE)
    plain = _WHITESPACE.sub(" ", plain).strip()
    plain = _TRAILING_ELLIPSIS.sub(".", plain)
    plain = _ELLIPSIS.sub(", ", plain)
    # The engine's option parser would read a leading "--" as a flag, and a
    # sentence cannot start with the pause an opening ellipsis turned into.
    plain = plain.lstrip("-, ").strip()
    return plain[:_MAX_TEXT_CHARS]


def _ascii_fold(text: str) -> str:
    """Drop accents and anything else outside ASCII."""
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def text_for_argv(text: str, *, platform: Optional[str] = None) -> str:
    """Return *text* in the form that reaches the engine as correct UTF-8.

    Everywhere but Windows, arguments are already bytes in UTF-8. On Windows
    the C runtime converts the command line to the ANSI code page, so the
    string passed is the one whose ANSI encoding *is* the wanted UTF-8 bytes.
    That exists for every single-byte code page; where it does not (a
    double-byte code page), accents are dropped rather than spoken as noise.
    """
    spoken = normalize_spoken_text(text)
    if (platform or sys.platform) != "win32" or spoken.isascii():
        return spoken
    try:
        wanted = spoken.encode("utf-8")
        carrier = wanted.decode("mbcs")
        if carrier.encode("mbcs") == wanted:
            return carrier
    except (UnicodeError, LookupError):
        pass
    return _ascii_fold(spoken)


def _engine_env(layout: VoiceLayout) -> dict[str, str]:
    """Environment for an engine process: its own libraries first.

    A PyInstaller-frozen core points the loader path at its own bundle; the
    engine must not inherit that, so the path the core was started with is
    used as the base instead.
    """
    env = dict(os.environ)
    if sys.platform == "win32":
        return env
    var = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    base = env.get(f"{var}_ORIG") if getattr(sys, "frozen", False) else env.get(var)
    engine = catalog.engine_asset()
    lib_dir = layout.root / (engine.install_dir if engine else "engine") / "lib"
    env[var] = str(lib_dir) + (os.pathsep + base if base else "")
    return env


async def run_engine(
    layout: VoiceLayout,
    program: str,
    args: Sequence[str],
    *,
    timeout: float,
) -> EngineResult:
    """Run one engine program to completion in the voice root.

    Raises :class:`EngineError` when the program is missing, cannot be
    started, or runs past *timeout*. A non-zero exit is returned, not raised:
    the caller knows what the program was asked to do and words the failure.
    """
    exe = layout.engine_program(program)
    if not exe.is_file():
        raise EngineError(f"The speech engine is not installed ({exe.name} is missing).")

    proc: Optional[asyncio.subprocess.Process] = None
    try:
        try:
            proc = await asyncio.create_subprocess_exec(
                str(exe),
                *args,
                cwd=str(layout.root),
                env=_engine_env(layout),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            raise EngineError(f"The speech engine could not be started: {exc}") from exc
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise EngineError(f"The speech engine did not finish within {timeout:.0f} s.") from exc
        return EngineResult(
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )
    finally:
        # Covers the timeout and a cancelled request alike: never leave an
        # engine process running after the request that wanted it is gone.
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except OSError:
                pass
            await proc.wait()


def failure_detail(result: EngineResult, limit: int = 300) -> str:
    """The last meaningful line the engine printed, for an error message."""
    lines = [ln.strip() for ln in (result.stderr + "\n" + result.stdout).splitlines()]
    lines = [ln for ln in lines if ln]
    return lines[-1][-limit:] if lines else f"exit code {result.returncode}"


async def probe_engine(layout: VoiceLayout, *, timeout: float = 20.0) -> str:
    """Start the engine once and return the version it reports.

    This is the install's last step: a download can verify perfectly and
    still not run on this machine, and the player should learn that from the
    installer, not from a conversation that stays silent.
    """
    result = await run_engine(layout, catalog.ENGINE_VERSION_PROGRAM, [], timeout=timeout)
    text = result.stdout + "\n" + result.stderr
    match = re.search(r"sherpa-onnx version\s*:\s*(\S+)", text)
    if result.returncode != 0 or match is None:
        raise EngineError(
            f"The speech engine was installed but did not start ({failure_detail(result)})."
        )
    return match.group(1)
