# SPDX-License-Identifier: Apache-2.0
"""Tests for the flyting half of the pack validator (issue #454).

These are the checks JSON Schema cannot express, so nothing else catches them:
a target with nothing to aim at, judge weights that do not sum to one, a
calibration suite naming a scenario or trait that does not exist, and a
scenario authored in a language the deterministic stages cannot read.

Each test covers one ``rule_id`` and asserts against the structured issue list
rather than message text, the same way ``test_pack_validator.py`` does. The
shipping Flyting School pack only ever exercises the happy path, which is
exactly why the failure paths need their own fixtures.
"""
from pathlib import Path

from convsim_core.packs.validator import validate_pack_dir
from tests.helpers import make_yaml_pack_dir

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FLYTING_SCENARIO = """\
schema_version: "0.1"
scenario_id: flyt
title: A Test Flyting
summary: A minimal flyting scenario for validator unit tests.
mode: flyting
player_role:
  label: Challenger
  brief: You are testing the volley pipeline.
npc:
  ref: ../npcs/flyt_npc.yaml
rubric:
  ref: ../rubrics/flyt_rubric.yaml
duration:
  max_turns: 10
opening:
  npc_says: Say something worth hearing, then.
goals:
  player_visible:
    - Out-talk the target
flyting:
  formats: [batting_practice]
  difficulty_multiplier: 1.0
"""

_FLYTING_NPC = """\
schema_version: "0.1"
npc_id: flyt_npc
display_name: Test Target
archetype: generic
fictional: true
age_band: adult
public_persona:
  occupation: Target of unit-test taunts
  speaking_style: Neutral and direct
  demeanor: Unimpressed
private_persona: {}
attack_surface:
  - id: vanity
    brief: Convinced the mirror is on their side.
    visibility: visible
  - id: new_money
    brief: The crest is newer than the carriage.
    visibility: discoverable
"""

# A rubric whose volley_judge block is well formed: weights sum to 1.0 and
# every judged dimension carries an anchor.
_FLYTING_RUBRIC = """\
schema_version: "0.1"
rubric_id: flyt_rubric
title: Test Flyting Rubric
dimensions:
  - id: quality
    name: Response Quality
    description: How well the player responded
    scoring:
      low: Poor response
      medium: Adequate response
      high: Strong response
volley_judge:
  weights:
    sting: 0.35
    wit: 0.25
    craft: 0.20
    fidelity: 0.20
  anchors:
    - dimension: sting
      score: 2
      example: You are the worst.
    - dimension: sting
      score: 6
      example: Your advice fits you about as well as your coat.
    - dimension: sting
      score: 9
      example: You preach thrift and bank the takings of two gin palaces.
    - dimension: wit
      score: 2
      example: You are bad and also bad.
    - dimension: wit
      score: 6
      example: You have the bearing of a man who has rehearsed it.
    - dimension: wit
      score: 9
      example: You came up the hill in a chair and have lectured us on the climb since.
    - dimension: craft
      score: 2
      example: you are bad at everything and everyone knows it
    - dimension: craft
      score: 6
      example: Your coat is fine; your argument is thin.
    - dimension: craft
      score: 9
      example: Powder, corset, and a crest by the yard — three coats on one rotten post.
    - dimension: fidelity
      score: 2
      example: your whole vibe is off
    - dimension: fidelity
      score: 6
      example: You are not the gentleman you pretend to be, sir.
    - dimension: fidelity
      score: 9
      example: I would call you a blackguard, but the word implies a guard.
"""

_CALIBRATION = """\
schema_version: "0.1"
calibration_id: flyt_calibration
scenario_id: flyt
description: Reference volleys for the test flyting scenario.
volleys:
  - id: too_short
    text: you stink
    expect:
      gate: dud
      band: dud
      flags: [too_short]
  - id: aimed
    text: Your crest is newer than your carriage, and both were bought on credit.
    expect:
      gate: ok
      hooks: [new_money]
"""


def _flyting_pack(
    tmp_path: Path,
    *,
    scenario: str = _FLYTING_SCENARIO,
    npc: str = _FLYTING_NPC,
    rubric: str = _FLYTING_RUBRIC,
    calibration: str | None = None,
    manifest: str | None = None,
) -> Path:
    """A YAML pack carrying one conversation scenario and one flyting scenario."""
    extra = {
        "scenarios/flyt.yaml": scenario,
        "npcs/flyt_npc.yaml": npc,
        "rubrics/flyt_rubric.yaml": rubric,
    }
    if calibration is not None:
        extra["calibration/flyt.yaml"] = calibration
    return make_yaml_pack_dir(tmp_path, manifest_yaml=manifest, extra_files=extra)


