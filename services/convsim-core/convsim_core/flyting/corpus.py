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


@dataclass(frozen=True)
class QuoteSignature:
    """A famous taunt identified by a keyword conjunction rather than stored text."""

    label: str
    keywords: Tuple[str, ...]

    def matches(self, words: frozenset[str]) -> bool:
        return all(keyword in words for keyword in self.keywords)


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
