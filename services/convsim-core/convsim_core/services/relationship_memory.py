# SPDX-License-Identifier: Apache-2.0
"""Extract and persist a bounded NPC relationship recap from session debrief data.

The recap is built deterministically from the debrief (no extra LLM call),
stored in the relationship_state table, and injected into the NPC prompt on the
next session as a capped context fragment.

Recap schema (schema_version "1"):
  {
    "schema_version": "1",
    "session_count": int,
    "last_session_at": str,       # ISO timestamp
    "key_observations": [str],    # max 5 items, each ≤ 150 chars
    "player_style_tags": [str],   # max 3 items, each ≤ 30 chars
    "last_outcome": str
  }

Safety constraints:
  - Items are sourced from the debrief "improvements" list (neutral coaching
    language). They describe player behaviour, not NPC leverage.
  - The prompt injection layer explicitly prohibits the NPC from referencing
    these observations directly, using them as threats, or deviating from the
    safety policy (#203).
  - The recap is bounded to avoid accumulating disproportionate context over
    many sessions (max 5 observations, rolling window).
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from convsim_core.storage.repositories.relationship_repo import (
    get_relationship_recap,
    upsert_relationship_recap,
)

logger = logging.getLogger(__name__)

# Hard bounds on recap content.
_MAX_OBSERVATIONS = 5
_MAX_OBSERVATION_CHARS = 150
_MAX_STYLE_TAGS = 3
_MAX_STYLE_TAG_CHARS = 30

# Dimension score thresholds for deriving style tags.
_WEAK_SCORE_THRESHOLD = 40.0
_STRONG_SCORE_THRESHOLD = 70.0

# Neutral, non-adversarial labels derived from dimension performance.
# These describe observable player behaviour, not leverage against the player.
_WEAK_TAGS: Dict[str, str] = {
    "listening": "tends to interrupt",
    "questioning": "asks few questions",
    "empathy": "low empathy shown",
    "assertiveness": "hesitant under pressure",
    "clarity": "unclear communicator",
}
_STRONG_TAGS: Dict[str, str] = {
    "listening": "active listener",
    "questioning": "probes well",
    "empathy": "high empathy",
    "assertiveness": "direct",
    "clarity": "clear communicator",
}

RECAP_SCHEMA_VERSION = "1"


def _truncate(text: str, max_chars: int) -> str:
    return text[:max_chars] if len(text) > max_chars else text


def _derive_style_tags(scores: Dict[str, float]) -> List[str]:
    """Derive at most _MAX_STYLE_TAGS from debrief dimension scores."""
    tags: List[str] = []
    for dim_id in sorted(scores):
        if len(tags) >= _MAX_STYLE_TAGS:
            break
        score = scores[dim_id]
        if score <= _WEAK_SCORE_THRESHOLD and dim_id in _WEAK_TAGS:
            tags.append(_WEAK_TAGS[dim_id])
        elif score >= _STRONG_SCORE_THRESHOLD and dim_id in _STRONG_TAGS:
            tags.append(_STRONG_TAGS[dim_id])
    return tags


def extract_recap(
    *,
    outcome: str,
    scores: Dict[str, float],
    improvements: List[str],
    generated_at: str,
    existing_recap: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build an updated relationship recap from the latest debrief data.

    Pure function — no DB or LLM calls.  Always returns a valid recap dict.
    """
    prev_count: int = (
        existing_recap.get("session_count", 0) if existing_recap else 0
    )
    prev_observations: List[str] = (
        existing_recap.get("key_observations", []) if existing_recap else []
    )

    # At most 2 improvement points from this session (neutral coaching language).
    new_obs: List[str] = [
        _truncate(item, _MAX_OBSERVATION_CHARS)
        for item in (improvements or [])[:2]
    ]

    # Rolling window: prepend newest observations, cap at _MAX_OBSERVATIONS.
    all_observations = (new_obs + prev_observations)[:_MAX_OBSERVATIONS]

    style_tags = _derive_style_tags(scores)

    return {
        "schema_version": RECAP_SCHEMA_VERSION,
        "session_count": prev_count + 1,
        "last_session_at": generated_at,
        "key_observations": all_observations,
        "player_style_tags": style_tags,
        "last_outcome": outcome,
    }


def validate_recap(recap: Dict[str, Any]) -> bool:
    """Return True iff recap satisfies all schema constraints."""
    if not isinstance(recap, dict):
        return False
    if recap.get("schema_version") != RECAP_SCHEMA_VERSION:
        return False
    obs = recap.get("key_observations", [])
    if not isinstance(obs, list) or len(obs) > _MAX_OBSERVATIONS:
        return False
    if any(not isinstance(o, str) or len(o) > _MAX_OBSERVATION_CHARS for o in obs):
        return False
    tags = recap.get("player_style_tags", [])
    if not isinstance(tags, list) or len(tags) > _MAX_STYLE_TAGS:
        return False
    if any(not isinstance(t, str) or len(t) > _MAX_STYLE_TAG_CHARS for t in tags):
        return False
    if not isinstance(recap.get("session_count", 0), int):
        return False
    return True


def update_relationship_memory(
    conn: sqlite3.Connection,
    *,
    npc_id: str,
    pack_id: str,
    outcome: str,
    scores: Dict[str, float],
    improvements: List[str],
    generated_at: str,
) -> None:
    """Extract, validate, and persist an updated relationship recap.

    Silently skips persistence if recap validation fails so a corrupt or
    unexpected input never rolls back a completed debrief.
    """
    try:
        existing = get_relationship_recap(conn, npc_id, pack_id)
        recap = extract_recap(
            outcome=outcome,
            scores=scores,
            improvements=improvements,
            generated_at=generated_at,
            existing_recap=existing,
        )
        if not validate_recap(recap):
            logger.warning(
                "Relationship recap failed validation for npc=%s pack=%s — skipping",
                npc_id, pack_id,
            )
            return
        upsert_relationship_recap(conn, npc_id, pack_id, recap, recap["session_count"])
        logger.debug(
            "Updated relationship memory for npc=%s pack=%s sessions=%d",
            npc_id, pack_id, recap["session_count"],
        )
    except Exception:
        logger.exception(
            "Unexpected error updating relationship memory for npc=%s pack=%s",
            npc_id, pack_id,
        )
