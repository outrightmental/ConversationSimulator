# SPDX-License-Identifier: Apache-2.0
"""Hardcoded scenario definitions for the turn pipeline.

These mirror the TypeScript SCENARIOS dict in apps/api/src/data/scenarios.ts.
Each entry provides the ScenarioData needed by the prompt composer plus
pipeline-level metadata (max_turns, supported_languages).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from convsim_prompt.types import (
    DifficultySettings,
    NpcData,
    NpcPrivatePersona,
    NpcPublicPersona,
    ResponseStyleOverrides,
    ScenarioData,
)
from convsim_core.scenario_state import ScenarioEvent


@dataclass
class ScenarioInfo:
    """Full scenario metadata used by the turn pipeline."""
    scenario_data: ScenarioData
    max_turns: int
    supported_languages: List[str]
    difficulty_options: Dict[str, DifficultySettings]
    opening_npc_says: str
    # Optional per-scenario simulation config; None means use baseline defaults.
    state_variable_overrides: Optional[Dict[str, Any]] = None
    events: Optional[List[ScenarioEvent]] = None
    ending_conditions: Optional[Dict[str, Any]] = None

    def get_scenario_data(self, difficulty: str) -> ScenarioData:
        """Return a ScenarioData with difficulty settings applied."""
        diff_settings = self.difficulty_options.get(
            difficulty,
            self.difficulty_options.get("standard", DifficultySettings()),
        )
        return ScenarioData(
            scenario_id=self.scenario_data.scenario_id,
            title=self.scenario_data.title,
            player_role_label=self.scenario_data.player_role_label,
            player_role_brief=self.scenario_data.player_role_brief,
            npc=self.scenario_data.npc,
            difficulty=difficulty,
            difficulty_settings=diff_settings,
            response_style=self.scenario_data.response_style,
            opening_npc_says=self.opening_npc_says,
            player_visible_goals=self.scenario_data.player_visible_goals,
        )


SCENARIOS: Dict[str, ScenarioInfo] = {
    "behavioral_interview": ScenarioInfo(
        scenario_data=ScenarioData(
            scenario_id="behavioral_interview",
            title="Behavioral Interview",
            player_role_label="Candidate",
            player_role_brief="You are interviewing for a product manager role.",
            npc=NpcData(
                npc_id="interviewer_alex",
                display_name="Alex Chen",
                public_persona=NpcPublicPersona(
                    occupation="Senior HR Manager at a mid-size tech company",
                    speaking_style="Professional, direct, and methodical. Uses structured questions.",
                    demeanor="Neutral and evaluative. Maintains professionalism throughout.",
                ),
                private_persona=NpcPrivatePersona(
                    hidden_agenda=[
                        "Assess candidate's self-awareness and communication clarity",
                        "Probe for specific behavioral examples, not generic answers",
                        "Notice whether the candidate takes ownership of past situations",
                    ],
                    biases_to_simulate=[
                        "Slightly skeptical of candidates who answer too quickly without thinking",
                    ],
                    boundaries=[
                        "Never make discriminatory remarks",
                        "Stay within professional interview norms",
                    ],
                ),
            ),
            player_visible_goals=[
                "Demonstrate relevant experience with clear STAR-format examples",
                "Show self-awareness about strengths and areas for growth",
                "Ask thoughtful questions about the role",
            ],
        ),
        max_turns=18,
        supported_languages=["en"],
        difficulty_options={
            "warm":        DifficultySettings(patience=80, volatility=20, disclosure=70, time_pressure=20),
            "standard":    DifficultySettings(patience=50, volatility=50, disclosure=50, time_pressure=50),
            "hard":        DifficultySettings(patience=25, volatility=70, disclosure=25, time_pressure=60),
            "adversarial": DifficultySettings(patience=10, volatility=90, disclosure=10, time_pressure=80),
        },
        opening_npc_says=(
            "Thanks for coming in today. I'm Alex Chen from HR. "
            "Tell me a little about yourself and why you're interested in this role."
        ),
    ),

    "hostile_executive_interview": ScenarioInfo(
        scenario_data=ScenarioData(
            scenario_id="hostile_executive_interview",
            title="Hostile Executive Interview",
            player_role_label="Candidate",
            player_role_brief="You are interviewing for a VP-level role. The interviewer is a skeptical executive.",
            npc=NpcData(
                npc_id="exec_morgan",
                display_name="Morgan Blake",
                public_persona=NpcPublicPersona(
                    occupation="Chief Revenue Officer",
                    speaking_style="Blunt, impatient, and direct. Gets to the point fast.",
                    demeanor="Skeptical. Challenges assumptions and pushes back on vague answers.",
                ),
                private_persona=NpcPrivatePersona(
                    hidden_agenda=[
                        "Determine whether the candidate can handle pressure",
                        "Test whether they have real strategic vision or are just buzzword-fluent",
                    ],
                    biases_to_simulate=[
                        "Dismisses candidates who hedge or use passive language",
                    ],
                    boundaries=[
                        "May be blunt but never personally insulting",
                        "Professional aggression only — no actual hostility",
                    ],
                ),
            ),
        ),
        max_turns=14,
        supported_languages=["en"],
        difficulty_options={
            "standard":    DifficultySettings(patience=30, volatility=60, disclosure=30, time_pressure=60),
            "hard":        DifficultySettings(patience=15, volatility=80, disclosure=15, time_pressure=75),
            "adversarial": DifficultySettings(patience=5,  volatility=95, disclosure=5,  time_pressure=90),
        },
        opening_npc_says=(
            "Let's skip the pleasantries. Why should I care about you? "
            "You have two minutes to impress me."
        ),
    ),

    "used_car_negotiation": ScenarioInfo(
        scenario_data=ScenarioData(
            scenario_id="used_car_negotiation",
            title="Used Car Negotiation",
            player_role_label="Buyer",
            player_role_brief="You want to buy a used car listed at $12,000 and get a fair deal.",
            npc=NpcData(
                npc_id="salesperson_pat",
                display_name="Pat Martinez",
                public_persona=NpcPublicPersona(
                    occupation="Pre-owned vehicle sales consultant",
                    speaking_style="Friendly and persuasive. Uses anchoring and urgency tactics.",
                    demeanor="Warm but persistent. Always looking for the close.",
                ),
                private_persona=NpcPrivatePersona(
                    hidden_agenda=[
                        "Minimum acceptable price is $10,500",
                        "Willing to throw in extras (floor mats, oil change) before dropping price",
                    ],
                    biases_to_simulate=[
                        "More flexible with buyers who seem genuinely interested",
                    ],
                    boundaries=[
                        "Never go below $10,000",
                        "Stays professional even under pressure",
                    ],
                ),
            ),
            player_visible_goals=[
                "Get the car for under $11,000",
                "Include at least one free extra in the deal",
            ],
        ),
        max_turns=16,
        supported_languages=["en", "es"],
        difficulty_options={
            "warm":        DifficultySettings(patience=80, volatility=20, disclosure=70, time_pressure=20),
            "standard":    DifficultySettings(patience=50, volatility=50, disclosure=50, time_pressure=50),
            "hard":        DifficultySettings(patience=25, volatility=70, disclosure=25, time_pressure=60),
            "adversarial": DifficultySettings(patience=10, volatility=90, disclosure=10, time_pressure=80),
        },
        opening_npc_says=(
            "Welcome! You're looking at one of our best deals. "
            "This 2021 Honda Civic has only 28,000 miles. What brings you in today?"
        ),
    ),

    "spanish_coffee": ScenarioInfo(
        scenario_data=ScenarioData(
            scenario_id="spanish_coffee",
            title="Spanish Coffee Chat",
            player_role_label="Language Learner",
            player_role_brief="Practice ordering coffee and chatting in Spanish at a local café.",
            npc=NpcData(
                npc_id="barista_sofia",
                display_name="Sofía",
                public_persona=NpcPublicPersona(
                    occupation="Barista and owner of a small café in Madrid",
                    speaking_style="Warm, patient, speaks clearly. Will slow down when asked.",
                    demeanor="Encouraging. Enjoys helping language learners practice.",
                ),
                private_persona=NpcPrivatePersona(
                    hidden_agenda=[
                        "Gently correct grammar mistakes without making it awkward",
                        "Keep the conversation flowing at a manageable pace",
                    ],
                    biases_to_simulate=[],
                    boundaries=[
                        "Never mock pronunciation or grammar errors",
                        "Always respond in Spanish unless explicitly asked to switch",
                    ],
                ),
            ),
            response_style=ResponseStyleOverrides(
                max_words=60,
                max_questions_per_turn=1,
                allow_short_responses=True,
                avoid_monologues=True,
            ),
        ),
        max_turns=20,
        supported_languages=["es", "en"],
        difficulty_options={
            "warm":     DifficultySettings(patience=80, volatility=20, disclosure=80, time_pressure=10),
            "standard": DifficultySettings(patience=55, volatility=45, disclosure=55, time_pressure=30),
            "hard":     DifficultySettings(patience=30, volatility=65, disclosure=30, time_pressure=55),
        },
        opening_npc_says="¡Buenos días! ¿Qué le pongo?",
    ),

    "coworker_feedback": ScenarioInfo(
        scenario_data=ScenarioData(
            scenario_id="coworker_feedback",
            title="Coworker Feedback",
            player_role_label="Colleague",
            player_role_brief="Give constructive feedback to a coworker about a project issue.",
            npc=NpcData(
                npc_id="coworker_jordan",
                display_name="Jordan",
                public_persona=NpcPublicPersona(
                    occupation="Software engineer on your team",
                    speaking_style="Casual but professional. Slightly guarded at first.",
                    demeanor="Initially defensive, becomes more open with patient listening.",
                ),
                private_persona=NpcPrivatePersona(
                    hidden_agenda=[
                        "Worried the feedback is a sign of deeper problems",
                        "Doesn't want the conversation to affect the team dynamic",
                    ],
                    biases_to_simulate=[
                        "More receptive when the player acknowledges their contributions",
                    ],
                    boundaries=[
                        "Shuts down if the tone becomes accusatory",
                    ],
                ),
            ),
            player_visible_goals=[
                "Communicate the issue clearly and without blame",
                "Agree on a concrete next step",
            ],
        ),
        max_turns=14,
        supported_languages=["en"],
        difficulty_options={
            "warm":        DifficultySettings(patience=80, volatility=20, disclosure=70, time_pressure=20),
            "standard":    DifficultySettings(patience=50, volatility=50, disclosure=50, time_pressure=50),
            "hard":        DifficultySettings(patience=25, volatility=70, disclosure=25, time_pressure=60),
            "adversarial": DifficultySettings(patience=10, volatility=90, disclosure=10, time_pressure=80),
        },
        opening_npc_says="Hey, you wanted to talk? What's up?",
        state_variable_overrides={
            # Jordan starts guarded — rapport begins below the baseline 50.
            "rapport": {"default": 30, "visibility": "visible"},
        },
        events=[
            ScenarioEvent(
                id="npc_defensive",
                when={"type": "variable_below", "variable": "patience", "threshold": 30},
                npc_instruction=(
                    "Jordan is becoming defensive. Give shorter, clipped replies "
                    "and stop volunteering information."
                ),
            ),
        ],
        ending_conditions={
            "success": {
                "type": "variable_above",
                "variable": "objective_progress",
                "threshold": 60,
            },
            "failure": {
                "type": "variable_below",
                "variable": "patience",
                "threshold": 15,
            },
        },
    ),

    # Zero-model instant-play tutorial (issue #305).  Played with the "scripted"
    # runtime — deterministic, no inference.  Registered here so it is resolvable
    # by get_scenario_info() and therefore playable through the normal
    # session-create → turn pipeline, exactly like the other built-in scenarios.
    # The matching pack (packs/official/first-words) supplies the library entry,
    # rubric, and safety policy; this entry drives play.
    "first_words_tutorial": ScenarioInfo(
        scenario_data=ScenarioData(
            scenario_id="first_words_tutorial",
            title="First Words",
            player_role_label="New Player",
            player_role_brief=(
                "You just installed Conversation Simulator. Alex Chen is here to "
                "show you how the app works before you jump into a real scenario. "
                "There's no wrong answer — just respond naturally and follow where "
                "Alex leads."
            ),
            npc=NpcData(
                npc_id="alex_chen_tutorial",
                display_name="Alex Chen",
                public_persona=NpcPublicPersona(
                    occupation="Tutorial guide for Conversation Simulator.",
                    speaking_style=(
                        "Warm, clear, and direct. Uses short sentences. Names the "
                        "mechanic being demonstrated before showing it."
                    ),
                    demeanor=(
                        "Encouraging without being patronising. Celebrates small "
                        "wins without overdoing it."
                    ),
                ),
                private_persona=NpcPrivatePersona(
                    hidden_agenda=[
                        "Ensure the player leaves feeling confident enough to try a real scenario",
                        "Demonstrate every core mechanic — meters, events, endings, debrief — exactly once",
                    ],
                    biases_to_simulate=[],
                    boundaries=[
                        "Never generate sexual, violent, or disturbing content",
                        "Never impersonate a real person or real company",
                        "Keep all language at a G content rating",
                    ],
                ),
            ),
            player_visible_goals=[
                "Learn how state meters work by watching them change as you talk",
                "Trigger a scenario event to see how events reshape a conversation",
                "Complete the tutorial and unlock the scenario library",
            ],
        ),
        max_turns=8,
        supported_languages=["en"],
        difficulty_options={
            "standard": DifficultySettings(patience=100, volatility=0, disclosure=100, time_pressure=0),
        },
        opening_npc_says=(
            "Welcome! I'm Alex Chen, your tutorial guide. This is Conversation "
            "Simulator — a private, offline practice space for conversations that "
            "matter. Notice the two meters at the top: Engagement and Confidence. "
            "They update every turn based on what you say. Go ahead — say anything "
            "to get us started."
        ),
        state_variable_overrides={
            # The tutorial deliberately shows exactly two meters.  Add
            # engagement/confidence as visible and hide every baseline variable so
            # only these two render for the player.
            "engagement": {"min": 0, "max": 100, "default": 30, "visibility": "visible", "max_delta_per_turn": 20},
            "confidence": {"min": 0, "max": 100, "default": 50, "visibility": "visible", "max_delta_per_turn": 15},
            "trust": {"visibility": "hidden"},
            "patience": {"visibility": "hidden"},
            "rapport": {"visibility": "hidden"},
            "openness": {"visibility": "hidden"},
            "objective_progress": {"visibility": "hidden"},
        },
        events=[
            ScenarioEvent(
                id="warm_moment",
                when={"type": "variable_above", "variable": "engagement", "threshold": 60},
                npc_instruction=(
                    "The player has shown genuine engagement and Engagement has "
                    "crossed 60. Warmly acknowledge the moment and use it as a "
                    "teaching point: explain that this is what a scenario event "
                    "looks like — a threshold crossing that shifts your hidden "
                    "instructions and changes how you behave for the rest of the "
                    "session."
                ),
                repeat=False,
            ),
        ],
        # No variable-based success/failure: the scripted runtime ends the session
        # on its final turn via session_control (see runtime/scripted.py).  A lower
        # success threshold would trip before the warm_moment event (engagement>60)
        # could fire.  Timeout is the only scenario-level safety net.
        ending_conditions={
            "timeout": {"type": "max_turns", "value": 8},
        },
    ),
}


# ---------------------------------------------------------------------------
# Dynamic scenario registry (workbench test sessions)
# ---------------------------------------------------------------------------

# Process-local registry for scenarios loaded from pack directories at runtime.
# Entries persist for the lifetime of the process; the data volume is negligible
# (one ScenarioInfo per active workbench test session).  Sessions cleaned up
# through DELETE /api/sessions/{id} do not remove entries here — that's
# acceptable for the workbench MVP where test sessions are short-lived.
_dynamic_registry: Dict[str, ScenarioInfo] = {}
_dynamic_lock = threading.Lock()


def register_dynamic_scenario(scenario_id: str, info: ScenarioInfo) -> None:
    """Register a temporary scenario (e.g., for a workbench test session)."""
    with _dynamic_lock:
        _dynamic_registry[scenario_id] = info


def unregister_dynamic_scenario(scenario_id: str) -> None:
    """Remove a dynamic scenario registration if present."""
    with _dynamic_lock:
        _dynamic_registry.pop(scenario_id, None)


def get_scenario_info(scenario_id: str) -> ScenarioInfo | None:
    """Return the ScenarioInfo for the given ID, or None if unknown."""
    return SCENARIOS.get(scenario_id) or _dynamic_registry.get(scenario_id)


def get_scenario_data(scenario_id: str, difficulty: str = "standard") -> ScenarioData | None:
    """Return a ScenarioData configured for the given difficulty, or None if unknown."""
    info = get_scenario_info(scenario_id)
    if info is None:
        return None
    return info.get_scenario_data(difficulty)


# ---------------------------------------------------------------------------
# Pack scenario loader (for workbench test sessions)
# ---------------------------------------------------------------------------


def _npc_data_from_dict(raw: Dict[str, Any]) -> NpcData:
    """Build an NpcData from a parsed NPC YAML dict (inline or file-loaded)."""
    pub = raw.get("public_persona") or {}
    priv = raw.get("private_persona") or {}
    return NpcData(
        npc_id=raw.get("npc_id") or "npc",
        display_name=raw.get("display_name") or "NPC",
        public_persona=NpcPublicPersona(
            occupation=pub.get("occupation") or "",
            speaking_style=pub.get("speaking_style") or "",
            demeanor=pub.get("demeanor") or "",
        ),
        private_persona=NpcPrivatePersona(
            hidden_agenda=list(priv.get("hidden_agenda") or []),
            biases_to_simulate=list(priv.get("biases_to_simulate") or []),
            boundaries=list(priv.get("boundaries") or []),
        ),
    )


def load_scenario_info_from_pack(pack_dir: Path, scenario_rel_path: str) -> ScenarioInfo:
    """Load a ScenarioInfo by reading scenario (and NPC) YAML files from a pack directory.

    Raises ``ValueError`` or ``OSError`` if the files cannot be read or parsed.
    """
    import yaml  # local import — only needed for workbench test sessions

    scenario_file = (pack_dir / scenario_rel_path).resolve()
    raw: Dict[str, Any] = yaml.safe_load(scenario_file.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Scenario YAML is not a mapping: {scenario_rel_path}")

    # NPC: resolve ref or use inline dict
    npc_section = raw.get("npc") or {}
    npc_ref: Optional[str] = npc_section.get("ref") if isinstance(npc_section, dict) else None
    if npc_ref:
        npc_file = (scenario_file.parent / npc_ref).resolve()
        npc_raw: Dict[str, Any] = yaml.safe_load(npc_file.read_text(encoding="utf-8")) or {}
        if not isinstance(npc_raw, dict):
            npc_raw = {}
    else:
        npc_raw = npc_section if isinstance(npc_section, dict) else {}

    npc = _npc_data_from_dict(npc_raw)

    player_role = raw.get("player_role") or {}
    opening_section = raw.get("opening") or {}
    opening_npc_says: str = opening_section.get("npc_says") or "Hello. Let's begin."

    goals_section = raw.get("goals") or {}
    player_visible_goals: List[str] = list(goals_section.get("player_visible") or [])

    duration = raw.get("duration") or {}
    max_turns: int = int(duration.get("max_turns") or 12)

    state_section = raw.get("state") or {}
    state_variable_overrides: Optional[Dict[str, Any]] = state_section.get("variables") or None

    scenario_data = ScenarioData(
        scenario_id=raw.get("scenario_id") or "workbench_test",
        title=raw.get("title") or "Workbench Test",
        player_role_label=player_role.get("label") or "Player",
        player_role_brief=player_role.get("brief") or "",
        npc=npc,
        player_visible_goals=player_visible_goals,
    )

    return ScenarioInfo(
        scenario_data=scenario_data,
        max_turns=max_turns,
        supported_languages=["en"],
        difficulty_options={"standard": DifficultySettings()},
        opening_npc_says=opening_npc_says,
        state_variable_overrides=state_variable_overrides,
    )
