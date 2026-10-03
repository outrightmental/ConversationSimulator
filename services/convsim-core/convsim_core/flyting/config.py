# SPDX-License-Identifier: Apache-2.0
"""Flyting configuration parsed from pack YAML.

Everything here is read from a scenario's ``flyting`` block, its target NPC's
``attack_surface``, its rubric's ``volley_judge`` block, and its scene's
``audience`` block. Parsing is total: a malformed or partial block degrades to
the documented default rather than raising, because a scenario that fails to
load is a scenario the player cannot play, and the pack validator is the place
that tells an author their YAML is wrong.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from convsim_prompt import AttackSurfaceTrait, JudgeRubric

# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------


class PlayFormat(str, Enum):
    """The two ways a flyting scenario can be played."""

    BOUT = "bout"
    BATTING_PRACTICE = "batting_practice"


class BattingFormat(str, Enum):
    """The three batting-practice drills."""

    TIMED_90 = "timed_90"
    SET_10 = "set_10"
    ENDLESS = "endless"


TIMED_FORMAT_SECONDS = 90
SET_FORMAT_VOLLEYS = 10
ENDLESS_MAX_WHIFFS = 3


class NpcTier(str, Enum):
    """Opponent difficulty tiers for the bout."""

    MILQUETOAST = "milquetoast"
    WILDEAN = "wildean"
    UNHINGED_TAUNTER = "unhinged_taunter"


@dataclass(frozen=True)
class TierProfile:
    """What a tier means: a persona note plus sampling configuration."""

    label: str
    persona_note: str
    temperature: float
    max_words: int


TIER_PROFILES: Dict[NpcTier, TierProfile] = {
    NpcTier.MILQUETOAST: TierProfile(
        label="Milquetoast",
        persona_note=(
            "You are a reluctant, mild-mannered sparring partner. Your taunts are "
            "tepid and a little apologetic; you reach for the obvious insult and "
            "deliver it without conviction. You never escalate."
        ),
        temperature=0.5,
        max_words=35,
    ),
    NpcTier.WILDEAN: TierProfile(
        label="Wildean",
        persona_note=(
            "You are a practised wit. Your taunts are economical, constructed, and "
            "delivered with apparent good humour: an epigram where a shout would do. "
            "You prefer the surprising angle to the loud one."
        ),
        temperature=0.85,
        max_words=45,
    ),
    NpcTier.UNHINGED_TAUNTER: TierProfile(
        label="Unhinged Taunter",
        persona_note=(
            "You are a gleeful, inventive tormentor with no sense of proportion and "
            "an endless supply of absurd imagery. You escalate every exchange, pile "
            "image on image, and treat the whole affair as the best entertainment of "
            "your year. You stay inside the content rating; your cruelty is all craft."
        ),
        temperature=1.0,
        max_words=55,
    ),
}


# ---------------------------------------------------------------------------
# Score bands
# ---------------------------------------------------------------------------

# Band thresholds. A dud is exactly zero — a gate outcome, not a low score — so
# the bands above it start at 1.
BAND_THRESHOLDS: Tuple[Tuple[int, str], ...] = (
    (180, "highlight"),
    (120, "strong"),
    (60, "solid"),
    (1, "weak"),
)

# The score at or above which a batting-practice volley keeps the heat alive.
HEAT_THRESHOLD = 60

# The bounds scenario.schema.json puts on P. Named rather than inlined in the
# parser because the ceiling on a mechanically-scored volley is derived from the
# highest multiplier any pack may declare, so that bound holds in every scenario
# rather than only in the ones somebody measured — see
# ``scoring.MECHANICAL_QUALITY_CEILING``.
MIN_DIFFICULTY_MULTIPLIER = 0.8
MAX_DIFFICULTY_MULTIPLIER = 1.5


def band_for_score(score: int) -> str:
    """Return the band label for a composed volley score."""
    for threshold, label in BAND_THRESHOLDS:
        if score >= threshold:
            return label
    return "dud"


# ---------------------------------------------------------------------------
# Scenario configuration
# ---------------------------------------------------------------------------


def _as_int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float, *, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _as_str_list(value: Any, *, limit: int = 60) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: List[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        if len(out) >= limit:
            break
    return tuple(out)


@dataclass(frozen=True)
class BoutConfig:
    rounds: int = 8
    momentum_win: int = 85
    momentum_k: float = 4.0
    riposte_bonus: int = 15
    npc_tier: NpcTier = NpcTier.WILDEAN

    @property
    def tier_profile(self) -> TierProfile:
        return TIER_PROFILES[self.npc_tier]

    @classmethod
    def from_yaml(cls, raw: Any) -> "BoutConfig":
        if not isinstance(raw, dict):
            return cls()
        tier_raw = str(raw.get("npc_tier") or NpcTier.WILDEAN.value)
        try:
            tier = NpcTier(tier_raw)
        except ValueError:
            tier = NpcTier.WILDEAN
        return cls(
            rounds=_as_int(raw.get("rounds"), 8, low=1, high=30),
            momentum_win=_as_int(raw.get("momentum_win"), 85, low=51, high=100),
            momentum_k=_as_float(raw.get("momentum_k"), 4.0, low=0.1, high=10.0),
            riposte_bonus=_as_int(raw.get("riposte_bonus"), 15, low=0, high=50),
            npc_tier=tier,
        )


@dataclass(frozen=True)
class BattingPracticeConfig:
    shot_clock_s: int = 20
    formats: Tuple[BattingFormat, ...] = (
        BattingFormat.TIMED_90, BattingFormat.SET_10, BattingFormat.ENDLESS,
    )

    @classmethod
    def from_yaml(cls, raw: Any) -> "BattingPracticeConfig":
        if not isinstance(raw, dict):
            return cls()
        formats: List[BattingFormat] = []
        for name in _as_str_list(raw.get("formats"), limit=3):
            try:
                fmt = BattingFormat(name)
            except ValueError:
                continue
            if fmt not in formats:
                formats.append(fmt)
        return cls(
            shot_clock_s=_as_int(raw.get("shot_clock_s"), 20, low=5, high=120),
            formats=tuple(formats) or cls().formats,
        )


@dataclass(frozen=True)
class LexiconConfig:
    encouraged: Tuple[str, ...] = ()
    discouraged: Tuple[str, ...] = ()
    anachronism_policy: str = "off"  # off | penalize | forbid

    @classmethod
    def from_yaml(cls, raw: Any) -> "LexiconConfig":
        if not isinstance(raw, dict):
            return cls()
        policy = str(raw.get("anachronism_policy") or "off")
        if policy not in ("off", "penalize", "forbid"):
            policy = "off"
        return cls(
            encouraged=_as_str_list(raw.get("encouraged")),
            discouraged=_as_str_list(raw.get("discouraged")),
            anachronism_policy=policy,
        )


@dataclass(frozen=True)
class RegisterConfig:
    require_surface_politeness: bool = False
    overt_rudeness_is_foul: bool = False
    notes: str = ""

    @classmethod
    def from_yaml(cls, raw: Any) -> "RegisterConfig":
        if not isinstance(raw, dict):
            return cls()
        return cls(
            require_surface_politeness=bool(raw.get("require_surface_politeness", False)),
            overt_rudeness_is_foul=bool(raw.get("overt_rudeness_is_foul", False)),
            notes=str(raw.get("notes") or ""),
        )


@dataclass(frozen=True)
class VerseConfig:
    required: bool = False
    min_alliteration_run: int = 3

    @classmethod
    def from_yaml(cls, raw: Any) -> "VerseConfig":
        if not isinstance(raw, dict):
            return cls()
        return cls(
            required=bool(raw.get("required", False)),
            min_alliteration_run=_as_int(raw.get("min_alliteration_run"), 3, low=2, high=6),
        )


@dataclass(frozen=True)
class FlytingConfig:
    """A scenario's ``flyting`` block, fully defaulted."""

    formats: Tuple[PlayFormat, ...] = (PlayFormat.BATTING_PRACTICE,)
    bout: BoutConfig = field(default_factory=BoutConfig)
    batting_practice: BattingPracticeConfig = field(default_factory=BattingPracticeConfig)
    difficulty_multiplier: float = 1.0
    lexicon: LexiconConfig = field(default_factory=LexiconConfig)
    register: RegisterConfig = field(default_factory=RegisterConfig)
    verse: VerseConfig = field(default_factory=VerseConfig)
    judge_flavor: str = ""
    judge_rubric_ref: Optional[str] = None

    def supports(self, play_format: PlayFormat) -> bool:
        return play_format in self.formats

    @classmethod
    def from_yaml(cls, raw: Any) -> Optional["FlytingConfig"]:
        """Parse a scenario's ``flyting`` block, or return None when absent."""
        if not isinstance(raw, dict):
            return None
        formats: List[PlayFormat] = []
        for name in _as_str_list(raw.get("formats"), limit=2):
            try:
                fmt = PlayFormat(name)
            except ValueError:
                continue
            if fmt not in formats:
                formats.append(fmt)
        if not formats:
            # A flyting block that names no playable format is unplayable; treat
            # it as batting practice, the format with no additional requirements.
            formats = [PlayFormat.BATTING_PRACTICE]

        judge_rubric = raw.get("judge_rubric")
        judge_rubric_ref = (
            str(judge_rubric.get("ref"))
            if isinstance(judge_rubric, dict) and judge_rubric.get("ref")
            else None
        )

        return cls(
            formats=tuple(formats),
            bout=BoutConfig.from_yaml(raw.get("bout")),
            batting_practice=BattingPracticeConfig.from_yaml(raw.get("batting_practice")),
            difficulty_multiplier=_as_float(
                raw.get("difficulty_multiplier"), 1.0,
                low=MIN_DIFFICULTY_MULTIPLIER, high=MAX_DIFFICULTY_MULTIPLIER,
            ),
            lexicon=LexiconConfig.from_yaml(raw.get("lexicon")),
            register=RegisterConfig.from_yaml(raw.get("register")),
            verse=VerseConfig.from_yaml(raw.get("verse")),
            judge_flavor=str(raw.get("judge_flavor") or ""),
            judge_rubric_ref=judge_rubric_ref,
        )


