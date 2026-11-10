# SPDX-License-Identifier: Apache-2.0
"""Does an NPC line repeat the NPC's own recent lines? (issue #580, P2)

On the starter model the NPC ended two turns running with the same question,
word for word, and said "We do have new tires on hand" three turns running.
The engine's repetition guard (``convsim_core.services.turn_pipeline``) asks
this module whether a reply repeats one of the NPC's last two lines, and the
D-05 pre-check (``scripts/demo_gate_checks.py``, check (a)) uses the same
word functions, so the engine and the pre-check count a repeat the same way.

A line repeats an earlier one when it:

  * shares a run of ``REPEAT_RUN_WORDS`` (6) or more consecutive words with it;
  * ends with the same question, of ``SAME_QUESTION_MIN_WORDS`` (4) or more
    words, as the previous line (a short tag such as "Okay?" said twice is a
    tic, not a loop);
  * or has a word-trigram Jaccard similarity above ``SIMILARITY_THRESHOLD``
    (0.5) with it, when both lines have ``SIMILARITY_MIN_WORDS`` (6) or more
    words. It catches a near-copy built from runs too short for the first
    test, such as the same short sentences in another order ("The brakes are
    fresh too. We have new tires." after "We have new tires. The brakes are
    fresh too.", 0.56).

Words are compared case- and punctuation-insensitively: text is NFKC
normalised and case-folded, apostrophes are dropped (so "What's" and
"What’s" are one word), and every other non-word character separates words.

A repeat the player asked for is not a loop. In spanish_coffee asking Rosa to
say it again, more slowly, is a repair strategy the rubric rewards, and the
pack's smoke and golden tests play it. ``asks_for_repeat`` tells such a
player line apart, and the guard and check (a) both leave the NPC's answer to
it alone.

Standard library only, like the rest of this package: the D-05 replay script
imports it and runs with the standard library and PyYAML.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Tuple

#: A shared run of this many consecutive words is a repeat.
REPEAT_RUN_WORDS = 6
#: A shared closing question counts from this many words.
SAME_QUESTION_MIN_WORDS = 4
#: Word-trigram Jaccard similarity above this is a repeat.
SIMILARITY_THRESHOLD = 0.5
#: Both lines need this many words (four trigrams) before their similarity
#: counts. On shorter lines one added word swings the score past the
#: threshold: "That's a fair point." after "That's a fair point, honestly."
#: scores 0.67, "Son cuatro euros con cincuenta." after the same price "por
#: favor" 0.60, and each hit costs the player a whole extra generation. From
#: six words a score above the threshold needs at least three shared trigrams.
SIMILARITY_MIN_WORDS = 6
#: How many of the NPC's most recent lines a reply is compared with.
GUARD_WINDOW = 2

RUN = "run"
QUESTION = "question"
SIMILAR = "similar"

_APOSTROPHES = re.compile(r"['‘’ʼ`´]")
_WORD = re.compile(r"\w+")


def words(text: str) -> List[str]:
    """Case- and punctuation-insensitive words of ``text``."""
    folded = unicodedata.normalize("NFKC", text or "").casefold()
    return _WORD.findall(_APOSTROPHES.sub("", folded))


def shared_runs(a: Sequence[str], b: Sequence[str], min_len: int) -> List[List[str]]:
    """Runs of ``min_len``+ consecutive words that appear in both ``a`` and ``b``.

    Each run is maximal (it cannot be extended on either side), and runs do not
    overlap in ``a``: the longest are kept first. Returned in ``a``'s order.
    """
    n, m = len(a), len(b)
    # common[i][j]: length of the common run ending at a[i-1] and b[j-1].
    common = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                common[i][j] = common[i - 1][j - 1] + 1
    candidates: List[Tuple[int, int]] = []  # (length, start in a)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            length = common[i][j]
            if length < min_len:
                continue
            if i < n and j < m and a[i] == b[j]:
                continue  # extends further; the longer run is collected later
            candidates.append((length, i - length))
    taken: List[Tuple[int, int]] = []  # (start, end) in a
    for length, start in sorted(candidates, key=lambda c: (-c[0], c[1])):
        end = start + length
        if any(start < t_end and t_start < end for t_start, t_end in taken):
            continue
        taken.append((start, end))
    return [list(a[s:e]) for s, e in sorted(taken)]


_CLOSERS = "\"'”’»)]*_ \t\r\n"
_QUESTION_MARKS = ("?", "？")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…！？。])\s+")


def ending_question(text: str) -> Optional[Tuple[str, ...]]:
    """The words of the question ``text`` ends with, or None if it ends otherwise.

    The question is the last sentence, where sentences break at whitespace after
    ``.``, ``!``, ``?`` or an ellipsis (so "8.50" stays one sentence). Spanish
    "¿...?" questions work the same way: the opening mark is punctuation.
    """
    s = (text or "").rstrip(_CLOSERS)
    if not s.endswith(_QUESTION_MARKS):
        return None
    last = _SENTENCE_BREAK.split(s)[-1]
    w = tuple(words(last))
    return w or None


def trigrams(ws: Sequence[str]) -> Set[Tuple[str, str, str]]:
    """The set of consecutive word triples in ``ws``."""
    return {(ws[i], ws[i + 1], ws[i + 2]) for i in range(len(ws) - 2)}


def trigram_similarity(a: Sequence[str], b: Sequence[str]) -> float:
    """Jaccard similarity of the word trigrams of ``a`` and ``b`` (0.0 to 1.0).

    0.0 when either has fewer than three words: there is nothing to compare.
    """
    ta, tb = trigrams(a), trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ---------------------------------------------------------------------------
# The guard's verdict
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepetitionMatch:
    """One way a line repeats one of the NPC's earlier lines.

    ``against`` counts back from the reply: 0 is the NPC's previous line, 1 the
    one before it. ``words`` are the repeated words (the run, or the closing
    question); a ``similar`` match has none and carries its ``similarity``.
    """

    kind: str
    against: int
    words: Tuple[str, ...] = ()
    similarity: float = 0.0

    def describe(self) -> str:
        """What repeated, without quoting it (the words are in ``words``)."""
        which = "the previous NPC line" if self.against == 0 else "the NPC line before the previous one"
        if self.kind == RUN:
            return f"shares a {len(self.words)}-word run with {which}"
        if self.kind == QUESTION:
            return f"ends with the same {len(self.words)}-word question as {which}"
        return f"has trigram similarity {self.similarity:.2f} with {which}"


@dataclass(frozen=True)
class RepetitionReport:
    """How much a line repeats the NPC's recent lines. Empty: not a repeat."""

    matches: Tuple[RepetitionMatch, ...] = ()

    @property
    def flagged(self) -> bool:
        return bool(self.matches)

    @property
    def longest_run(self) -> int:
        return max((len(m.words) for m in self.matches if m.kind == RUN), default=0)

    @property
    def similarity(self) -> float:
        return max((m.similarity for m in self.matches if m.kind == SIMILAR), default=0.0)

    @property
    def against(self) -> Tuple[int, ...]:
        """Which earlier lines the reply repeats (0 = the previous), oldest first."""
        return tuple(sorted({m.against for m in self.matches}, reverse=True))

    def severity(self) -> Tuple[int, int, float]:
        """Orders reports from least to most repetitive.

        More matches is worse (a reply that repeats both earlier lines, or one
        line in two ways, repeats more), then a longer shared run, then a
        higher similarity.
        """
        return (len(self.matches), self.longest_run, round(self.similarity, 4))

    def describe(self) -> str:
        return "; ".join(m.describe() for m in self.matches)


