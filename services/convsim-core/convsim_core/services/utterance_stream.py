# SPDX-License-Identifier: Apache-2.0
"""Pull the NPC's spoken line out of the model's JSON as it is written (#538).

The turn schema puts ``npc_utterance`` first, and llama.cpp's schema-constrained
output follows schema order, so the words the player is waiting for exist long
before the turn's bookkeeping is finished. :class:`UtteranceStreamExtractor`
consumes the raw token stream and yields the decoded contents of that string as
it grows — escapes, ``\\uXXXX``, surrogate pairs, sequences split across
chunks — and stops at the closing quote. If the runtime does not put the line
first, or the output is not an object at all, the extractor gives up and the
turn behaves exactly as before: nothing is released.

:class:`SentenceGate` decides what may be shown. A sentence is released only
once the whole line so far, with that sentence included, passes the output
check, so nothing is ever shown and then withdrawn (design question 2 on
#518). Released text is committed text: a later sentence that fails the check
is withheld, generation stops, and the line is committed as what was released.

The gate also holds back a first sentence that repeats one of the NPC's last
two lines (issue #580): the repetition guard's retry may only replace a line
nobody has seen, and before the first release is the one point where it still
can. Once a sentence is out, later ones are not held for repetition: cutting
the line there would commit a stub (an answer without its question), and no
retry could replace it. See :meth:`SentenceGate._repeats`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from convsim_prompt.output_validator import OutputValidationResult, validate_npc_output
from convsim_prompt.repetition import RepetitionReport, check_repetition

from convsim_core.tts.sentence_splitter import sentence_boundaries

logger = logging.getLogger(__name__)

_KEY = '"npc_utterance"'
_SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


class UtteranceStreamExtractor:
    """Incremental decoder for the first string property of a JSON object.

    Feed it the raw text chunks a runtime yields; ``feed`` returns the decoded
    utterance text that became available with that chunk (often empty while the
    stream is still in the key, or mid-escape). ``done`` is True once the
    closing quote has been seen; ``abandoned`` is True once the stream has shown
    it will not put ``npc_utterance`` first, after which ``feed`` returns ''.
    """

    def __init__(self) -> None:
        self._state = "start"  # start → key → colon → quote → string → done | abandoned
        self._key_progress = 0
        self._pending_escape = ""  # characters of an escape sequence seen so far, after the backslash
        self._in_escape = False
        self._high_surrogate: Optional[int] = None
        self._text: List[str] = []

    @property
    def done(self) -> bool:
        return self._state == "done"

    @property
    def abandoned(self) -> bool:
        return self._state == "abandoned"

    @property
    def active(self) -> bool:
        """True while the line may still grow."""
        return self._state not in ("done", "abandoned")

    @property
    def text(self) -> str:
        return "".join(self._text)

    def feed(self, chunk: str) -> str:
        if not self.active or not chunk:
            return ""
        out: List[str] = []
        for ch in chunk:
            if self._state == "string":
                piece = self._string_char(ch)
                if piece:
                    out.append(piece)
                if self._state in ("done", "abandoned"):
                    break
            else:
                self._prefix_char(ch)
                if self._state == "abandoned":
                    break
        released = "".join(out)
        if released:
            self._text.append(released)
        return released

    # ── before the string ────────────────────────────────────────────────

    def _prefix_char(self, ch: str) -> None:
        if self._state == "start":
            if ch.isspace():
                return
            if ch == "{":
                self._state = "key"
                return
            self._state = "abandoned"
            return
        if self._state == "key":
            if self._key_progress == 0 and ch.isspace():
                return
            if ch == _KEY[self._key_progress]:
                self._key_progress += 1
                if self._key_progress == len(_KEY):
                    self._state = "colon"
                return
            self._state = "abandoned"
            return
        if self._state == "colon":
            if ch.isspace():
                return
            if ch == ":":
                self._state = "quote"
                return
            self._state = "abandoned"
            return
        if self._state == "quote":
            if ch.isspace():
                return
            if ch == '"':
                self._state = "string"
                return
            self._state = "abandoned"
            return

    # ── inside the string ────────────────────────────────────────────────

    def _string_char(self, ch: str) -> str:
        if self._in_escape:
            return self._escape_char(ch)
        if ch == "\\":
            self._in_escape = True
            self._pending_escape = ""
            return ""
        if ch == '"':
            self._state = "done"
            return self._flush_surrogate()
        return self._flush_surrogate() + ch

    def _escape_char(self, ch: str) -> str:
        if not self._pending_escape:
            if ch == "u":
                self._pending_escape = "u"
                return ""
            self._in_escape = False
            if ch in _SIMPLE_ESCAPES:
                return self._flush_surrogate() + _SIMPLE_ESCAPES[ch]
            # Not a JSON escape. The output is not the JSON the schema promised;
            # keep the characters rather than guess.
            return self._flush_surrogate() + "\\" + ch
        # \uXXXX: collect four hex digits, possibly across chunks.
        self._pending_escape += ch
        if len(self._pending_escape) < 5:
            return ""
        self._in_escape = False
        hex_digits = self._pending_escape[1:]
        self._pending_escape = ""
        try:
            code = int(hex_digits, 16)
        except ValueError:
            return self._flush_surrogate() + "\\u" + hex_digits
        if 0xD800 <= code <= 0xDBFF:
            # High surrogate: hold it until its low half arrives.
            flushed = self._flush_surrogate()
            self._high_surrogate = code
            return flushed
        if 0xDC00 <= code <= 0xDFFF:
            if self._high_surrogate is not None:
                combined = 0x10000 + ((self._high_surrogate - 0xD800) << 10) + (code - 0xDC00)
                self._high_surrogate = None
                return chr(combined)
            # A lone low surrogate is not a character; U+FFFD keeps the text
            # encodable where a surrogate code point would not be.
            return "�"
        return self._flush_surrogate() + chr(code)

    def _flush_surrogate(self) -> str:
        if self._high_surrogate is None:
            return ""
        self._high_surrogate = None
        return "�"


# ---------------------------------------------------------------------------
# Sentence gate
# ---------------------------------------------------------------------------


Checker = Callable[[str], OutputValidationResult]


@dataclass
class SentenceGate:
    """Release the line one checked sentence at a time.

    ``feed(text, done)`` takes the whole decoded utterance so far and returns the
    newly releasable slices, in order. Every slice is an exact substring of the
    line, so concatenating every released slice reproduces the committed line
    byte for byte. A slice is released only when the cumulative text up to and
    including it passes ``checker``; the first failure sets ``blocked`` with the
    offending validation result and nothing further is ever released.

    With ``previous_lines`` (the NPC's last lines, newest first), the first
    slice must also not repeat them; if it does, ``repeated`` is set and nothing
    is ever released, so the whole line is still the engine's to replace.
    Unlike ``blocked``, ``repeated`` does not ask for generation to stop: the
    line is retried from the complete output. Later slices are checked for
    safety only (see ``_repeats``).
    """

    hidden_agenda: Optional[List[str]] = None
    checker: Optional[Checker] = None
    released_upto: int = 0
    blocked: Optional[OutputValidationResult] = None
    released: List[str] = field(default_factory=list)
    previous_lines: Sequence[str] = ()
    repeated: Optional[RepetitionReport] = None

    def _check(self, text: str) -> OutputValidationResult:
        if self.checker is not None:
            return self.checker(text)
        return validate_npc_output(utterance=text, hidden_agenda=self.hidden_agenda)

    def _repeats(self, text: str, complete: bool) -> RepetitionReport:
        """Whether the first release, ``text``, would make the line a repeat.

        Only the first release is judged. Held back, it leaves nothing on
        screen, and the repetition guard can still replace the whole line with
        its retry. Any later sentence is the rest of a line the player is
        already reading: holding it back cannot undo what is out, it only cuts
        the line short. On the starter model that cut "An N+1 query behind
        holiday timeouts, fixed overnight." off Dana's next question, which
        shared a stock 7-word run with her opening, and left Ray's answer to a
        walk-away ultimatum at "I understand your offer." A later repeat is let
        through and noted after the line (``repetition_retry_skipped``).

        The first release passes if, taken as the whole line, it shares no
        6-word run with an earlier line and does not end with the previous
        line's closing question. Similarity measures the whole line, so it is
        judged only when the first release is the ``complete`` line.

        The guard must never cost the player a turn: should the check itself
        fail, the sentence is not held back for it.
        """
        if not self.previous_lines or self.released:
            return RepetitionReport()
        try:
            return check_repetition(text, self.previous_lines, similarity=complete)
        except Exception:  # noqa: BLE001 — a broken guard must not break the stream
            logger.exception("Repetition check failed on a streamed sentence; releasing it")
            return RepetitionReport()

    @property
    def released_text(self) -> str:
        return "".join(self.released)

    def feed(self, text: str, done: bool) -> List[str]:
        if self.blocked is not None or self.repeated is not None:
            return []
        ends = sentence_boundaries(text)
        if done:
            if not ends or ends[-1] != len(text):
                ends.append(len(text))
        else:
            # The last boundary may sit at the very end of what has arrived so
            # far; that "sentence" could still be growing (a '.' followed by
            # more of the same sentence after a chunk boundary is rare but a
            # quote or bracket can follow), so hold it until more text or the
            # closing quote arrives.
            ends = [e for e in ends if e < len(text)]
        out: List[str] = []
        for end in ends:
            if end <= self.released_upto:
                continue
            candidate = text[:end]
            result = self._check(candidate)
            if not result.is_safe:
                self.blocked = result
                break
            repeat = self._repeats(candidate, complete=done and end == len(text))
            if repeat.flagged:
                self.repeated = repeat
                break
            slice_ = text[self.released_upto:end]
            self.released_upto = end
            self.released.append(slice_)
            out.append(slice_)
        return out


def _passes(_text: str) -> OutputValidationResult:
    return OutputValidationResult()


def first_sentence_repeats(line: str, previous_lines: Sequence[str]) -> RepetitionReport:
    """Why the gate would hold back the complete ``line``'s first sentence, if it would.

    The repetition guard judges the retry of a line the gate held by this as
    well as by the whole line (issue #580), so the retry is kept only if it
    repeats less in the terms that held the first reply: a retry that opens
    with the previous line's closing question again repeats as much. Only the
    repetition test runs; the output check is the guard's, on the whole line.
    """
    gate = SentenceGate(previous_lines=previous_lines, checker=_passes)
    gate.feed(line, True)
    return gate.repeated or RepetitionReport()
