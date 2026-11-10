# SPDX-License-Identifier: Apache-2.0
"""The five demo conversations' authored content, as the engine reads it (#580).

The demo gate pre-check (D-05) found the starter model improvising facts the
NPC files never gave it (Ray's tire history, Jordan's research, Rosa's menu),
asking for things it should have said, and firing ask_for_raise's probes on
turn 1 because they were true at the scenario defaults. The NPC files now
carry concrete do / never rules and the facts each character answers from.

These tests read the real pack files through the same loader, composer and
output check that play uses, and pin what the rewrite relies on:

- no authored event or ending is already true at a scenario's defaults, and
  every ending can still be reached within the scenario's turn limit;
- each persona agrees with what else the prompt carries: Ray's argument with
  his counter ladder, Diane's timeline with the scenario's event, Rosa's
  correction rules with the difficulty preset text;
- the facts each NPC answers from are in a persona field the turn prompt
  renders, so they survive the three-exchange transcript window;
- secrets stay in the private persona;
- the longer personas still fit the prompt budget with a full transcript;
- the lines the rules ask for do not trip the hidden-agenda leak check, which
  would turn a good reply into a retry or a fallback line.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Dict, Optional

import pytest
import yaml

from convsim_core import edition
from convsim_core.scenario_state import (
    apply_state_delta,
    build_variable_defs,
    evaluate_ending_condition,
    evaluate_event_triggers,
    initialize_state,
)
from convsim_core.scenarios import ScenarioInfo, load_scenario_info_from_pack
from convsim_core.services.safety_policy_service import load_safety_policy
from convsim_core.services.turn_pipeline import _safety_policy_config_to_prompt_policy
from convsim_prompt import compose_turn_prompt, validate_npc_output
from convsim_prompt.types import PromptComposerInput, SessionState, TranscriptEntry

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OFFICIAL_PACKS = _REPO_ROOT / "packs" / "official"


def _pack_dirs() -> Dict[str, Path]:
    """pack_id → pack directory, read from the bundled manifests."""
    index: Dict[str, Path] = {}
    for manifest in sorted(_OFFICIAL_PACKS.glob("*/manifest.yaml")):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        index[data["pack_id"]] = manifest.parent
    return index


_PACK_DIRS = _pack_dirs()


def _load(scenario_id: str) -> ScenarioInfo:
    demo = next(s for s in edition.DEMO_SCENARIOS if s.scenario_id == scenario_id)
    return load_scenario_info_from_pack(
        _PACK_DIRS[demo.pack_id], f"scenarios/{scenario_id}.yaml"
    )


def _pack_dir(scenario_id: str) -> Path:
    demo = next(s for s in edition.DEMO_SCENARIOS if s.scenario_id == scenario_id)
    return _PACK_DIRS[demo.pack_id]


def _turn_prompt_layers(scenario_id: str, difficulty: str = "standard") -> Dict[str, str]:
    """The first turn prompt's layers, by layer name."""
    info = _load(scenario_id)
    state = initialize_state(build_variable_defs(info.state_variable_overrides))
    bundle = compose_turn_prompt(PromptComposerInput(
        scenario=info.get_scenario_data(difficulty),
        session_state=SessionState(variables=state, turn_number=1),
        safety_policy=_prompt_safety_policy(scenario_id),
        player_utterance="Hello.",
    ))
    return bundle.layer_map


def _persona_layers(scenario_id: str, difficulty: str = "standard") -> tuple[str, str]:
    """The NPC_PUBLIC_PERSONA and NPC_PRIVATE_PERSONA text the turn prompt carries."""
    layers = _turn_prompt_layers(scenario_id, difficulty)
    return layers["NPC_PUBLIC_PERSONA"], layers["NPC_PRIVATE_PERSONA"]


def _prompt_safety_policy(scenario_id: str):
    pack_dir = _pack_dir(scenario_id)
    manifest = yaml.safe_load((pack_dir / "manifest.yaml").read_text(encoding="utf-8"))
    config = load_safety_policy(pack_dir / manifest["safety"]["policy"])
    return _safety_policy_config_to_prompt_policy(config)


_DEMO_IDS = list(edition.DEMO_SCENARIO_IDS)


