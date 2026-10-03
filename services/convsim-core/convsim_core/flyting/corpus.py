# SPDX-License-Identifier: Apache-2.0
"""Bundled corpora: word frequency ranks, cliché insults, pop-culture signatures.

All three ship inside the package (``flyting/data``) and are loaded once,
lazily, so importing the flyting engine costs nothing until a volley is scored.
Nothing here touches the network: the corpora are the whole reason the novelty
and plagiarism stages work on an offline machine with no embedding model
installed.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Dict, Tuple

_DATA = files("convsim_core") / "flyting" / "data"

_WORD_RE = re.compile(r"[a-z']+")


def _read_lines(name: str) -> Tuple[str, ...]:
    text = (_DATA / name).read_text(encoding="utf-8")
    return tuple(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


@lru_cache(maxsize=1)
def word_ranks() -> Dict[str, int]:
    """word → 1-based frequency rank, first occurrence winning."""
    ranks: Dict[str, int] = {}
    for index, word in enumerate(_read_lines("word_frequency_ranks.txt"), start=1):
        ranks.setdefault(word.lower(), index)
    return ranks


@lru_cache(maxsize=1)
def known_word_count() -> int:
    return len(word_ranks())


def zipf_for_rank(rank: int) -> float:
    """Zipf frequency from a 1-based rank: ``8 - log10(rank)``.

    Reproduces the familiar scale closely enough to place a word in a band:
    rank 1 ≈ 8.0, rank 100 ≈ 6.0, rank 1000 ≈ 5.0, rank 10000 ≈ 4.0.
    """
    return 8.0 - math.log10(max(1, rank))


@lru_cache(maxsize=1)
def cliche_insults() -> Tuple[str, ...]:
    """Stock forms and public-domain greatest hits, normalised for comparison."""
    return _read_lines("cliche_insults.txt")


# How much room a signature's keywords get beyond their own count. The taunts
# these stand for are short phrases — "your mother was a hamster", "you fight
# like a dairy farmer", "your mother is so fat" — so two tokens of slack absorbs
# the articles, the auxiliary and the vocative a player adds ("your mother was a
# hamster, sir") without reaching across a clause. It is the clause boundary
# that matters: three tokens of slack still let ``mother, so, fat`` reach from a
# subordinate clause into the main one, which is where the collisions were.
#
# Order is deliberately not required: the keyword lists are written as the words
# a quotation is made of rather than as its word order, and the same joke is
# told with the clauses either way round.
KEYWORD_WINDOW_SLACK = 2


def _shortest_window(positions: Tuple[Tuple[int, ...], ...]) -> int:
    """Width of the smallest span of tokens holding one of every keyword.

    ``positions[i]`` is where keyword *i* occurs, ascending. Returns a width in
    tokens (1 for a single position), or 0 when some keyword never occurs.
    """
    if any(not group for group in positions):
        return 0
    merged = sorted(
        (index, which) for which, group in enumerate(positions) for index in group
    )
    needed = len(positions)
    seen: Dict[int, int] = {}
    best = 0
    left = 0
    for right, (_, which) in enumerate(merged):
        seen[which] = seen.get(which, 0) + 1
        while len(seen) == needed:
            width = merged[right][0] - merged[left][0] + 1
            if best == 0 or width < best:
                best = width
            dropped = merged[left][1]
            seen[dropped] -= 1
            if seen[dropped] == 0:
                del seen[dropped]
            left += 1
    return best


@dataclass(frozen=True)
class QuoteSignature:
    """A famous taunt identified by a keyword phrase rather than stored text."""

    label: str
    keywords: Tuple[str, ...]

    @property
    def window(self) -> int:
        """How many tokens the keywords may span and still be the phrase."""
        return len(self.keywords) + KEYWORD_WINDOW_SLACK

    def matches(self, tokens: Tuple[str, ...]) -> bool:
        """Whether the keywords occur together, inside one short span.

        Proximity, not mere presence. Testing presence anywhere in the volley —
        as this used to — made a signature of ordinary words fire on original
        work: ``mother, so, fat`` caught "Your mother would be so ashamed of
        that fat purse you call a conscience", ``fighting, left, hand`` caught
        "I am fighting a man who cannot tell his left hand from his ledger", and
        both lines were capped at ten points and told they were borrowed.
        Lineage and duelling are the launch pack's own registers, so those
        collisions are the common case rather than the contrived one, and the
        file this reads from promises the opposite: specific enough not to fire
        on original work.
        """
        positions = tuple(
            tuple(i for i, token in enumerate(tokens) if token == keyword)
            for keyword in self.keywords
        )
        width = _shortest_window(positions)
        return 0 < width <= self.window


@lru_cache(maxsize=1)
def quote_signatures() -> Tuple[QuoteSignature, ...]:
    """Pop-culture taunt signatures.

    Stored as keyword conjunctions so that no copyrighted dialogue ships in the
    application: enough to catch a quotation or light paraphrase of a line the
    whole room knows, specific enough not to fire on original work.
    """
    out = []
    for line in _read_lines("pop_culture_signatures.txt"):
        if "|" not in line:
            continue
        label, _, keywords = line.partition("|")
        parsed = tuple(
            k.strip().lower() for k in keywords.split(",") if k.strip()
        )
        if label.strip() and parsed:
            out.append(QuoteSignature(label=label.strip(), keywords=parsed))
    return tuple(out)


def tokenize(text: str) -> Tuple[str, ...]:
    """Lowercase alphabetic tokens, the shared tokenisation for every corpus check."""
    return tuple(_WORD_RE.findall(text.lower().replace("’", "'")))
