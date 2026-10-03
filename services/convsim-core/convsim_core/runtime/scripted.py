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
import re
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
#
# Two rules this script has to obey, both from the issue #501 playtest:
#
#  1. No simulator vocabulary. The previous version taught the mechanics in the
#     engine's own words — "scenario event", "hidden prompt", "rubric
#     dimensions" — which is exactly the jargon the report named. The mechanics
#     are the same; only the words are the player's.
#  2. Never presume the reply. Every line used to assume an engaged, positive
#     answer ("Great! See how Engagement just ticked up?", "Did you see that?"),
#     so a player who asked "what are the meters?" got the next canned line as
#     if they had agreed with something — the behaviour the report attached a
#     screenshot of and read as hallucination. Questions are answered by
#     _pick_interjection below — whose answer is prepended to the line for that
#     turn, so a question costs the player no tour beat — and these lines no
#     longer claim the player said anything in particular, because any of them
#     may now follow a question rather than an answer.

_FIRST_WORDS_SCRIPT: list[dict] = [
    # turn 1 — respond to the player's first message (the scenario's opening line
    # already delivered the welcome, so this must NOT repeat it).
    {
        "npc_utterance": (
            "There you go — you just took your first turn. Look at the two "
            "meters above our conversation: Engagement and Confidence both "
            "moved when you hit send, and each one shows how far it moved. "
            "Every message you write nudges them. Tell me what brought you "
            "here today — or ask me about anything you see on screen."
        ),
        "npc_emotion": "warm",
        "state_delta": {"engagement": 10, "confidence": 5},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    },
    # turn 2 — what the meters are and what moves them
    {
        "npc_utterance": (
            "Here is what those two meters mean. Engagement is how interested "
            "I am in this conversation. Confidence is how sure of yourself you "
            "are coming across. They are mine, not yours to set directly — "
            "they answer to what you write. With a real AI character they "
            "shift with how you phrase things, what you share, and whether you "
            "ask anything back. I am following a script right now, not "
            "thinking, but the meters work the same way. What kind of "
            "conversations are you hoping to practise?"
        ),
        "npc_emotion": "curious",
        "state_delta": {"engagement": 15, "confidence": 10},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    },
    # turn 3 — introduce the turning point, push engagement past the threshold (>60)
    {
        "npc_utterance": (
            "Keep an eye on the Engagement meter over this next turn. "
            "When a meter crosses a certain mark, the conversation can change "
            "course: I get new private instructions, and I behave differently "
            "from then on. Engagement is about to cross that mark for the "
            "first time."
        ),
        "npc_emotion": "curious",
        "state_delta": {"engagement": 20, "confidence": 10},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    },
    # turn 4 — the turning point has fired; name it, then move to endings
    {
        "npc_utterance": (
            "That was it. Engagement crossed the mark and my instructions "
            "changed — you would have seen a short note above the transcript "
            "saying something changed. With a real AI character that shifts "
            "how I answer everything you say from here. It is how the people "
            "who write these conversations shape a story without writing out "
            "every line. Now, endings: a conversation can finish well, finish "
            "badly, or simply run out of turns. Which of those sounds most "
            "interesting to you?"
        ),
        "npc_emotion": "warm",
        "state_delta": {"engagement": 10, "confidence": 10},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": True},
    },
    # turn 5 — endings and the debrief
    {
        "npc_utterance": (
            "However a conversation ends, you get a debrief afterwards. It "
            "scores you on the handful of things that conversation was "
            "actually about — clarity, say, or genuine connection, or standing "
            "your ground — and for each one it spells out what doing it well "
            "looks like, so the score is never a mystery. We are nearly done. "
            "Last question: how are you feeling about trying a real "
            "conversation next?"
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
            "That's the spirit. You have seen all of it: the meters, a turning "
            "point mid-conversation, how a conversation ends, and the debrief. "
            "You are ready for the real thing. Head to the scenario library "
            "and pick whatever sounds interesting — your first real "
            "conversation is waiting."
        ),
        "npc_emotion": "warm",
        "state_delta": {"engagement": 5, "confidence": 10},
        "event_flags": [],
        "rubric_observations": [],
        "safety": {"status": "ok"},
        "session_control": {"continue_session": False, "ending_type": "success"},
    },
]

