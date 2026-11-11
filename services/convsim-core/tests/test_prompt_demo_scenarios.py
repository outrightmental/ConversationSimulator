# SPDX-License-Identifier: Apache-2.0
"""The five demo conversations, as the turn prompt presents them (issue #580).

Demo gate D-05 failed on NPC coherence in four of the five. These tests load
each demo scenario from its official pack, the way the demo edition plays it,
and check the prompt text aimed at that: the chosen difficulty preset's
authored description reaches the scenario brief (at ``standard`` it is the
only difficulty text the NPC gets), the transcript names the NPC "(you)" and
the player by role, and the conversation rule block stays short. The role line
of the rule block is also read for every official and catalog scenario, which
the full app plays.
"""
import re
from pathlib import Path

import pytest
import yaml

from convsim_core.edition import DEMO_SCENARIOS
from convsim_core.scenarios import SCENARIOS, load_scenario_info_from_pack
from convsim_prompt import (
    PromptComposerInput,
    SafetyPolicy,
    SessionState,
    TranscriptEntry,
    compose_turn_prompt,
)
from convsim_prompt.layers import _conversation_rules, _player_label, _short_role

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OFFICIAL_PACKS = _REPO_ROOT / "packs" / "official"

_POLICY = SafetyPolicy(policy_id="default_pg", content_rating="PG", prohibited=["nsfw_sexual_content"])


def _pack_dir(pack_id: str) -> Path:
    for manifest in _OFFICIAL_PACKS.glob("*/manifest.yaml"):
        if yaml.safe_load(manifest.read_text(encoding="utf-8")).get("pack_id") == pack_id:
            return manifest.parent
    raise AssertionError(f"no official pack {pack_id}")


def _load(pack_id: str, scenario_id: str):
    pack_dir = _pack_dir(pack_id)
    rel_path = f"scenarios/{scenario_id}.yaml"
    raw = yaml.safe_load((pack_dir / rel_path).read_text(encoding="utf-8"))
    return raw, load_scenario_info_from_pack(pack_dir, rel_path)


def _compose(scenario_data, transcript=()):
    return compose_turn_prompt(PromptComposerInput(
        scenario=scenario_data,
        session_state=SessionState(variables={"trust": 50}, turn_number=1),
        safety_policy=_POLICY,
        player_utterance="Hello.",
        recent_transcript=list(transcript),
    ))


_DEMO = [pytest.param(d.pack_id, d.scenario_id, id=d.scenario_id) for d in DEMO_SCENARIOS]


@pytest.mark.parametrize("pack_id,scenario_id", _DEMO)
def test_every_preset_description_reaches_the_scenario_brief(pack_id, scenario_id):
    raw, info = _load(pack_id, scenario_id)
    options = raw["difficulty"]["options"]
    assert "standard" in options
    for preset, authored in options.items():
        description = authored["description"].strip()
        data = info.get_scenario_data(preset)
        assert data.difficulty_settings.description == description
        brief = _compose(data).layer_map["SCENARIO_BRIEF"]
        assert f'Difficulty as described to the player: "{description}"' in brief, preset


@pytest.mark.parametrize("pack_id,scenario_id", _DEMO)
def test_transcript_names_the_npc_and_the_player(pack_id, scenario_id):
    _raw, info = _load(pack_id, scenario_id)
    data = info.get_scenario_data("standard")
    bundle = _compose(data, [
        TranscriptEntry(speaker="npc_opening", text=info.opening_npc_says, turn_number=0),
        TranscriptEntry(speaker="player", text="Hello.", turn_number=1),
    ])
    transcript = bundle.layer_map["RECENT_TRANSCRIPT"]
    assert f"{data.npc.display_name} (you): " in transcript
    assert f"{data.player_role_label} (the player): Hello." in transcript
    assert f'\n"{info.opening_npc_says.strip()}"\n' in bundle.user_prompt
    assert "That was your previous line." in bundle.user_prompt


@pytest.mark.parametrize("pack_id,scenario_id", _DEMO)
def test_conversation_rules_stay_short(pack_id, scenario_id):
    _raw, info = _load(pack_id, scenario_id)
    data = info.get_scenario_data("standard")
    rules = "\n".join(_conversation_rules(data))
    assert f"You are {data.npc.display_name} (" in rules
    assert f"the player is the {data.player_role_label}." in rules
    # The composer's four-characters-per-token estimate.
    assert len(rules) // 4 <= 135


def _every_scenario():
    """Every official pack scenario, then every hardcoded catalog scenario."""
    params = []
    for path in sorted(_OFFICIAL_PACKS.glob("*/scenarios/*.yaml")):
        params.append(pytest.param(path, None, id=f"{path.parent.parent.name}/{path.stem}"))
    for scenario_id in SCENARIOS:
        params.append(pytest.param(None, scenario_id, id=f"catalog/{scenario_id}"))
    return params


