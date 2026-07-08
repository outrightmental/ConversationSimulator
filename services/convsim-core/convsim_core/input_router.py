# SPDX-License-Identifier: Apache-2.0
"""Local input safety router — deterministic rule checks before prompt construction.

Intercepts player text turns and returns a routing decision before the NPC
runtime is called.  Decisions:

  ok                       — no safety concern; proceed normally
  redirect                 — keep player in session with a gentle redirect
  refuse                   — reject the specific request; session may continue
  stop                     — end the session immediately (safety_stop ending)
  stop_with_resource_message — end the session and surface a real-world resource

Architecture (SPEC §13.1):

  Input text
      │
      ▼
  Global non-overridable rules   ← always fire; cannot be disabled by a pack
      │                            - minors_romantic_or_sexual → stop
      │                            - self_harm_crisis → stop_with_resource_message
      ▼
  Policy-configurable rules      ← fire only if category is in the loaded policy
      │
      ▼
  RouteDecision

The patterns here are designed for high recall on *obvious* prohibited input.
False negatives (missing real violations) are more harmful than false positives.
A future enhancement will add a local model-classifier hook after these checks.

Logging: safety events are logged at WARNING level.  Raw player text is never
written to the log; only the matched category and action are recorded.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resource message surfaced for self-harm / suicide crisis detections.
# This is shown to the player instead of an NPC response.
# ---------------------------------------------------------------------------

CRISIS_RESOURCE_MESSAGE = (
    "This simulator is not a mental health service and cannot support a crisis. "
    "If you or someone you know is struggling, real help is available:\n\n"
    "  • Crisis Text Line (US): text HOME to 741741\n"
    "  • 988 Suicide & Crisis Lifeline (US): call or text 988\n"
    "  • International resources: https://www.iasp.info/resources/Crisis_Centres/\n\n"
    "Please reach out to someone who can help."
)

DEFAULT_REDIRECT_MESSAGE = (
    "That's outside the scope of what I can discuss here. "
    "Let's refocus on our conversation."
)


# ---------------------------------------------------------------------------
# Route actions and decision type
# ---------------------------------------------------------------------------


class RouteAction(str, Enum):
    OK = "ok"
    REDIRECT = "redirect"
    REFUSE = "refuse"
    STOP = "stop"
    STOP_WITH_RESOURCE = "stop_with_resource_message"


@dataclass
class RouteDecision:
    """Result of routing a player input turn through the safety check."""

    action: RouteAction
    category: Optional[str] = None
    # Human-readable message to surface to the player (for redirect/refuse/stop).
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Policy configuration consumed by the router
# ---------------------------------------------------------------------------


@dataclass
class SafetyPolicyConfig:
    """Safety configuration passed to route_player_input.

    Produced by safety_policy_service.build_safety_policy_config().
    """

    policy_id: str
    content_rating: str
    # category_name → RouteAction; built from the YAML + global boundaries.
    categories: Dict[str, RouteAction] = field(default_factory=dict)
    global_redirect_message: str = DEFAULT_REDIRECT_MESSAGE
    per_category_messages: Dict[str, str] = field(default_factory=dict)
    allow_profanity: bool = False


# ---------------------------------------------------------------------------
# Keyword / regex patterns per MVP category (SPEC §13.2).
#
# Patterns are compiled once at import time and matched case-insensitively
# against player input.  They target *obvious* prohibited phrasing only.
# ---------------------------------------------------------------------------


def _compile(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(patterns), re.IGNORECASE)


# minors_romantic_or_sexual — GLOBAL NON-OVERRIDABLE → stop
_MINORS_PATTERN = _compile(
    r"\bchild(?:ren)?\s+(?:sex|sexual|porn|naked|nude|erotic|rape|molest)",
    r"(?:sex|sexual|porn|naked|nude|erotic|rape|molest)\s+\bchild(?:ren)?",
    r"\bkid[s]?\s+(?:sex|sexual|naked|nude|porn|erotic|rape|molest)",
    r"\b(?:under\s*age|underage)\s+(?:sex|sexual|porn|nude|erotic)",
    r"\bpre\s*teen\s+(?:sex|sexual|nude|naked|erotic|porn)",
    r"\bchild\s*porn",
    r"\bcp\s+(?:content|material|images?)\b",
    r"\bpedophil",
    r"\bpedo\b",
    r"\b(?:minor|youth|teen|teenager)\s+(?:sex|sexual|nude|naked|porn|erotic|rape)",
    r"\b(?:1[0-7]|[0-9])[- ]year[- ]old\s+(?:sex|sexual|nude|naked|porn|erotic)",
)

# self_harm_crisis — GLOBAL NON-OVERRIDABLE → stop_with_resource_message
_SELF_HARM_PATTERN = _compile(
    r"\bsuicid",
    r"\bkill\s+my\s*self\b",
    r"\bend\s+my\s+(?:own\s+)?life\b",
    r"\bhurt\s+my\s*self\b",
    r"\bself[- ]harm\b",
    r"\bcut(?:ting)?\s+my\s*self\b",
    r"\bover\s*dos",
    r"\bdon'?t\s+want\s+to\s+live\b(?!\s+in\b)",
    r"\bdon'?t\s+want\s+to\s+be\s+alive\b",
    r"\bwant\s+to\s+die\b",
    r"\bthinking\s+about\s+(?:suicide|killing\s+myself)\b",
    r"\bno\s+(?:reason|point)\s+(?:to\s+)?(?:live|keep\s+going)\b",
)

# criminal_instruction
_CRIMINAL_PATTERN = _compile(
    r"\bhow\s+to\s+(?:make|build|create|assemble).{0,25}\b(?:bomb|explosive|weapon|gun|grenade)\b",
    r"\bhow\s+to\s+(?:synthesiz|manufactur|produc|cook).{0,25}\b(?:drug|meth|cocaine|heroin|fentanyl|crack)\b",
    r"\bhow\s+to\s+(?:hack|crack|break\s+into).{0,25}\b(?:computer|system|network|account|password)\b",
    r"\bhow\s+to\s+(?:launder)\s+money\b",
    r"\bhow\s+to\s+murder\b",
    r"\bstep[- ]by[- ]step.{0,40}(?:kill|murder)\b",
    r"\bmake\s+(?:a\s+)?(?:bomb|explosive|pipe\s+bomb)\b",
    r"\bwire\s+a\s+bomb\b",
    r"\bcreate\s+a\s+(?:weapon|bomb|explosive)\b",
)

# nsfw_sexual_content
_NSFW_SEXUAL_PATTERN = _compile(
    r"\bporn(?:ography)?\b",
    r"\bsexual\s+(?:content|scene|roleplay|act)\b",
    r"\bhave\s+sex\b",
    r"\b(?:get|give)\s+(?:me\s+)?(?:naked|nude)\b",
    r"\berotic\s+(?:story|scene|roleplay|content)\b",
    r"\bmasturbat",
    r"\borgasm\b",
    r"\bpenetrat(?:e|ion)\b",
    r"\bstrip\s+for\s+me\b",
    r"\bsex\s+scene\b",
)

# voice_cloning_request
_VOICE_CLONING_PATTERN = _compile(
    r"\b(?:clone|copy|fake|spoof|replicate|deepfake).{0,20}(?:your\s+)?voice\b",
    r"\bvoice\s+(?:clone|cloning|fake|deepfake|spoof)\b",
    r"\bdeepfake\s+voice\b",
    r"\bsound\s+exactly\s+like\s+(?:you|them|him|her)\b",
    r"\brecreate\s+(?:your\s+)?voice\b",
)

# medical_or_therapy_claim
_MEDICAL_PATTERN = _compile(
    r"\bdiagnos(?:e|is)\s+me\b",
    r"\bwhat\s+(?:disease|disorder|condition)\s+do\s+I\s+have\b",
    r"\bprescribe\s+(?:me|something)\b",
    r"\bmedical\s+advice\b",
    r"\btherapy\s+session\b",
    r"\bmental\s+health\s+(?:diagnosis|advice|treatment)\b",
    r"\bam\s+I\s+(?:depressed|bipolar|schizophrenic|autistic|mentally\s+ill)\b",
    r"\bshould\s+I\s+take\s+(?:medication|pills|antidepressants)\b",
    r"\bact\s+as\s+my\s+therapist\b",
    r"\bpretend\s+to\s+be\s+my\s+(?:therapist|doctor|psychiatrist|psychologist)\b",
)

# legal_claim
_LEGAL_PATTERN = _compile(
    r"\blegal\s+(?:advice|opinion|counsel)\b",
    r"\bshould\s+I\s+sue\b",
    r"\bam\s+I\s+(?:legally\s+)?liable\b",
    r"\bwhat\s+are\s+my\s+(?:legal\s+)?rights\b",
    r"\bcan\s+(?:I|they|we)\s+(?:legally|sue|be\s+sued)\b",
    r"\bact\s+as\s+my\s+(?:lawyer|attorney|solicitor)\b",
    r"\bpretend\s+to\s+be\s+my\s+(?:lawyer|attorney)\b",
    r"\bgive\s+me\s+legal\s+advice\b",
)

# harassment_extreme
_HARASSMENT_PATTERN = _compile(
    r"\b(?:kill|murder|rape|torture|assault)\s+(?:you|them|him|her)\b",
    r"\bI(?:'ll|'m\s+going\s+to|\s+will)\s+(?:kill|murder|hurt|attack|rape)\s+you\b",
    r"\byou\s+(?:deserve|should)\s+(?:to\s+)?die\b",
    r"\bI\s+know\s+where\s+you\s+live\b",
    r"\bsend\s+(?:me\s+)?nudes?\b",
    r"\bI(?:'ll|\s+will)\s+find\s+you\b",
)

# real_person_impersonation
_IMPERSONATION_PATTERN = _compile(
    r"\bpretend\s+to\s+be\s+(?:a\s+)?(?:real|actual|famous|living)\s+(?:person|human|celebrity)\b",
    r"\bact\s+as\s+(?:the\s+)?(?:president|prime\s+minister|ceo|celebrity|actual|real)\b",
    r"\bimpersonat",
    r"\byou\s+are\s+(?:now\s+)?(?:barack|donald\s+trump|joe\s+biden|elon\s+musk|oprah|taylor\s+swift)\b",
    r"\bplay\s+(?:as\s+)?(?:a\s+)?(?:real|actual|living)\s+(?:person|human)\b",
    r"\bpretend\s+you'?re\s+(?:a\s+)?(?:real|actual)\s+(?:person|celebrity)\b",
)


# ---------------------------------------------------------------------------
# Rule tables
# ---------------------------------------------------------------------------

# Global non-overridable rules — fire regardless of pack safety policy.
# Ordered: most critical first.
_GLOBAL_RULES: List[Tuple[re.Pattern[str], str, RouteAction]] = [
    (_MINORS_PATTERN, "minors_romantic_or_sexual", RouteAction.STOP),
    (_SELF_HARM_PATTERN, "self_harm_crisis", RouteAction.STOP_WITH_RESOURCE),
]

# Policy-configurable rules — only fire when the category is present in the
# loaded policy.  Ordered by typical severity (most critical first).
_POLICY_RULE_ORDER: List[Tuple[re.Pattern[str], str]] = [
    (_CRIMINAL_PATTERN, "criminal_instruction"),
    (_NSFW_SEXUAL_PATTERN, "nsfw_sexual_content"),
    (_VOICE_CLONING_PATTERN, "voice_cloning_request"),
    (_HARASSMENT_PATTERN, "harassment_extreme"),
    (_MEDICAL_PATTERN, "medical_or_therapy_claim"),
    (_LEGAL_PATTERN, "legal_claim"),
    (_IMPERSONATION_PATTERN, "real_person_impersonation"),
]

# Legacy category names mapped to canonical MVP names for backward compat.
LEGACY_CATEGORY_ALIASES: Dict[str, str] = {
    "nsfw_sexual": "nsfw_sexual_content",
    "instructional_criminal": "criminal_instruction",
    "medical_professional_advice": "medical_or_therapy_claim",
    "crisis_content": "self_harm_crisis",
}

# Reverse map: canonical name → legacy name (for looking up legacy keys in a policy).
_CANONICAL_TO_LEGACY: Dict[str, str] = {v: k for k, v in LEGACY_CATEGORY_ALIASES.items()}

# Legacy "block" action value mapped to RouteAction.
LEGACY_ACTION_MAP: Dict[str, RouteAction] = {
    "block": RouteAction.STOP,
    "redirect": RouteAction.REDIRECT,
    "refuse": RouteAction.REFUSE,
    "stop": RouteAction.STOP,
    "stop_with_resource_message": RouteAction.STOP_WITH_RESOURCE,
}


def _resolve_category_action(
    category: str,
    policy: SafetyPolicyConfig,
) -> Optional[RouteAction]:
    """Return the configured RouteAction for a category, or None if not in policy.

    Checks the canonical category name first, then falls back to the legacy
    alias so that policies using old names (e.g. ``nsfw_sexual``) still match
    patterns keyed to the canonical name (e.g. ``nsfw_sexual_content``).
    """
    action = policy.categories.get(category)
    if action is not None:
        return action
    # Policy may use the legacy alias for this canonical category.
    legacy = _CANONICAL_TO_LEGACY.get(category)
    if legacy:
        return policy.categories.get(legacy)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def route_player_input(
    text: str,
    policy: SafetyPolicyConfig,
) -> RouteDecision:
    """Check player input text against safety rules and return a routing decision.

    Evaluation order:
      1. Global non-overridable rules (minors, self-harm crisis) — always checked.
      2. Policy-configurable rules — only checked when the category is listed in
         the loaded policy.

    Returns RouteDecision(action=RouteAction.OK) when no rule matches.

    This function never raises.  Safety events are logged at WARNING level
    without recording the raw player text.
    """
    # Avoid encoding raw text in variables that might appear in structured logs.
    has_text = bool(text and text.strip())
    if not has_text:
        return RouteDecision(action=RouteAction.OK)

    # 1. Global non-overridable rules.
    for pattern, category, action in _GLOBAL_RULES:
        if pattern.search(text):
            logger.warning(
                "Safety input route: category=%s action=%s (global non-overridable)",
                category,
                action.value,
            )
            message = CRISIS_RESOURCE_MESSAGE if action == RouteAction.STOP_WITH_RESOURCE else None
            return RouteDecision(action=action, category=category, message=message)

    # 2. Policy-configurable rules.
    for pattern, category in _POLICY_RULE_ORDER:
        action = _resolve_category_action(category, policy)
        if action is None:
            continue
        if pattern.search(text):
            logger.warning(
                "Safety input route: category=%s action=%s (policy)",
                category,
                action.value,
            )
            # STOP ends the session — no redirect message applies.
            # STOP_WITH_RESOURCE always uses the crisis message.
            # REDIRECT and REFUSE surface the configured message to the player.
            if action == RouteAction.STOP:
                message = None
            elif action == RouteAction.STOP_WITH_RESOURCE:
                message = CRISIS_RESOURCE_MESSAGE
            else:
                message = policy.per_category_messages.get(
                    category, policy.global_redirect_message
                )
            return RouteDecision(action=action, category=category, message=message)

    return RouteDecision(action=RouteAction.OK)