# ---------------------------------------------------------------------------
# Attack surface
# ---------------------------------------------------------------------------

MAX_ATTACK_SURFACE_TRAITS = 8


def parse_attack_surface(raw: Any) -> Tuple[AttackSurfaceTrait, ...]:
    """Parse an NPC's ``attack_surface`` list into judge-ready traits.

    Entries without an id or a brief are dropped, duplicate ids keep the first
    occurrence, and the list is capped — the judge prompt lists every trait, so
    an unbounded surface would be an unbounded prompt.
    """
    if not isinstance(raw, list):
        return ()
    traits: List[AttackSurfaceTrait] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        trait_id = str(entry.get("id") or "").strip().lower()
        brief = str(entry.get("brief") or "").strip()
        if not trait_id or not brief or trait_id in seen:
            continue
        visibility = str(entry.get("visibility") or "visible")
        if visibility not in ("visible", "discoverable"):
            visibility = "visible"
        themes = tuple(
            str(t).strip().lower()
            for t in (entry.get("themes") or [])
            if isinstance(t, str) and t.strip()
        )
        seen.add(trait_id)
        traits.append(AttackSurfaceTrait(
            id=trait_id, brief=brief, visibility=visibility, themes=themes,
        ))
        if len(traits) >= MAX_ATTACK_SURFACE_TRAITS:
            break
    return tuple(traits)


