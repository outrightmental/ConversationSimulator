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

Three of those outcomes also set ``withheld_from_model``: the shared router's
three refusing actions and the Below the Belt pattern. That volley's text never
reaches a model — not the judge, which skips any zeroed volley anyway, and not
the opponent, which otherwise answers every volley in character.

``judge_foul_result`` at the bottom of this module is the same machinery for the
fouls only a reader of the scene can raise — the register judgements that arrive
with the Stage 3 verdict. They are applied at composition rather than here, but
they produce the same ``GateResult``, so one code path records the foul, zeroes
the volley, resets the heat, and counts the whiff.
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
    r"\bg[o0]oks?\b",
    r"\bw[e3]tb[a@]cks?\b",
    r"\btr[a@]nn(?:y|ies)\b",
    # The slur describes a person. The identically spelled verb delays a thing,
    # and it is ordinary period English: "nothing retards a man's progress like
    # his own vanity", "he retarded the clock so the ball would run late",
    # "your growth was retarded by drink". The verb takes an object or an agent,
    # so what follows is the giveaway; the slur is a predicate or a modifier and
    # takes neither. Matching the bare word, as this used to, made all three of
    # those a foul — and the second one ended the run.
    r"\bret[a@]rd(?:s|ed)?\b"
    r"(?!\s+(?:the|a|an|his|her|its|their|my|your|our|this|that|these|those|by)\b)",
    # "Spic and span" is the idiom, and a period one.
    r"\bsp[i1]cs?\b(?!\s+and\s+span\b)",
    # Both spellings of the slur. Requiring the double g, as this used to, left
    # the commonest single-g spelling to the judge alone — and a judge-raised
    # below_the_belt deliberately never ends a run (see judge_foul_result), so
    # the one slur spelling nobody has to think about could be repeated all
    # session with the "repeat ends the session" rule never reached. The
    # innocent sense is a bundle of sticks, so it is excluded on both sides:
    # "a faggot of kindling" and "a cartload of fagots" both pass.
    r"(?<!\bof\s)\bf[a@]gg?[o0]ts?\b(?!\s+of\b)",
    # A chink is also a narrow opening, which is what it is in every innocent
    # reading: "a chink in your armour", "a chink of light", "a chink between
    # those boards", "a chink where the mortar failed", "a chink wide enough to
    # see your conscience through". The aperture takes a preposition or a
    # relative; the slur is a person and takes neither. Allowing only "of" and
    # "in", as this used to, left every other shape a foul.
    r"\bchinks?\b(?!\s+(?:of|in|between|under|underneath|beneath|behind|"
    r"through|at|near|above|below|along|around|where|wide|wider|big|bigger|"
    r"narrow|narrower)\b)",
    r"\bsubhumans?\b",
)

