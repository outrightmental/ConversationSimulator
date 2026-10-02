# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the nightly real-model smoke harness (issue #457).

These run on every PR and need no model, no network and no llama-server: they
cover the harness's decision logic — checksum verification, the end-to-end
assertions, budget evaluation, failure classification and reporting — so that
when the nightly goes red, the verdict it prints can be trusted.

The real-model path itself is exercised only by
.github/workflows/model-smoke-nightly.yml; see docs/real-model-smoke.md.
"""
from __future__ import annotations

import hashlib
import http.client
import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "nightly-model-smoke.py"


def _load_module():
    """Import the hyphenated script as a module."""
    spec = importlib.util.spec_from_file_location("nightly_model_smoke", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke = _load_module()


# ---------------------------------------------------------------------------
# Failure classification contract
# ---------------------------------------------------------------------------


class TestFailureClassification:
    """Each class maps to its own exit code, so CI can tell failures apart."""

    def test_every_class_has_a_unique_exit_code(self) -> None:
        codes = list(smoke.EXIT_CODES.values())
        assert len(codes) == len(set(codes)), "exit codes must be distinguishable"
        assert 0 not in codes, "a failure must never exit 0"

    def test_every_class_has_an_exit_code_and_a_remedy(self) -> None:
        classes = {
            value for name, value in vars(smoke.FailureClass).items()
            if not name.startswith("_") and isinstance(value, str)
        }
        assert classes == set(smoke.EXIT_CODES)
        assert classes == set(smoke.REMEDIES)

    def test_download_and_checksum_are_separate_classes(self) -> None:
        # The acceptance criterion for #457: a download failure and a checksum
        # drift must not look alike in CI output.
        assert smoke.EXIT_CODES[smoke.FailureClass.DOWNLOAD] != smoke.EXIT_CODES[
            smoke.FailureClass.CHECKSUM
        ]

    def test_failure_carries_its_exit_code_and_remedy(self) -> None:
        exc = smoke.SmokeFailure(smoke.FailureClass.RUNTIME, "boom", phase="runtime_start")
        assert exc.exit_code == smoke.EXIT_CODES[smoke.FailureClass.RUNTIME]
        assert exc.phase == "runtime_start"
        assert exc.remedy == smoke.REMEDIES[smoke.FailureClass.RUNTIME]

    def test_a_failure_can_override_its_class_remedy(self) -> None:
        # Failures that borrow a class's exit code without matching its usual
        # cause must not print that class's advice.
        exc = smoke.SmokeFailure(
            smoke.FailureClass.PIPELINE, "boom", remedy="Do this instead."
        )
        assert exc.exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        assert exc.remedy == "Do this instead."


# ---------------------------------------------------------------------------
# Checksum verification
# ---------------------------------------------------------------------------


class TestChecksumVerification:
    """Checksum drift must fail loudly, and must not poison the next run."""

    @staticmethod
    def _write(tmp_path: Path, payload: bytes = b"gguf-ish bytes") -> tuple[Path, str]:
        path = tmp_path / "model.gguf"
        path.write_bytes(payload)
        return path, hashlib.sha256(payload).hexdigest()

    def test_matching_checksum_returns_the_digest(self, tmp_path: Path) -> None:
        path, digest = self._write(tmp_path)
        assert smoke.verify_model_checksum(path, digest) == digest
        assert path.exists()

    def test_drift_raises_checksum_class(self, tmp_path: Path) -> None:
        path, _ = self._write(tmp_path)
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke.verify_model_checksum(path, "0" * 64)
        assert exc_info.value.failure_class == smoke.FailureClass.CHECKSUM
        assert exc_info.value.exit_code == 3

    def test_drift_deletes_the_bad_file_so_a_rerun_redownloads(self, tmp_path: Path) -> None:
        path, _ = self._write(tmp_path)
        with pytest.raises(smoke.SmokeFailure):
            smoke.verify_model_checksum(path, "0" * 64)
        assert not path.exists()

    def test_drift_can_keep_the_file_for_inspection(self, tmp_path: Path) -> None:
        path, _ = self._write(tmp_path)
        with pytest.raises(smoke.SmokeFailure):
            smoke.verify_model_checksum(path, "0" * 64, delete_on_mismatch=False)
        assert path.exists()

    def test_missing_file_is_a_download_failure_not_a_checksum_failure(self, tmp_path: Path) -> None:
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke.verify_model_checksum(tmp_path / "absent.gguf", "0" * 64)
        assert exc_info.value.failure_class == smoke.FailureClass.DOWNLOAD

    def test_download_skips_the_fetch_but_still_verifies_an_existing_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = b"already here"
        (tmp_path / "m.gguf").write_bytes(payload)

        def _never(*args: object, **kwargs: object) -> None:
            raise AssertionError("must not re-download an existing file")

        monkeypatch.setattr(smoke, "_download_with_progress", _never)
        # Correct digest: returns the path.
        assert smoke.download_model(
            "http://example.invalid/m.gguf", hashlib.sha256(payload).hexdigest(), "m", tmp_path
        ) == tmp_path / "m.gguf"
        # Wrong digest: a cache hit with drifted bytes still fails.
        (tmp_path / "m.gguf").write_bytes(payload)
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke.download_model("http://example.invalid/m.gguf", "0" * 64, "m", tmp_path)
        assert exc_info.value.failure_class == smoke.FailureClass.CHECKSUM


class TestDownloadFailureClassification:
    """Every way a fetch can break has to land in the `download` class."""

    @staticmethod
    def _urlopen_raising(exc: BaseException):
        class _Resp:
            headers = {"Content-Length": "1048576"}

            def read(self, _n: int) -> bytes:
                raise exc

            def __enter__(self):
                return self

            def __exit__(self, *a: object) -> bool:
                return False

        return lambda *args, **kwargs: _Resp()

    @pytest.mark.parametrize("exc", [
        # A cut-off response mid-body. NOT an OSError, so an OSError-only
        # handler let it escape as a traceback — exit 1, which reads as `budget`.
        http.client.IncompleteRead(b"partial"),
        ConnectionResetError("peer hung up"),
        TimeoutError("read timed out"),
    ])
    def test_a_broken_transfer_is_a_download_failure(
        self, exc: BaseException, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            smoke.urllib.request, "urlopen", self._urlopen_raising(exc)
        )
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._download_with_progress("https://example.invalid/m.gguf", tmp_path / "m.gguf")
        assert exc_info.value.failure_class == smoke.FailureClass.DOWNLOAD
        assert exc_info.value.exit_code == 2

    def test_a_broken_transfer_leaves_no_partial_file_to_checksum_fail_on(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dest = tmp_path / "m.gguf"
        monkeypatch.setattr(
            smoke.urllib.request, "urlopen",
            self._urlopen_raising(http.client.IncompleteRead(b"partial")),
        )
        with pytest.raises(smoke.SmokeFailure):
            smoke._download_with_progress("https://example.invalid/m.gguf", dest)
        assert not dest.exists()


# ---------------------------------------------------------------------------
# Registry resolution
# ---------------------------------------------------------------------------


class TestRegistryResolution:
    """The workflow's cache key, URL and checksum come from one lookup."""

    def test_resolves_the_real_starter_model(self) -> None:
        model = smoke.resolve_registry_model("starter")
        assert model["id"]
        assert model["url"].startswith("https://")
        assert len(model["sha256"]) == 64
        assert model["sha256"] == model["sha256"].lower()

    def test_starter_is_the_smallest_registry_model(self) -> None:
        # #457 asks for the smallest registry model; guard against a future
        # registry edit that makes "starter" no longer the smallest.
        import yaml

        registry = yaml.safe_load(
            (REPO_ROOT / "model-registry" / "registry.yaml").read_text(encoding="utf-8")
        )
        # The user-supplied placeholder has no size and nothing to download.
        sizes = {
            m["id"]: m["size_gb"] for m in registry["models"]
            if m.get("size_gb") is not None
        }
        starter = smoke.resolve_registry_model("starter")
        assert sizes[starter["id"]] == min(sizes.values())

    def test_unknown_role_is_not_a_download_failure(self, tmp_path: Path) -> None:
        # `download`'s remedy ends "Nothing about the app changed — re-run the
        # job", which would send a triager round a loop: no number of re-runs
        # makes a missing `role: starter` entry appear. A registry that does not
        # describe a usable model is a repository problem, so it takes the
        # harness's catch-all class and its own remedy.
        registry = tmp_path / "registry.yaml"
        registry.write_text("models: []\n", encoding="utf-8")
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke.resolve_registry_model("starter", registry)
        assert exc_info.value.failure_class == smoke.FailureClass.PIPELINE
        assert exc_info.value.exit_code == 5
        assert "registry.yaml" in exc_info.value.remedy
        assert "re-run the job" not in exc_info.value.remedy.lower()

    def test_two_models_claiming_the_same_role_are_rejected(self, tmp_path: Path) -> None:
        # The cache key, the download URL and the verified checksum all come
        # from this one lookup, so an ambiguous role must stop the run rather
        # than let it pick arbitrarily.
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            "models:\n"
            "  - id: a\n"
            "    role: starter\n"
            "    download: {url: https://example.invalid/a.gguf, sha256: aa}\n"
            "  - id: b\n"
            "    role: starter\n"
            "    download: {url: https://example.invalid/b.gguf, sha256: bb}\n",
            encoding="utf-8",
        )
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke.resolve_registry_model("starter", registry)
        assert exc_info.value.failure_class == smoke.FailureClass.PIPELINE
        assert "expected exactly one" in str(exc_info.value)

    def test_model_without_checksum_is_rejected(self, tmp_path: Path) -> None:
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            "models:\n"
            "  - id: x\n"
            "    role: starter\n"
            "    download:\n"
            "      url: https://example.invalid/x.gguf\n",
            encoding="utf-8",
        )
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke.resolve_registry_model("starter", registry)
        assert "sha256" in str(exc_info.value)
        assert exc_info.value.failure_class == smoke.FailureClass.PIPELINE

    def test_github_output_is_appended(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        out = tmp_path / "gh-output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        smoke._emit_github_output({"model_id": "abc", "model_sha256": "def"})
        assert out.read_text(encoding="utf-8").splitlines() == [
            "model_id=abc",
            "model_sha256=def",
        ]


# ---------------------------------------------------------------------------
# Conversation assertions
# ---------------------------------------------------------------------------


def _turn(**overrides: object) -> dict:
    turn = {
        "label": "player_turn_1",
        "turn_number": 1,
        "model_generated": True,
        "npc_excerpt": "Tell me more about that platform.",
        "used_fallback": False,
    }
    turn.update(overrides)
    return turn


class TestEvaluateTurns:
    """Real NPC turns are the whole point of the nightly."""

    def test_healthy_conversation_passes(self) -> None:
        failures, warnings = smoke.evaluate_turns([_turn(), _turn(turn_number=2)])
        assert failures == []
        assert warnings == []

    def test_no_turns_fails(self) -> None:
        failures, _ = smoke.evaluate_turns([])
        assert failures

    def test_empty_npc_utterance_fails(self) -> None:
        failures, _ = smoke.evaluate_turns([_turn(npc_excerpt="")])
        assert any("no NPC utterance" in f for f in failures)

    def test_all_generated_turns_falling_back_fails(self) -> None:
        turns = [_turn(used_fallback=True), _turn(turn_number=2, used_fallback=True)]
        failures, _ = smoke.evaluate_turns(turns)
        assert any("fell back" in f for f in failures)

    def test_one_fallback_among_several_only_warns(self) -> None:
        turns = [_turn(used_fallback=True), _turn(turn_number=2), _turn(turn_number=3)]
        failures, warnings = smoke.evaluate_turns(turns)
        assert failures == []
        assert any("fell back" in w for w in warnings)

    def test_authored_opening_does_not_count_as_a_generated_turn(self) -> None:
        # The NPC opening is scenario text, not inference. A run whose only
        # non-fallback turn is the opening has produced no real NPC turns.
        turns = [
            {"label": "npc_opening", "turn_number": 0, "model_generated": False,
             "npc_excerpt": "Thanks for coming in."},
            _turn(used_fallback=True),
        ]
        failures, _ = smoke.evaluate_turns(turns)
        assert any("fell back" in f for f in failures)

    def test_missing_parse_flags_warn_that_the_fallback_check_did_not_run(self) -> None:
        # The flags come from the best-effort debug endpoint. Without them a
        # canned fallback looks exactly like real model output (a non-empty
        # utterance), so the run must not imply a proof it does not have.
        turns = [{"label": "player_turn_1", "turn_number": 1,
                  "model_generated": True, "npc_excerpt": "Go on."}]
        failures, warnings = smoke.evaluate_turns(turns)
        assert failures == []
        assert any("fallback check did not run" in w for w in warnings)

    def test_present_parse_flags_do_not_warn(self) -> None:
        failures, warnings = smoke.evaluate_turns([_turn()])
        assert failures == []
        assert warnings == []

    def test_opening_only_run_fails(self) -> None:
        turns = [{"label": "npc_opening", "turn_number": 0, "model_generated": False,
                  "npc_excerpt": "Thanks for coming in."}]
        failures, _ = smoke.evaluate_turns(turns)
        assert any("No model-generated" in f for f in failures)


# ---------------------------------------------------------------------------
# Debrief assertions
# ---------------------------------------------------------------------------


def _debrief(**overrides: object) -> dict:
    doc = {
        "scores": {"structure": 56.0, "evidence": 48.0},
        "overall_score": 52.0,
        "summary": "You gave concrete examples but hedged on the trade-off question.",
        "turning_points": [{"turn_number": 2, "description": "d", "impact": "i"}],
        "used_fallback": False,
    }
    doc.update(overrides)
    return doc


class TestEvaluateDebrief:
    """"Assert a scored debrief is produced" — the #457 acceptance criterion."""

    def test_scored_debrief_passes(self) -> None:
        failures, warnings = smoke.evaluate_debrief(_debrief())
        assert failures == []
        assert warnings == []

    def test_missing_debrief_fails(self) -> None:
        assert smoke.evaluate_debrief(None)[0]

    def test_unscored_debrief_fails(self) -> None:
        failures, _ = smoke.evaluate_debrief(_debrief(scores={}, overall_score=None))
        assert any("no rubric dimension scores" in f for f in failures)
        assert any("not numeric" in f for f in failures)

    def test_unscored_debrief_says_it_may_not_be_a_regression(self) -> None:
        # The scores come only from rubric_observations the model volunteers,
        # and nothing in the prompt asks for them (the built-in scenario defines
        # no rubric and no prompt layer names one), so an empty array satisfies
        # the turn schema. `pipeline`'s stock advice — inspect the per-turn
        # used_fallback flags — would send triage hunting a parse failure that
        # never happened, so the failure has to carry its own note.
        failures, _ = smoke.evaluate_debrief(_debrief(scores={}))
        no_scores = next(f for f in failures if "no rubric dimension scores" in f)
        assert smoke.UNSCORED_DEBRIEF_NOTE in no_scores
        assert "real-model-smoke.md" in no_scores

    def test_no_observations_anywhere_names_the_product_gap(self) -> None:
        # The run checked, and the model volunteered nothing to score: the
        # failure can state that outright instead of listing both possibilities.
        failures, _ = smoke.evaluate_debrief(
            _debrief(scores={}), rubric_observations_seen=0
        )
        no_scores = next(f for f in failures if "no rubric dimension scores" in f)
        assert "no NPC turn carried a rubric_observation" in no_scores
        assert smoke.UNSCORED_DEBRIEF_NOTE in no_scores
        assert smoke.UNSCORED_WITH_OBSERVATIONS_NOTE not in no_scores

    def test_observations_that_never_reached_the_debrief_are_a_regression(self) -> None:
        # The opposite case, and the one the harness exists to catch: the turns
        # returned observations and the debrief scored nothing, so the model did
        # its part and the debrief engine dropped the result. Printing the
        # "nothing asked the model for them" note here would excuse a real bug.
        failures, _ = smoke.evaluate_debrief(
            _debrief(scores={}), rubric_observations_seen=4
        )
        no_scores = next(f for f in failures if "no rubric dimension scores" in f)
        assert "returned 4 rubric observation(s)" in no_scores
        assert smoke.UNSCORED_WITH_OBSERVATIONS_NOTE in no_scores
        assert smoke.UNSCORED_DEBRIEF_NOTE not in no_scores
        assert "_parse_rubric_observations" in no_scores

    def test_a_scored_debrief_passes_whatever_the_turns_reported(self) -> None:
        # The count only explains an *unscored* debrief; it must never fail a
        # scored one (the debrief re-derives scores from stored raw output, so
        # the two counts are not required to agree).
        assert smoke.evaluate_debrief(_debrief(), rubric_observations_seen=0) == ([], [])

    def test_non_numeric_overall_score_fails(self) -> None:
        failures, _ = smoke.evaluate_debrief(_debrief(overall_score="52"))
        assert any("not numeric" in f for f in failures)

    def test_boolean_overall_score_is_not_a_number(self) -> None:
        failures, _ = smoke.evaluate_debrief(_debrief(overall_score=True))
        assert any("not numeric" in f for f in failures)

    @pytest.mark.parametrize("score", [-1, 101])
    def test_out_of_range_overall_score_fails(self, score: float) -> None:
        failures, _ = smoke.evaluate_debrief(_debrief(overall_score=score))
        assert any("outside [0, 100]" in f for f in failures)

    def test_empty_summary_fails(self) -> None:
        failures, _ = smoke.evaluate_debrief(_debrief(summary="   "))
        assert any("summary is shorter" in f for f in failures)

    def test_fallback_narrative_only_warns_because_scores_are_still_real(self) -> None:
        failures, warnings = smoke.evaluate_debrief(_debrief(used_fallback=True))
        assert failures == []
        assert any("fallback" in w for w in warnings)

    def test_absent_turning_points_only_warn(self) -> None:
        failures, warnings = smoke.evaluate_debrief(_debrief(turning_points=[]))
        assert failures == []
        assert any("turning points" in w for w in warnings)


# ---------------------------------------------------------------------------
# Budget evaluation
# ---------------------------------------------------------------------------


class TestEvaluateBudgets:
    def test_within_budget_passes(self) -> None:
        failures, lines = smoke.evaluate_budgets({"full_response_ms": 100_000}, 20.0)
        assert failures == []
        assert any("PASS" in line for line in lines)

    def test_tolerance_is_applied_before_failing(self) -> None:
        # 10 000 ms × 2 × 1.20 = 24 000 ms ceiling.
        assert smoke.evaluate_budgets({"full_response_ms": 23_999}, 2.0)[0] == []
        assert smoke.evaluate_budgets({"full_response_ms": 24_001}, 2.0)[0]

    def test_unbudgeted_metrics_are_not_checked(self) -> None:
        # session_start_ms and debrief_ms are reported but have no budget: the
        # opening is authored text and debrief latency has no documented SLO.
        assert "session_start_ms" not in smoke.BUDGETS_MS
        assert "debrief_ms" not in smoke.BUDGETS_MS
        failures, lines = smoke.evaluate_budgets(
            {"session_start_ms": 10 ** 9, "debrief_ms": 10 ** 9}, 1.0
        )
        assert failures == []
        assert lines == []

    def test_missing_measurement_is_skipped_not_failed(self) -> None:
        assert smoke.evaluate_budgets({}, 20.0) == ([], [])

    def test_failure_message_shows_the_arithmetic(self) -> None:
        failures, _ = smoke.evaluate_budgets({"full_response_ms": 10 ** 6}, 20.0)
        assert "documented budget 10000 ms × 20.0 × 1.2" in failures[0]


# ---------------------------------------------------------------------------
# Wall-clock budget
# ---------------------------------------------------------------------------


# Steps that burn the job's clock before the harness starts and so are invisible
# to its own deadline: checkout, three pip installs, the cache restore and, on a
# cache miss, the 2.5 GB download plus the cache save that follows it.  ~9 min
# cold; see the breakdown in docs/real-model-smoke.md.
PRE_SMOKE_JOB_MINUTES = 9

_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "model-smoke-nightly.yml"


def _workflow_text() -> str:
    return _WORKFLOW_PATH.read_text(encoding="utf-8")


def _workflow_budget_s() -> float:
    import re

    match = re.search(r"--wall-clock-budget-s (\d+)", _workflow_text())
    assert match, "the smoke step must pass an explicit --wall-clock-budget-s"
    return float(match.group(1))


def _job_timeout_minutes() -> int:
    import yaml

    return yaml.safe_load(_workflow_text())["jobs"]["model-smoke"]["timeout-minutes"]


class TestWorkflowBudgetAgreement:
    """The harness deadline must beat the job timeout, or exit 6 is unreachable."""

    def test_the_harness_deadline_trips_before_the_job_timeout(self) -> None:
        # timeout-minutes covers the whole job; the harness clock starts only at
        # its own step.  If the two are set as if they measured the same thing,
        # GitHub cancels the job first and the attributed timeout never prints.
        harness_min = _workflow_budget_s() / 60
        job_min = _job_timeout_minutes()
        assert harness_min + PRE_SMOKE_JOB_MINUTES <= job_min, (
            f"a {harness_min:.0f} min harness budget plus ~{PRE_SMOKE_JOB_MINUTES} min of "
            f"setup exceeds the {job_min} min job timeout, so GitHub cancels the job "
            "before the harness can report an attributed timeout"
        )

    def test_the_documented_target_is_under_thirty_minutes(self) -> None:
        # The acceptance criterion in #457: "< 30 min on standard GitHub runners".
        assert _job_timeout_minutes() <= 30

    def test_the_default_matches_what_the_workflow_passes(self) -> None:
        assert _workflow_budget_s() == smoke.DEFAULT_WALL_CLOCK_BUDGET_S


class TestDeadline:
    def test_phase_durations_are_recorded(self) -> None:
        clock = smoke.Deadline(60.0)
        clock.enter("checksum")
        clock.enter("runtime_start")
        durations = clock.finish()
        assert set(durations) >= {"startup", "checksum", "runtime_start"}

    def test_exhausted_budget_raises_timeout_naming_the_phase(self) -> None:
        clock = smoke.Deadline(0.0)
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            clock.check()
        assert exc_info.value.failure_class == smoke.FailureClass.TIMEOUT
        assert exc_info.value.exit_code == 6
        # The phase recorded is the one that ran out of budget.
        assert exc_info.value.phase == "startup"
        assert "startup" in str(exc_info.value)

    def test_an_overrun_found_at_a_boundary_blames_the_phase_that_ran_long(self) -> None:
        # The remedy for a timeout is "look at phase_durations_s", so the phase
        # it names has to be the one that consumed the budget. Blaming the phase
        # about to start would point triage at code that never executed.
        clock = smoke.Deadline(0.0)
        clock._phase = "conversation"  # the phase that overran
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            clock.enter("debrief")
        assert exc_info.value.phase == "conversation"
        assert "conversation" in str(exc_info.value)
        assert "debrief" not in str(exc_info.value)

    def test_cap_clamps_a_request_timeout_to_the_remaining_budget(self) -> None:
        clock = smoke.Deadline(30.0)
        assert clock.cap(10.0) == 10.0
        assert clock.cap(10_000.0) <= 30.0

    def test_cap_never_returns_a_useless_zero_timeout(self) -> None:
        clock = smoke.Deadline(1.0)
        assert clock.cap(600.0) >= 5.0

    def test_finish_does_not_raise_on_an_exhausted_budget(self) -> None:
        # finish() runs from run_smoke's finally block, where the timeout has
        # already been classified; raising there would discard the verdict.
        clock = smoke.Deadline(0.0)
        assert "startup" in clock.finish()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


class TestStepSummary:
    def test_failure_summary_names_class_and_remedy(self) -> None:
        text = smoke.render_step_summary({
            "verdict": "fail",
            "model_id": "qwen3-4b",
            "failure_class": smoke.FailureClass.RUNTIME,
            "exit_code": 4,
            "failures": ["convsim-core exited with code 1"],
            "wall_clock_s": 123.0,
            "wall_clock_budget_s": 1500.0,
            "phase_durations_s": {"runtime_start": 42.0},
        })
        assert "FAIL" in text
        assert "`runtime`" in text
        assert "convsim-core exited with code 1" in text
        assert smoke.REMEDIES[smoke.FailureClass.RUNTIME] in text

    def test_pass_summary_tabulates_measurements_with_ceilings(self) -> None:
        text = smoke.render_step_summary({
            "verdict": "pass",
            "model_id": "qwen3-4b",
            "ci_hardware_factor": 20.0,
            "measured_ms": {"full_response_ms": 110_000, "debrief_ms": 200_000},
            "wall_clock_s": 900.0,
            "wall_clock_budget_s": 1500.0,
        })
        assert "PASS" in text
        assert "240000 ms" in text  # 10 000 × 20 × 1.2
        assert "| `debrief_ms` | 200000 ms | — |" in text

    def test_summary_is_not_written_without_the_github_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        smoke._write_step_summary({"verdict": "pass"})  # must not raise

    def test_summary_is_appended_when_github_env_var_is_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
        smoke._write_step_summary({"verdict": "pass", "model_id": "m"})
        assert "PASS" in path.read_text(encoding="utf-8")

    def test_report_is_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "report.json"
        smoke._write_report(path, {"verdict": "pass", "failures": []})
        assert json.loads(path.read_text(encoding="utf-8"))["verdict"] == "pass"


# ---------------------------------------------------------------------------
# Event-payload extraction
# ---------------------------------------------------------------------------


class TestEventExtraction:
    def test_npc_turn_content_is_extracted(self) -> None:
        events = [
            {"event_type": "player_turn", "payload": {"content": "hi"}},
            {"event_type": "npc_turn", "payload": {"content": "Go on."}},
        ]
        assert smoke._npc_turn_content(events) == "Go on."

    def test_npc_opening_content_is_extracted(self) -> None:
        events = [{"event_type": "npc_opening", "payload": {"content": "Welcome."}}]
        assert smoke._npc_turn_content(events) == "Welcome."

    def test_absent_npc_event_yields_empty_string(self) -> None:
        assert smoke._npc_turn_content([{"event_type": "tts_chunk", "payload": {}}]) == ""

    def test_a_non_dict_payload_does_not_raise(self) -> None:
        # The excerpt is reported, not asserted on, so a surprising payload shape
        # must not turn an otherwise-green run into a harness bug (exit 5).
        assert smoke._npc_turn_content([{"event_type": "npc_turn", "payload": None}]) == ""
        assert smoke._npc_turn_content([{"event_type": "npc_turn"}]) == ""

    def test_rubric_observations_are_counted(self) -> None:
        events = [{"event_type": "npc_turn", "payload": {
            "content": "Go on.",
            "rubric_observations": [
                {"rubric_id": "structure", "observation": "o", "score_delta": 1},
                {"rubric_id": "evidence", "observation": "o", "score_delta": -1},
            ],
        }}]
        assert smoke._rubric_observation_count(events) == 2

    @pytest.mark.parametrize("payload", [
        {"content": "x"},                      # key absent entirely
        {"content": "x", "rubric_observations": []},
        {"content": "x", "rubric_observations": None},
    ])
    def test_absent_or_empty_rubric_observations_count_zero(self, payload: dict) -> None:
        assert smoke._rubric_observation_count(
            [{"event_type": "npc_turn", "payload": payload}]
        ) == 0

    def test_excerpt_is_bounded_and_collapsed(self) -> None:
        excerpt = smoke._excerpt("a\n\n  b" + "x" * 500)
        assert excerpt.startswith("a b")
        assert len(excerpt) <= smoke.EXCERPT_CHARS + 1  # + the ellipsis
        assert excerpt.endswith("…")


# ---------------------------------------------------------------------------
# Scripted conversation shape
# ---------------------------------------------------------------------------


class TestScriptedConversation:
    def test_the_script_is_a_multi_turn_conversation(self) -> None:
        assert len(smoke.SCRIPTED_PLAYER_TURNS) >= 2
        assert all(t.strip() for t in smoke.SCRIPTED_PLAYER_TURNS)

    def test_the_script_matches_the_fake_runtime_playthrough(self) -> None:
        # Keeping the two harnesses on the same script means the nightly and
        # the release-time fake-runtime smoke cover the same conversation shape,
        # so a difference between them is the runtime and nothing else.
        source = (REPO_ROOT / "tests" / "e2e" / "test_scripted_playthrough.py").read_text(
            encoding="utf-8"
        )
        for turn in smoke.SCRIPTED_PLAYER_TURNS:
            assert turn in source, f"scripted turn drifted from the e2e playthrough: {turn!r}"


# ---------------------------------------------------------------------------
# HTTP transport: status code -> failure class
# ---------------------------------------------------------------------------


class _Response:
    """Minimum of an http.client.HTTPResponse that _request_json touches."""

    def __init__(self, status: int = 200, body: bytes = b"{}") -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *a: object) -> bool:
        return False