def _rule_ids(result) -> set[str]:
    return {i.rule_id for i in result.errors} | {i.rule_id for i in result.warnings}


def _issue(result, rule_id: str):
    for issue in (*result.errors, *result.warnings):
        if issue.rule_id == rule_id:
            return issue
    return None


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_well_formed_flyting_scenario_raises_nothing(tmp_path):
    result = validate_pack_dir(_flyting_pack(tmp_path, calibration=_CALIBRATION))
    assert result.errors == []
    assert not {r for r in _rule_ids(result) if r.startswith("FLYTING_")}


def test_conversation_scenario_is_not_held_to_flyting_rules(tmp_path):
    """The pack's own `intro.yaml` declares no mode, so none of this applies."""
    # No flyting scenario at all: the default YAML pack, whose NPC declares no
    # attack surface and whose rubric carries no volley_judge block.
    result = validate_pack_dir(make_yaml_pack_dir(tmp_path))
    assert not {r for r in _rule_ids(result) if r.startswith("FLYTING_")}


# ---------------------------------------------------------------------------
# The attack surface
# ---------------------------------------------------------------------------


def test_target_with_no_attack_surface_is_an_error(tmp_path):
    npc = _FLYTING_NPC.split("attack_surface:")[0]
    result = validate_pack_dir(_flyting_pack(tmp_path, npc=npc))
    assert "FLYTING_NO_ATTACK_SURFACE" in {i.rule_id for i in result.errors}
    assert result.valid is False


def test_single_trait_attack_surface_warns(tmp_path):
    npc = _FLYTING_NPC.replace(
        "  - id: new_money\n"
        "    brief: The crest is newer than the carriage.\n"
        "    visibility: discoverable\n",
        "",
    )
    result = validate_pack_dir(_flyting_pack(tmp_path, npc=npc))
    ids = {i.rule_id for i in result.warnings}
    assert "FLYTING_THIN_ATTACK_SURFACE" in ids
    # A one-trait visible surface is also a surface with nothing to discover.
    assert "FLYTING_NO_DISCOVERABLE_TRAIT" in ids


def test_fully_visible_attack_surface_warns(tmp_path):
    npc = _FLYTING_NPC.replace("visibility: discoverable", "visibility: visible")
    result = validate_pack_dir(_flyting_pack(tmp_path, npc=npc))
    assert "FLYTING_NO_DISCOVERABLE_TRAIT" in {i.rule_id for i in result.warnings}
    assert "FLYTING_THIN_ATTACK_SURFACE" not in {i.rule_id for i in result.warnings}


# ---------------------------------------------------------------------------
# The judge rubric
# ---------------------------------------------------------------------------


def test_judge_weights_that_do_not_sum_to_one_warn(tmp_path):
    rubric = _FLYTING_RUBRIC.replace("sting: 0.35", "sting: 0.5")
    result = validate_pack_dir(_flyting_pack(tmp_path, rubric=rubric))
    issue = _issue(result, "FLYTING_JUDGE_WEIGHTS_SUM")
    assert issue is not None
    assert "1.15" in issue.message


_FIDELITY_ANCHORS = (
    "    - dimension: fidelity\n      score: 2\n"
    "      example: your whole vibe is off\n",
    "    - dimension: fidelity\n      score: 6\n"
    "      example: You are not the gentleman you pretend to be, sir.\n",
    "    - dimension: fidelity\n      score: 9\n"
    "      example: I would call you a blackguard, but the word implies a guard.\n",
)


def _rubric_without(*anchors: str) -> str:
    rubric = _FLYTING_RUBRIC
    for anchor in anchors:
        assert anchor in rubric
        rubric = rubric.replace(anchor, "")
    return rubric


def test_dimension_with_no_anchor_warns(tmp_path):
    rubric = _rubric_without(*_FIDELITY_ANCHORS)
    result = validate_pack_dir(_flyting_pack(tmp_path, rubric=rubric))
    issue = _issue(result, "FLYTING_ANCHOR_COVERAGE")
    assert issue is not None
    assert "fidelity" in issue.message
    # Absent, not thin: the two checks must not both fire for one dimension.
    assert _issue(result, "FLYTING_ANCHOR_DEPTH") is None