NOT_REPEATED = RepetitionReport()


def check_repetition(
    line: str,
    previous_lines: Sequence[str],
    *,
    runs: bool = True,
    question: bool = True,
    similarity: bool = True,
) -> RepetitionReport:
    """Whether ``line`` repeats any of ``previous_lines``, newest first.

    Only the first ``GUARD_WINDOW`` previous lines are read. The closing
    question is compared with the previous line only. ``runs``, ``question``
    and ``similarity`` switch the three tests: the streaming gate checks a line
    it has only part of, where only a shared run is already certain (see
    ``SentenceGate`` in convsim-core).
    """
    line_words = words(line)
    if not line_words:
        return NOT_REPEATED
    matches: List[RepetitionMatch] = []
    closing = ending_question(line) if question else None
    for index, previous in enumerate(list(previous_lines)[:GUARD_WINDOW]):
        previous_words = words(previous)
        if not previous_words:
            continue
        if runs:
            for run in shared_runs(line_words, previous_words, REPEAT_RUN_WORDS):
                matches.append(RepetitionMatch(kind=RUN, against=index, words=tuple(run)))
        if (
            index == 0
            and closing is not None
            and len(closing) >= SAME_QUESTION_MIN_WORDS
            and closing == ending_question(previous)
        ):
            matches.append(RepetitionMatch(kind=QUESTION, against=index, words=closing))
        if similarity and min(len(line_words), len(previous_words)) >= SIMILARITY_MIN_WORDS:
            score = trigram_similarity(line_words, previous_words)
            if score > SIMILARITY_THRESHOLD:
                matches.append(RepetitionMatch(kind=SIMILAR, against=index, similarity=score))
    return RepetitionReport(matches=tuple(matches))


