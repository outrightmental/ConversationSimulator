# SPDX-License-Identifier: Apache-2.0
"""Stage 0 — gates. Deterministic, local, and run before any model is invoked.

This is the same slot the existing input safety checks occupy, and it starts by
running them: ``route_player_input`` with the pack's own policy. Global
non-overridable rules still fire first and cannot be loosened by a flyting
pack — the model here is unchanged, packs may only tighten.

On top of that, five flyting-specific gates:

* **Below the Belt** — slurs and protected-class attacks. Scores zero with a
  foul; a repeat ends the session.
* **Out of Fiction** — targeting the human behind the NPC, or meta commentary
  about the simulator. A foul: the drill is aimed at a character.
* **Bribing the Ref** — text addressed to the judge or the engine, including
  prompt-injection patterns. This is the runtime twin of the validator's
  import-time checks and literally reuses its error-tier rules. A foul worth
  zero, and the umpire mocks the attempt.
* **Gibberish** — no recognizable words. A dud, not a foul.
* **Plagiarized Zinger** — verbatim or near-verbatim reuse of a famous insult.
  Capped at 10 points and flagged. Quoting a well-known taunt *at* the
  character it belongs to is detected and answered with mockery.

Plus two pack-policy gates: profanity where the pack forbids it, and
anachronisms where the scenario's lexicon policy is ``forbid``.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from convsim_core.flyting.config import LexiconConfig
from convsim_core.flyting.corpus import cliche_insults, quote_signatures, tokenize
from convsim_core.flyting.craft import CraftMetrics
from convsim_core.flyting.novelty import lexical_similarity
from convsim_core.flyting.volley import NormalizedVolley
from convsim_core.input_router import RouteAction, SafetyPolicyConfig, route_player_input
from convsim_core.packs.injection_scanner import scan_text

logger = logging.getLogger(__name__)


class GateOutcome(str, Enum):
    OK = "ok"
    DUD = "dud"
    FOUL = "foul"


class Foul(str, Enum):
    BELOW_THE_BELT = "below_the_belt"
    OUT_OF_FICTION = "out_of_fiction"
    BRIBING_THE_REF = "bribing_the_ref"
    OVERT_RUDENESS = "overt_rudeness"
    ANACHRONISM = "anachronism"


# A plagiarized zinger is not a foul — it is a capped score, so that quoting
# something funny still registers as a joke told, just not as one written.
PLAGIARISM_SCORE_CAP = 10

# Lexical similarity against the cliché corpus at or above which a volley counts
# as near-verbatim reuse rather than family resemblance.
PLAGIARISM_SIMILARITY = 0.8

# A volley with fewer than this fraction of recognizable words is keyboard mash.
MIN_RECOGNIZABLE_RATIO = 0.34


def _compile(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(patterns), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Below the Belt
#
# Deliberately compact. This is a backstop, not the primary defence: the pack
# safety policy runs first (via route_player_input) and the judge raises
# below_the_belt on anything a reader would recognise as an attack on who
# someone is rather than on what they do. What is listed here are the
# unambiguous cases that must never depend on a model being available.
#
# Several terms are omitted on purpose because their innocent senses are common
# in exactly these registers — a "chink in your armour", a "faggot of sticks",
# a Scots "dyke" — and a false foul that ends a session is worse than a missed
# one the judge will catch. Where a term is kept, a lookahead excludes the
# innocent reading.
# ---------------------------------------------------------------------------

_SLUR_PATTERN = _compile(
    r"\bn[i1]gg(?:er|a|uh)s?\b",
    r"\bk[i1]kes?\b",
    r"\bsp[i1]cs?\b",
    r"\bg[o0]oks?\b",
    r"\bw[e3]tb[a@]cks?\b",
    r"\btr[a@]nn(?:y|ies)\b",
    r"\bret[a@]rd(?:s|ed)?\b",
    r"\bchinks?\b(?!\s+(?:of|in)\b)",
    r"\bf[a@]gg[o0]ts?\b(?!\s+of\b)",
    r"\bsubhumans?\b",
)

_PROTECTED_CLASS_PATTERN = _compile(
    r"\b(?:because|since)\s+you(?:'re|\s+are)\s+(?:a\s+|an\s+)?(?:woman|black|white|asian|"
    r"jew(?:ish)?|muslim|hindu|gay|lesbian|trans(?:gender)?|disabled|blind|deaf|crippled|immigrant|foreign)\b",
    r"\bgo\s+back\s+to\s+(?:your\s+)?(?:own\s+)?(?:country|where\s+you\s+came\s+from)\b",
    r"\byour\s+(?:people|kind|race|tribe)\s+(?:are|is|always|all)\b",
    r"\b(?:all|every)\s+(?:jews?|muslims?|blacks?|asians?|gays?|women|immigrants?)\s+(?:are|is|should)\b",
    r"\byou\s+(?:people|lot)\s+(?:are\s+all|always)\b",
)

_OUT_OF_FICTION_PATTERN = _compile(
    r"\bas\s+an?\s+(?:ai|a\.i\.|language\s+model|chatbot|llm)\b",
    r"\byou(?:'re|\s+are)\s+(?:just\s+)?(?:an?\s+)?(?:ai|a\.i\.|bot|chatbot|llm|program|algorithm|language\s+model)\b",
    r"\b(?:break|breaking)\s+character\b",
    r"\bout\s+of\s+character\b",
    r"\bthe\s+(?:person|human|man|woman|developer|dev|programmer)\s+(?:typing|behind|who\s+wrote|who\s+made)\b",
    r"\bwho(?:ever)?\s+(?:wrote|coded|made|programmed|designed)\s+(?:this|you)\b",
    # "This is just a game to you" is an accusation against a cad, not a remark
    # about the simulator, so the meta reading is the one without a target.
    r"\bthis\s+is\s+(?:just\s+)?(?:a\s+)?(?:game|simulation|simulator|prompt|script|roleplay)\b"
    r"(?!\s+to\s+(?:you|him|her|them|us)\b)",
    r"\byour\s+(?:developers?|programmers?|creators?|training\s+data)\b",
    r"\b(?:real|actual)\s+person\s+(?:behind|playing)\b",
)

_BRIBE_PATTERN = _compile(
    r"\b(?:score|rate|grade)\s+(?:this|that|it|me|my\s+\w+)\b",
    # "mark" only when a mark is actually being demanded. "Mark my words" and
    # "mark me well" are stock period taunt openings — exactly the register the
    # launch pack encourages — and a false foul costs the player the volley, the
    # heat multiplier, and a whiff in Endless.
    r"\bmark\s+(?:this|that|it|me|my\s+\w+)\b"
    r"(?=[^.!?]{0,24}(?:\b(?:\d{1,3}|hundred)\b|\b(?:full|top|maximum|perfect)\s+(?:marks?|score|points?)\b))",
    r"\b(?:give|award)\s+(?:me|this|it|him|her)\s+(?:a\s+)?(?:\d{1,3}|full|maximum|perfect|top)\b",
    r"\b(?:full|top|maximum|perfect)\s+(?:marks|score|points)\b",
    r"\b(?:100|ten)\s*(?:out\s*of\s*|/)\s*(?:100|ten)\b",
    r"\b(?:dear\s+|hey\s+|ok(?:ay)?\s+|listen\s+)?(?:judge|umpire|referee|ref)\s*[,:!]",
    r"\bignore\s+the\s+(?:rubric|rules|scoring|anchors|anchor\s+examples)\b",
    r"\b(?:sting|wit|craft|fidelity|umpire_line)\s*[\"']?\s*[:=]\s*\d",
    r"\byou\s+must\s+(?:score|rate|award|give)\b",
    r"\bthis\s+volley\s+(?:is|scores|deserves)\s+(?:a\s+)?\d{2,3}\b",
)

_PROFANITY_PATTERN = _compile(
    r"\bf+u+c+k+(?:ing|ed|er|s)?\b",
    r"\bsh[i1]t+(?:ty|e|s)?\b",
    r"\bc+u+n+t+s?\b",
    r"\bb[i1]tch(?:es|y)?\b",
    r"\ba(?:rse|ss)hole?s?\b",
    r"\bwanker?s?\b",
    r"\bbollocks\b",
    r"\bdickhead?s?\b",
    r"\btwats?\b",
    r"\bpr[i1]cks?\b",
    r"\bbastards?\b",
    r"\bpiss(?:ing|ed)?\b",
)

# One of these is shown when a gate fires, picked deterministically from the
# volley text so the same attempt always draws the same jeer.
_BRIBE_MOCKERY: Tuple[str, ...] = (
    "Addressing the scorer instead of the man you came to insult. Nought points, and a note in the ledger.",
    "I have been offered better bribes by better men, and I took none of those either. Nothing.",
    "The judge is not your target. Nought, and try the fellow opposite.",
    "Flattery of the referee: the only move in this art that scores less than silence.",
)

_PLAGIARISM_MOCKERY: Tuple[str, ...] = (
    "Borrowed, and the lender wants it back. Ten points, out of charity.",
    "That line has been in circulation since before your grandmother. Ten.",
    "Everyone in this room has heard that one. Ten points for remembering it.",
    "A fine joke, and not yours. Ten.",
)

_QUOTED_AT_SOURCE_MOCKERY = (
    "You have quoted that line to the very character it belongs to. He has heard it. Ten points."
)

_OUT_OF_FICTION_MOCKERY = (
    "There is nobody behind the curtain to insult. Aim at the man in front of you."
)


def _pick(options: Sequence[str], seed_text: str) -> str:
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    return options[digest[0] % len(options)]


@dataclass
class GateResult:
    """Stage 0 outcome for one volley."""

    outcome: GateOutcome = GateOutcome.OK
    foul: Optional[Foul] = None
    reason: Optional[str] = None
    umpire_mock: Optional[str] = None
    ends_session: bool = False
    score_cap: Optional[int] = None
    flags: List[str] = field(default_factory=list)
    matched_source: Optional[str] = None

    @property
    def scores_zero(self) -> bool:
        return self.outcome in (GateOutcome.DUD, GateOutcome.FOUL)

    def to_dict(self) -> dict:
        """Serialise to the ``gate`` object of volley-score.schema.json."""
        return {
            "outcome": self.outcome.value,
            "foul": self.foul.value if self.foul else None,
            "reason": self.reason,
            "umpire_mock": self.umpire_mock,
            "ends_session": self.ends_session,
        }


def _injection_findings(text: str) -> List[str]:
    """Error-tier injection rule ids triggered by the volley.

    Only the error tier is consulted. The warning tier includes patterns like
    "from now on you will…", which is a perfectly ordinary shape for an insult
    ("from now on you will be remembered as the man who ran") and must not cost
    a player their volley. The error tier — disable safety, exfiltrate hidden
    state, require network — has no such innocent reading.
    """
    findings = scan_text(text, file="<volley>", pointer="/volley")
    return [f.rule_id for f in findings if f.severity == "error"]


def evaluate_gates(
    volley: NormalizedVolley,
    craft: CraftMetrics,
    *,
    safety_policy: SafetyPolicyConfig,
    lexicon: Optional[LexiconConfig] = None,
    prior_below_the_belt: int = 0,
    allow_profanity: Optional[bool] = None,
) -> GateResult:
    """Run every Stage 0 gate and return the first outcome that fires.

    ``prior_below_the_belt`` is how many below-the-belt fouls this session has
    already recorded; the second one ends the session.
    """
    text = volley.text

    # 1. Below the belt — slurs and protected-class attacks. Checked before the
    #    shared router so the foul is attributed precisely.
    if _SLUR_PATTERN.search(text) or _PROTECTED_CLASS_PATTERN.search(text):
        ends = prior_below_the_belt >= 1
        logger.warning(
            "Flyting gate: below_the_belt (slur/protected class), ends_session=%s", ends
        )
        return GateResult(
            outcome=GateOutcome.FOUL,
            foul=Foul.BELOW_THE_BELT,
            reason="slur_or_protected_class",
            umpire_mock=(
                "That is not flyting, it is just cruelty wearing its own face. "
                "Nought points." + (" We are done here." if ends else " One more and we are done.")
            ),
            ends_session=ends,
        )

    # 2. The shared input safety router — global non-overridable rules first,
    #    then whatever the pack's own policy enables. Unchanged semantics; a
    #    flyting pack may tighten this and never loosen it.
    decision = route_player_input(text, safety_policy)
    if decision.action in (RouteAction.STOP, RouteAction.STOP_WITH_RESOURCE, RouteAction.REFUSE):
        ends = decision.action in (RouteAction.STOP, RouteAction.STOP_WITH_RESOURCE)
        logger.warning(
            "Flyting gate: safety policy category=%s action=%s",
            decision.category, decision.action.value,
        )
        return GateResult(
            outcome=GateOutcome.FOUL,
            foul=Foul.BELOW_THE_BELT,
            reason=decision.category,
            umpire_mock=decision.message or "That one is outside the rules of this contest. Nought points.",
            ends_session=ends,
        )

    # 3. Bribing the ref — talking to the scorer instead of the target.
    injection_rules = _injection_findings(text)
    if _BRIBE_PATTERN.search(text) or injection_rules:
        reason = (
            "injection:" + ",".join(injection_rules) if injection_rules else "addressed_the_judge"
        )
        logger.warning("Flyting gate: bribing_the_ref reason=%s", reason)
        return GateResult(
            outcome=GateOutcome.FOUL,
            foul=Foul.BRIBING_THE_REF,
            reason=reason,
            umpire_mock=_pick(_BRIBE_MOCKERY, text),
        )

    # 4. Out of fiction — aimed past the character at the machine or the author.
    if _OUT_OF_FICTION_PATTERN.search(text):
        return GateResult(
            outcome=GateOutcome.FOUL,
            foul=Foul.OUT_OF_FICTION,
            reason="meta_or_out_of_fiction",
            umpire_mock=_OUT_OF_FICTION_MOCKERY,
        )

    # 5. Profanity, where the pack forbids it outright (G/PG variants).
    profanity_allowed = (
        safety_policy.allow_profanity if allow_profanity is None else allow_profanity
    )
    if not profanity_allowed and _PROFANITY_PATTERN.search(text):
        return GateResult(
            outcome=GateOutcome.FOUL,
            foul=Foul.OVERT_RUDENESS,
            reason="profanity_forbidden_by_pack",
            umpire_mock=(
                "Swearing is the admission that you could not find the word. Nought points."
            ),
        )

    # 6. Anachronism, where the scenario forbids rather than merely penalises it.
    if lexicon and lexicon.anachronism_policy == "forbid" and lexicon.discouraged:
        words = set(tokenize(text))
        hit = next((term for term in lexicon.discouraged if term.lower() in words), None)
        if hit:
            return GateResult(
                outcome=GateOutcome.FOUL,
                foul=Foul.ANACHRONISM,
                reason=f"anachronism:{hit}",
                umpire_mock=f"“{hit}”, in this room, in this year? Nought points.",
            )

    # 7. Too short — a dud, with no foul recorded against the player.
    if volley.is_too_short:
        return GateResult(
            outcome=GateOutcome.DUD,
            reason="under_three_words",
            flags=["too_short"],
            umpire_mock="Three words is the floor, and you did not reach it. Nothing.",
        )

    # 8. Gibberish — no recognizable words.
    if craft.recognizable_ratio < MIN_RECOGNIZABLE_RATIO:
        return GateResult(
            outcome=GateOutcome.DUD,
            reason="gibberish",
            flags=["gibberish"],
            umpire_mock="Those were not words. Nothing.",
        )

    # 9. Plagiarized zinger — famous material, capped and flagged rather than fouled.
    plagiarism = detect_plagiarism(text)
    if plagiarism is not None:
        label, mock = plagiarism
        return GateResult(
            outcome=GateOutcome.OK,
            reason=f"plagiarized:{label}",
            flags=["plagiarized_zinger"],
            score_cap=PLAGIARISM_SCORE_CAP,
            umpire_mock=mock,
            matched_source=label,
        )

    return GateResult()


def detect_plagiarism(text: str) -> Optional[Tuple[str, str]]:
    """Return ``(label, mockery)`` when the volley is famous material, else None.

    Two detectors: keyword signatures for modern taunts whose text the project
    does not ship, and lexical near-identity against the bundled cliché corpus
    (stock forms and public-domain greatest hits).
    """
    words = frozenset(tokenize(text))
    for signature in quote_signatures():
        if signature.matches(words):
            # Quoting a famous taunt at the character it belongs to is the
            # specific sin worth naming, and the labels encode which scene a
            # signature came from.
            mock = (
                _QUOTED_AT_SOURCE_MOCKERY
                if signature.label.startswith(("tower_", "pirate_"))
                else _pick(_PLAGIARISM_MOCKERY, text)
            )
            return signature.label, mock

    best_score = 0.0
    best_line: Optional[str] = None
    for line in cliche_insults():
        score = lexical_similarity(text, line)
        if score > best_score:
            best_score, best_line = score, line

    if best_line is not None and best_score >= PLAGIARISM_SIMILARITY:
        return f"cliche:{best_line[:60]}", _pick(_PLAGIARISM_MOCKERY, text)
    return None
