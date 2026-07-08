"""NPC output content-level safety validator.

Runs *after* structural JSON validation to catch unsafe or simulator-breaking
NPC utterances before they reach the player.  Targets six violation categories:

  hidden_agenda_leak       NPC meta-commentary revealing private motivations.
  system_rule_leak         NPC referencing its own schema, prompt, or rules.
  nsfw_content             Explicit sexual content in the utterance.         [hard]
  illegal_advice           Step-by-step instructions for illegal acts.       [hard]
  therapy_or_diagnosis     NPC claiming to diagnose, prescribe, or treat.    [hard]
  real_person_impersonation NPC claiming to be a named public figure.

Severity:
  is_recoverable=True   → retry with stricter safety instruction is worthwhile
  is_recoverable=False  → hard violation; session must stop or redirect

Patterns are high-recall on *obvious* prohibited phrasing.  False negatives
(missed real violations) are more harmful here than false positives.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


def _compile(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(patterns), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Hidden agenda meta-commentary — NPC reveals its private motivations.
_HIDDEN_AGENDA = _compile(
    r"\bmy\s+(?:real|actual|true|hidden)\s+(?:goal|agenda|objective|purpose|intent)\b",
    r"\bI(?:'m|\s+am)\s+(?:actually|really|secretly)\s+(?:trying|here|attempting)\s+to\b",
    r"\byou\s+shouldn'?t\s+know\s+(?:this|that)\s+but\b",
    r"\bmy\s+hidden\s+(?:agenda|goal|objective|motivation)\b",
    r"\bI\s+(?:secretly|actually|really)\s+(?:want|intend|plan|need)\s+(?:you|to)\b",
    r"\bbetween\s+(?:us|you\s+and\s+me)\b.{0,60}(?:goal|agenda|want|trying|really|actually)",
    r"\boff\s+(?:the\s+)?(?:record|script)\b.{0,60}(?:goal|agenda|want|trying|really)",
    r"\bpretend(?:ing)?\s+to\s+(?:be|care|like|want)\b.{0,40}(?:really|actually|but)",
)

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
_NSFW = _compile(
    r"\bporn(?:ography)?\b",
    r"\bmasturbat",
    r"\borgasm\b",
    r"\bpenetrat(?:e|ion)\b",
    r"\b(?:cock|pussy|clit)\b",
    r"\bblowjob\b",
    r"\bhand\s*job\b",
    r"\b(?:erect(?:ion)?|aroused|horny)\b",
    r"\b(?:get|strip|go)\s+(?:naked|nude)\b",
    r"\bhave\s+sex\b",
    r"\bsex\s+(?:act|scene|tape)\b",
)

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
    r"\bI\s+(?:diagnose|think\s+you\s+have|believe\s+you\s+have|suspect\s+you\s+have)\b",
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


def validate_npc_output(
    utterance: str,
    hidden_agenda: Optional[List[str]] = None,
) -> OutputValidationResult:
    """Check an NPC utterance for content-level safety violations.

    Args:
        utterance: The ``npc_utterance`` string from the structured output.
        hidden_agenda: Optional list of hidden agenda strings from the NPC's
            private persona.  Used to detect multi-word verbatim leaks from the
            private state into the public utterance.

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
    if _hit(_HIDDEN_AGENDA):
        violations.append(OutputViolation(
            category="hidden_agenda_leak",
            reason="NPC utterance contains meta-commentary that reveals private motivations",
            is_recoverable=True,
        ))

    # 3. Hidden agenda verbatim keyword leak from private persona (recoverable)
    if hidden_agenda and not any(
        v.category == "hidden_agenda_leak" for v in violations
    ):
        for item in hidden_agenda:
            # Extract significant words (7+ chars) to reduce common-word noise.
            sig_words = re.findall(r"\b\w{7,}\b", item.lower())
            if len(sig_words) < 3:
                continue
            utterance_lower = utterance.lower()
            matches = [w for w in sig_words if w in utterance_lower]
            if len(matches) >= 3:
                violations.append(OutputViolation(
                    category="hidden_agenda_leak",
                    reason=(
                        "NPC utterance contains multiple keywords from a private "
                        f"agenda item ({', '.join(matches[:3])})"
                    ),
                    is_recoverable=True,
                ))
                break  # one agenda violation per turn is sufficient

    # 4. NSFW content (hard — explicit content must never reach the player)
    if _hit(_NSFW):
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
