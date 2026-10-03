# SPDX-License-Identifier: Apache-2.0
"""The flyting calibration suites, run against the real scoring pipeline.

This is the CI half of ``scripts/flyting-calibration.py``: the deterministic
expectations (gate outcomes, fouls, flags, the plagiarism cap) need no model, so
they run on every commit. A change to the gates, the cliché corpus, or the craft
metrics that moves scoring shows up here instead of in a player's run.

The judged expectations — bands, hooks — are skipped by definition without a
model; ``--judge RUNTIME_ID`` on the script is the nightly, real-model path.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "flyting-calibration.py"
_OFFICIAL_PACKS = _REPO_ROOT / "packs" / "official"


def _load_runner():
    """Import the calibration runner from scripts/ (not an installed module)."""
    if not _SCRIPT.is_file():
        pytest.skip(f"Calibration runner not found: {_SCRIPT}")
    spec = importlib.util.spec_from_file_location("flyting_calibration", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


@pytest.fixture(scope="module")
def pack_dirs(runner):
    if not _OFFICIAL_PACKS.is_dir():
        pytest.skip(f"Official packs directory not found: {_OFFICIAL_PACKS}")
    dirs = runner.default_pack_dirs()
    if not dirs:
        pytest.skip("No official pack ships a calibration suite")
    return dirs


class TestOfficialCalibration:
    def test_every_deterministic_expectation_holds(self, runner, pack_dirs):
        failures: list[str] = []
        checked = 0
        for pack_dir in pack_dirs:
            for suite in runner.run_pack(pack_dir):
                checked += suite.checked
                failures += [f"{suite.path}: {error}" for error in suite.errors]
                failures += [
                    f"{suite.path} [{volley.volley_id}] {failure}"
                    for volley in suite.volleys
                    for failure in volley.failures
                ]
        assert not failures, "Calibration drift:\n  " + "\n  ".join(failures)
        # A suite that asserts nothing would pass silently, which is the one
        # failure mode a calibration runner cannot be allowed to have.
        assert checked > 0

    def test_the_flyting_pack_ships_a_suite_per_scenario(self, runner):
        """Every shipped flyting scenario is covered, so drift cannot hide."""
        pack_dir = _OFFICIAL_PACKS / "flyting-school"
        if not pack_dir.is_dir():
            pytest.skip("Flyting School pack not found")
        covered = {suite.scenario_id for suite in runner.run_pack(pack_dir)}
        assert covered == set(runner._flyting_scenarios(pack_dir))


class TestJudgedSampling:
    """``--limit N`` is the nightly's whole judge budget, so it must buy calls.

    Every expectation in these suites carries a band, gated volleys included, so
    "prefer the judged ones" is not a strong enough rule on its own: a suite
    that opens with a dud and two fouls would spend its entire sample on volleys
    that never reach a model, pass, and report nothing about judge drift.
    """

    def test_a_limited_sample_prefers_volleys_that_reach_the_judge(self, runner):
        data = {
            "volleys": [
                {"id": "short", "expect": {"gate": "dud", "band": "dud"}},
                {"id": "foul", "expect": {"gate": "foul", "band": "dud"}},
                {"id": "aimed", "expect": {"gate": "ok", "band": "solid"}},
                {"id": "strong", "expect": {"gate": "ok", "band": "strong"}},
            ]
        }
        picked = [entry["id"] for entry in runner._entries_for(data, 2)]
        assert picked == ["aimed", "strong"]

    def test_a_gated_volley_is_still_sampled_once_the_judged_ones_are_in(self, runner):
        data = {
            "volleys": [
                {"id": "short", "expect": {"gate": "dud", "band": "dud"}},
                {"id": "aimed", "expect": {"gate": "ok", "band": "solid"}},
                {"id": "no_expectations", "expect": {}},
            ]
        }
        # File order is preserved in the output, so this asserts membership.
        assert [entry["id"] for entry in runner._entries_for(data, 2)] == ["short", "aimed"]

    def test_no_limit_runs_every_volley(self, runner):
        data = {"volleys": [{"id": "a", "expect": {}}, {"id": "b", "expect": {}}]}
        assert [entry["id"] for entry in runner._entries_for(data, None)] == ["a", "b"]

    def test_a_missing_gate_expectation_counts_as_reaching_the_judge(self, runner):
        """An author who omits ``gate`` is describing an ordinary volley."""
        assert runner._reaches_the_judge({"expect": {"band": "solid"}}) is True
        assert runner._reaches_the_judge({"expect": {"gate": "foul"}}) is False

    def test_every_official_suite_spends_a_small_sample_on_the_judge(
        self, runner, pack_dirs
    ):
        """The nightly dispatches ``--limit 3``; each suite must then cost 3 calls."""
        import yaml

        for pack_dir in pack_dirs:
            for path in sorted((pack_dir / "calibration").glob("*.yaml")):
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                sample = runner._entries_for(data, 3)
                judged = [e for e in sample if runner._reaches_the_judge(e)]
                assert len(judged) == min(
                    3, sum(1 for e in data["volleys"] if runner._reaches_the_judge(e))
                ), f"{path.name} spends its judged sample on gated volleys"


class TestDeterministicBands:
    """A zeroed volley's band needs no model, so CI checks it on every commit.

    ``band`` is normally a judged expectation, but a volley the gates dud or
    foul scores 0 whatever a judge would have said and never reaches a model.
    Skipping its band only because of the key's usual tier would leave a real
    assertion — "this gate fired" — unchecked until somebody dispatched a
    nightly.
    """

    def _result(self, runner, expect, *, text="go away", judged=False):
        pack_dir = _OFFICIAL_PACKS / "flyting-school"
        scenarios = runner._flyting_scenarios(pack_dir)
        scenario = scenarios["whitechapel_rose"]
        from convsim_core.flyting.service import VolleyScoringService

        service = VolleyScoringService(scenario.scoring_context())
        score = service.score_mechanically(text, volley_number=1)
        return runner._check_volley("probe", expect, score, judged=judged)

    def test_a_gated_bands_expectation_is_checked_without_a_judge(self, runner):
        result = self._result(runner, {"gate": "dud", "band": "dud"})
        assert result.failures == []
        assert result.checked == 2   # gate and band
        assert result.skipped == 0

    def test_a_wrong_gated_band_fails_without_a_judge(self, runner):
        result = self._result(runner, {"band": "solid"})
        assert result.skipped == 0
        assert any("band" in failure for failure in result.failures)

    def test_an_ungated_band_is_still_judged_only(self, runner):
        result = self._result(
            runner,
            {"band": "solid"},
            text="You polish your virtue like your carriage brass, and both are plate.",
        )
        assert result.skipped == 1
        assert result.failures == []

    def test_a_gated_band_is_not_double_counted_on_a_judged_run(self, runner):
        result = self._result(runner, {"gate": "dud", "band": "dud"}, judged=True)
        assert result.failures == []
        assert result.checked == 2


class TestNoOpExpectations:
    """An expectation block has to actually assert something.

    ``expect`` carries ``minProperties: 1`` so that an empty block cannot ship:
    it would cost a judge call, check nothing, and be reported as a pass. An
    empty *list* under one of the three list-valued keys slipped through that
    guard and did exactly the same thing, and ``judge_unavailable`` did it while
    looking like a real assertion — the runner skips that flag outright, because
    it is a property of the run rather than of the volley (present on every
    ungated volley of a judge-free run and on none of a judged one).

    Both are now schema errors, so an author hears about it from
    ``convsim-validate-pack`` rather than from a green run that proved nothing.
    """

    @staticmethod
    def _errors(expect: dict) -> list[str]:
        import json

        import jsonschema

        schema = json.loads(
            (_REPO_ROOT / "schemas" / "flyting-calibration.schema.json").read_text(
                encoding="utf-8"
            )
        )
        document = {
            "schema_version": "0.1",
            "calibration_id": "probe",
            "scenario_id": "whitechapel_rose",
            "description": "A probe suite.",
            "volleys": [
                {"id": "probe", "text": "You are plate, not sterling.", "expect": expect}
            ],
        }
        validator = jsonschema.Draft202012Validator(schema)
        return [error.message for error in validator.iter_errors(document)]

    @pytest.mark.parametrize("key", ["flags", "hooks", "judge_fouls"])
    def test_an_empty_assertion_list_is_a_schema_error(self, key):
        assert self._errors({key: []}), (
            f"{key}: [] asserts nothing, so it must not validate — it would cost "
            "a judge call and be reported as a pass"
        )

    def test_judge_unavailable_is_not_an_assertable_flag(self):
        assert self._errors({"flags": ["judge_unavailable"]}), (
            "judge_unavailable must not validate: the runner skips it, so an "
            "entry asserting only that flag checks nothing and passes"
        )

    def test_the_runner_still_ignores_judge_unavailable_if_it_reaches_it(self, runner):
        """The schema is the gate; the runner stays defensive behind it.

        A pack can be hand-edited after validation, and a flag the runner cannot
        check must not be counted as checked — which would report a pass on an
        assertion nobody made.
        """
        result = TestDeterministicBands()._result(
            runner, {"gate": "dud", "flags": ["judge_unavailable"]}
        )
        assert result.failures == []
        assert result.checked == 1  # the gate only
        assert result.skipped == 0

    def test_a_real_assertion_list_still_validates(self):
        assert self._errors({"flags": ["too_short"], "hooks": ["vanity"]}) == []


class TestMeasurementConditions:
    """What a judged measurement is taken under, pinned.

    A recorded band is only reproducible if the run-dependent inputs are the
    same every time, and the subtlest of them is the discovery ledger. Eight
    reference volleys across four suites exist to strike a ``discoverable``
    trait, and their bands were measured with the x2 that the first strike on
    one is worth — because ``_score_with_judge`` hands the judge an *empty*
    ledger, in which every discoverable trait reads as freshly found.

    "Empty" and "absent" are one refactor apart: ``judge_volley`` normalises
    ``discovered_traits`` with ``set(discovered_traits or ())``, so dropping
    that normalisation (or threading a real ``None`` through to
    ``parse_volley_judgment``) would turn ``HookClaim.discovered`` off and lower
    all eight bands with nothing failing to say so. This is the test that says
    so.
    """

    _VERDICT = {
        "sting": 8,
        "wit": 8,
        "craft": 9,
        "fidelity": 9,
        # ``new_money`` is visibility: discoverable on Lord Bellingham.
        "hooks": [{"trait": "new_money", "evidence": "plate, not sterling"}],
        "themes": ["wealth"],
        "devices": ["metaphor"],
        "riposte": {"is_riposte": False, "evidence": None},
        "callback": {"is_callback": False, "evidence": None},
        "fouls": [],
        "umpire_line": "Borrowed brass, and he knows it.",
    }

    _TEXT = (
        "Lord B—, you polish your virtue like your carriage brass, and both are "
        "plate, not sterling, worn thin where the public grips them."
    )

    class _StubJudge:
        """A runtime that answers the judge schema and nothing else."""

        def __init__(self, verdict):
            self._verdict = verdict

        async def chat_stream(self, request):
            import json

            from convsim_core.runtime.types import ChatFinal

            yield ChatFinal(
                text=json.dumps(self._verdict),
                structured=self._verdict,
                model_id="stub-judge",
                input_tokens=1,
                output_tokens=1,
            )

    def _score(self, runner):
        import asyncio

        from convsim_core.flyting.service import VolleyScoringService

        pack_dir = _OFFICIAL_PACKS / "flyting-school"
        scenario = runner._flyting_scenarios(pack_dir)["whitechapel_rose"]
        service = VolleyScoringService(scenario.scoring_context())
        return asyncio.run(
            runner._score_with_judge(
                service, scenario, self._TEXT, self._StubJudge(self._VERDICT)
            )
        )

    def test_a_hook_on_a_discoverable_trait_counts_as_a_discovery(self, runner):
        score = self._score(runner)
        assert score.judgment is not None, "the stub judge was not consulted"
        assert [(h.trait, h.discovered) for h in score.judgment.hooks] == [
            ("new_money", True)
        ], (
            "A judged measurement must start from an empty discovery ledger, so "
            "the first strike on a discoverable trait is a discovery. Without "
            "it the eight discoverable-trait bands in the launch pack are "
            "measured against different arithmetic than they record."
        )

    def test_the_discovery_doubling_is_in_the_measured_topicality(self, runner):
        score = self._score(runner)
        # One verified hook at the default 0.15, doubled for the discovery.
        assert score.topicality == pytest.approx(1.30)

    def test_nothing_run_dependent_other_than_the_ledger_is_supplied(self, runner):
        """The other three isolation conditions, so the docstring cannot drift.

        Freshness is measured against the cliché corpus alone, theme decay never
        applies, and the device-rotation window is empty — so a volley with any
        named device takes the +5.
        """
        score = self._score(runner)
        assert score.freshness.nearest_source in ("cliche", "none")
        assert score.freshness.theme_decay == pytest.approx(1.0)
        assert [b.id for b in score.bonuses] == ["device_rotation"]