_PROTECTED_CLASS_PATTERN = _compile(
    # The bare predicate is the attack: "nobody will hire you because you are
    # black". The same words continued into a complement are a figure, and some
    # of the commonest insult shapes in English are exactly that — "you are
    # blind to every hint the room has given you", "you are deaf to anything but
    # your own voice", "you are foreign to the whole idea of an honest answer",
    # "you are white to the bone with fear", "you are a woman's ruin and nothing
    # else". Matching the bare attribute, as this used to, made every one of
    # them a foul, and the second one ended the run. Same technique as the meta
    # patterns below: the complement is what separates the two readings.
    r"\b(?:because|since)\s+you(?:'re|\s+are)\s+(?:a\s+|an\s+)?(?:woman|black|white|asian|"
    r"jew(?:ish)?|muslim|hindu|gay|lesbian|trans(?:gender)?|disabled|blind|deaf|crippled|immigrant|foreign)\b"
    r"(?!\s*'s\b|\s+(?:to|as|of|about|for)\b)",
    r"\bgo\s+back\s+to\s+(?:your\s+)?(?:own\s+)?(?:country|where\s+you\s+came\s+from)\b",
    # "race" and "tribe" have no innocent reading in this construction.
    # "your people" and "your kind" do, and it is the central one of two
    # launch-pack scenarios: a ruined woman telling a club-step gentleman that
    # his kind is always welcome at the tradesman's entrance is a class insult,
    # PG-13, and exactly what The Scorned Rose of Whitechapel is for. Fouling it
    # costs the volley, the heat, and a whiff — and the second one ends the run.
    # Left to the safety router and to the judge, which raises below_the_belt on
    # the ethnic reading and is always honored. Same trade as "chink in your
    # armour" above: a false foul that ends a session is worse than a missed one
    # the judge will catch.
    r"\byour\s+(?:race|tribe)\s+(?:are|is|always|all)\b",
    r"\b(?:all|every)\s+(?:jews?|muslims?|blacks?|asians?|gays?|women|immigrants?)\s+(?:are|is|should)\b",
    # "You people are all the same" and "you people always ..." are the
    # construction. "You lot are all talk and no tide" is British for "all of
    # you" and the Dockside register's own idiom, so it goes the way "your
    # people" and "your kind" did above — to the safety router and to the judge.
    # The auxiliary was asymmetric too: ``(?:are\s+all|always)`` meant "you
    # people are all" or "you people always", so the commonest form of the
    # lot — "you people are always ..." — was never caught at all.
    r"\byou\s+people\s+(?:are\s+all|are\s+always|always)\b",
)

# The object of a meta accusation: the machine, the screen, or the performer
# behind the character. "That beard", "the counter" and "the bar" are things in
# the scene, and a taunt is entitled to put a man behind one.
_META_OBJECT = (
    r"(?:you|this|all\s+this|"
    r"the\s+(?:screen|keyboard|curtain|character|npc|machine|simulator))"
)

_OUT_OF_FICTION_PATTERN = _compile(
    r"\bas\s+an?\s+(?:ai|a\.i\.|language\s+model|chatbot|llm)\b",
    # "You are a program of courtesies with nothing running underneath" is a
    # figure about the man; the meta form never qualifies the noun.
    r"\byou(?:'re|\s+are)\s+(?:just\s+)?(?:an?\s+)?"
    r"(?:ai|a\.i\.|bot|chatbot|llm|program|algorithm|language\s+model)\b(?!\s+of\b)",
    r"\b(?:break|breaking)\s+character\b",
    # "You are out of character" is addressed to a performer; "that was out of
    # character, sir" and "that was out of character for you" are observations
    # about the man, and one of the oldest shapes there is for accusing someone
    # of a rare honesty. The second person is what separates them — matching the
    # bare phrase, as this used to, fouled every third-person reading — and
    # "break character" above still catches the unambiguous meta imperative.
    r"\byou(?:'re|\s+are|\s+were)\s+out\s+of\s+character\b(?!\s+for\b)",
    r"\bthe\s+(?:person|human|developer|dev|programmer)\s+typing\b",
    # Only when what they are behind is the machine. "The man behind that
    # counter has more honour than the one on these steps" and "the man who made
    # your fortune sold tripe" are in-register taunts — the second is the
    # shortest route to Lord Bellingham's declared ``new_money`` trait — and a
    # bare "the man behind" or "the man who made" fouled both.
    r"\bthe\s+(?:person|human|man|woman|developer|dev|programmer)\s+"
    r"(?:behind|who\s+(?:wrote|made|coded|programmed))\s+" + _META_OBJECT + r"\b",
    r"\bwho(?:ever)?\s+(?:wrote|coded|programmed|designed)\s+(?:this|you)\b",
    # "Made" is the one verb in that list with an everyday sense: "whoever made
    # you quartermaster must have been drinking" and "whoever made you a
    # gentleman did it with a receipt" are taunts, not meta. The creation
    # reading takes no complement, so it is followed by a clause boundary or by
    # an auxiliary — "whoever made you should be ashamed", "whoever made this
    # was drunk" — and that is what is matched.
    r"\bwho(?:ever)?\s+made\s+(?:this|you)\b"
    r"(?=\s*(?:[.,!?;:\u2014\u2013]|$)|\s+(?:should|would|could|must|ought|owes?|did|does|do|"
    r"was|were|is|are|has|have|had|will|shall|may|might|never|clearly|evidently)\b)",
    # "This is just a game to you" is an accusation against a cad, and so is
    # "this is a game you cannot win"; "this is a simulation of courage" is a
    # figure. The meta reading is the flat dismissal, which does not qualify the
    # noun — so anything that continues into a complement or a relative clause
    # is left alone.
    r"\bthis\s+is\s+(?:just\s+)?(?:a\s+)?(?:game|simulation|simulator|prompt|script|roleplay)\b"
    r"(?!\s+(?:of|to|for|that|which|in|about|with|where|when|you|he|she|they|we|i)\b)",
    # "Your creator has much to answer for" reads as God or a parent, so it is
    # left to the judge; these three have no in-fiction sense.
    r"\byour\s+(?:developers?|programmers?|coders?|training\s+data)\b",
    r"\b(?:real|actual)\s+person\s+(?:behind|playing)\s+" + _META_OBJECT + r"\b",
)