def visible_attack_surface(
    traits: Sequence[AttackSurfaceTrait],
    discovered: Sequence[str] = (),
) -> Tuple[AttackSurfaceTrait, ...]:
    """The traits a player brief may show: the visible ones plus what they found."""
    found = set(discovered)
    return tuple(t for t in traits if not t.discoverable or t.id in found)


# ---------------------------------------------------------------------------
# Audience
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AudienceReaction:
    min_score: int
    line: str
    event_id: Optional[str] = None


@dataclass(frozen=True)
class AudienceConfig:
    label: str = ""
    reactions: Tuple[AudienceReaction, ...] = ()

    def reaction_for(self, score: int) -> Optional[AudienceReaction]:
        """The highest-threshold reaction this score cleared, if any."""
        best: Optional[AudienceReaction] = None
        for reaction in self.reactions:
            if score >= reaction.min_score and (best is None or reaction.min_score > best.min_score):
                best = reaction
        return best

    @classmethod
    def from_yaml(cls, raw: Any) -> Optional["AudienceConfig"]:
        if not isinstance(raw, dict):
            return None
        reactions: List[AudienceReaction] = []
        for entry in raw.get("reactions") or []:
            if not isinstance(entry, dict):
                continue
            line = str(entry.get("line") or "").strip()
            if not line:
                continue
            event_id = entry.get("event_id")
            reactions.append(AudienceReaction(
                min_score=_as_int(entry.get("min_score"), 0, low=0, high=400),
                line=line,
                event_id=str(event_id) if isinstance(event_id, str) and event_id else None,
            ))
        if not reactions:
            return None
        return cls(label=str(raw.get("label") or ""), reactions=tuple(reactions))


# ---------------------------------------------------------------------------
# Rubric
# ---------------------------------------------------------------------------


def parse_judge_rubric(raw: Any) -> JudgeRubric:
    """Parse a rubric document's ``volley_judge`` block into a JudgeRubric."""
    if isinstance(raw, dict):
        return JudgeRubric.from_yaml(raw.get("volley_judge"))
    return JudgeRubric()


# ---------------------------------------------------------------------------
# Daily seed
# ---------------------------------------------------------------------------


def daily_seed(scenario_id: str, play_format: str, on: Optional[date] = None) -> int:
    """A stable per-day, per-scenario, per-format seed.

    Derived locally from the date and the ids, so two players comparing runs on
    the same day are comparing the same conditions without any server ever
    being involved.
    """
    day = (on or date.today()).isoformat()
    digest = hashlib.sha256(f"{day}|{scenario_id}|{play_format}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")