def test_dimension_with_too_few_anchors_warns(tmp_path):
    """One anchor is a single end of a scale, not a scale.

    A pack that supplies `anchors` replaces the engine's defaults wholesale, so
    a dimension given one anchor keeps one — and the judge is told the anchors
    are the scale. The launch pack's own Veiled Civility rubric had exactly this
    shape (one wit anchor, no sting ceiling), which the zero-anchor check could
    not see.
    """
    rubric = _rubric_without(*_FIDELITY_ANCHORS[1:])
    result = validate_pack_dir(_flyting_pack(tmp_path, rubric=rubric))
    issue = _issue(result, "FLYTING_ANCHOR_DEPTH")
    assert issue is not None
    assert "fidelity (1)" in issue.message
    assert _issue(result, "FLYTING_ANCHOR_COVERAGE") is None
    assert result.errors == []


# ---------------------------------------------------------------------------
# Calibration suites
# ---------------------------------------------------------------------------


def test_calibration_naming_an_unknown_scenario_is_an_error(tmp_path):
    calibration = _CALIBRATION.replace("scenario_id: flyt", "scenario_id: nope")
    result = validate_pack_dir(_flyting_pack(tmp_path, calibration=calibration))
    assert "FLYTING_CALIBRATION_UNKNOWN_SCENARIO" in {i.rule_id for i in result.errors}


def test_calibration_expecting_an_undeclared_hook_is_an_error(tmp_path):
    calibration = _CALIBRATION.replace("hooks: [new_money]", "hooks: [cowardice]")
    result = validate_pack_dir(_flyting_pack(tmp_path, calibration=calibration))
    issue = _issue(result, "FLYTING_CALIBRATION_UNKNOWN_HOOK")
    assert issue is not None
    assert "cowardice" in issue.message


def test_calibration_with_an_impossible_band_is_an_error(tmp_path):
    calibration = _CALIBRATION.replace(
        "      gate: ok\n      hooks: [new_money]\n",
        "      min_score: 200\n      max_score: 100\n",
    )
    result = validate_pack_dir(_flyting_pack(tmp_path, calibration=calibration))
    assert "FLYTING_CALIBRATION_IMPOSSIBLE_BAND" in {i.rule_id for i in result.errors}


# ---------------------------------------------------------------------------
# Language scope
#
# Stages 0-2 read English spelling: the frequency table, the second-person aim
# check, the sound-play approximations, and the recognisable-word test behind
# the gibberish gate. A non-Latin-script scenario is unplayable — every volley
# is dudded before the judge is called — and a Latin-script one scores with no
# craft metrics, so the author is told rather than left to discover it.
# ---------------------------------------------------------------------------


def test_non_english_flyting_scenario_warns(tmp_path):
    scenario = _FLYTING_SCENARIO + "supported_languages:\n  - fr\n"
    result = validate_pack_dir(_flyting_pack(tmp_path, scenario=scenario))
    issue = _issue(result, "FLYTING_NON_ENGLISH_SCENARIO")
    assert issue is not None
    assert issue.pointer == "/supported_languages"
    assert "fr" in issue.message


def test_flyting_scenario_offering_english_among_others_does_not_warn(tmp_path):
    scenario = _FLYTING_SCENARIO + "supported_languages:\n  - fr\n  - en\n"
    result = validate_pack_dir(_flyting_pack(tmp_path, scenario=scenario))
    assert "FLYTING_NON_ENGLISH_SCENARIO" not in _rule_ids(result)


def test_flyting_scenario_inherits_a_non_english_manifest(tmp_path):
    """An omitted list means "inherit the manifest's" (scenario.schema.json)."""
    from tests.helpers import _VALID_MANIFEST_YAML

    manifest = _VALID_MANIFEST_YAML.replace(
        "supported_languages:\n  - en\n", "supported_languages:\n  - de\n"
    )
    result = validate_pack_dir(_flyting_pack(tmp_path, manifest=manifest))
    issue = _issue(result, "FLYTING_NON_ENGLISH_SCENARIO")
    assert issue is not None
    assert issue.pointer == "(root)"
    assert "de" in issue.message


def test_conversation_scenario_in_another_language_does_not_warn(tmp_path):
    """Only the flyting stages are English-only; a conversation pack is not."""
    from tests.helpers import _VALID_MANIFEST_YAML

    manifest = _VALID_MANIFEST_YAML.replace(
        "supported_languages:\n  - en\n", "supported_languages:\n  - de\n"
    )
    result = validate_pack_dir(make_yaml_pack_dir(tmp_path, manifest_yaml=manifest))
    assert "FLYTING_NON_ENGLISH_SCENARIO" not in _rule_ids(result)