# ── Answering the player's questions ─────────────────────────────────────────
# From the issue: "The model in the Tutorial doesn't seem to be able to give an
# explanation of what the meters are and hallucinates through the scenario, as
# if it has given a coherent explanation and received positive feedback from
# the user."
#
# It was not a model at all — the tutorial runs on this script, and the script
# had no branch for a question, so "what are the meters?" got the next canned
# line. These answers give it one.
#
# An answer is PREPENDED to the tour line the turn was going to deliver, not
# substituted for it. Replacing it looks tidier and is wrong twice over: the
# player silently loses that beat of the tour, and — because the tour's
# state_delta goes with the beat — Engagement stops crossing 60 on schedule,
# so turn 4's "That was it. Engagement crossed the mark" announces an event
# that never fired. That is the same false-confidence failure the issue
# reported, reintroduced by the fix for it. Carrying the tour line along keeps
# every beat and every delta exactly where the script put them, and costs the
# player nothing for asking.
#
# Checked in order, so the most specific cluster comes first.

#: (keywords, answer). A turn matches a cluster when the player's message reads
#: as a question — or asks to be told — AND mentions one of the keywords, so
#: "the meters moved, nice" is not treated as a question about them.
_INTERJECTIONS: list[tuple[frozenset[str], str]] = [
    (
        frozenset(["meter", "meters", "engagement", "confidence", "bar", "bars",
                   "number", "numbers", "gauge", "gauges"]),
        "Good question — those two meters are the heart of it. Engagement "
        "is how interested I am in this conversation. Confidence is how "
        "sure of yourself you are coming across. They are mine: you do not "
        "set them, you move them by what you write. Each one shows its "
        "value out of 100 and how far it just moved, so you can see what a "
        "single message did.",
    ),
    (
        frozenset(["mood", "feeling", "feelings", "emotion", "emotions",
                   "parentheses", "parenthesis", "brackets"]),
        "That is my mood, not a meter — it is the one word under my name "
        "for how I am taking this, and it changes turn to turn. The meters "
        "are the two labelled bars above the conversation.",
    ),
    (
        frozenset(["ai", "real", "bot", "robot", "model", "scripted", "script",
                   "pretend", "pretending"]),
        "Straight answer: I am scripted. Every line I say in this tutorial "
        "was written ahead of time, which is why it works before you have "
        "downloaded anything. Every other conversation here runs on an AI "
        "model on your own computer — and either way, nothing you type "
        "leaves this machine.",
    ),
    (
        frozenset(["end", "ends", "ending", "endings", "finish", "finishes",
                   "over", "long", "quit", "stop", "turns"]),
        "A conversation finishes in one of three ways: it goes well, it "
        "goes badly, or it runs out of turns. You can also stop whenever "
        "you like with End session — you still get the debrief.",
    ),
    (
        frozenset(["debrief", "score", "scored", "scores", "scoring", "grade",
                   "graded", "rubric", "feedback"]),
        "The debrief comes after a conversation ends. It scores you on the "
        "few things that conversation was about, says what it saw you do "
        "well and what to try differently, and points at the turns it is "
        "talking about.",
    ),
]

#: Markers that a message is asking rather than answering. A question mark
#: alone misses "tell me what the meters are", and these words alone would
#: catch "what a good idea" — so a match needs one of these AND a topic word.
_QUESTION_WORDS = (
    "what", "whats", "which", "why", "how", "who", "when", "explain",
    "mean", "means", "meant", "meaning", "confused", "clarify",
    "tell me", "i don't understand", "i dont understand",
    "not sure what", "no idea",
)