# ---------------------------------------------------------------------------
# A player who asks for the line again
# ---------------------------------------------------------------------------

#: Ways a player asks the NPC to say it again, or more slowly, in the
#: languages the official packs play (en, es, fr, ja). Word phrases match whole
#: words, compared without case, punctuation or accents, so "mas despacio"
#: typed without its accent counts.
REPEAT_REQUEST_WORDS: Tuple[Tuple[str, ...], ...] = tuple(
    tuple(phrase.split())
    for phrase in (
        # English
        "repeat", "say that again", "say it again", "come again", "pardon",
        "one more time", "more slowly", "slower",
        # Spanish
        "repetir", "repite", "repita", "repitelo", "repitalo", "repetirlo",
        "repitemelo", "repitamelo", "repetirmelo", "otra vez", "mas despacio",
        "mas lento", "mas lentamente",
        # French
        "repeter", "repetez", "repete", "encore une fois", "plus lentement",
    )
)
#: Phrases of languages written without spaces, matched as text.
REPEAT_REQUEST_TEXT: Tuple[str, ...] = ("もう一度", "もう一回", "ゆっくり")
#: Words after "repeat" that make it a complaint about the NPC, not a request
#: ("don't repeat yourself"). "Repeating" is not a request word at all.
_REPEAT_NOT_A_REQUEST = frozenset({"yourself", "yourselves"})


def _bare_words(text: str) -> List[str]:
    """``words`` with accents removed as well, for matching typed phrases."""
    decomposed = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text or ""))
    bare = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WORD.findall(_APOSTROPHES.sub("", bare.casefold()))


def asks_for_repeat(player_line: str) -> bool:
    """Whether the player's line asks the NPC to say it again, or more slowly.

    The NPC's answer to such a line is meant to repeat what it said, so the
    repetition guard does not retry it and check (a) does not fail it.
    """
    text = unicodedata.normalize("NFKC", player_line or "").casefold()
    if any(phrase in text for phrase in REPEAT_REQUEST_TEXT):
        return True
    ws = _bare_words(text)
    for phrase in REPEAT_REQUEST_WORDS:
        n = len(phrase)
        for i in range(len(ws) - n + 1):
            if tuple(ws[i:i + n]) != phrase:
                continue
            if phrase == ("repeat",) and i + 1 < len(ws) and ws[i + 1] in _REPEAT_NOT_A_REQUEST:
                continue
            return True
    return False


def less_repetitive(candidate: RepetitionReport, incumbent: RepetitionReport) -> bool:
    """True when ``candidate`` repeats strictly less than ``incumbent``.

    A tie keeps the incumbent: the retry has to improve on the first reply.
    """
    return candidate.severity() < incumbent.severity()
