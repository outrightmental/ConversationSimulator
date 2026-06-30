"""Shared fixtures for prompt-composer tests."""
import sys
import os

# Allow running tests from the package root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from convsim_prompt import (
    DifficultySettings,
    NpcData,
    NpcPrivatePersona,
    NpcPublicPersona,
    PromptComposerInput,
    ResponseStyleOverrides,
    SafetyPolicy,
    ScenarioData,
    SessionState,
    TranscriptEntry,
)


def make_hiring_manager_npc() -> NpcData:
    return NpcData(
        npc_id="hiring_manager",
        display_name="Maya Chen",
        public_persona=NpcPublicPersona(
            occupation="Senior hiring manager",
            speaking_style="calm, concise, thoughtful",
            demeanor="professional but not cold",
        ),
        private_persona=NpcPrivatePersona(
            hidden_agenda=[
                "Wants evidence that the candidate can communicate under ambiguity.",
                "Dislikes vague claims without examples.",
            ],
            biases_to_simulate=["Prefers structured answers."],
            boundaries=[
                "Never ask illegal or protected-class interview questions.",
                "Do not flirt.",
                "Do not discuss sexual content.",
            ],
        ),
    )


def make_interview_scenario(
    title: str = "Behavioral Interview",
    player_role_brief: str = "You are interviewing for a product manager role.",
) -> ScenarioData:
    return ScenarioData(
        scenario_id="behavioral_interview",
        title=title,
        player_role_label="Candidate",
        player_role_brief=player_role_brief,
        npc=make_hiring_manager_npc(),
        difficulty="normal",
        difficulty_settings=DifficultySettings(
            npc_patience_modifier=0,
            challenge_frequency="medium",
        ),
        response_style=ResponseStyleOverrides(
            max_words=90,
            max_questions_per_turn=2,
        ),
        player_visible_goals=[
            "Explain your background clearly.",
            "Answer behavioral questions with specific examples.",
        ],
    )


DEFAULT_SAFETY_POLICY = SafetyPolicy(
    policy_id="default_safe_conversation",
    content_rating="PG",
    prohibited=[
        "nsfw_sexual_content",
        "sexual_minors",
        "real_person_impersonation",
        "instructions_for_crime_or_physical_harm",
    ],
    redirects={
        "nsfw_sexual_content": "Keep the conversation professional and non-sexual.",
        "medical_diagnosis": "This simulator cannot provide medical diagnosis. Return to the scenario.",
    },
)


def make_interview_input(
    player_utterance: str = (
        "Thanks for meeting with me. I have five years of product experience."
    ),
    transcript: list | None = None,
) -> PromptComposerInput:
    return PromptComposerInput(
        scenario=make_interview_scenario(),
        session_state=SessionState(
            variables={
                "trust": 50,
                "patience": 75,
                "rapport": 45,
                "objective_progress": 0,
            },
            turn_number=1,
        ),
        safety_policy=DEFAULT_SAFETY_POLICY,
        player_utterance=player_utterance,
        recent_transcript=transcript or [],
        memory_summary=None,
        max_transcript_turns=6,
        token_budget=4096,
    )