# ── Events and endings ────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario_id", _DEMO_IDS)
def test_no_authored_event_or_ending_is_true_at_the_defaults(scenario_id):
    """An event true at the defaults fires on turn 1 whatever the player says.

    ask_for_raise's vague_claim_probe (evidence_strength 0 < 30) and
    no_number_anchor (case_clarity 10 < 25) used to; once fired event
    instructions reach the prompt, the repeating probe would have pinned
    Diane to "give me specifics" from the first reply.
    """
    info = _load(scenario_id)
    state = initialize_state(build_variable_defs(info.state_variable_overrides))
    assert info.events, f"{scenario_id}: expected authored events"
    fired = evaluate_event_triggers(state, 1, info.events, set())
    assert fired == [], f"{scenario_id}: true at the defaults: {fired}"
    ending = evaluate_ending_condition(state, 1, info.max_turns, info.ending_conditions)
    assert ending is None, f"{scenario_id}: ending {ending!r} is true at the defaults"


def _turns_at_the_delta_limit(info: ScenarioInfo, condition: dict, fires) -> Optional[int]:
    """Fewest turns, moving the condition's variable by its per-turn limit, until ``fires``."""
    defs = build_variable_defs(info.state_variable_overrides)
    variable = condition["variable"]
    step = defs[variable].max_delta_per_turn
    step = step if condition["type"] == "variable_above" else -step
    state = initialize_state(defs)
    for turn in range(1, info.max_turns + 1):
        state = apply_state_delta(state, {variable: step}, defs).new_state
        if fires(state, turn):
            return turn
    return None


def _turns_to_ending(info: ScenarioInfo, kind: str) -> Optional[int]:
    """Fewest turns, at the per-turn delta limit, until the ending fires (None: never)."""
    condition = info.ending_conditions[kind]
    return _turns_at_the_delta_limit(info, condition, lambda state, turn: (
        evaluate_ending_condition(state, turn, info.max_turns + 1, {kind: condition}) == kind
    ))


@pytest.mark.parametrize("scenario_id", _DEMO_IDS)
@pytest.mark.parametrize("kind", ["success", "failure"])
def test_endings_are_reachable_within_the_turn_limit(scenario_id, kind):
    info = _load(scenario_id)
    turns = _turns_to_ending(info, kind)
    assert turns is not None, f"{scenario_id}: {kind} cannot be reached in {info.max_turns} turns"
    assert turns >= 2, f"{scenario_id}: {kind} can fire on the first turn"


# Fewest turns, each moving the ending's variable by its per-turn limit, until
# the ending fires (issue #580). Once the model has to report every authored
# variable every turn, these are reachable: at the old limits two strong lines
# ended behavioral_interview, the_ask (before any ask) and spanish_coffee.
_EARLIEST_ENDING = {
    "behavioral_interview": {"success": 4, "failure": 6},
    "used_car_negotiation": {"success": 4, "failure": 3},
    "ask_for_raise": {"success": 4, "failure": 3},
    "the_ask": {"success": 5, "failure": 4},
    "spanish_coffee": {"success": 4, "failure": 4},
}


@pytest.mark.parametrize("scenario_id", _DEMO_IDS)
def test_no_ending_can_fire_in_the_first_turns(scenario_id):
    info = _load(scenario_id)
    turns = {kind: _turns_to_ending(info, kind) for kind in ("success", "failure")}
    assert turns == _EARLIEST_ENDING[scenario_id]
    assert turns["success"] >= 4, f"{scenario_id}: success after {turns['success']} turns"
    assert turns["failure"] >= 3, f"{scenario_id}: failure after {turns['failure']} turns"


def _turns_to_event(info: ScenarioInfo, event_id: str) -> Optional[int]:
    """Fewest turns, at the per-turn delta limit, until the event fires (None: never)."""
    event = next(e for e in info.events if e.id == event_id)
    return _turns_at_the_delta_limit(info, event.when, lambda state, turn: bool(
        evaluate_event_triggers(state, turn, [event], set())
    ))


def test_ask_for_raise_keeps_its_original_pacing():
    """Moving the probes off the defaults must not shorten the conversation.

    Before #580, case_clarity climbed from 10 to above 65 for success and
    evidence_strength from 0 to above 70 for strong_case_acknowledged: four
    turns each at the delta limit. Both still need the same climb, so any
    sequence of strengthening turns reaches them on the same turn as before.
    """
    info = _load("ask_for_raise")
    defs = build_variable_defs(info.state_variable_overrides)
    success = info.ending_conditions["success"]
    strong = next(e for e in info.events if e.id == "strong_case_acknowledged").when

    assert success["threshold"] - defs["case_clarity"].default == 65 - 10
    assert strong["threshold"] - defs["evidence_strength"].default == 70 - 0
    assert _turns_to_ending(info, "success") == 4
    assert _turns_to_event(info, "strong_case_acknowledged") == 4


