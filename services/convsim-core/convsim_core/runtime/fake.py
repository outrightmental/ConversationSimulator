# SPDX-License-Identifier: Apache-2.0
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

_MODELS = [
    ModelInfo(id="fake-small", name="Fake Small", size_category="small", context_length=4096),
    ModelInfo(id="fake-large", name="Fake Large", size_category="large", context_length=32768),
]

_PLAIN_RESPONSE = "This is a fake response for testing and demo purposes."

_STRUCTURED_RESPONSE: dict = {
    "npc_utterance": "Hello there. I am a simulated NPC.",
    "npc_emotion": "neutral",
    "state_delta": {},
    "event_flags": [],
    "rubric_observations": [],
    "safety": {"status": "ok"},
    "session_control": {"continue_session": True},
}

_DEBRIEF_NARRATIVE_RESPONSE: dict = {
    "summary": (
        "This was a simulated practice session. "
        "You engaged with the scenario and completed the conversation."
    ),
    "strengths": [
        "You maintained engagement throughout the session.",
    ],
    "improvements": [
        "Consider exploring different conversational strategies in a replay.",
    ],
    "missed_opportunities": [
        "Look for moments where asking a follow-up question could have deepened the dialogue.",
    ],
    "turning_points": [],
    "replay_suggestions": [
        "Try adjusting your opening approach to set a different tone.",
    ],
}

# Discriminant key present in the debrief narrative schema but not the NPC turn schema.
_DEBRIEF_SCHEMA_DISCRIMINANT = "replay_suggestions"


@register("fake")
class FakeChatRuntime(ChatRuntime):
    """Deterministic fake runtime for tests and text-only demo development.

    Streams tokens word-by-word with no real model calls. Always returns the
    same response so test assertions are stable.
    """

    @property
    def id(self) -> str:
        return "fake"

    @property
    def display_name(self) -> str:
        return "Fake (deterministic)"

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
            # Return the debrief narrative response when the debrief schema is detected.
            if _DEBRIEF_SCHEMA_DISCRIMINANT in (request.json_schema.get("properties") or {}):
                chosen = _DEBRIEF_NARRATIVE_RESPONSE
            else:
                chosen = _STRUCTURED_RESPONSE
            response_text = json.dumps(chosen)
            structured = chosen
        else:
            response_text = _PLAIN_RESPONSE
            structured = None

        words = response_text.split()
        for word in words:
            await asyncio.sleep(0)
            yield ChatToken(text=word + " ")

        model_id = request.model_id or "fake-small"
        input_tokens = sum(len(m.content.split()) for m in request.messages)
        yield ChatFinal(
            text=response_text,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=len(words),
            structured=structured,
        )

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(
            runtime_id=self.id,
            runtime_name=self.display_name,
            status=RuntimeStatus.READY,
            model_id="fake-small",
            latency_ms=0.0,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