def _scenario_data(path, catalog_id):
    if catalog_id is not None:
        return SCENARIOS[catalog_id].get_scenario_data("standard")
    info = load_scenario_info_from_pack(path.parent.parent, f"scenarios/{path.name}")
    return info.get_scenario_data("standard")


_DANGLING = {
    "a", "an", "the", "and", "or", "but", "who", "which", "that", "where", "whose",
    "while", "in", "at", "on", "near", "for", "with", "from", "of", "by", "to",
}


@pytest.mark.parametrize("path,catalog_id", _every_scenario())
def test_role_line_reads_as_a_whole_phrase(path, catalog_id):
    """In the full app every scenario plays, not only the five demo ones.

    The role is cut at a clause or phrase boundary, never mid-phrase; it holds
    no nested parenthesis and no "you"/"your" meant for the player; and a
    label that names no role ("Yourself") is not put in "the player is the ...".
    """
    data = _scenario_data(path, catalog_id)
    role = _short_role(data.npc.public_persona.occupation)
    assert role and len(role.split()) <= 12, role
    assert role.split()[-1].lower() not in _DANGLING, role
    assert "(" not in role and ")" not in role, role
    assert not re.search(r"\byour?\b", role, re.IGNORECASE), role

    side = next(r for r in _conversation_rules(data) if r.startswith("- You are "))
    assert side.startswith(f"- You are {data.npc.display_name} ({role})"), side
    label = _player_label(data.player_role_label)
    if label:
        assert f"; the player is the {label}. " in side
    else:
        assert "the player is the" not in side


@pytest.mark.parametrize("path,catalog_id,expected", [
    (_OFFICIAL_PACKS / "dating-confidence-boundaries/scenarios/holding_your_ground.yaml", None,
     "- You are Ryan Kowalski (a paramedic who works rotating shifts); the player is the Neighbor."),
    (_OFFICIAL_PACKS / "dating-confidence-boundaries/scenarios/graceful_exit.yaml", None,
     "- You are Priya Singh (a graphic designer who works at a mid-sized agency downtown)."),
    (_OFFICIAL_PACKS / "job-interview-basic/scenarios/blue_collar_supervisor_interview.yaml", None,
     "- You are Ray Morales (Warehouse Operations Supervisor at Crestview Distribution Co.); "
     "the player is the Job Candidate."),
    (_OFFICIAL_PACKS / "language-cafe/scenarios/japanese_convenience_store.yaml", None,
     "- You are Kenji Yamamoto (Part-time store clerk at a 24-hour convenience store in the "
     "Shinjuku district); the player is the Language Learner."),
    (None, "coworker_feedback",
     "- You are Jordan (Software engineer on the player's team); the player is the Colleague."),
    (None, "first_words_tutorial",
     "- You are Alex Chen (Tutorial guide for Conversation Simulator)."),
], ids=["cut_at_clause", "yourself_label", "abbreviation", "cut_at_phrase", "second_person", "new_player_label"])
def test_role_lines_that_used_to_read_wrongly(path, catalog_id, expected):
    rules = "\n".join(_conversation_rules(_scenario_data(path, catalog_id)))
    assert expected in rules


def test_a_yourself_label_is_not_a_transcript_speaker():
    data = _scenario_data(
        _OFFICIAL_PACKS / "dating-confidence-boundaries/scenarios/graceful_exit.yaml", None
    )
    assert data.player_role_label == "Yourself"
    transcript = _compose(data, [
        TranscriptEntry(speaker="npc_opening", text="Hi!", turn_number=0),
        TranscriptEntry(speaker="player", text="Hello.", turn_number=1),
    ]).layer_map["RECENT_TRANSCRIPT"]
    assert "Player: Hello." in transcript
    assert "Yourself" not in transcript


def test_a_preset_without_a_description_carries_none(tmp_path):
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "scenarios" / "s.yaml").write_text(
        "scenario_id: s\n"
        "title: S\n"
        "npc:\n"
        "  display_name: Sam\n"
        "difficulty:\n"
        "  options:\n"
        "    standard: {patience: 50}\n"
        "    hard: {patience: 20, description: '   '}\n"
        "    warm: {patience: 80, description: ' Sam is kind. '}\n",
        encoding="utf-8",
    )
    info = load_scenario_info_from_pack(tmp_path, "scenarios/s.yaml")
    assert info.get_scenario_data("standard").difficulty_settings.description is None
    assert info.get_scenario_data("hard").difficulty_settings.description is None
    assert info.get_scenario_data("warm").difficulty_settings.description == "Sam is kind."
    brief = _compose(info.get_scenario_data("standard")).layer_map["SCENARIO_BRIEF"]
    assert "described to the player" not in brief