def _http_error(code: int, body: bytes = b"server traceback"):
    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(
            getattr(req, "full_url", "http://x"), code, "err", {}, io.BytesIO(body)
        )

    return _raise


class TestRequestClassification:
    """`runtime` means the server broke; `pipeline` means it rejected the ask.

    Every orchestration test below replaces _request_json wholesale, so without
    these the one function that decides "crashed server" vs "end-to-end
    assertion" — the distinction #457 asks CI output to make — is never run.
    """

    @pytest.mark.parametrize("code", [500, 502, 503])
    def test_a_5xx_is_a_runtime_failure(
        self, code: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(smoke.urllib.request, "urlopen", _http_error(code))
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._request_json("http://127.0.0.1:1/api/sessions", payload={}, timeout=1)
        assert exc_info.value.failure_class == smoke.FailureClass.RUNTIME
        assert exc_info.value.exit_code == 4

    @pytest.mark.parametrize("code", [400, 404, 409, 422])
    def test_a_4xx_is_a_pipeline_failure(
        self, code: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The server is up and routing; it refused what the smoke asked for —
        # a 409 from POST /end on an already-ended session, say. That is an
        # assertion about the API contract, not a crash.
        monkeypatch.setattr(smoke.urllib.request, "urlopen", _http_error(code))
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._request_json("http://127.0.0.1:1/api/sessions", payload={}, timeout=1)
        assert exc_info.value.failure_class == smoke.FailureClass.PIPELINE
        assert exc_info.value.exit_code == 5

    def test_the_server_side_detail_reaches_the_failure_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The 5xx body is the only place convsim-core's own error text appears
        # on the client side, and it is what the runtime remedy sends a triager
        # to read.
        monkeypatch.setattr(
            smoke.urllib.request, "urlopen",
            _http_error(500, b"Debrief generation failed"),
        )
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._request_json("http://127.0.0.1:1/api/x", payload={}, timeout=1)
        assert "Debrief generation failed" in str(exc_info.value)

    @pytest.mark.parametrize("exc", [
        ConnectionResetError("peer hung up"),
        TimeoutError("read timed out"),
    ])
    def test_a_transport_error_is_a_runtime_failure(
        self, exc: BaseException, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(req, timeout=None):
            raise exc

        monkeypatch.setattr(smoke.urllib.request, "urlopen", _raise)
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._request_json("http://127.0.0.1:1/api/health", timeout=1)
        assert exc_info.value.failure_class == smoke.FailureClass.RUNTIME

    def test_an_unparseable_body_is_a_runtime_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            smoke.urllib.request, "urlopen",
            lambda req, timeout=None: _Response(200, b"<html>502 Bad Gateway</html>"),
        )
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._request_json("http://127.0.0.1:1/api/health", timeout=1)
        assert exc_info.value.failure_class == smoke.FailureClass.RUNTIME

    def test_an_unexpected_success_status_is_a_pipeline_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # urllib raises for >= 400, so this branch only ever sees a 2xx/3xx the
        # contract did not promise.
        monkeypatch.setattr(
            smoke.urllib.request, "urlopen", lambda req, timeout=None: _Response(204)
        )
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._request_json("http://127.0.0.1:1/api/health", timeout=1)
        assert exc_info.value.failure_class == smoke.FailureClass.PIPELINE
        assert "HTTP 204" in str(exc_info.value)

    def test_a_healthy_response_is_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            smoke.urllib.request, "urlopen",
            lambda req, timeout=None: _Response(200, b'{"session_id": "sess-1"}'),
        )
        assert smoke._request_json(
            "http://127.0.0.1:1/api/sessions", payload={"a": 1}, timeout=1
        ) == {"session_id": "sess-1"}


# ---------------------------------------------------------------------------
# Readiness polling
# ---------------------------------------------------------------------------


class _PolledProc:
    def __init__(self, returncode: int | None = None) -> None:
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode


class TestWaitForHttp:
    """A server that died on startup is nameable immediately, not after a wait."""

    def test_a_child_that_exited_short_circuits_the_wait(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The realistic case is a runner OOM on model load. Polling a port
        # nobody is listening on for the full timeout would bury the exit code
        # and burn the wall-clock budget that exit 6 is measured against.
        def _refused(*a: object, **k: object):
            raise ConnectionRefusedError()

        monkeypatch.setattr(smoke.urllib.request, "urlopen", _refused)
        # The timeout is deliberately far below the 300 s the real model-load
        # wait allows: a regression that drops the short-circuit must turn this
        # test red quickly rather than stall the per-PR suite for five minutes.
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._wait_for_http(
                "http://127.0.0.1:1/v1/models", timeout_s=2.0,
                label="llama-server", proc=_PolledProc(137),
            )
        assert exc_info.value.failure_class == smoke.FailureClass.RUNTIME
        assert "llama-server exited with code 137" in str(exc_info.value)

    def test_a_server_that_never_answers_is_a_runtime_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _refused(*a: object, **k: object):
            raise ConnectionRefusedError()

        monkeypatch.setattr(smoke.urllib.request, "urlopen", _refused)
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._wait_for_http(
                "http://127.0.0.1:1/api/health", timeout_s=0.0, label="convsim-core"
            )
        assert exc_info.value.failure_class == smoke.FailureClass.RUNTIME
        assert "convsim-core" in str(exc_info.value)

    def test_the_not_ready_message_carries_the_last_connection_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # It is the only diagnostic a readiness `runtime` verdict leaves behind,
        # and str() on an exception raised with no arguments is empty.
        def _refused(*a: object, **k: object):
            raise ConnectionRefusedError()

        monkeypatch.setattr(smoke.urllib.request, "urlopen", _refused)
        # The poll backs off a second between attempts; skip the wait so this
        # test costs nothing. The timeout still has to leave room for one
        # attempt, or last_err is never set.
        monkeypatch.setattr(smoke.time, "sleep", lambda _s: None)
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._wait_for_http(
                "http://127.0.0.1:1/api/health", timeout_s=0.01, label="convsim-core"
            )
        assert "ConnectionRefusedError" in str(exc_info.value)

    def test_a_live_child_is_not_mistaken_for_a_crashed_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            smoke.urllib.request, "urlopen", lambda *a, **k: _Response(200)
        )
        assert smoke._wait_for_http(
            "http://127.0.0.1:1/v1/models", timeout_s=30.0,
            label="llama-server", proc=_PolledProc(None),
        ) is None

    def test_an_http_error_still_means_the_server_is_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A 404 is a routed response: the process is listening, which is all
        # readiness means.
        monkeypatch.setattr(smoke.urllib.request, "urlopen", _http_error(404))
        assert smoke._wait_for_http(
            "http://127.0.0.1:1/api/health", timeout_s=30.0, label="convsim-core"
        ) is None


# ---------------------------------------------------------------------------
# Full-run orchestration, with llama-server and convsim-core faked out
# ---------------------------------------------------------------------------


class _FakeProc:
    """Minimum of subprocess.Popen that run_smoke touches."""

    def __init__(self, returncode: int | None = None) -> None:
        self.stdout = iter(())
        self.stderr = iter(())
        self._returncode = returncode
        self.terminated = False

    @property
    def returncode(self) -> int | None:
        return self._returncode

    def poll(self) -> int | None:
        return self._returncode

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return self._returncode or 0

    def kill(self) -> None:  # pragma: no cover - only on a hung child
        self.terminated = True


_OPENING = {"events": [{"event_type": "npc_opening",
                        "payload": {"content": "Thanks for coming in today."}}]}
_NPC_TURN = {"events": [{"event_type": "npc_turn",
                         "payload": {"content": "Walk me through that trade-off."}}],
             "ending_type": None}


def _npc_turn_with_observations(count: int) -> dict:
    """An NPC turn whose payload carries ``count`` validated rubric observations."""
    return {"events": [{"event_type": "npc_turn", "payload": {
        "content": "Walk me through that trade-off.",
        "rubric_observations": [
            {"rubric_id": f"dim{i}", "observation": "o", "score_delta": 1}
            for i in range(count)
        ],
    }}], "ending_type": None}


def _fake_core(debrief: dict, *, debug_turns: list | None = None, turn: dict | None = None):
    """Build a _request_json stand-in that answers convsim-core's endpoints."""
    calls: list[str] = []

    def _request_json(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
        calls.append(url)
        if url.endswith("/health"):
            return {"llm_runtime": {"runtime_id": "llama_cpp"}}
        if url.endswith("/api/sessions"):
            return {"session_id": "sess-1"}
        if url.endswith("/start"):
            return _OPENING
        if url.endswith("/turn"):
            return turn if turn is not None else _NPC_TURN
        if url.endswith("/debug"):
            return {"turns": debug_turns if debug_turns is not None else [
                {"turn_number": n, "used_fallback": False,
                 "used_native_structured_output": True}
                for n in range(1, len(smoke.SCRIPTED_PLAYER_TURNS) + 1)
            ]}
        if url.endswith("/end"):
            return {"state": "Ended"}
        if url.endswith("/debrief"):
            return debrief
        raise AssertionError(f"unexpected request to {url}")

    _request_json.calls = calls  # type: ignore[attr-defined]
    return _request_json


@pytest.fixture()
def staged_model(tmp_path: Path) -> tuple[Path, str, str]:
    """A fake GGUF on disk plus its id and digest."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    payload = b"\x00gguf stand-in"
    (models_dir / "test-model.gguf").write_bytes(payload)
    return models_dir, "test-model", hashlib.sha256(payload).hexdigest()


@pytest.fixture()
def fake_servers(monkeypatch: pytest.MonkeyPatch) -> dict[str, _FakeProc]:
    """Replace both child processes and the readiness polling with fakes."""
    procs = {"llama": _FakeProc(), "core": _FakeProc()}
    monkeypatch.setattr(smoke, "_start_llama_server", lambda *a, **k: procs["llama"])
    monkeypatch.setattr(smoke, "_start_core", lambda *a, **k: procs["core"])
    monkeypatch.setattr(smoke, "_wait_for_http", lambda *a, **k: None)
    return procs


class TestRunSmokeOrchestration:
    """The phases, the report and the exit code, without a real model."""

    def test_healthy_run_passes_and_reports(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, digest = staged_model
        monkeypatch.setattr(smoke, "_request_json", _fake_core(_debrief()))
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == 0
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["verdict"] == "pass"
        assert results["failure_class"] is None
        assert results["runtime_id"] == "llama_cpp"
        # One authored opening + every scripted player turn.
        assert len(results["turns"]) == len(smoke.SCRIPTED_PLAYER_TURNS) + 1
        assert results["turns"][0]["model_generated"] is False
        assert all(t["model_generated"] for t in results["turns"][1:])
        assert all(t["used_native_structured_output"] for t in results["turns"][1:])
        assert results["debrief"]["overall_score"] == 52.0
        assert set(results["measured_ms"]) >= {
            "session_start_ms", "full_response_ms", "debrief_ms"
        }
        assert set(results["phase_durations_s"]) >= {
            "checksum", "runtime_start", "conversation", "debrief", "assertions", "budget"
        }
        assert results["warnings"] == []

    def test_both_children_are_stopped_even_on_a_pass(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        models_dir, model_id, digest = staged_model
        monkeypatch.setattr(smoke, "_request_json", _fake_core(_debrief()))
        smoke.run_smoke(model_id, 20.0, None, model_sha256=digest, models_dir=models_dir)
        assert fake_servers["llama"].terminated
        assert fake_servers["core"].terminated

    def test_the_data_directory_outlives_convsim_core_and_is_then_removed(
        self, staged_model, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The throwaway data dir must not be deleted while core is still running.

        It holds convsim-core's SQLite database, WAL and logs. Removing it
        before the child is stopped races the server's own writes, and an
        rmtree that lost that race would be caught as an unexpected harness
        error and reported as a `pipeline` failure on an otherwise green run.
        """
        models_dir, model_id, digest = staged_model
        monkeypatch.setattr(smoke, "_request_json", _fake_core(_debrief()))
        seen: dict = {}

        core = _FakeProc()

        def _terminate() -> None:
            seen["existed_at_terminate"] = seen["data_dir"].exists()
            core.terminated = True

        core.terminate = _terminate  # type: ignore[method-assign]

        def _start_core(data_dir, *args, **kwargs) -> _FakeProc:
            seen["data_dir"] = Path(data_dir)
            return core

        monkeypatch.setattr(smoke, "_start_llama_server", lambda *a, **k: _FakeProc())
        monkeypatch.setattr(smoke, "_start_core", _start_core)
        monkeypatch.setattr(smoke, "_wait_for_http", lambda *a, **k: None)

        exit_code = smoke.run_smoke(
            model_id, 20.0, None, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == 0
        assert seen["existed_at_terminate"] is True
        assert not seen["data_dir"].exists(), "the data directory leaked"

    def test_unscored_debrief_is_a_pipeline_failure(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, digest = staged_model
        monkeypatch.setattr(
            smoke, "_request_json",
            _fake_core(_debrief(scores={}, overall_score=None)),
        )
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["failure_class"] == smoke.FailureClass.PIPELINE
        assert results["failed_phase"] == "assertions"
        assert any("rubric dimension scores" in f for f in results["failures"])
        # The artifact carries the advice, not just the class: the failure table
        # in the docs sends triage here for a `pipeline` verdict.
        assert results["remedy"] == smoke.REMEDIES[smoke.FailureClass.PIPELINE]
        # The turns volunteered nothing to score, so the verdict says so rather
        # than asking the reader to go and diff the previous nightly's artifact.
        assert results["rubric_observations_seen"] == 0
        assert any(smoke.UNSCORED_DEBRIEF_NOTE in f for f in results["failures"])

    def test_unscored_debrief_with_scorable_turns_is_named_a_regression(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The same exit 5, the opposite diagnosis.

        When the NPC turns did return rubric observations and the debrief still
        scored nothing, the model is not the problem and the stock note
        ("nothing asks the model for them") would excuse a real bug in the
        debrief engine's score accumulation.
        """
        models_dir, model_id, digest = staged_model
        monkeypatch.setattr(
            smoke, "_request_json",
            _fake_core(
                _debrief(scores={}, overall_score=None),
                turn=_npc_turn_with_observations(2),
            ),
        )
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["rubric_observations_seen"] == 2 * len(smoke.SCRIPTED_PLAYER_TURNS)
        assert all(
            t["rubric_observation_count"] == 2 for t in results["turns"][1:]
        ), "the per-turn count belongs in the artifact, not just the total"
        assert any(smoke.UNSCORED_WITH_OBSERVATIONS_NOTE in f for f in results["failures"])
        assert not any(smoke.UNSCORED_DEBRIEF_NOTE in f for f in results["failures"])

    def test_latency_regression_is_a_budget_failure_not_a_pipeline_one(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import time

        models_dir, model_id, digest = staged_model
        base = _fake_core(_debrief())

        def _slow_turn(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith("/turn"):
                time.sleep(0.02)  # measurable, so the 0 ms ceiling is exceeded
            return base(url, payload=payload, timeout=timeout, expect=expect)

        monkeypatch.setattr(smoke, "_request_json", _slow_turn)
        report = tmp_path / "report.json"

        # Factor 0 ⇒ a 0 ms ceiling, so any measurable latency regresses.
        exit_code = smoke.run_smoke(
            model_id, 0.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.BUDGET]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["failure_class"] == smoke.FailureClass.BUDGET
        assert results["failed_phase"] == "budget"

    def test_a_crashed_child_outranks_the_client_side_symptom(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # convsim-core dies mid-run: the client sees a pipeline-shaped error, but
        # the real story is the crash, so the verdict must be `runtime`.
        models_dir, model_id, digest = staged_model
        fake_servers["core"]._returncode = 1

        def _boom(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith("/health"):
                return {"llm_runtime": {"runtime_id": "llama_cpp"}}
            raise smoke.SmokeFailure(smoke.FailureClass.PIPELINE, "connection reset")

        monkeypatch.setattr(smoke, "_request_json", _boom)
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.RUNTIME]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["failure_class"] == smoke.FailureClass.RUNTIME
        assert "convsim-core exited with code 1" in results["failures"][0]

    def test_a_fake_runtime_is_refused(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, digest = staged_model

        def _fake_runtime(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            assert url.endswith("/health"), "must not play a turn on the fake runtime"
            return {"llm_runtime": {"runtime_id": "fake"}}

        monkeypatch.setattr(smoke, "_request_json", _fake_runtime)
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert "runtime_id" in results["failures"][0]

    def test_checksum_drift_stops_the_run_before_any_server_starts(
        self, staged_model, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, _ = staged_model

        def _never(*args: object, **kwargs: object):
            raise AssertionError("must not load a model that failed verification")

        monkeypatch.setattr(smoke, "_start_llama_server", _never)
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256="0" * 64, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.CHECKSUM]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["failed_phase"] == "checksum"

    def test_run_without_a_checksum_warns_that_drift_was_not_checked(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, _ = staged_model
        monkeypatch.setattr(smoke, "_request_json", _fake_core(_debrief()))
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(model_id, 20.0, report, models_dir=models_dir)

        assert exit_code == 0
        results = json.loads(report.read_text(encoding="utf-8"))
        assert any("checksum drift was not checked" in w for w in results["warnings"])

    def test_an_absent_model_is_a_download_failure(
        self, fake_servers, tmp_path: Path
    ) -> None:
        exit_code = smoke.run_smoke(
            "absent", 20.0, None, models_dir=tmp_path / "empty"
        )
        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.DOWNLOAD]

    def test_exhausted_wall_clock_budget_is_a_timeout(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, digest = staged_model
        monkeypatch.setattr(smoke, "_request_json", _fake_core(_debrief()))
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir,
            wall_clock_budget_s=0.0,
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.TIMEOUT]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["failure_class"] == smoke.FailureClass.TIMEOUT

    def test_a_normal_run_still_ends_the_session_explicitly(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, digest = staged_model
        fake = _fake_core(_debrief())
        monkeypatch.setattr(smoke, "_request_json", fake)

        assert smoke.run_smoke(
            model_id, 20.0, None, model_sha256=digest, models_dir=models_dir
        ) == 0
        assert any(url.endswith("/end") for url in fake.calls)

    def test_request_timeouts_outlast_the_adapter_so_slowness_is_not_a_crash(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Whoever gives up first decides the verdict.  The adapter timeout
        # handed to convsim-core has to clear the debrief (the slowest single
        # generation), and our own POST timeout has to clear the adapter's, or
        # a slow model is reported as a crashed server instead of a budget
        # regression.
        models_dir, model_id, digest = staged_model
        adapter_timeout: dict[str, float] = {}
        post_timeouts: list[float] = []

        def _record_core(data_dir, port, llama_port, llama_timeout_s):
            adapter_timeout["s"] = llama_timeout_s
            return fake_servers["core"]

        base = _fake_core(_debrief())

        def _record_timeout(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith(("/turn", "/debrief")):
                post_timeouts.append(timeout)
            return base(url, payload=payload, timeout=timeout, expect=expect)

        monkeypatch.setattr(smoke, "_start_core", _record_core)
        monkeypatch.setattr(smoke, "_request_json", _record_timeout)

        assert smoke.run_smoke(
            model_id, 20.0, None, model_sha256=digest, models_dir=models_dir,
            wall_clock_budget_s=24 * 3600,  # large, so cap() does not clamp
        ) == 0

        ci_ceiling_s = (
            smoke.BUDGETS_MS["full_response_ms"] * 20.0 * smoke.REGRESSION_TOLERANCE
        ) / 1000
        assert adapter_timeout["s"] >= ci_ceiling_s * smoke.DEBRIEF_SLOWDOWN_FACTOR
        assert post_timeouts and all(t > adapter_timeout["s"] for t in post_timeouts)

    def test_a_deadline_induced_transport_error_is_a_timeout_not_a_crash(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # cap() shrinks every request timeout to the budget that is left, so the
        # last request before the deadline dies client-side and _request_json
        # reports it as RUNTIME ("the server never answered").  Nothing crashed
        # — the budget ran out — and only the TIMEOUT remedy points at
        # phase_durations_s, so the verdict has to be TIMEOUT.
        import time

        models_dir, model_id, digest = staged_model
        base = _fake_core(_debrief())

        def _overruns(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith("/api/sessions"):
                time.sleep(0.3)  # outlast the budget below
                raise smoke.SmokeFailure(
                    smoke.FailureClass.RUNTIME,
                    f"{url} did not answer with usable JSON after {timeout:.0f} s",
                )
            return base(url, payload=payload, timeout=timeout, expect=expect)

        monkeypatch.setattr(smoke, "_request_json", _overruns)
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir,
            wall_clock_budget_s=0.2,
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.TIMEOUT]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["failure_class"] == smoke.FailureClass.TIMEOUT
        assert any("Wall-clock budget" in f for f in results["failures"])

    def test_a_crash_still_outranks_an_exhausted_budget(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Both are true at once; "convsim-core exited with code 1" is the more
        # actionable story, so RUNTIME keeps precedence over TIMEOUT.
        import time

        models_dir, model_id, digest = staged_model
        fake_servers["core"]._returncode = 1
        base = _fake_core(_debrief())

        def _overruns(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith("/api/sessions"):
                time.sleep(0.3)
                raise smoke.SmokeFailure(smoke.FailureClass.PIPELINE, "connection reset")
            return base(url, payload=payload, timeout=timeout, expect=expect)

        monkeypatch.setattr(smoke, "_request_json", _overruns)
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir,
            wall_clock_budget_s=0.2,
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.RUNTIME]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert "convsim-core exited with code 1" in results["failures"][0]

    def test_an_unexpected_harness_bug_is_reported_not_raised(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, digest = staged_model

        def _bug(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith("/health"):
                return {"llm_runtime": {"runtime_id": "llama_cpp"}}
            raise TypeError("harness bug")

        monkeypatch.setattr(smoke, "_request_json", _bug)
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code != 0
        results = json.loads(report.read_text(encoding="utf-8"))
        assert "bug in the smoke harness" in results["failures"][0]
        # It borrows `pipeline`'s exit code but not its cause, so the remedy
        # must point at the traceback, not at the model's turn output.
        assert results["remedy"] != smoke.REMEDIES[smoke.FailureClass.PIPELINE]
        assert "harness bug" in results["remedy"]
        assert results["remedy"] in smoke.render_step_summary(results)

    def test_a_scenario_that_ends_early_stops_the_scripted_turns(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, digest = staged_model
        base = _fake_core(_debrief(), debug_turns=[
            {"turn_number": 1, "used_fallback": False, "used_native_structured_output": True},
        ])

        def _ends_after_one(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith("/turn"):
                return {**_NPC_TURN, "ending_type": "success"}
            return base(url, payload=payload, timeout=timeout, expect=expect)

        monkeypatch.setattr(smoke, "_request_json", _ends_after_one)
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == 0
        results = json.loads(report.read_text(encoding="utf-8"))
        assert len(results["turns"]) == 2  # opening + the one turn that ended it
        # The turn pipeline already moved the session to 'Ended', so POST /end
        # would answer 409 and the run would die as a bogus `pipeline` failure.
        assert not any(url.endswith("/end") for url in base.calls), (
            "must not POST /end to a session the scenario already ended"
        )
        assert results["debrief"] is not None

    def test_unavailable_debug_flags_warn_instead_of_silently_passing(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # The debug endpoint is a diagnostic, so losing it must not turn a
        # healthy run red — but it is also the only thing that tells a real NPC
        # turn from the canned fallback, so the report has to say the check
        # did not run.
        models_dir, model_id, digest = staged_model
        base = _fake_core(_debrief())

        def _no_debug(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith("/debug"):
                raise smoke.SmokeFailure(smoke.FailureClass.PIPELINE, "HTTP 404")
            return base(url, payload=payload, timeout=timeout, expect=expect)

        monkeypatch.setattr(smoke, "_request_json", _no_debug)
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == 0
        results = json.loads(report.read_text(encoding="utf-8"))
        assert any("fallback check did not run" in w for w in results["warnings"])

    @pytest.mark.parametrize(
        "debug_body",
        [
            {},                                      # no turns key at all
            {"turns": None},                         # turns present but not a list
            {"turns": [{"used_fallback": False}]},   # entry that cannot be keyed
            {"turns": ["not-a-dict"]},
        ],
        ids=["no-turns-key", "turns-not-a-list", "entry-without-turn-number", "entry-not-a-dict"],
    )
    def test_a_malformed_debug_payload_does_not_fail_an_otherwise_green_run(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path, debug_body: dict,
    ) -> None:
        # Same contract as a 404 from the debug endpoint: it is a diagnostic,
        # so a shape we cannot read must degrade to "the check did not run",
        # not raise out of the helper and land in run_smoke's catch-all as a
        # harness bug (exit 5) on a run where the product did nothing wrong.
        models_dir, model_id, digest = staged_model
        base = _fake_core(_debrief())

        def _bad_debug(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith("/debug"):
                return debug_body
            return base(url, payload=payload, timeout=timeout, expect=expect)

        monkeypatch.setattr(smoke, "_request_json", _bad_debug)
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == 0
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["verdict"] == "pass"
        assert any("fallback check did not run" in w for w in results["warnings"])


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    """exit 1 means `budget` and nothing else, so nothing may escape unclassified."""

    def test_registry_lookup_writes_github_output_and_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "gh-output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        assert smoke.main(["--print-registry-model", "starter"]) == 0
        written = dict(
            line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines()
        )
        assert len(written["model_sha256"]) == 64
        assert written["model_url"].startswith("https://")

    def test_a_malformed_registry_is_classified_not_a_bare_traceback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # yaml raises ParserError, not SmokeFailure.  Escaping exits 1, which
        # EXIT_CODES reads as `budget` — "the product is fine, just slow" — and
        # writes no banner or step summary at all.
        registry = tmp_path / "registry.yaml"
        registry.write_text("models: [ unterminated\n", encoding="utf-8")
        # Point the real resolver at the malformed file (its registry_path
        # default is bound at def time, so the module constant cannot be
        # patched), so the failure under test is yaml's, not the patch's.
        real_resolve = smoke.resolve_registry_model
        monkeypatch.setattr(
            smoke, "resolve_registry_model",
            lambda role, registry_path=None: real_resolve(role, registry),
        )

        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        exit_code = smoke.main(["--print-registry-model", "starter"])

        assert exit_code != smoke.EXIT_CODES[smoke.FailureClass.BUDGET]
        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        assert "FAIL" in summary.read_text(encoding="utf-8")

    def test_a_registry_missing_the_role_prints_registry_advice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The step summary is the whole triage surface for a red nightly, so
        # the advice in it has to match the failure: `pipeline`'s own remedy
        # ("inspect the per-turn used_fallback flags") describes a run that
        # never happened here.
        registry = tmp_path / "registry.yaml"
        registry.write_text("models: []\n", encoding="utf-8")
        real_resolve = smoke.resolve_registry_model
        monkeypatch.setattr(
            smoke, "resolve_registry_model",
            lambda role, registry_path=None: real_resolve(role, registry),
        )
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        exit_code = smoke.main(["--print-registry-model", "starter"])

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        text = summary.read_text(encoding="utf-8")
        assert "registry.yaml" in text
        assert "used_fallback" not in text

    def test_a_download_failure_keeps_its_own_exit_code_and_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        # --verify-only against an empty directory: no file to hash.
        exit_code = smoke.main([
            "--verify-only", "--model-id", "absent",
            "--model-sha256", "0" * 64, "--models-dir", str(tmp_path / "empty"),
        ])
        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.DOWNLOAD]
        assert "`download`" in summary.read_text(encoding="utf-8")

    def test_a_failure_in_run_smokes_prologue_is_classified_not_exit_one(
        self, staged_model, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # run_smoke classifies everything inside its own try/finally, but the
        # throwaway data directory is created before it and the report is
        # written after it.  A full disk there — realistic right after a 2.5 GB
        # download and a 2.5 GB cache save — must not escape as a bare
        # traceback: Python would exit 1, which EXIT_CODES reads as `budget`.
        models_dir, model_id, digest = staged_model

        def _no_space(*args: object, **kwargs: object) -> str:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(smoke.tempfile, "mkdtemp", _no_space)
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

        exit_code = smoke.main([
            "--model-id", model_id, "--model-sha256", digest,
            "--models-dir", str(models_dir),
        ])

        assert exit_code != smoke.EXIT_CODES[smoke.FailureClass.BUDGET]
        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        text = summary.read_text(encoding="utf-8")
        assert "FAIL" in text
        assert "No space left on device" in text

    def test_a_failure_writing_the_report_does_not_become_a_budget_verdict(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # The report write follows the verdict, outside run_smoke's handlers.
        models_dir, model_id, digest = staged_model
        monkeypatch.setattr(smoke, "_request_json", _fake_core(_debrief()))

        def _no_space(*args: object, **kwargs: object) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(smoke, "_write_report", _no_space)

        exit_code = smoke.main([
            "--model-id", model_id, "--model-sha256", digest,
            "--models-dir", str(models_dir), "--report-path", str(tmp_path / "r.json"),
        ])

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]

    def test_a_usage_error_is_not_mistaken_for_a_download_failure(self) -> None:
        # argparse exits 2 on a bad command line, and 2 is the `download` code,
        # whose remedy is "nothing about the app changed, re-run the job" —
        # advice that loops forever on a job that cannot succeed. A malformed
        # invocation is a harness problem: `pipeline`, like every other surprise.
        with pytest.raises(SystemExit) as exc_info:
            smoke.main(["--download-only", "--model-id", "x"])  # no url / sha256
        assert exc_info.value.code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        assert exc_info.value.code != smoke.EXIT_CODES[smoke.FailureClass.DOWNLOAD]
