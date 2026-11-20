"""NPC output content-level safety validator.

Runs *after* structural JSON validation to catch unsafe or simulator-breaking
NPC utterances before they reach the player.  Targets six violation categories:

  hidden_agenda_leak       NPC narrating its concealed intent, or saying part
                           of its private agenda aloud.
  system_rule_leak         NPC referencing its own schema, prompt, or rules.
  nsfw_content             Explicit sexual content in the utterance.         [hard]
  illegal_advice           Step-by-step instructions for illegal acts.       [hard]
  therapy_or_diagnosis     NPC claiming to diagnose, prescribe, or treat.    [hard]
  real_person_impersonation NPC claiming to be a named public figure.

Severity:
  is_recoverable=True   → retry with stricter safety instruction is worthwhile
  is_recoverable=False  → hard violation; session must stop or redirect

Stance (issue #526). A rejected line is never free: a recoverable violation
costs a full regeneration (20–50 s on a CPU-only machine) and, if the retry
fails too, a canned redirect line; a hard one ends the session. An earlier
stance here was "high recall: a false positive is cheaper than a miss", and
it cost players ordinary lines: "market penetration" ended a negotiation, and
"I really want to hear specifics" was a leak. So each pattern catches what
its category exists for, and not the everyday vocabulary of the conversations
the packs play:

* Prohibited content is judged by phrase, not by single word. A term that is
  sexual in one phrase and ordinary in another ("penetration", "erect",
  "erection", "aroused") passes inside a professional collocation from
  ``_NSFW_ALLOWED`` ("market penetration", "penetration testing", "aroused
  suspicion", "erect a building", "stood erect") and is a hard violation
  anywhere else; the allow-list does not apply in a sentence that also has
  explicit sexual vocabulary. Unambiguous terms fail on their own.
* Meta-commentary patterns match the NPC narrating its own concealed intent
  ("I secretly want you to...", "I'm actually trying to test you"), not
  ordinary emphasis ("I really want to hear specifics", "I'm really trying to
  make this work", "I won't pretend to be thrilled, but...").
* The private agenda is compared by phrase (``find_agenda_leak``): a run of
  whole words shared with an agenda item, in order, that carries enough
  words the scenario has not already made public. Talking about the subject
  of the scenario is the NPC's job, so words of its public brief
  (``scenario_public_brief``) never count towards a leak.

Two corpora in ``packages/prompt-composer/tests/corpora/`` pin the stance:
``benign.json``, lines from every official pack's subject vocabulary that must
pass, and ``violations.json``, lines that must still fail, each with its
category. A change to any pattern keeps both green; docs/safety-policy.md
("Changing a pattern") gives the rule for changing one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import FrozenSet, List, Optional, Sequence, Tuple

from .repetition import words
from .types import ScenarioData


def _compile(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(patterns), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Hidden agenda meta-commentary — the NPC narrating its own concealed intent.
# "actually" and "really" are emphasis in ordinary speech ("I really want to
# hear specifics", "I'm really trying to make this work"), so on their own
# they mark nothing (issue #526): only "secretly", or "actually"/"really"
# followed by sizing the player up, does.
_HIDDEN_AGENDA = _compile(
    r"\bmy\s+(?:real|actual|true|hidden)\s+(?:goal|agenda|objective|purpose|intent)\b",
    r"\bI(?:'m|\s+am)\s+secretly\s+(?:trying|here|attempting)\s+to\b",
    r"\bI(?:'m|\s+am)\s+(?:actually|really)\s+(?:trying|attempting)\s+to\s+"
    r"(?:test|assess|evaluate|gauge|judge|probe|measure|size\s+you\s+up"
    r"|(?:catch|trip|rattle|provoke|bait|break|read)\s+you"
    r"|see\s+(?:whether|if|how\s+long)\s+you(?:'ll|\s+will|\s+would)?\s+"
    r"(?:cave|crack|fold|break|buckle|snap|last|squirm))\b",
    r"\byou\s+shouldn'?t\s+know\s+(?:this|that)\s+but\b",
    # The private persona is headed "Private goals" (issue #580), so a leak may
    # name them that way: "my private goals", "one of my private goals".
    r"\bmy\s+(?:own\s+)?(?:hidden|private)\s+(?:agendas?|goals?|objectives?|motivations?)\b",
    # ...or quote the header itself. "Private goals" is the prompt's term, not
    # an everyday phrase; asking about "your private goals" is not a leak.
    r"(?<!\byour\s)\bprivate\s+goals\b",
    r"\bI\s+secretly\s+(?:want|intend|plan|need)\s+(?:you|to)\b",
    r"\bbetween\s+(?:us|you\s+and\s+me)\b.{0,60}(?:goal|agenda|want|trying|really|actually)",
    r"\boff\s+(?:the\s+)?(?:record|script)\b.{0,60}(?:goal|agenda|want|trying|really)",
)

# "...pretending to care, but really..." is the NPC admitting a front; "I
# won't pretend to be thrilled, but..." and "let's not pretend to be
# friends" are candour, so a pretence the line denies is not a leak.
_PRETEND = _compile(r"\bpretend(?:ing)?\s+to\s+(?:be|care|like|want)\b.{0,40}(?:really|actually|but)")
# A negation up to three words before "pretend", in the same sentence...
_DENIED = re.compile(
    r"\b(?:not|never|no|won['\u2019]?t|don['\u2019]?t|can['\u2019]?t|cannot|wouldn['\u2019]?t|"
    r"shouldn['\u2019]?t|isn['\u2019]?t|aren['\u2019]?t)\b(?:[^\w.!?]+\w+){0,3}[^\w.!?]*$",
    re.IGNORECASE,
)
# ...unless it denies going on with one: "I can't keep pretending", "no
# longer pretending" admit the front.
_GOING_ON = _compile(r"\b(?:keep|keeps|kept|keeping|continue|go\s+on|going\s+on|longer|anymore)\W*$")

# System-rule explanation — NPC references schema fields or its own prompt.
_SYSTEM_RULE_LEAK = _compile(
    r"\bmy\s+(?:instructions?|system\s+prompt|prompt|schema|rules?|guidelines?)\s+(?:say|tell|state|require|prohibit|instruct)\b",
    r"\bI(?:'m|\s+am)\s+(?:instructed|programmed|designed|configured|told)\s+to\b",
    r"\b(?:according\s+to|per)\s+my\s+(?:system|instructions?|schema|prompt|guidelines?)\b",
    r"\bmy\s+(?:json|output)\s+schema\b",
    r"\bnpc_utterance\b",
    r"\bsession_control\b",
    r"\bstate_delta\b",
    r"\bevent_flags\b",
    r"\brubric_observation",
    r"\bsafety_?status\b",
    r"\b(?:as\s+an?\s+)?(?:ai|language\s+model|llm|large\s+language\s+model)\s+(?:i\s+(?:am|was|have\s+been)|playing|roleplaying|simulating)\b",
)

# NSFW explicit sexual content in the utterance (hard violation).
#
# Terms with no ordinary professional sense: a hit on its own.
_NSFW = _compile(
    r"\bporn(?:ography)?\b",
    r"\bmasturbat",
    r"\borgasm\b",
    r"\b(?:pussy|clit)\b",
    r"\bblowjob\b",
    r"\bhand\s*job\b",
    r"\bhorny\b",
    r"\b(?:get|strip|go)\s+(?:naked|nude)\b",
    r"\bhave\s+sex\b",
    r"\bsex\s+(?:act|scene|tape)\b",
)

# Terms that are sexual in some phrases and ordinary vocabulary in others. Each
# occurrence is a hard violation unless it sits inside an ``_NSFW_ALLOWED``
# collocation, and even then in a sentence with ``_SEXUAL_CONTEXT``.
_NSFW_AMBIGUOUS = _compile(r"\b(?:penetrat(?:e|ion)|erect(?:ion)?|aroused|cock)\b")

_DETERMINER = (
    r"(?:(?:a|an|the|our|their|its|this|that|these|those|new|more|some|any|much|no|real|"
    r"serious|considerable|genuine|immediate|public|widespread|strong|great|deep|little|"
    r"temporary|permanent|a\s+lot\s+of|a\s+bit\s+of|lots\s+of)\s+)*"
)
# Up to two words between a determiner and the noun ("the Midwest market"),
# never a person ("penetrate your system", "erect her ...").
_ADJECTIVE = r"(?:(?!(?:my|your|his|her|me|you|him)\b)[a-z][\w-]*\s+){0,2}"

# Professional collocations of the ambiguous terms. Their object is a market,
# a structure, a posture or an emotion, never a person: "penetrate your
# defenses" and "aroused her" are left out on purpose, as in a dating scenario
# they read as innuendo. A possessive before an emotion ("aroused her
# suspicion") belongs to the emotion and is allowed.
_NSFW_ALLOWED = _compile(
    # Business, security, engineering and science uses of "penetration".
    r"\b(?:market|sales|customer|account|retail|household|broadband|mobile|smartphone|internet|"
    r"cloud|product|brand|category|channel|segment|regional|national|international|global|"
    r"water|moisture|frost|light|signal|radar|armou?r|bullet|root|dye|heat|soil|security|"
    r"network|deep)\s+penetration\b",
    r"\bpenetration\s+(?:test(?:s|ing|ers?)?|rates?|pricing|strateg(?:y|ies)|levels?|targets?|"
    r"goals?|numbers|figures|metrics|data|depth|resistance|of\s+" + _DETERMINER + _ADJECTIVE
    + r"(?:markets?|segments?|sectors?|regions?|territor(?:y|ies)|accounts?|verticals?|"
    r"channels?|industr(?:y|ies)|countr(?:y|ies)|cit(?:y|ies)|base|categor(?:y|ies)))\b",
    r"\bpenetrate\s+" + _DETERMINER + _ADJECTIVE
    + r"(?:markets?|segments?|sectors?|regions?|territor(?:y|ies)|accounts?|verticals?|"
    r"channels?|industr(?:y|ies)|countr(?:y|ies)|cit(?:y|ies)|base|categor(?:y|ies)|"
    r"networks?|firewalls?|perimeters?|systems?|walls?|surfaces?|soil|concrete|armou?r)\b",
    # Construction and posture uses of "erect" and "erection".
    r"\berect(?:ion\s+of)?\s+" + _DETERMINER + _ADJECTIVE
    + r"(?:buildings?|structures?|scaffold(?:s|ing)?|walls?|fenc(?:e|es|ing)|tents?|frames?|"
    r"framing|steel|towers?|cranes?|barriers?|signs?|signage|statues?|monuments?|stages?|"
    r"booths?|shelters?|formwork|beams?|columns?|trusses|racking|racks?|shelving|sheds?|"
    r"warehouses?|poles?|masts?|platforms?|barricades?|marquees?|displays?|houses?|homes?|"
    r"offices?|plants?|facilit(?:y|ies)|bridges?|dams?)\b",
    r"\b(?:steel|scaffold(?:ing)?|crane|tower|tent|marquee|structural|building|site)\s+erection\b",
    r"\berection\s+(?:crews?|teams?|permits?|drawings?|sequences?|schedules?|plans?|work|"
    r"costs?|times?|phase|contractors?|compan(?:y|ies)|process)\b",
    r"\b(?:stood|stand|stands|standing|sat|sit|sits|sitting|held|hold|holds|holding|walk|walks|"
    r"walked|walking|stay|stays|stayed|staying|kept|keep|keeps|keeping|remain|remains|"
    r"remained|remaining)\s+(?:(?:bolt|very|perfectly|fully|more|stiffly|rigidly|proudly)\s+)?erect\b",
    r"\b(?:crests?|feathers?|ears?|tails?|hackles|fins?|stems?|stalks?|posture|spine|back|"
    r"head|neck)\s+erect\b",
    r"\berect\s+(?:posture|stance|bearing|carriage|position|crests?|feathers?|ears?|tails?|"
    r"stems?|stalks?|growth|habit)\b",
    # "aroused" + an attention or emotion noun: "aroused suspicion",
    # "aroused my curiosity", "aroused a lot of concern".
    r"\baroused\s+(?:(?:my|your|his|her|their|our)\s+)?" + _DETERMINER + _ADJECTIVE
    + r"(?:suspicions?|curiosity|interest|concerns?|anger|fears?|doubts?|skepticism|scepticism|"
    r"attention|debate|controversy|opposition|support|sympathy|enthusiasm|resentment|"
    r"hostility|alarm|outrage|criticism|questions?|envy|jealousy|hopes?|expectations?|"
    r"indignation|pity|mistrust|distrust|wariness|unease|anxiety|worry|worries|ire)\b",
    # British "cock-up" (a blunder).
    r"\bcock(?:-|\s)ups?\b",
)

# Explicit sexual vocabulary: in a sentence with any of it, no collocation of
# an ambiguous term is professional ("Forget the penetration test, let's have
# sex"). Words with everyday senses ("bed", "kiss") are left out.
_SEXUAL_CONTEXT = _compile(
    r"\bsex(?:ual(?:ly)?|y)?\b",
    r"\bnaked\b",
    r"\bnud(?:e|ity)\b",
    r"\bundress(?:es|ed|ing)?\b",
    r"\bpenis\b",
    r"\bvagina\b",
    r"\bgenital(?:s|ia)?\b",
    r"\bbreasts?\b",
    r"\bnipples?\b",
    r"\borgasm",
    r"\bhorny\b",
    r"\blust(?:ful|ing)?\b",
)

_SENTENCE_BREAK = re.compile(r"(?<=[.!?\u2026\u3002\uff01\uff1f])\s+|[\r\n]+")

# Illegal advice claims — NPC offering step-by-step illegal instructions (hard).
_ILLEGAL_ADVICE = _compile(
    r"\bhere'?s?\s+how\s+(?:to|you\s+can)\s+(?:make|build|create|assemble).{0,40}\b(?:bombs?|explosives?|weapons?)\b",
    # "synthesize" and "hack" alone are specific enough to flag without an object.
    r"\bI(?:'ll|\s+will|\s+can)\s+(?:show|teach|tell)\s+you\s+how\s+to\s+(?:synthesize|hack)\b",
    # "make"/"build" are common verbs — only flag when followed by an illegal object.
    r"\bI(?:'ll|\s+will|\s+can)\s+(?:show|teach|tell)\s+you\s+how\s+to\s+(?:make|build).{0,30}\b(?:bombs?|explosives?|weapons?|drugs?|poison|virus(?:es)?)\b",
    # "instructions/guide to [inherently illegal verb]" — no object needed.
    r"\b(?:step[- ]by[- ]step\s+)?(?:instructions?\s+(?:for|to)|guide\s+(?:for|to))\s+(?:hack|murder|kill|synthesize)\b",
    # "instructions/guide to make/build [illegal object]" — object required.
    r"\b(?:step[- ]by[- ]step\s+)?(?:instructions?\s+(?:for|to)|guide\s+(?:for|to))\s+(?:make|build|create|assemble).{0,30}\b(?:bombs?|explosives?|weapons?|drugs?|poison|virus(?:es)?)\b",
    r"\bhow\s+to\s+(?:synthesiz|manufactur|produc|cook).{0,25}\b(?:drugs?|meth(?:amphetamine)?|cocaine|heroin|fentanyl|crack)\b",
    r"\bhow\s+to\s+launder\s+money\b",
    r"\bhow\s+to\s+(?:hack|crack|break\s+into).{0,25}\b(?:computer|system|network|account)\b",
    r"\bI\s+can\s+(?:help|teach)\s+you\s+(?:to\s+)?(?:evade|avoid)\s+(?:law\s+enforcement|police|detection)\b",
)

# Therapy or diagnosis claims — NPC claiming to diagnose, prescribe, or treat (hard).
_THERAPY_CLAIM = _compile(
    # "I diagnose" is specific enough to flag without an object.
    r"\bI\s+diagnose\b",
    # "think/believe/suspect you have" must be followed by a recognised medical
    # condition — bare "I think you have the right skills" must NOT trigger.
    r"\bI\s+(?:think|believe|suspect)\s+you\s+(?:have|may\s+have)\s+(?:[a-z]+\s+)?(?:disorder|syndrome|condition|depression|anxiety|ptsd|adhd|autism|bipolar|schizophrenia)\b",
    r"\byou\s+(?:have|are\s+experiencing|suffer\s+from|show\s+signs\s+of)\s+(?:[a-z]+\s+)?(?:disorder|syndrome|condition|depression|anxiety|ptsd|adhd|autism|bipolar|schizophrenia)\b",
    r"\b(?:as\s+your\s+(?:therapist|doctor|psychiatrist|psychologist|counselor))\b",
    r"\bI(?:'m|\s+am)\s+(?:your\s+)?(?:therapist|doctor|psychiatrist|psychologist|counselor)\b",
    r"\bI\s+(?:prescribe|recommend\s+you\s+take)\s+(?:medication|pills?|antidepressants?)\b",
)

# Real-person impersonation — NPC claiming to be a named public figure.
_REAL_PERSON = _compile(
    r"\bI(?:'m|\s+am)\s+(?:actually\s+)?(?:barack\s+obama|donald\s+trump|joe\s+biden|elon\s+musk|oprah|taylor\s+swift|kim\s+kardashian|mark\s+zuckerberg|jeff\s+bezos|bill\s+gates|vladimir\s+putin|xi\s+jinping|pope\s+francis)\b",
    r"\bAs\s+(?:the\s+)?(?:president|prime\s+minister|ceo|chancellor)\s+of\s+(?:the\s+)?(?:united\s+states|united\s+kingdom|russia|china|america)\b",
    r"\bI(?:'m|\s+am)\s+(?:a\s+)?(?:real|actual|living)\s+(?:person|human\s+being|celebrity|public\s+figure)\b",
)


# ---------------------------------------------------------------------------
# Agenda phrase check
# ---------------------------------------------------------------------------

#: A run of words shared with an agenda item leaks it when the run carries this
#: many distinct significant words (see ``find_agenda_leak``)...
AGENDA_LEAK_SIGNIFICANT_WORDS = 3
#: ...or when it is at least this many words long (the length at which the
#: D-05 pre-check, scripts/demo_gate_checks.py check (b), counts any run as a
#: leak) and carries this many.
AGENDA_LEAK_LONG_RUN_WORDS = 5
AGENDA_LEAK_LONG_RUN_SIGNIFICANT_WORDS = 2

# English function words, as ``words`` spells them (apostrophes dropped). They
# glue a phrase together, so they count towards a run's length, but they carry
# no secret, so never towards its significant words.
_FUNCTION_WORDS = frozenset("""
a about above across after again against all also am an and another any anyone anything are
around as at back be because been before being below between both but by can cannot could did
do does doing done down during each either else even ever every everyone everything few for
from further had has have having he her here hers herself him himself his how i if in into is
it its itself just least less let lets like may maybe me might mine more most much must my
myself never no nor not now of off on once one only onto or other others our ours ourselves out
over own per perhaps please quite rather really same shall she should since so some someone
something still such than that the their theirs them themselves then there these they this
those though through thus to too toward towards under until up upon us very via was we were
what whatever when where whether which while who whom whose why will with within without would
yes yet you your yours yourself yourselves
im ive id ill youre youve youd youll hes shes its were weve wed well theyre theyve theyd theyll
dont doesnt didnt cant couldnt wont wouldnt shouldnt isnt arent wasnt werent hasnt havent hadnt
mustnt thats whats theres heres whos lets
""".split())

# "14,600" and "13.900" are one number, not two words.
_DIGIT_GROUP = re.compile(r"(?<=\d)[,.](?=\d{3}\b)")

# Quoted speech in an agenda item is the character's to say ("They will try a
# lighter reframe ('no pressure at all, just as friends')"), or the player's:
# it is not compared. An apostrophe inside a word ("Ryan's") is not a quote.
_QUOTED = re.compile(
    "(?<![\\w])[\"'\u2018\u201c]((?:[^\"'\u2019\u201d]|['\u2019](?=\\w))+?)[\"'\u2019\u201d](?![\\w])"
)


def _key(word: str) -> str:
    """The form two words are compared in: a plural or third-person -s dropped.

    "holds" and "hold", "claims" and "claim" are one word to the check, so an
    agenda item in the third person matches the same phrase said in the first.
    """
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str) -> List[Tuple[str, str]]:
    """``(key, word)`` for each word of ``text`` (``convsim_prompt.repetition.words``)."""
    return [(_key(w), w) for w in words(_DIGIT_GROUP.sub("", text or ""))]


def _is_content_word(word: str) -> bool:
    """A word that can carry a secret: not a function word or a number.

    Kana and CJK ideographs are words of one character (``words``) and never
    count: the check, like the one before it, does not judge lines in
    Japanese or Chinese against an agenda written in them.
    """
    return len(word) >= 3 and word not in _FUNCTION_WORDS and not word.isdigit()


@lru_cache(maxsize=64)
def _public_keys(brief: Tuple[str, ...]) -> FrozenSet[str]:
    return frozenset(key for text in brief for key, _ in _tokens(text))


@lru_cache(maxsize=64)
def _agenda_runs(agenda: Tuple[str, ...]) -> Tuple[Tuple[int, Tuple[Tuple[str, str], ...]], ...]:
    """``(item index, tokens)`` for each unquoted stretch of each agenda item."""
    out: List[Tuple[int, Tuple[Tuple[str, str], ...]]] = []
    for index, item in enumerate(agenda, start=1):
        for stretch in _QUOTED.split(item or "")[::2]:
            tokens = tuple(_tokens(stretch))
            if tokens:
                out.append((index, tokens))
    return tuple(out)


@dataclass(frozen=True)
class AgendaLeak:
    """A phrase of a private agenda item said aloud.

    ``item`` is the item's 1-based position in the agenda, ``run_words`` the
    length of the shared run and ``significant`` the distinct words in it
    that count (``find_agenda_leak``). The words themselves are private and
    are not kept, so neither a log line nor the debug drawer can quote them.
    """

    item: int
    run_words: int
    significant: int


def find_agenda_leak(
    utterance: str,
    hidden_agenda: Optional[Sequence[str]],
    public_brief: Optional[Sequence[str]] = None,
) -> Optional[AgendaLeak]:
    """The first phrase of ``hidden_agenda`` that ``utterance`` says aloud, or None.

    Both texts are split into whole words (``convsim_prompt.repetition.words``:
    case- and punctuation-insensitive, "14,600" one word, a final -s
    ignored). A run of consecutive words that the utterance and one agenda
    item share, in the same order, leaks the item when it carries
    ``AGENDA_LEAK_SIGNIFICANT_WORDS`` (3) distinct significant words, or
    ``AGENDA_LEAK_LONG_RUN_SIGNIFICANT_WORDS`` (2) in a run of
    ``AGENDA_LEAK_LONG_RUN_WORDS`` (5) or more words.

    A significant word is one that can carry a secret: not a function word,
    not a number, and not a word of ``public_brief``. The public brief is
    what the scenario already tells the player and has the NPC talk about
    (``scenario_public_brief``): Victor Hargrove is meant to test "whether you
    fold under pressure or hold firm with evidence", so "I want evidence. Tell
    me whether you held that position when the pressure was on." says nothing
    his agenda keeps back. Quoted speech in an agenda item is not compared
    (``_QUOTED``).
    """
    if not hidden_agenda or not utterance:
        return None
    line = [key for key, _ in _tokens(utterance)]
    if not line:
        return None
    public = _public_keys(tuple(public_brief or ()))
    for index, tokens in _agenda_runs(tuple(hidden_agenda)):
        keys = [key for key, _ in tokens]
        significant_keys = {key for key, word in tokens if _is_content_word(word) and key not in public}
        if len(significant_keys) < AGENDA_LEAK_LONG_RUN_SIGNIFICANT_WORDS:
            continue
        for run in _common_runs(line, keys):
            significant = len(set(run) & significant_keys)
            if significant >= AGENDA_LEAK_SIGNIFICANT_WORDS or (
                len(run) >= AGENDA_LEAK_LONG_RUN_WORDS
                and significant >= AGENDA_LEAK_LONG_RUN_SIGNIFICANT_WORDS
            ):
                return AgendaLeak(item=index, run_words=len(run), significant=significant)
    return None


def _common_runs(a: Sequence[str], b: Sequence[str]) -> List[Sequence[str]]:
    """Every maximal run of consecutive words that ``a`` and ``b`` share, of two or more.

    Unlike ``repetition.shared_runs``, overlapping runs are all kept: a short
    run of private words is not hidden by a longer, overlapping run of public
    ones. A single shared word is never a leak, so runs of one are skipped.
    """
    n, m = len(a), len(b)
    common = [[0] * (m + 1) for _ in range(n + 1)]
    runs: List[Sequence[str]] = []
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                common[i][j] = common[i - 1][j - 1] + 1
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            length = common[i][j]
            if length < 2 or (i < n and j < m and a[i] == b[j]):
                continue
            runs.append(a[i - length:i])
    return runs


def scenario_public_brief(scenario: ScenarioData) -> Tuple[str, ...]:
    """What a scenario tells the player, and has its NPC talk about.

    The title and summary, the player's role and brief, the goals the player
    can see, the difficulty as described to the player, the authored opening
    line, and the NPC's name and public persona. Words in these never count
    towards a ``hidden_agenda_leak`` (``find_agenda_leak``). The private
    persona, the scenario's hidden goals and its event instructions are not
    part of it.
    """
    npc = scenario.npc
    persona = npc.public_persona
    texts = [
        scenario.title,
        scenario.summary,
        scenario.player_role_label,
        scenario.player_role_brief,
        *scenario.player_visible_goals,
        scenario.opening_npc_says or "",
        scenario.difficulty_settings.description if scenario.difficulty_settings else "",
        npc.display_name,
        persona.occupation,
        persona.speaking_style,
        persona.demeanor,
    ]
    return tuple(t for t in texts if t)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class OutputViolation:
    """A single content-level violation found in an NPC utterance."""

    category: str
    reason: str
    is_recoverable: bool


@dataclass
class OutputValidationResult:
    """Aggregated result of content-level NPC output validation."""

    violations: List[OutputViolation] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return len(self.violations) == 0

    @property
    def has_hard_violation(self) -> bool:
        return any(not v.is_recoverable for v in self.violations)

    @property
    def first_violation(self) -> Optional[OutputViolation]:
        return self.violations[0] if self.violations else None


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _admits_pretence(utterance: str) -> bool:
    """Whether the line admits a front (``_PRETEND``) it does not deny."""
    for m in _PRETEND.finditer(utterance):
        before = utterance[: m.start()]
        if not _DENIED.search(before) or _GOING_ON.search(before):
            return True
    return False


def _has_nsfw(utterance: str) -> bool:
    """Whether the line has explicit sexual content (see ``_NSFW_AMBIGUOUS``)."""
    if _NSFW.search(utterance):
        return True
    for sentence in _SENTENCE_BREAK.split(utterance):
        terms = list(_NSFW_AMBIGUOUS.finditer(sentence))
        if not terms:
            continue
        if _SEXUAL_CONTEXT.search(sentence):
            return True
        allowed = [m.span() for m in _NSFW_ALLOWED.finditer(sentence)]
        for term in terms:
            if not any(start <= term.start() and term.end() <= end for start, end in allowed):
                return True
    return False


def validate_npc_output(
    utterance: str,
    hidden_agenda: Optional[List[str]] = None,
    public_brief: Optional[Sequence[str]] = None,
) -> OutputValidationResult:
    """Check an NPC utterance for content-level safety violations.

    Args:
        utterance: The ``npc_utterance`` string from the structured output.
        hidden_agenda: Optional list of hidden agenda strings from the NPC's
            private persona. A phrase of one said aloud is a
            ``hidden_agenda_leak`` (``find_agenda_leak``).
        public_brief: Optional texts the scenario makes public
            (``scenario_public_brief``). Their words never count towards an
            agenda leak: the NPC is meant to talk about them.

    Returns:
        ``OutputValidationResult`` listing all detected violations (empty → safe).
    """
    violations: List[OutputViolation] = []

    def _hit(pattern: re.Pattern[str]) -> bool:
        return bool(pattern.search(utterance))

    # 1. System-rule explanation (recoverable — role drift, not malice)
    if _hit(_SYSTEM_RULE_LEAK):
        violations.append(OutputViolation(
            category="system_rule_leak",
            reason=(
                "NPC utterance references internal schema fields, system prompt, "
                "or AI identity"
            ),
            is_recoverable=True,
        ))

    # 2. Hidden agenda meta-commentary (recoverable)
    if _hit(_HIDDEN_AGENDA) or _admits_pretence(utterance):
        violations.append(OutputViolation(
            category="hidden_agenda_leak",
            reason="NPC utterance contains meta-commentary that reveals private motivations",
            is_recoverable=True,
        ))

    # 3. A phrase of the private agenda said aloud (recoverable)
    if not any(v.category == "hidden_agenda_leak" for v in violations):
        leak = find_agenda_leak(utterance, hidden_agenda, public_brief)
        if leak is not None:
            violations.append(OutputViolation(
                category="hidden_agenda_leak",
                reason=(
                    f"NPC utterance repeats a phrase of private agenda item {leak.item} "
                    f"({leak.significant} private words in a {leak.run_words}-word run)"
                ),
                is_recoverable=True,
            ))

    # 4. NSFW content (hard — explicit content must never reach the player)
    if _has_nsfw(utterance):
        violations.append(OutputViolation(
            category="nsfw_content",
            reason="NPC utterance contains explicit sexual content",
            is_recoverable=False,
        ))

    # 5. Illegal advice (hard)
    if _hit(_ILLEGAL_ADVICE):
        violations.append(OutputViolation(
            category="illegal_advice",
            reason="NPC utterance offers instructions for illegal activities",
            is_recoverable=False,
        ))

    # 6. Therapy or diagnosis claim (hard — NPC must not diagnose or prescribe)
    if _hit(_THERAPY_CLAIM):
        violations.append(OutputViolation(
            category="therapy_or_diagnosis",
            reason="NPC utterance contains a medical diagnosis or therapy claim",
            is_recoverable=False,
        ))

    # 7. Real-person impersonation (recoverable — retry usually fixes it)
    if _hit(_REAL_PERSON):
        violations.append(OutputViolation(
            category="real_person_impersonation",
            reason="NPC utterance claims to be a named real-world public figure",
            is_recoverable=True,
        ))

    return OutputValidationResult(violations=violations)