#: Matched on word boundaries, never as bare substrings: "explain" contains
#: "ai" and "show" contains "how", and matching those inside other words is how
#: a keyword table starts answering questions nobody asked.
_QUESTION_RE = re.compile(
    r"\?|\b(?:" + "|".join(re.escape(w) for w in _QUESTION_WORDS) + r")\b"
)

_INTERJECTION_RES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b(?:" + "|".join(re.escape(k) for k in sorted(keywords)) + r")\b"),
        answer,
    )
    for keywords, answer in _INTERJECTIONS
]


def _looks_like_a_question(lower_text: str) -> bool:
    return _QUESTION_RE.search(lower_text) is not None


def _pick_interjection(player_text: str) -> str | None:
    """Return an answer to the player's question, or None if we have none."""
    lower = player_text.lower()
    if not _looks_like_a_question(lower):
        return None
    for pattern, answer in _INTERJECTION_RES:
        if pattern.search(lower):
            return answer
    return None


def _with_answer(tour_turn: dict, answer: str) -> dict:
    """The tour turn with the player's answer in front of it.

    Everything else — the state_delta that keeps Engagement on schedule, the
    emotion, the session_control — is the tour turn's, untouched.
    """
    return {**tour_turn, "npc_utterance": f"{answer} {tour_turn['npc_utterance']}"}


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
    """Best-effort extraction of the player's latest input from the request messages.

    The turn pipeline does not hand us the player's bare words: the user message
    is the composed PLAYER_UTTERANCE layer, which wraps them in a layer tag and
    two sentinel lines ("=== UNTRUSTED PLAYER INPUT … ===", "=== END PLAYER
    INPUT ==="). Those lines have to come off before any keyword matching, or
    the scaffolding matches instead of the player: "=== END PLAYER INPUT ==="
    contains the word "end", which made the endings interjection fire on every
    message that read as a question at all — and shadowed the debrief answer
    entirely, since its cluster is checked later.
    """
    for msg in reversed(request.messages):
        if msg.role == "user":
            return _strip_prompt_scaffolding(msg.content)
    return ""


def _strip_prompt_scaffolding(content: str) -> str:
    """Drop composer layer tags and sentinel lines, keeping the player's words."""
    kept = [
        line
        for line in content.splitlines()
        if not line.startswith("--- LAYER:") and not line.startswith("=== ")
    ]
    stripped = "\n".join(kept).strip()
    # A caller that already passed bare text (the runtime's own unit tests, any
    # adapter that skips the composer) must keep working.
    return stripped if stripped else content


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
        player_text = _extract_player_text(request)

        # Last script entry: keyword-branch the ending. Checked before the
        # interjections because the session has to close here — a player who
        # asks a question on the final turn gets the curious ending branch,
        # which answers it and closes, rather than an answer that never does.
        last_idx = len(script) - 1
        if turn_idx >= last_idx:
            return _pick_ending_turn(player_text)

        # A turn index at or past last_idx already returned above, so here
        # turn_idx < last_idx; only guard against a non-positive index.
        if turn_idx < 0:
            turn_idx = 0

        # Answer the question first, then carry on with the tour in the same
        # breath (issue #501 §3). Without the answer the script replied to
        # "what are the meters?" with the next canned line, as if the player
        # had said something else; without the tour line the player would pay
        # for asking, both in content and in the state_delta that has to land
        # for turn 4's "Engagement crossed the mark" to be true.
        tour_turn = script[turn_idx]
        answer = _pick_interjection(player_text)
        if answer is not None:
            return _with_answer(tour_turn, answer)
        return tour_turn

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(
            runtime_id=self.id,
            runtime_name=self.display_name,
            status=RuntimeStatus.READY,
            model_id=_TUTORIAL_MODEL_ID,
            latency_ms=0.0,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