def test_jordan_warms_before_the_conversation_can_succeed():
    """positive_signal fires on the turn after jordan_interest passes 60, so at
    the delta limit it reaches the prompt by the turn success can end it on."""
    info = _load("the_ask")
    assert _turns_to_event(info, "positive_signal") < _turns_to_ending(info, "success")


def test_ask_for_raise_probes_wait_for_a_turn_that_weakens_the_case():
    info = _load("ask_for_raise")
    defs = build_variable_defs(info.state_variable_overrides)
    state = initialize_state(defs)
    events = {e.id: e for e in info.events}

    weaker = apply_state_delta(state, {"evidence_strength": -20, "case_clarity": -18}, defs).new_state
    fired = evaluate_event_triggers(weaker, 2, info.events, set())
    assert "vague_claim_probe" in fired
    assert "no_number_anchor" in fired

    slightly_weaker = apply_state_delta(state, {"evidence_strength": -3, "case_clarity": -3}, defs).new_state
    fired = evaluate_event_triggers(slightly_weaker, 2, info.events, set())
    assert "vague_claim_probe" in fired
    assert "no_number_anchor" in fired

    stronger = apply_state_delta(state, {"evidence_strength": 20, "case_clarity": 18}, defs).new_state
    fired = evaluate_event_triggers(stronger, 2, info.events, set())
    assert "vague_claim_probe" not in fired
    assert "no_number_anchor" not in fired
    assert events["vague_claim_probe"].repeat is True


# ── What each state variable means ────────────────────────────────────────────


def _words(text: str) -> list:
    """Words as the D-05 replay compares them: NFKC, case-folded, no apostrophes."""
    text = unicodedata.normalize("NFKC", text).casefold().replace("'", "").replace("’", "")
    return [w for w in re.split(r"\W+", text) if w]


def _runs(words: list, n: int) -> set:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


@pytest.mark.parametrize("scenario_id", _DEMO_IDS)
def test_every_variable_says_what_it_means(scenario_id):
    """The model updates every authored variable every turn (issue #580); the
    STATE_VARIABLES layer shows each one's authored meaning, in full."""
    info = _load(scenario_id)
    data = info.get_scenario_data("standard")
    assert data.state_variable_names == list(info.state_variable_overrides)
    layer = _turn_prompt_layers(scenario_id)["STATE_VARIABLES"]
    for variable in data.state_variables:
        assert variable.description, f"{scenario_id}: {variable.name} has no description"
        assert len(variable.description.split()) <= 45, f"{scenario_id}: {variable.name} would be clipped"
        assert variable.cues == []
        assert f"a turn): {variable.description}" in layer


@pytest.mark.parametrize("scenario_id", _DEMO_IDS)
def test_no_description_repeats_the_hidden_agenda(scenario_id):
    """A reply that echoes a variable's meaning must not read as an agenda
    leak to the D-05 replay, which flags any five-word run of the agenda."""
    info = _load(scenario_id)
    agenda = set()
    for item in info.scenario_data.npc.private_persona.hidden_agenda:
        agenda |= _runs(_words(item), 5)
    for variable in info.get_scenario_data("standard").state_variables:
        shared = _runs(_words(variable.description), 5) & agenda
        assert not shared, f"{scenario_id}: {variable.name} repeats {shared}"


# ── Facts the NPC answers from survive the transcript window ──────────────────

# Each entry: facts the NPC must be able to state on any turn, so they have to
# live in a rendered persona field rather than only in the opening line or the
# scenario summary (neither of which the turn prompt carries after turn 3).
_RENDERED_FACTS = {
    "used_car_negotiation": ["$15,500", "$13,500 to $14,200", "41,000 miles", "service records", "tread"],
    "ask_for_raise": ["pay band", "HR", "end of week"],
    "the_ask": ["green corridors", "bird", "Thursday afternoon seminar"],
    "spanish_coffee": ["Sevilla", "three years", "cruasán 1,80 €", "café con leche 1,80 €"],
    "behavioral_interview": ["eight engineers", "deploy pipeline", "first 90 days", "B2B"],
}


@pytest.mark.parametrize("scenario_id", _DEMO_IDS)
def test_npc_facts_are_in_a_rendered_persona_field(scenario_id):
    public, private = _persona_layers(scenario_id)
    rendered = public + "\n" + private
    for fact in _RENDERED_FACTS[scenario_id]:
        assert fact in rendered, f"{scenario_id}: {fact!r} is not in the NPC persona layers"


