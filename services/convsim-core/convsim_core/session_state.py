# SPDX-License-Identifier: Apache-2.0
"""Session state enum for convsim-core.

These string values are the canonical names shared between the frontend
(packages/shared-types/src/session.ts SessionState enum) and the backend.
Both sides must use these exact strings when serialising state over the API
or WebSocket.
"""

from __future__ import annotations

from enum import Enum


class SessionState(str, Enum):
    """All states a conversation session can occupy."""

    NOT_STARTED = "NotStarted"
    LOADING_MODEL = "LoadingModel"
    LOADING_SCENARIO = "LoadingScenario"
    BRIEFING = "Briefing"
    NPC_OPENING = "NpcOpening"
    PLAYER_TURN_LISTENING = "PlayerTurnListening"
    PLAYER_TURN_REVIEW = "PlayerTurnReview"
    NPC_THINKING = "NpcThinking"
    NPC_SPEAKING = "NpcSpeaking"
    SCENARIO_EVENT = "ScenarioEvent"
    DEBRIEF_GENERATING = "DebriefGenerating"
    DEBRIEF_READY = "DebriefReady"
    ENDED = "Ended"
    ERROR = "Error"
