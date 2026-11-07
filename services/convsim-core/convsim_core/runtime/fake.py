# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from convsim_core.runtime.base import ChatRuntime
from convsim_core.runtime.registry import register
from convsim_core.runtime.types import (
    ChatChunk,
    ChatFinal,
    ChatProgress,
    ChatRequest,
    ChatTimings,
    ChatToken,
    ModelInfo,
    RuntimeCapabilities,
    RuntimeHealth,
    RuntimeStatus,
)

# Deterministic speeds the fake engine "measures", so timing tests have fixed
# figures to assert against (issue #519): one millisecond per prompt token read,
# two per token written.
FAKE_READING_TPS = 1000.0
FAKE_WRITING_TPS = 500.0


def deterministic_timings(input_tokens: int, output_tokens: int) -> ChatTimings:
    """The engine report a fake or scripted runtime attaches to its ChatFinal."""
    prompt_ms = round(input_tokens * (1000.0 / FAKE_READING_TPS), 1)
    generation_ms = round(output_tokens * (1000.0 / FAKE_WRITING_TPS), 1)
    return ChatTimings(
        prompt_tokens=input_tokens,
        cached_tokens=0,
        evaluated_tokens=input_tokens,
        output_tokens=output_tokens,
        prompt_ms=prompt_ms,
        generation_ms=generation_ms,
        reading_tps=FAKE_READING_TPS,
        writing_tps=FAKE_WRITING_TPS,
    )


def deterministic_progress(input_tokens: int) -> list[ChatProgress]:
    """Two reading-progress chunks: nothing read yet, then everything read."""
    return [
        ChatProgress(stage="reading", processed=0, total=input_tokens, cached=0),
        ChatProgress(stage="reading", processed=input_tokens, total=input_tokens, cached=0),
    ]

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

    def chat_stream(self, request: ChatRequest) -> AsyncGenerator[ChatChunk, None]:
        return self._stream(request)

    async def _stream(self, request: ChatRequest) -> AsyncGenerator[ChatChunk, None]:
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
        input_tokens = sum(len(m.content.split()) for m in request.messages)
        # A real engine reports prompt progress before the first token; the fake
        # does the same with fixed values so the pipeline's stage timing is
        # exercised in tests (issue #519).
        for progress in deterministic_progress(input_tokens):
            await asyncio.sleep(0)
            yield progress
        for word in words:
            await asyncio.sleep(0)
            yield ChatToken(text=word + " ")

        model_id = request.model_id or "fake-small"
        yield ChatFinal(
            text=response_text,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=len(words),
            structured=structured,
            timings=deterministic_timings(input_tokens, len(words)),
            finish_reason="stop",
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