@pytest.mark.parametrize("scenario_id", _DEMO_IDS)
def test_no_rule_depends_on_a_setting_the_prompt_never_shows(scenario_id):
    """Rosa's corrections were keyed on correction_style, which no layer renders.

    Difficulty-dependent behaviour has to name the preset the scenario brief
    prints ("Difficulty preset: standard").
    """
    public, private = _persona_layers(scenario_id)
    assert "correction_style" not in public + private


def test_ray_keeps_his_floor_and_ladder_private():
    public, private = _persona_layers("used_car_negotiation")
    for secret in ("13,800", "14,600"):
        assert secret not in public, f"{secret} must stay in the private persona"
        assert secret in private


def test_ray_argues_above_the_comps_and_his_ladder_agrees():
    """Ray's persona once said the car "belongs at the top of" the comps.

    That made $14,200 his own fair price, with his first counters (15,000,
    14,600) above it. He now argues the car is worth more than the comps, and
    the ladder comes down from the list to the comps' top and holds there,
    above the floor.
    """
    public, _ = _persona_layers("used_car_negotiation")
    comps = next(s for s in public.split(". ") if "$13,500 to $14,200" in s)
    assert "worth more than" in comps
    assert "top of that range" not in public

    agenda = _load("used_car_negotiation").scenario_data.npc.private_persona.hidden_agenda
    ladder_item = next(item for item in agenda if "list one step" in item)
    ladder = [int(n.replace(",", "")) for n in re.findall(r"\b1\d,\d{3}\b", ladder_item.split(":", 1)[1])]
    assert ladder == [15000, 14600, 14200], "down from the 15,500 list to the comps' top"
    assert "I could do 15,000" in public, "the speaking-style example counter is the first step"
    floor_item = next(item for item in agenda if "Your floor is" in item)
    floor = int(re.search(r"\b1\d,\d{3}\b", floor_item).group().replace(",", ""))
    assert floor == 13800
    assert floor < 13900 < ladder[-1], "the one last move stays above the floor"


def test_diane_gives_the_timeline_the_scenario_gives():
    """Diane's process said "within two weeks"; the scenario's event says "end of week"."""
    public, _ = _persona_layers("ask_for_raise")
    info = _load("ask_for_raise")
    strong = next(e for e in info.events if e.id == "strong_case_acknowledged")
    assert "end of week" in strong.npc_instruction
    assert "end of week" in public
    assert "two weeks" not in public and "two-week" not in public


def _rosa_correction_rules() -> Dict[str, str]:
    public, _ = _persona_layers("spanish_coffee")
    style = public.split("Speaking style: ", 1)[1].split("\nDemeanor: ", 1)[0]
    return dict(re.findall(r"\b(Warm|Standard|Hard|Adversarial): ([^.]+)\.", style))


def test_rosa_has_a_correction_rule_per_preset_that_fits_the_preset_text():
    """Rosa once coached adversarial customers like hard ones.

    The adversarial preset renders low disclosure and high time pressure, so
    she leaves mistakes alone there. Hard renders low disclosure too, so its
    one correction (the pack's documented hard mode) is all she volunteers.
    """
    rules = _rosa_correction_rules()
    assert set(rules) == {"Warm", "Standard", "Hard", "Adversarial"}

    adversarial = _turn_prompt_layers("spanish_coffee", "adversarial")["SCENARIO_BRIEF"]
    assert "NPC disclosure: low" in adversarial and "Time pressure: high" in adversarial
    assert "leaves mistakes alone" in rules["Adversarial"]
    assert "no hints" in rules["Adversarial"]
    assert "try again" not in rules["Adversarial"]

    hard = _turn_prompt_layers("spanish_coffee", "hard")["SCENARIO_BRIEF"]
    assert "NPC disclosure: low" in hard
    assert "try again" in rules["Hard"]
    assert "all she volunteers" in rules["Hard"]

    warm = _turn_prompt_layers("spanish_coffee", "warm")["SCENARIO_BRIEF"]
    assert "NPC disclosure: high" in warm
    assert "never corrects" in rules["Warm"]
    assert "recasts" in rules["Standard"]


