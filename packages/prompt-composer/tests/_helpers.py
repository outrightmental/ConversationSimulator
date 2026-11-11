"""Shared fixtures for prompt-composer tests."""
import sys
import os

# Allow running tests from the package root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from convsim_prompt import (
    DifficultySettings,
    NpcData,
    NpcPrivatePersona,
    NpcPublicPersona,
    PromptComposerInput,
    ResponseStyleOverrides,
    RubricDimension,
    SafetyPolicy,
    ScenarioData,
    ScenarioRubric,
    SessionState,
    StateVariable,
    StateVariableCue,
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
        difficulty="standard",
        difficulty_settings=DifficultySettings(
            patience=50,
            volatility=50,
            disclosure=50,
            time_pressure=50,
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


def make_interview_rubric() -> ScenarioRubric:
    """A two-dimension rubric shaped like packs/official/job-interview-basic's."""
    return ScenarioRubric(
        rubric_id="interview_rubric",
        title="Interview Performance Rubric",
        dimensions=[
            RubricDimension(
                id="specificity",
                name="Specificity",
                description="Uses concrete examples instead of generic claims.",
                low="Mostly generic claims.",
                medium="Some examples but thin details.",
                high="Specific examples with context, action, and result.",
                weight=0.6,
            ),
            RubricDimension(
                id="self_awareness",
                name="Self-awareness",
                description="Shows reflection and learning.",
                low="Blames others or avoids weakness.",
                medium="Acknowledges lessons in simple terms.",
                high="Owns mistakes and explains growth.",
                weight=0.4,
            ),
        ],
    )


def make_rubric_interview_input(**kwargs) -> PromptComposerInput:
    """make_interview_input with the scenario's rubric loaded, as a pack scenario has."""
    inp = make_interview_input(**kwargs)
    inp.scenario.rubric = make_interview_rubric()
    return inp


def make_interview_state_variables() -> list:
    """State variables shaped like behavioral_interview's: two authored, one baseline it declares."""
    return [
        StateVariable(
            name="impression", min=0, max=100, max_delta_per_turn=6,
            description="Maya's overall read of the candidate as a hire.",
        ),
        StateVariable(
            name="specificity_score", min=0, max=100, max_delta_per_turn=15,
            cues=[StateVariableCue(
                direction="above", threshold=75,
                text="The candidate just gave a specific answer. Follow up on it.",
            )],
        ),
        StateVariable(name="rapport", min=0, max=100, max_delta_per_turn=10),
    ]


def make_stateful_interview_input(**kwargs) -> PromptComposerInput:
    """make_interview_input with state variables of the scenario's own (issue #580)."""
    inp = make_interview_input(**kwargs)
    inp.scenario.state_variables = make_interview_state_variables()
    inp.session_state.variables.update({"impression": 50, "specificity_score": 50})
    return inp


def make_full_interview_input(**kwargs) -> PromptComposerInput:
    """An input with every optional system layer filled: a rubric, state, a fired event."""
    inp = make_stateful_interview_input(**kwargs)
    inp.scenario.rubric = make_interview_rubric()
    inp.scenario_event_instructions = ["Maya is losing confidence. Begin wrapping up."]
    return inp
