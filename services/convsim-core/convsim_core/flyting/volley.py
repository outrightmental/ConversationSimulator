# SPDX-License-Identifier: Apache-2.0
"""The volley — the unit of scoring.

One volley is the full text submitted in a single player turn, after
normalization. A multi-sentence submission is still **one** volley: compound
construction can earn a bonus, but three insults crammed into one turn are not
three volleys. Every score, multiplier, bonus, and foul attaches to exactly one
volley, and a session result is a pure aggregate over volleys.

Bounds:
  * under 3 words  → a *dud*: scores 0, no foul
  * soft cap 60 words → beyond it, run-on decay of x0.9 per additional 10 words,
    and the topicality bonus stops accruing (padding is worthless by design)
  * hard cap 500 characters, refused at the input
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Tuple

MAX_VOLLEY_CHARS = 500
MIN_VOLLEY_WORDS = 3
SOFT_WORD_CAP = 60
RUN_ON_DECAY_PER_10_WORDS = 0.9

_WHITESPACE_RE = re.compile(r"\s+")
# Runs of the same punctuation mark collapse to one, so "you fool!!!!!" and
# "you fool!" are the same volley for novelty, plagiarism, and evidence checks.
_REPEATED_PUNCT_RE = re.compile(r"([!?.,;:\-—–_*~\"'])\1+")
_WORD_RE = re.compile(r"[\w'’-]+", re.UNICODE)
# Two different splits, because two different questions are being asked.
#
# Prosodic units (for rhyme and scansion) break wherever a reader would draw
# breath, which in this register includes the em dash and the colon.
_PROSODIC_SPLIT_RE = re.compile(r"[.!?;:]+|\s[—–]\s")
# Independent constructions (for the compound bonus) break only at sentence
# boundaries and semicolons. An em dash usually *extends* a figure rather than
# starting a new one — "both are plate, not sterling" is the same construction
# as the brass it follows — and counting those as two would hand the compound
# bonus to every volley with a dash in it.
_SENTENCE_SPLIT_RE = re.compile(r"[.!?;]+")


class VolleyInputError(ValueError):
    """Raised when submitted text cannot be a volley at all (hard cap)."""


def normalize_volley_text(raw: str) -> str:
    """Trim, NFC-normalise, collapse whitespace, and collapse repeated punctuation."""
    text = unicodedata.normalize("NFC", raw or "")
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return _REPEATED_PUNCT_RE.sub(r"\1", text)


def run_on_decay(word_count: int) -> float:
    """x0.9 per additional 10 words (or part thereof) past the soft cap."""
    if word_count <= SOFT_WORD_CAP:
        return 1.0
    steps = math.ceil((word_count - SOFT_WORD_CAP) / 10)
    return RUN_ON_DECAY_PER_10_WORDS ** steps


@dataclass
class NormalizedVolley:
    """A normalized volley with its bounds already resolved."""

    text: str
    words: Tuple[str, ...]
    clauses: Tuple[str, ...]       # prosodic units, for rhyme and scansion
    sentences: Tuple[str, ...] = ()  # sentence-level units, for the compound bonus
    flags: List[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.words)

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def is_too_short(self) -> bool:
        return self.word_count < MIN_VOLLEY_WORDS

    @property
    def is_run_on(self) -> bool:
        return self.word_count > SOFT_WORD_CAP

    @property
    def decay(self) -> float:
        return run_on_decay(self.word_count)

    @property
    def independent_clauses(self) -> Tuple[str, ...]:
        """Clauses substantial enough to count as a construction of their own.

        Three words is the floor — "you are vain" is a construction. The
        compound bonus additionally requires devices or hooks, so this threshold
        does not have to carry the whole judgement of "two things that land".
        """
        return tuple(s for s in self.sentences if len(_WORD_RE.findall(s)) >= 3)


def analyze_volley(raw: str) -> NormalizedVolley:
    """Normalise submitted text and resolve its bounds.

    Raises VolleyInputError when the text exceeds the hard character cap; the
    caller surfaces that as a 400 rather than scoring it, because the cap is an
    input constraint, not a scoring outcome.
    """
    text = normalize_volley_text(raw)
    if len(text) > MAX_VOLLEY_CHARS:
        raise VolleyInputError(
            f"A volley is {len(text)} characters; the maximum is {MAX_VOLLEY_CHARS}."
        )

    words = tuple(_WORD_RE.findall(text))
    clauses = tuple(
        part.strip() for part in _PROSODIC_SPLIT_RE.split(text) if part and part.strip()
    )
    sentences = tuple(
        part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part and part.strip()
    )

    volley = NormalizedVolley(
        text=text, words=words, clauses=clauses, sentences=sentences
    )
    if volley.is_too_short:
        volley.flags.append("too_short")
    if volley.is_run_on:
        volley.flags.append("run_on")
    return volley
