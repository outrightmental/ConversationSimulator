# SPDX-License-Identifier: Apache-2.0
"""Scripted NPC runtime adapter — table-driven, zero inference.

Returns deterministic pre-authored responses from a turn script embedded in
pack content.  Labeled "Scripted tutorial" in the UI so players are never
misled about whether AI is generating responses.

Currently bundles the "First Words" tutorial script.  The model_id field of
the ChatRequest identifies which script to use (defaults to the tutorial).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from convsim_core.runtime.base import ChatRuntime
from convsim_core.runtime.registry import register
from convsim_core.runtime.types import (
    ChatFinal,
    ChatRequest,
    ChatToken,
    ModelInfo,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeStatus,
)

# ── First Words tutorial script ───────────────────────────────────────────────
# Each entry is the NPC response for that 1-based game turn.
# state_delta values are bounded by the scenario's max_delta_per_turn.
# The final turn sets session_control.continue_session=False to end the session
# and trigger the debrief.

_FIRST_WORDS_SCRIPT: list[dict] = [
    # turn 1 — respond to the player's first message (the scenario's opening line
    # already delivered the welcome, so this must NOT repeat it).
    {
        "npc_utterance": (
            "There you go — you just took your very first turn! Look up at the two "
            "meters: Engagement and Confidence both nudged the moment you hit send. "
            "Every message you write moves them a little; that's the heartbeat of "
            "every scenario. Keep going — tell me what brought you here today."
        ),
        "npc_emotion": "warm",
        "state_delta": {"engagement": 10, "confidence": 5},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    },
    # turn 2 — explain the meters
    {
        "npc_utterance": (
            "Great! See how Engagement just ticked up? Every message you send shifts "
            "the conversation state. In real AI-powered scenarios these meters respond "
            "dynamically to how you phrase things, what you reveal, and whether you "
            "ask follow-up questions. Right now I'm scripted — not AI-generated — "
            "but the meter logic is identical. "
            "Tell me: what kind of conversations are you hoping to practise?"
        ),
        "npc_emotion": "curious",
        "state_delta": {"engagement": 15, "confidence": 10},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    },
    # turn 3 — introduce events, push engagement past the event threshold (>60)
    {
        "npc_utterance": (
            "That sounds like a great goal. Now watch closely — I'm about to trigger "
            "a *scenario event*. Events fire automatically when a meter crosses a "
            "threshold or a flag is set. They inject new instructions into the NPC's "
            "hidden prompt, changing how I behave for the rest of the conversation. "
            "You're about to see Engagement cross 60 for the first time..."
        ),
        "npc_emotion": "curious",
        "state_delta": {"engagement": 20, "confidence": 10},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    },
    # turn 4 — warm_moment event has fired; acknowledge it
    {
        "npc_utterance": (
            "Did you see that? The warm_moment event just fired — Engagement crossed "
            "60 and my hidden instructions shifted. In a live AI scenario that "
            "would change how I respond to everything you say from here on. "
            "Events are how pack authors shape narrative beats without scripting every line. "
            "Now let's talk about how a session ends. There are three ways a "
            "conversation can finish: success, failure, or timeout. "
            "Which sounds most interesting to you — winning, recovering from a stumble, "
            "or seeing what happens when time runs out?"
        ),
        "npc_emotion": "warm",
        "state_delta": {"engagement": 10, "confidence": 10},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    },
    # turn 5 — explain endings and the debrief
    {
        "npc_utterance": (
            "After a session ends — however it ends — you get a debrief. "
            "The debrief scores you against the scenario's rubric dimensions: "
            "things like Clarity, Genuine Connection, or Assertiveness depending "
            "on what the pack is testing. Each dimension has a low/medium/high "
            "scoring guide so you know exactly what 'doing well' looks like. "
            "We're almost at the end of this tutorial. One last question: "
            "how are you feeling about trying a real conversation next?"
        ),
        "npc_emotion": "warm",
        "state_delta": {"engagement": 10, "confidence": 15},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    },
    # turn 6 — keyword-branched ending (override in _pick_ending_turn)
    {
        "npc_utterance": (
            "That's the spirit! You've covered all the basics: meters, events, "
            "ending conditions, and the debrief. You're ready for the real thing. "
            "Head to the scenario library and pick whatever sounds interesting — "
            "your first real conversation is waiting."
        ),
        "npc_emotion": "warm",
        "state_delta": {"engagement": 5, "confidence": 10},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": False, "ending_type": "success"},
    },
]

# Keyword clusters for the three ending branches on turn 6.
_ENDING_EXCITED_KEYWORDS = frozenset(
    ["love", "excited", "great", "amazing", "awesome", "fantastic",
     "ready", "can't wait", "yes", "definitely", "absolutely"]
)
_ENDING_CURIOUS_KEYWORDS = frozenset(
    ["how", "why", "what", "curious", "wonder", "interesting",
     "tell me", "more about", "explain", "question", "unsure", "not sure"]
)


def _pick_ending_turn(player_text: str) -> dict:
    """Return the turn-6 scripted response keyed to the player's latest input."""
    lower = player_text.lower()

    if any(kw in lower for kw in _ENDING_EXCITED_KEYWORDS):
        return {
            "npc_utterance": (
                "I love the enthusiasm! That energy is exactly what makes practice "
                "sessions click. Jump straight into the scenario library — pick "
                "something that excites you and see how far you can go. "
                "Your first real conversation is ready when you are."
            ),
            "npc_emotion": "impressed",
            "state_delta": {"engagement": 10, "confidence": 15},
            "event_flags": [],
            "rubric_observations": [],
            "safety": {"status": "ok"},
            "session_control": {"continue_session": False, "ending_type": "success"},
        }

    if any(kw in lower for kw in _ENDING_CURIOUS_KEYWORDS):
        return {
            "npc_utterance": (
                "Curiosity is the best starting point. Every scenario has a rubric "
                "that spells out exactly what's being measured — you can read it "
                "before you start. And if something surprises you mid-conversation, "
                "the debrief will explain it. Head to the library and explore — "
                "the scenarios will answer your questions better than I can."
            ),
            "npc_emotion": "curious",
            "state_delta": {"engagement": 5, "confidence": 10},
            "event_flags": [],
            "rubric_observations": [],
            "safety": {"status": "ok"},
            "session_control": {"continue_session": False, "ending_type": "success"},
        }

    # Default: steady/measured response
    return {
        "npc_utterance": (
            "That's completely understandable. Take your time — the library is "
            "there whenever you're ready. You can replay any scenario as many "
            "times as you like, and each attempt is private. "
            "There's no rush. Just start when it feels right."
        ),
        "npc_emotion": "neutral",
        "state_delta": {"engagement": 5, "confidence": 5},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": False, "ending_type": "success"},
    }


