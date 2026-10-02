# SPDX-License-Identifier: Apache-2.0
"""Stage 2 — novelty.

``s_max`` is the maximum similarity between this volley and

  (a) every prior volley this session — the player's *and* the opponent's, so
      parroting the opponent counts as redundancy, and
  (b) the shipped cliché corpus of stock insults.

Freshness is then ``F = clamp(1 - s_max^2, 0.1, 1.0)``. Squaring forgives family
resemblance and hammers near-duplicates: two volleys that merely share a subject
(s_max 0.4) keep 84% of their value, while a rephrasing (s_max 0.9) keeps 19%.

Local-first, in two tiers:

* With an embedding model available (a small GGUF served by the existing
  llama.cpp runtime), similarity is cosine similarity over embeddings.
* Without one — the default on a fresh install — the fallback is lemma Jaccard
  plus character-trigram cosine. Deterministic, offline, no download, and good
  enough to catch the repetition the stage exists to punish. The chosen method
  is reported on the scorecard so a player is never confused about why two runs
  scored differently.

Theme decay is also here: the nth volley leaning primarily on an already-used
theme has its topicality bonus scaled by ``decay^(n-1)``, which is what makes
the third hygiene joke visibly near-worthless.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

from convsim_core.flyting.corpus import tokenize

logger = logging.getLogger(__name__)

FRESHNESS_FLOOR = 0.1
FRESHNESS_CEILING = 1.0

_TRIGRAM_WEIGHT = 0.5
_JACCARD_WEIGHT = 0.5

_SUFFIXES: Tuple[str, ...] = ("ingly", "edly", "ing", "ies", "ied", "es", "ed", "er", "est", "ly", "s")


class EmbeddingProvider(Protocol):
    """Anything that can turn texts into vectors, locally."""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        ...


def _lemma(token: str) -> str:
    """Crude suffix stripping — enough to make "polishing" and "polished" agree."""
    for suffix in _SUFFIXES:
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _lemmas(text: str) -> frozenset[str]:
    return frozenset(_lemma(t) for t in tokenize(text))


def _trigrams(text: str) -> Dict[str, int]:
    flat = re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", text.lower())).strip()
    counts: Dict[str, int] = {}
    for i in range(len(flat) - 2):
        gram = flat[i : i + 3]
        counts[gram] = counts.get(gram, 0) + 1
    return counts


def _cosine(a: Dict[str, int], b: Dict[str, int]) -> float:
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in shared)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def lexical_similarity(a: str, b: str) -> float:
    """Offline similarity in [0, 1]: lemma Jaccard plus character-trigram cosine.

    Also used by the Plagiarized Zinger gate, so that "near-verbatim" means the
    same thing to the gate and to the freshness multiplier.
    """
    jaccard = _jaccard(_lemmas(a), _lemmas(b))
    trigram = _cosine(_trigrams(a), _trigrams(b))
    return _JACCARD_WEIGHT * jaccard + _TRIGRAM_WEIGHT * trigram


def vector_cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def freshness_from_similarity(s_max: float) -> float:
    """``clamp(1 - s_max^2, 0.1, 1.0)``.

    The similarity is itself clamped into [0, 1] first: a cosine from an
    embedding model can land slightly outside that range, and squaring a
    negative number would read as *more* similar rather than less.
    """
    similarity = max(0.0, min(1.0, s_max))
    value = 1.0 - (similarity * similarity)
    return max(FRESHNESS_FLOOR, min(FRESHNESS_CEILING, value))


@dataclass
class FreshnessResult:
    """Stage 2 output."""

    value: float = 1.0
    s_max: float = 0.0
    method: str = "lexical"          # lexical | embedding
    nearest_source: str = "none"     # none | session | cliche
    nearest_label: Optional[str] = None
    theme_uses: Dict[str, int] = field(default_factory=dict)
    theme_decay: float = 1.0

    def to_dict(self) -> dict:
        """Serialise to the ``freshness`` object of volley-score.schema.json."""
        return {
            "value": round(self.value, 4),
            "s_max": round(self.s_max, 4),
            "method": self.method,
            "nearest_source": self.nearest_source,
            "nearest_label": self.nearest_label,
            "theme_uses": dict(self.theme_uses),
            "theme_decay": round(self.theme_decay, 4),
        }


def compute_freshness(
    text: str,
    *,
    prior_volleys: Sequence[str] = (),
    cliches: Sequence[str] = (),
    provider: Optional[EmbeddingProvider] = None,
) -> FreshnessResult:
    """Compare a volley against the session so far and the cliché corpus."""
    candidates: List[Tuple[str, str]] = [("session", prior) for prior in prior_volleys]
    candidates += [("cliche", line) for line in cliches]
    if not candidates:
        return FreshnessResult(value=FRESHNESS_CEILING, s_max=0.0, method="lexical")

    method = "lexical"
    scores: List[float] = []
    if provider is not None:
        try:
            vectors = provider.embed([text] + [c[1] for c in candidates])
            head, rest = vectors[0], vectors[1:]
            scores = [vector_cosine(head, vector) for vector in rest]
            method = "embedding"
        except Exception as exc:  # noqa: BLE001 — a missing model must not end a volley
            logger.warning(
                "Embedding provider failed (%s); falling back to lexical novelty", exc
            )
            scores = []

    if not scores:
        scores = [lexical_similarity(text, candidate) for _, candidate in candidates]

    best_index = max(range(len(scores)), key=scores.__getitem__)
    s_max = max(0.0, min(1.0, scores[best_index]))
    source, label = candidates[best_index]

    return FreshnessResult(
        value=freshness_from_similarity(s_max),
        s_max=s_max,
        method=method,
        nearest_source=source if s_max > 0 else "none",
        nearest_label=label[:120] if s_max > 0 else None,
    )


def theme_decay_factor(
    themes: Sequence[str],
    theme_uses: Dict[str, int],
    decay: float,
) -> float:
    """``decay^(n-1)`` for the volley's primary theme, where n counts this use.

    The *primary* theme is the first the judge tagged. A volley that opens a new
    line of attack is undecayed even if it brushes a theme already used, which
    is the behaviour the rule is for: it punishes returning to the same well,
    not acknowledging that the well exists.
    """
    if not themes:
        return 1.0
    primary = themes[0]
    prior_uses = max(0, theme_uses.get(primary, 0))
    return max(0.0, min(1.0, decay ** prior_uses))