def test_jordan_keeps_the_pack_safety_boundaries():
    """The rewrite changes Jordan's facts and rules, never the PG-13 posture."""
    npc = yaml.safe_load(
        (_pack_dir("the_ask") / "npcs" / "jordan_chen.yaml").read_text(encoding="utf-8")
    )
    boundaries = npc["private_persona"]["boundaries"]
    assert any("flirtation" in b for b in boundaries)
    assert any("pushy or pressuring" in b for b in boundaries)
    assert npc["archetype"] == "classmate"
    manifest = yaml.safe_load((_pack_dir("the_ask") / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["content_rating"] == "PG-13"


# ── Prompt budget ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario_id", _DEMO_IDS)
def test_full_transcript_window_still_fits_the_prompt_budget(scenario_id):
    """Over budget, the composer halves the transcript window (6 → 3 entries)."""
    info = _load(scenario_id)
    state = initialize_state(build_variable_defs(info.state_variable_overrides))
    line = " ".join(["word"] * 90)  # the NPC's default per-reply word cap
    transcript = [
        TranscriptEntry(speaker="player" if i % 2 == 0 else "npc", text=line, turn_number=i // 2 + 1)
        for i in range(6)
    ]
    bundle = compose_turn_prompt(PromptComposerInput(
        scenario=info.get_scenario_data("standard"),
        session_state=SessionState(variables=state, turn_number=4),
        safety_policy=_prompt_safety_policy(scenario_id),
        player_utterance=line,
        recent_transcript=transcript,
    ))
    assert not bundle.was_truncated, (
        f"{scenario_id}: {bundle.estimated_token_count} estimated tokens halves the transcript"
    )


# ── The lines the rules ask for pass the leak check ───────────────────────────

# In-character replies of the kind each NPC's new rules ask for. The output
# check flags a reply that shares three or more long words with one hidden
# agenda item, so an agenda written in the words the NPC is meant to say would
# turn exactly these replies into retries or fallback lines.
_RULE_FOLLOWING_LINES = {
    "used_car_negotiation": [
        "I can't get there on a one-owner car with records. I could do 15,000 out the door.",
        "I hear you on the comps. I can come down to 14,600, with a full folder of service records.",
        "Fourteen-two is where I hold. If you're serious about walking, I'll put four new tires on it at 14,200.",
        "Brakes and battery were replaced last spring, and the records are in the folder. The tires have about a year left.",
        "Thirteen-nine is my final number, and I can do the paperwork right now.",
    ],
    "ask_for_raise": [
        "Fifteen percent above what you're paid now — where does that number come from?",
        "Three postings and two offers in your network. That's a source I can use. What range are you asking for?",
        "I check it against the pay band for the role, HR reviews it, and I'll come back to you by end of week.",
        "That's a fair question — what would a backfill actually cost us, in your view?",
    ],
    "the_ask": [
        "Close — birds, not sleep. It's on green corridors: the strips of trees that link city parks, and whether more bird species nest because of them.",
        "I'm out at six most mornings counting birds along the old rail line park. Last month a pair of warblers nested there. What's your problem set on?",
        "Ha — maybe. Let me survive this week first.",
        "A few of us from the seminar grab coffee after class on Thursdays. You should come along sometime.",
        "Good questions. I'm curious what you're reading for the seminar, honestly.",
    ],
    "spanish_coffee": [
        "¡Marchando un café con leche! ¿Algo para comer?",
        "Te recomiendo el cruasán, 1,80 €, o la tarta de queso, 3,50 €.",
        "No, soy de Sevilla, pero vivo en Madrid desde hace diez años. Llevo tres años en Café Sol.",
        "Un café con leche y un cruasán son 3,60 €. ¡Muchas gracias!",
        "¡Correcto! Muy natural. Gracias.",
    ],
    "behavioral_interview": [
        "A load test in CI so it couldn't come back — good. Tell me about a mistake you made and what you learned from it.",
        "In the first month you'd ship a small change through the deploy pipeline and shadow on-call. By day ninety you'd run the load test for our next large customer.",
        "The platform team is eight engineers. We own the API gateway, the job queue and the deploy pipeline.",
        "How do you operate under ambiguity, without explicit requirements or much guidance?",
        "I appreciate the ownership and the reflection there — owning a mistake like that is rare.",
    ],
}


@pytest.mark.parametrize("scenario_id", _DEMO_IDS)
def test_rule_following_lines_pass_the_hidden_agenda_leak_check(scenario_id):
    info = _load(scenario_id)
    agenda = info.scenario_data.npc.private_persona.hidden_agenda
    for line in _RULE_FOLLOWING_LINES[scenario_id]:
        result = validate_npc_output(line, hidden_agenda=agenda)
        assert result.violations == [], (
            f"{scenario_id}: {line!r} flagged: {[v.reason for v in result.violations]}"
        )