_DEBRIEF_RESPONSE: dict = {
    "summary": (
        "You completed the First Words tutorial. You learned how state meters track "
        "conversation dynamics, how scenario events fire at threshold crossings, and "
        "how the debrief rubric scores your performance on each dimension."
    ),
    "strengths": [
        "You engaged with the tutorial prompts and advanced through all the concepts.",
        "You saw a live scenario event fire — a key mechanic in every pack.",
    ],
    "improvements": [
        "In real scenarios, try varying how you phrase things to see how the meters respond differently.",
    ],
    "missed_opportunities": [],
    "turning_points": [
        {
            "turn_number": 3,
            "description": (
                "The warm_moment event fired — this is where Engagement crossed 60 "
                "and the NPC instructions shifted."
            ),
            "impact": "positive",
        },
    ],
    "replay_suggestions": [
        "Jump into a real scenario from the library — the behavioral interview is a great first challenge.",
    ],
}

_DEBRIEF_SCHEMA_DISCRIMINANT = "replay_suggestions"

_TUTORIAL_MODEL_ID = "first-words-tutorial"

_MODELS = [
    ModelInfo(
        id=_TUTORIAL_MODEL_ID,
        name="First Words Tutorial",
        size_category=None,
        context_length=None,
    ),
]


def _extract_player_text(request: ChatRequest) -> str:
    """Best-effort extraction of the player's latest input from the request messages."""
    for msg in reversed(request.messages):
        if msg.role == "user":
            return msg.content
    return ""


@register("scripted")
class ScriptedChatRuntime(ChatRuntime):
    """Deterministic scripted NPC runtime — table-driven, zero inference.

    Implements the same ChatRuntime interface as llama.cpp and Ollama adapters
    but returns pre-authored responses in sequence, using the scripted_turn_index
    field of the request to select the correct turn.  On the final scripted turn
    keyword matching on the player's latest input selects one of three ending branches.

    Always labeled "Scripted tutorial" so the UI can display an honest label.
    """

    @property
    def id(self) -> str:
        return "scripted"

    @property
    def display_name(self) -> str:
        return "Scripted tutorial"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            streaming=True,
            json_schema=True,
            grammar=False,
            tool_calling=False,
            embeddings=False,
        )

    async def list_models(self) -> list[ModelInfo]:
        return list(_MODELS)

    def chat_stream(self, request: ChatRequest) -> AsyncGenerator[ChatToken | ChatFinal, None]:
        return self._stream(request)

    async def _stream(self, request: ChatRequest) -> AsyncGenerator[ChatToken | ChatFinal, None]:
        if request.json_schema is not None:
            if _DEBRIEF_SCHEMA_DISCRIMINANT in (request.json_schema.get("properties") or {}):
                chosen = _DEBRIEF_RESPONSE
            else:
                chosen = self._pick_npc_turn(request)
            response_text = json.dumps(chosen)
            structured = chosen
        else:
            response_text = "This is a scripted tutorial response."
            structured = None

        words = response_text.split()
        for word in words:
            await asyncio.sleep(0)
            yield ChatToken(text=word + " ")

        input_tokens = sum(len(m.content.split()) for m in request.messages)
        yield ChatFinal(
            text=response_text,
            model_id=_TUTORIAL_MODEL_ID,
            input_tokens=input_tokens,
            output_tokens=len(words),
            structured=structured,
        )

    def _pick_npc_turn(self, request: ChatRequest) -> dict:
        """Select the scripted NPC turn for the current game turn."""
        turn_idx = (request.scripted_turn_index or 1) - 1  # 0-based index
        script = _FIRST_WORDS_SCRIPT

        # Last script entry: keyword-branch the ending
        last_idx = len(script) - 1
        if turn_idx >= last_idx:
            player_text = _extract_player_text(request)
            return _pick_ending_turn(player_text)

        # Clamp to valid range (cycle from last non-ending entry if we overshoot)
        if turn_idx < 0:
            turn_idx = 0
        elif turn_idx >= last_idx:
            turn_idx = last_idx - 1

        return script[turn_idx]

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(
            runtime_id=self.id,
            runtime_name=self.display_name,
            status=RuntimeStatus.READY,
            model_id=_TUTORIAL_MODEL_ID,
            latency_ms=0.0,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
