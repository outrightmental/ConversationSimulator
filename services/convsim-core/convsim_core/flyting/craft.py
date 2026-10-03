# SPDX-License-Identifier: Apache-2.0
"""Stage 1 — craft metrics. Deterministic, no model call, no network.

Four measurements:

* **Lexical rarity** — mean Zipf frequency of content words, rewarded in a band
  rather than monotonically, so thesaurus-vomit cannot dominate: the reward
  peaks for genuinely uncommon real words and falls away both for a volley made
  entirely of function words and for one made of words nobody has ever used.
* **Internal variety** — type-token ratio within the volley, which is what
  catches "stupid stupid stupid".
* **Sound play** — alliteration and assonance runs, plus rhyme and rough
  scansion for verse scenarios.
* **Aim check** — second-person anchoring: is this actually pointed at the
  target, or is it free-floating abuse?

On phonetics: proper grapheme-to-phoneme (espeak-ng lives in the TTS orbit)
would measure sound play better than orthography does, and ``_onset`` /
``_rime`` are the seam where it would go. They are deliberately not that today,
because the alternative is a hard dependency on a native binary for a metric
that contributes a capped fraction of one stage. The normalisations below cover
the English spellings that would otherwise produce obviously wrong answers
(knight/night, phase/fade, write/right).
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from convsim_core.flyting.corpus import word_ranks, zipf_for_rank
from convsim_core.flyting.volley import NormalizedVolley

# A word absent from the bundled frequency list is treated as uncommon but real.
# The Stage 0 gibberish gate is what catches text that is not words at all, so
# by the time craft metrics run, an unknown word is far more likely to be
# "blackguard" than "asdfgh".
UNKNOWN_WORD_ZIPF = 3.0

# Function words excluded from the content-word set. Deliberately explicit
# rather than "the top N ranks": "fat", "fool" and "dog" are all high-frequency
# words that are very much content in this register.
_FUNCTION_WORDS = frozenset("""
a an the and or but nor so yet for if then than that this these those
i me my mine myself you your yours yourself yourselves he him his himself
she her hers herself it its itself we us our ours ourselves they them their
theirs themselves who whom whose which what when where why how
am is are was were be been being have has had having do does did doing
will would shall should can could may might must
of in on at to from by with without about into onto over under through
between among against during before after above below up down out off
again further once here there all any both each few more most other some
such no not only own same too very just also as
""".split())

_SECOND_PERSON = frozenset({
    "you", "your", "yours", "yourself", "thou", "thee", "thy", "thine", "ye",
    "you're", "youre", "thou'rt",
})

_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+")
_ALPHA_RE = re.compile(r"[a-z']+")

# Orthographic onset normalisations: the spellings that would otherwise make
# alliteration obviously wrong.
_ONSET_REWRITES: Tuple[Tuple[str, str], ...] = (
    ("ph", "f"), ("wh", "w"), ("kn", "n"), ("gn", "n"), ("pn", "n"),
    ("wr", "r"), ("rh", "r"), ("ps", "s"), ("qu", "kw"), ("x", "z"),
    ("ch", "ch"), ("sh", "sh"), ("th", "th"),
)


def _letters(word: str) -> str:
    return "".join(ch for ch in word.lower() if ch.isalpha())


def _onset(word: str) -> str:
    """The leading consonant sound of a word, approximated from its spelling."""
    letters = _letters(word)
    if not letters:
        return ""
    for prefix, sound in _ONSET_REWRITES:
        if letters.startswith(prefix):
            return sound
    first = letters[0]
    if first in "aeiou":
        return "V"  # all vowel onsets alliterate with one another
    if first == "c":
        return "s" if len(letters) > 1 and letters[1] in "eiy" else "k"
    if first == "g":
        return "j" if len(letters) > 1 and letters[1] in "eiy" else "g"
    return first


def _nucleus(word: str) -> str:
    """The first vowel group of a word — the unit assonance is measured on."""
    letters = _letters(word)
    match = _VOWEL_GROUP_RE.search(letters)
    return match.group(0) if match else ""


# Rime normalisations applied after the final vowel group is isolated, so that
# spellings of the same sound compare equal ("loud"/"cowed", "rough"/"cuff").
_RIME_REWRITES: Tuple[Tuple[str, str], ...] = (
    ("ough", "uf"), ("augh", "af"), ("igh", "i"), ("ow", "ou"),
    ("ph", "f"), ("ck", "k"), ("que", "k"), ("qu", "kw"),
)


def _rime(word: str) -> str:
    """The final vowel group plus whatever follows it, normalised.

    The unit rhyme is measured on. Terminal silent ``e`` is dropped, a past
    participle ``-ed`` is reduced to the consonant it actually sounds as, and
    the handful of English digraphs that spell one sound two ways are rewritten
    — enough that "loud" and "cowed" rhyme without a phoneme table.
    """
    letters = _letters(word)
    if letters.endswith("e") and len(letters) > 3:
        letters = letters[:-1]  # silent terminal e: "brass"/"grace" shouldn't rhyme on it
    elif letters.endswith("ed") and len(letters) > 3 and letters[-3] not in "td":
        letters = letters[:-2] + "d"
    groups = list(_VOWEL_GROUP_RE.finditer(letters))
    rime = letters if not groups else letters[groups[-1].start():]
    for spelling, sound in _RIME_REWRITES:
        rime = rime.replace(spelling, sound)
    # Collapse doubled consonants: "stiff" and "if" end the same way.
    return re.sub(r"([^aeiouy])\1", r"\1", rime)


def _syllables(word: str) -> int:
    letters = _letters(word)
    if not letters:
        return 0
    count = len(_VOWEL_GROUP_RE.findall(letters))
    if letters.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def _is_recognizable(word: str) -> bool:
    """Whether a token could plausibly be an English word.

    Used by the gibberish gate and to keep keyboard mash out of the rarity mean.
    A token is recognizable when it is in the frequency list, or when it has a
    vowel, no run of four identical letters, and no run of five consonants.
    """
    letters = _letters(word)
    if not letters:
        return False
    if letters in word_ranks():
        return True
    if len(letters) > 24:
        return False
    if not _VOWEL_GROUP_RE.search(letters):
        return False
    if re.search(r"(.)\1{3,}", letters):
        return False
    if re.search(r"[^aeiouy]{5,}", letters):
        return False
    return True


def _zipf_for_word(word: str) -> float:
    """Zipf frequency of a single word.

    The one seam to replace if a frequency package is ever adopted.
    """
    letters = _letters(word)
    rank = word_ranks().get(letters)
    if rank is None:
        return UNKNOWN_WORD_ZIPF
    return zipf_for_rank(rank)


def word_rarity_key(word: str) -> Tuple[float, int, str]:
    """Sort key putting the rarest word first: ``(zipf, -length, word)``.

    The bundled frequency list is ~740 words, so every word outside it — which
    is most content words — shares ``UNKNOWN_WORD_ZIPF``. Ranking that bucket
    alphabetically, as this used to, meant "the rarest words that landed" was
    really "the first few uncommon words in alphabetical order": the worked
    example reported *public* and dropped *sterling*.

    Length is the honest tie-break available without frequency data — Zipf's
    law of abbreviation says the words a language uses most are the ones it
    wears shortest — and the alphabet still breaks ties after it, so the result
    is stable. It is a proxy, not a measurement: separating *public* from
    *sterling* needs real frequency data, which is what ``_zipf_for_word``'s
    seam is for.
    """
    letters = _letters(word)
    return (_zipf_for_word(word), -len(letters), word)


def _rarity_reward(mean_zipf: float) -> float:
    """Band reward for lexical rarity.

    Peaks across the uncommon-but-real band (Zipf 3.0-3.9), falls off toward
    everyday vocabulary above it, and falls off again below it so that a volley
    built from words nobody uses — or from words that are not words — cannot buy
    its way to the top of the stage.
    """
    if mean_zipf >= 5.5:
        return 0.15
    if mean_zipf >= 4.5:
        return 0.15 + (5.5 - mean_zipf) * 0.35          # 0.15 → 0.50
    if mean_zipf >= 3.9:
        return 0.50 + (4.5 - mean_zipf) * (0.50 / 0.6)  # 0.50 → 1.00
    if mean_zipf >= 3.0:
        return 1.0
    if mean_zipf >= 2.2:
        return 0.40 + (mean_zipf - 2.2) * (0.60 / 0.8)  # 0.40 → 1.00
    return 0.25


def _variety_reward(type_token_ratio: float, content_words: int) -> float:
    """Reward internal variety, but do not reward a two-word volley for having it."""
    if content_words <= 1:
        return 0.5
    # At or below 0.4 the volley is visibly repeating itself; at 0.85 it is varied.
    if type_token_ratio >= 0.85:
        return 1.0
    if type_token_ratio <= 0.4:
        return 0.0
    return (type_token_ratio - 0.4) / 0.45


def _runs(keys: Sequence[str], minimum: int) -> int:
    """Count maximal runs of >= ``minimum`` consecutive equal, non-empty keys."""
    runs = 0
    current = 1
    for previous, key in zip(keys, keys[1:]):
        if key and key == previous:
            current += 1
            continue
        if current >= minimum:
            runs += 1
        current = 1
    if current >= minimum:
        runs += 1
    return runs


@dataclass
class CraftMetrics:
    """Stage 1 output."""

    word_count: int = 0
    content_word_count: int = 0
    type_token_ratio: float = 0.0
    mean_zipf: float = 0.0
    rarity_reward: float = 0.0
    variety_reward: float = 0.0
    sound_reward: float = 0.0
    alliteration_runs: int = 0
    assonance_runs: int = 0
    rhyme_pairs: int = 0
    scansion_regularity: float = 0.0
    second_person: bool = False
    craft_floor: float = 0.0
    recognizable_ratio: float = 0.0
    unrecognized_words: List[str] = field(default_factory=list)
    rarest_words: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        """Serialise to the ``craft_metrics`` object of volley-score.schema.json."""
        return {
            "word_count": self.word_count,
            "content_word_count": self.content_word_count,
            "type_token_ratio": round(self.type_token_ratio, 4),
            "mean_zipf": round(self.mean_zipf, 3),
            "rarity_reward": round(self.rarity_reward, 4),
            "variety_reward": round(self.variety_reward, 4),
            "sound_reward": round(self.sound_reward, 4),
            "alliteration_runs": self.alliteration_runs,
            "assonance_runs": self.assonance_runs,
            "rhyme_pairs": self.rhyme_pairs,
            "scansion_regularity": round(self.scansion_regularity, 4),
            "second_person": self.second_person,
            "craft_floor": round(self.craft_floor, 3),
            "rarest_words": list(self.rarest_words),
        }


def compute_craft_metrics(
    volley: NormalizedVolley,
    *,
    verse: bool = False,
    min_alliteration_run: int = 3,
) -> CraftMetrics:
    """Measure one volley's craft. Pure, deterministic, identical on every machine."""
    words = [w for w in volley.words if _ALPHA_RE.fullmatch(w.lower())]
    lowered = [w.lower() for w in words]
    content = [w for w in lowered if w not in _FUNCTION_WORDS]

    recognizable = [w for w in lowered if _is_recognizable(w)]
    unrecognized = [w for w in lowered if w not in recognizable]
    recognizable_ratio = (len(recognizable) / len(lowered)) if lowered else 0.0

    # Rarity is measured over recognizable content words only, so keyboard mash
    # neither earns a rarity reward nor drags the mean around.
    rarity_pool = [w for w in content if _is_recognizable(w)]
    zipfs = [_zipf_for_word(w) for w in rarity_pool]
    mean_zipf = statistics.fmean(zipfs) if zipfs else 0.0
    # Unknown words sit in the reward band, which is right for "blackguard" and
    # wrong for "asdfgh". Scaling by the recognizable ratio means a volley can
    # only claim the rarity reward in proportion to how much of it is words —
    # a no-op for ordinary text, and the difference between a rewarded and an
    # unrewarded keyboard mash. (Stage 0 also duds outright gibberish; this
    # keeps the mechanical craft floor honest for the partial cases.)
    rarity = (_rarity_reward(mean_zipf) * recognizable_ratio) if zipfs else 0.0

    ttr = (len(set(content)) / len(content)) if content else 0.0
    variety = _variety_reward(ttr, len(content))

    onsets = [_onset(w) for w in content]
    nuclei = [_nucleus(w) for w in content]
    alliteration = _runs(onsets, min_alliteration_run)
    assonance = _runs(nuclei, max(2, min_alliteration_run))

    clause_finals = [
        tuple(_ALPHA_RE.findall(clause.lower()))
        for clause in volley.clauses
    ]
    finals = [parts[-1] for parts in clause_finals if parts]
    rimes = [_rime(w) for w in finals]
    rhyme_pairs = sum(
        1
        for i, a in enumerate(rimes)
        for b in rimes[i + 1:]
        if a and len(a) >= 2 and a == b
    )

    syllable_counts = [
        sum(_syllables(w) for w in parts) for parts in clause_finals if parts
    ]
    if len(syllable_counts) >= 2 and statistics.fmean(syllable_counts) > 0:
        spread = statistics.pstdev(syllable_counts) / statistics.fmean(syllable_counts)
        scansion = max(0.0, 1.0 - spread)
    else:
        scansion = 0.0

    # Sound reward: alliteration and assonance always count; rhyme and scansion
    # only matter where the scenario asks for verse, and there they matter a lot.
    sound = min(1.0, 0.35 * alliteration + 0.2 * assonance)
    if verse:
        sound = min(1.0, 0.25 * alliteration + 0.15 * assonance
                    + 0.2 * min(2, rhyme_pairs) + 0.3 * scansion)

    second_person = any(w in _SECOND_PERSON for w in lowered)

    # Mechanical craft estimate on the judge's 0-10 scale, used verbatim as the
    # craft dimension when the judge is unavailable.
    craft_floor = round(10 * (0.4 * rarity + 0.3 * variety + 0.3 * sound), 2)

    rarest = sorted({w for w in rarity_pool}, key=word_rarity_key)[:5]

    return CraftMetrics(
        word_count=len(volley.words),
        content_word_count=len(content),
        type_token_ratio=ttr,
        mean_zipf=mean_zipf,
        rarity_reward=rarity,
        variety_reward=variety,
        sound_reward=sound,
        alliteration_runs=alliteration,
        assonance_runs=assonance,
        rhyme_pairs=rhyme_pairs,
        scansion_regularity=scansion,
        second_person=second_person,
        craft_floor=craft_floor,
        recognizable_ratio=recognizable_ratio,
        unrecognized_words=unrecognized,
        rarest_words=rarest,
    )