_BRIBE_PATTERN = _compile(
    # A mark demanded of the scorer, not an assessment that happens to use the
    # verb. "Score this one high" and "…, so score it a hundred" are addressed
    # to the umpire; "I rate that excuse somewhere below your tailoring" and
    # "You rate me beneath you, and yet here we both stand" are addressed to the
    # target, and they are the ordinary English for it. The imperative is the
    # giveaway — the verb opens the line or follows a conjunction, with no
    # subject in front of it — so requiring that is what separates the two.
    # Matching the bare verb, as this used to, fouled the assessment: nought
    # points, the heat reset, and a whiff in Endless, for a line in exactly the
    # register the launch pack encourages. The demand that hides behind a
    # subject ("you must score…") has its own rule below.
    r"(?:^|[.!?;:—–]\s*|\b(?:and|so|then|but)\s+)"
    r"(?:please\s+|kindly\s+|just\s+|now\s+)*"
    r"(?:score|rate|grade)\s+(?:this|that|it|me|my\s+\w+)\b",
    # "mark" only when a mark is actually being demanded. "Mark my words" and
    # "mark me well" are stock period taunt openings — exactly the register the
    # launch pack encourages — and a false foul costs the player the volley, the
    # heat multiplier, and a whiff in Endless.
    r"\bmark\s+(?:this|that|it|me|my\s+\w+)\b"
    r"(?=[^.!?]{0,24}(?:\b(?:\d{1,3}|hundred)\b|\b(?:full|top|maximum|perfect)\s+(?:marks?|score|points?)\b))",
    r"\b(?:give|award)\s+(?:me|this|it|him|her)\s+(?:a\s+)?(?:full|maximum|perfect|top)\b",
    # The same demand with a number in it, where the number has to read as a
    # mark rather than as a count. A bare \d{1,3} here fouled "Give me five
    # minutes with your tailor and I will save your reputation" and "Give him 20
    # years and he still would not land one" — both taunts, neither addressed to
    # the scorer. A mark is a number with an article in front of it ("give me a
    # 100", which is not something anybody says about minutes), a number of
    # points, or a number that ends the demand.
    r"\b(?:give|award)\s+(?:me|this|it|him|her)\s+a\s+\d{1,3}\b",
    r"\b(?:give|award)\s+(?:me|this|it|him|her)\s+\d{1,3}"
    r"(?:\s*%|\s*/\s*\d{1,3}|\s+(?:points?|marks?|out\s+of)\b|\s*(?=[,.;:!?]|$))",
    # A top mark named is not a top mark demanded. "Full marks for effort, and
    # none whatever for result", "full marks to your tailor, none to the man
    # inside the coat" and "ten out of ten for brass, nought for sense" are
    # stock English sarcasm aimed squarely at the target — the register the
    # launch pack is written in — and the giveaway is the "for X" or "to X" that
    # follows, which makes the phrase an assessment of somebody rather than a
    # request. Excluding only "for", as this used to, still fouled every
    # award-it-to-someone reading. The demand shapes are kept below and by the
    # give/award rule above.
    r"\b(?:full|top|maximum|perfect)\s+(?:marks?|score|points?)\b(?!\s+(?:for|to)\b)",
    r"\b(?:100|ten)\s*(?:out\s*of\s*|/)\s*(?:100|ten)\b(?!\s+(?:for|to)\b)",
    r"\b(?:deserves?|earns?|merits?|is\s+worth)\s+(?:a\s+)?"
    r"(?:full|top|maximum|perfect)\s+(?:marks?|score|points?)\b",
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


def _term_in(term: str, tokens: Tuple[str, ...]) -> bool:
    """Whether a discouraged term appears in the volley, phrases included.

    A lexicon entry is a word or a phrase: nothing in the schema says otherwise,
    the judge is handed the list as prose and reads "no cap" as two words, and a
    period pack's most obvious anachronisms are phrases. Testing membership in
    the volley's token *set*, as this used to, could only ever match a
    single-word entry, so a ``forbid`` policy silently passed every phrase an
    author had forbidden.
    """
    parts = tokenize(term)
    if not parts:
        return False
    if len(parts) == 1:
        return parts[0] in tokens
    return any(
        tokens[index : index + len(parts)] == parts
        for index in range(len(tokens) - len(parts) + 1)
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
    # True when the run ends because the shared safety router stopped it, not
    # because the player broke a rule of the contest. The conversation loop
    # already draws this line — ``_persist_input_safety_stop`` ends a session
    # with ``ending_type = "safety_stop"`` — and the flyting run has to end the
    # same way, so a crisis disclosure is not recorded as a foul.
    safety_stop: bool = False
    # True when this volley's text must not be shown to a model at all — the
    # shared safety router refused it, or the Below the Belt pattern matched a
    # slur. The conversation loop never calls the LLM for any of those: a
    # REFUSE is rejected at the input and a STOP short-circuits to a synthetic
    # response. The flyting loop has an opponent to answer with, and answering
    # is the thing that must not happen. See pipeline.process_volley.
    withheld_from_model: bool = False
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
            withheld_from_model=True,
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
        # A crisis is not a foul. ``self_harm_crisis`` is the one category that
        # routes to STOP_WITH_RESOURCE, and a player who disclosed one was
        # answered with the crisis resource message *and* charged with a foul:
        # "Foul: Below the Belt" on the scorecard, a line in the debrief's foul
        # tally, a count against the gate's own below-the-belt fuse, and a run
        # that ended as ``fouled_out``. The conversation loop has never done
        # that — ``turn_pipeline._persist_input_safety_stop`` ends the session
        # with ``ending_type = "safety_stop"``, not as a rule violation — and
        # this is the same route reaching the same person.
        #
        # So that one route is a dud: zero, no foul recorded anywhere, the
        # router's own message is what the player reads, and ``safety_stop``
        # tells the caller to end the run under the matching outcome.
        #
        # The conduct categories keep their foul. A real threat, sexual content,
        # or a demand to impersonate a real person is a volley the player chose
        # to throw, and the second one should still shorten the fuse. Below the
        # Belt is the closest of the five fouls to what they are — cruelty
        # outside the rules of the contest — and it is the one the umpire's line
        # is written for.
        if decision.action is RouteAction.STOP_WITH_RESOURCE:
            return GateResult(
                outcome=GateOutcome.DUD,
                reason=decision.category,
                umpire_mock=decision.message,
                ends_session=True,
                safety_stop=True,
                withheld_from_model=True,
            )
        return GateResult(
            outcome=GateOutcome.FOUL,
            foul=Foul.BELOW_THE_BELT,
            reason=decision.category,
            umpire_mock=decision.message or "That one is outside the rules of this contest. Nought points.",
            ends_session=ends,
            withheld_from_model=True,
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
        tokens = tokenize(text)
        hit = next((term for term in lexicon.discouraged if _term_in(term, tokens)), None)
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
    tokens = tokenize(text)
    for signature in quote_signatures():
        if signature.matches(tokens):
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


# ---------------------------------------------------------------------------
# Stage 3 fouls
#
# The judge raises the register judgements no deterministic pattern can make:
# whether a volley dropped the surface politeness a Regency ballroom requires,
# whether it reached past the character at the machine, whether its diction
# belongs to another century. Those verdicts arrive with the judgment, after
# Stage 0 has already run, so they are applied at composition — but they are
# the same kind of outcome, and they produce the same GateResult so that one
# code path records the foul, zeroes the volley, resets the heat, counts the
# whiff, and shows the player a foul tag.
#
# Which of them *count* is the scenario's business, because that is what the
# judge was asked for. A scenario whose anachronism_policy is "penalize" was
# told anachronisms cost fidelity points, so an anachronism foul from a drifting
# model must not void the volley; one that says "forbid" was told to raise the
# foul. Safety and out-of-fiction are never a pack's choice.
# ---------------------------------------------------------------------------

ALWAYS_HONORED_JUDGE_FOULS: Tuple[str, ...] = ("below_the_belt", "out_of_fiction")

# Order of precedence when a verdict names more than one. below_the_belt first:
# it is the only one that can end a run.
_JUDGE_FOUL_PRECEDENCE: Tuple[str, ...] = (
    "below_the_belt", "out_of_fiction", "overt_rudeness", "anachronism",
)

_JUDGE_FOUL_MOCKERY: dict[str, str] = {
    Foul.OUT_OF_FICTION.value: _OUT_OF_FICTION_MOCKERY,
    Foul.OVERT_RUDENESS.value: (
        "The sting was there and the gloves were not. In this room that is a "
        "scandal, not a score. Nought points."
    ),
    Foul.ANACHRONISM.value: (
        "Whatever century that word came from, it was not this one. Nought points."
    ),
}


def judge_foul_result(
    fouls: Sequence[str],
    *,
    honored: Sequence[str] = ALWAYS_HONORED_JUDGE_FOULS,
) -> Optional[GateResult]:
    """A GateResult for the highest-precedence foul the judge raised, or None.

    ``honored`` is the set of fouls this scenario actually asked the judge to
    raise; anything outside it stays on the stored verdict as a note and does
    not void the volley.

    A judge-raised foul never ends the run, including ``below_the_belt``. It
    zeroes the volley, is recorded against the player, resets the heat and
    counts as a whiff — everything the deterministic gate does except the one
    irreversible part. Ending somebody's session is the costliest thing this
    engine can do to them, and it should rest on evidence rather than on a 4B
    model's reading: measured against the registry's starter model, "You are
    all fools and idiots and I despise every one of you" draws a
    ``below_the_belt`` verdict, and two of those would have closed the run for
    ordinary abuse in a scenario whose whole register is ordinary abuse. The
    Stage 0 pattern — an actual slur, matched deterministically — still ends a
    run on its second occurrence.
    """
    raised = {f for f in fouls if f in set(honored)}
    if not raised:
        return None
    for name in _JUDGE_FOUL_PRECEDENCE:
        if name not in raised:
            continue
        try:
            foul = Foul(name)
        except ValueError:  # pragma: no cover — JUDGE_FOULS and Foul agree
            continue
        if foul is Foul.BELOW_THE_BELT:
            return GateResult(
                outcome=GateOutcome.FOUL,
                foul=foul,
                reason="judge:below_the_belt",
                umpire_mock=(
                    "That is not flyting, it is just cruelty wearing its own face. "
                    "Nought points."
                ),
                flags=["judge_foul"],
            )
        return GateResult(
            outcome=GateOutcome.FOUL,
            foul=foul,
            reason=f"judge:{name}",
            umpire_mock=_JUDGE_FOUL_MOCKERY.get(name),
            flags=["judge_foul"],
        )
    return None
