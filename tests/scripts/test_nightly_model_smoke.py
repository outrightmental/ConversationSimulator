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
import socket
import statistics
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

    def test_the_pipeline_remedy_carves_out_the_unscored_debrief(self) -> None:
        # All pipeline assertions are raised together, so this one remedy is
        # printed under every one of them and cannot be swapped per failure.
        # Three of the four unscored-debrief causes are nothing to do with the
        # per-turn flags it otherwise sends the reader to -- the docs failure
        # table says so, and the advice beside the banner is what triage
        # actually reads, so it has to say so too.
        remedy = smoke.REMEDIES[smoke.FailureClass.PIPELINE]
        assert "unscored debrief" in remedy.lower()
        doc = (REPO_ROOT / "docs" / "real-model-smoke.md").read_text(encoding="utf-8")
        assert "## Unscored debrief" in doc, "the remedy names a section that must exist"


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

    def test_the_same_digest_in_a_different_case_is_not_drift(self, tmp_path: Path) -> None:
        # The registry pins lower-case hex, but --model-sha256 is typed by hand
        # in the local repro. An upper-case paste is the same digest, and
        # string equality would call it drift -- deleting a 2.5 GB file and
        # reporting "the pinned upstream file was replaced", which is both
        # expensive and wrong.
        path, digest = self._write(tmp_path)
        assert smoke.verify_model_checksum(path, digest.upper()) == digest
        assert path.exists()

    def test_a_digest_pasted_with_stray_whitespace_is_not_drift(self, tmp_path: Path) -> None:
        path, digest = self._write(tmp_path)
        assert smoke.verify_model_checksum(path, f"  {digest}\n") == digest
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

    def test_a_malformed_digest_is_not_drift_and_keeps_the_file(self, tmp_path: Path) -> None:
        # A digest short by one character is the ordinary outcome of copying 64
        # hex characters out of a terminal by hand, and it can never match any
        # file's hash -- so comparing against it is not a check. Treating it as
        # drift deleted a 2.5 GB download and reported that the pinned upstream
        # file had been replaced, which is the expensive, misleading verdict the
        # case/whitespace normalisation above exists to avoid.
        path, digest = self._write(tmp_path)
        for malformed in (digest[:-1], digest + "0", "not-a-digest", "", digest[:-1] + "g"):
            with pytest.raises(smoke.SmokeFailure) as exc_info:
                smoke.verify_model_checksum(path, malformed)
            assert exc_info.value.failure_class == smoke.FailureClass.PIPELINE, malformed
            assert path.exists(), f"{malformed!r} must not delete the model"
            # The checksum remedy ("the pinned upstream file was replaced ...
            # do NOT relax this check") is the wrong advice here.
            assert exc_info.value.remedy != smoke.REMEDIES[smoke.FailureClass.CHECKSUM]

    def test_a_malformed_digest_is_caught_before_the_file_is_hashed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Hashing 2.5 GB to compare it against something that cannot match is
        # pure waste, and a missing file would otherwise be reported as
        # `download` while the real problem is the argument.
        def _never(*args: object, **kwargs: object) -> str:
            raise AssertionError("must not hash the file for a malformed digest")

        monkeypatch.setattr(smoke, "sha256_file", _never)
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke.verify_model_checksum(tmp_path / "absent.gguf", "deadbeef")
        assert exc_info.value.failure_class == smoke.FailureClass.PIPELINE

    def test_a_malformed_digest_is_rejected_before_anything_is_fetched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Rejecting it only at verification time means the reader waits out a
        # 2.5 GB download to be told the argument was wrong -- and the realistic
        # source of a malformed digest is exactly the hand-pasted --model-sha256
        # of the local repro, which runs --download-only. No bytes could have
        # changed the verdict, and docs/real-model-smoke.md promises the download
        # is not spent on one.
        def _never(*args: object, **kwargs: object) -> None:
            raise AssertionError("must not fetch 2.5 GB to compare it to a non-digest")

        monkeypatch.setattr(smoke, "_download_with_progress", _never)
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke.download_model("https://example.invalid/m.gguf", "deadbeef", "m", tmp_path)
        assert exc_info.value.failure_class == smoke.FailureClass.PIPELINE
        assert not (tmp_path / "m.gguf").exists()

    def test_the_registry_pin_is_a_well_formed_digest(self) -> None:
        # The one digest the nightly actually runs on has to pass the guard
        # above, or the job fails before it fetches anything.
        model = smoke.resolve_registry_model("starter")
        assert len(model["sha256"]) == smoke.SHA256_HEX_CHARS
        assert set(model["sha256"].lower()) <= smoke._HEX_DIGITS

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

    @pytest.mark.parametrize(
        "url",
        [
            "<model_url from step 2>",  # the repro block's placeholder, pasted verbatim
            "example.invalid/m.gguf",  # scheme omitted
        ],
    )
    def test_an_unrequestable_url_is_not_reported_as_a_harness_bug(
        self, url: str, tmp_path: Path
    ) -> None:
        # urllib raises ValueError out of Request's *constructor* for a string
        # it cannot read as a URL, which used to sit above the handler — so it
        # escaped to main's catch-all as "most likely a bug in the smoke
        # harness", advising a re-run with the same arguments. The arguments are
        # the problem, and the local repro in docs/real-model-smoke.md hands the
        # reader a --model-url placeholder to substitute.
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._download_with_progress(url, tmp_path / "m.gguf")
        assert exc_info.value.failure_class == smoke.FailureClass.PIPELINE
        assert "not a usable download url" in str(exc_info.value).lower()
        # Its own remedy, not the class default: "inspect the per-turn
        # used_fallback flags" is useless when no turn was ever played.
        assert exc_info.value.remedy != smoke.REMEDIES[smoke.FailureClass.PIPELINE]
        assert "--model-url" in exc_info.value.remedy
        assert "registry" in exc_info.value.remedy

    def test_a_crawling_transfer_is_bounded_and_classified(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A transfer that keeps delivering bytes, just far too slowly, never
        # trips urllib's per-read timeout. The download runs in its own step
        # before the smoke, on a job clock the harness's Deadline cannot see, so
        # without its own budget this is the one remaining way to reach the
        # unattributable "The operation was canceled".
        dest = tmp_path / "m.gguf"
        clock = iter([0.0] + [1.0] * 8)  # started, then one read inside the budget

        class _Resp:
            headers = {"Content-Length": str(100 << 20)}

            def read(self, _n: int) -> bytes:
                return b"\0" * (1 << 20)  # never ends

            def __enter__(self):
                return self

            def __exit__(self, *a: object) -> bool:
                return False

        monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda *a, **k: _Resp())
        monkeypatch.setattr(
            smoke.time, "monotonic", lambda: next(clock, 10.0)
        )
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._download_with_progress(
                "https://example.invalid/m.gguf", dest, budget_s=5.0
            )
        assert exc_info.value.failure_class == smoke.FailureClass.DOWNLOAD
        assert exc_info.value.exit_code == 2
        assert "budget" in str(exc_info.value)
        # Its own remedy, naming why the bound exists at all — not the generic
        # "download failed for <url>: SmokeFailure(...)" a re-wrap would give.
        assert exc_info.value.remedy != smoke.REMEDIES[smoke.FailureClass.DOWNLOAD]
        assert "job clock" in exc_info.value.remedy
        # The partial file still goes, or the next run checksum-fails on it.
        assert not dest.exists()

    def test_one_quiet_stretch_cannot_outlast_the_whole_budget(self) -> None:
        # urllib's timeout is per socket operation, so a read timeout at or
        # above the transfer budget means a single silent connection decides how
        # long the download runs, and the budget never gets to.
        assert smoke.DOWNLOAD_READ_TIMEOUT_S < smoke.DOWNLOAD_BUDGET_S

    def test_progress_is_logged_sparsely_not_once_per_megabyte(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        # The "\r" updates collapse in a terminal but not in a CI log, where
        # each flush is its own line: the one nightly that missed the model
        # cache logged 2381 of them for a 2.3 GiB GGUF, directly above the
        # verdict a triager is looking for.
        megabytes = 200
        chunks = [b"\0" * (1 << 20)] * megabytes

        class _Resp:
            headers = {"Content-Length": str(megabytes << 20)}

            def read(self, _n: int) -> bytes:
                return chunks.pop(0) if chunks else b""

            def __enter__(self):
                return self

            def __exit__(self, *a: object) -> bool:
                return False

        monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda *a, **k: _Resp())
        smoke._download_with_progress("https://example.invalid/m.gguf", tmp_path / "m.gguf")

        progress_lines = [
            line for line in capsys.readouterr().out.split("\r") if line.strip().endswith("MB)")
        ]
        # One per PROGRESS_LOG_STEP_PCT, plus the 0 % line: nowhere near one per MB.
        assert len(progress_lines) <= 100 // smoke.PROGRESS_LOG_STEP_PCT + 1
        # Still enough to show where a stalled transfer stopped.
        assert len(progress_lines) >= 2
        assert "100%" in progress_lines[-1]


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

    @pytest.mark.parametrize(
        ("url", "sha256", "expected_field"),
        [
            ("PENDING", "ab" * 32, "download.url"),
            ("https://example.invalid/x.gguf", "PENDING", "download.sha256"),
            ("PENDING", "PENDING", "download.url"),
        ],
    )
    def test_an_unpinned_entry_is_a_registry_problem_not_a_download_one(
        self, tmp_path: Path, url: str, sha256: str, expected_field: str
    ) -> None:
        # "PENDING" is the placeholder model-registry.schema.json allows for an
        # entry that has been added but not pinned, and the no-PENDING check in
        # scripts/validate-registry.py only runs in registry-nightly.yml — not
        # per-PR — so an un-pinned `role: starter` can reach main.  Passed along
        # as a value it produces two confidently wrong verdicts: a "PENDING"
        # sha256 downloads 2.5 GB and then fails `checksum` with "the pinned
        # upstream file was replaced … do NOT relax this check", and a "PENDING"
        # url raises out of urllib's Request constructor into main's catch-all
        # as a suspected harness bug.  It is neither: it is the registry failing
        # to describe a usable model, which must stop the run at the lookup.
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            "models:\n"
            "  - id: next-starter\n"
            "    role: starter\n"
            f"    download: {{url: {url!r}, sha256: {sha256!r}}}\n",
            encoding="utf-8",
        )
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke.resolve_registry_model("starter", registry)
        assert exc_info.value.failure_class == smoke.FailureClass.PIPELINE
        assert exc_info.value.exit_code == 5
        assert expected_field in str(exc_info.value)
        assert "not pinned" in str(exc_info.value)
        assert exc_info.value.remedy == smoke.REGISTRY_REMEDY

    def test_the_real_starter_entry_is_pinned(self) -> None:
        # The flip side: the guard above must not be able to red the nightly on
        # the registry as it actually stands.
        model = smoke.resolve_registry_model("starter")
        assert model["url"] != smoke.REGISTRY_PENDING
        assert model["sha256"] != smoke.REGISTRY_PENDING

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

    @pytest.mark.parametrize(
        "turns, expected",
        [
            ([], False),
            ([{"label": "npc_opening", "turn_number": 0, "model_generated": False,
               "npc_excerpt": "Thanks for coming in."}], False),
            ([_turn(used_fallback=True), _turn(turn_number=2, used_fallback=True)], True),
            ([_turn(used_fallback=True), _turn(turn_number=2)], False),
            # Flags unavailable: an absent used_fallback is not a fallback.
            ([_turn(), _turn(turn_number=2)], False),
        ],
    )
    def test_the_two_verdicts_agree_on_what_all_fell_back_means(
        self, turns: list, expected: bool
    ) -> None:
        # evaluate_turns fails the run for it and evaluate_debrief uses it to
        # say the unscored debrief is downstream of it. If the two disagreed,
        # one verdict would carry both notes, each naming the other as the
        # wrong place to start.
        assert smoke._all_generated_turns_fell_back(turns) is expected
        failures, _ = smoke.evaluate_turns(list(turns))
        assert any("fell back to the canned" in f for f in failures) is expected

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

    def test_every_turn_reciting_the_opening_fails(self) -> None:
        # Real model output, every parse flag healthy, and not one reply: the
        # exact run the fallback check cannot see.
        turns = [
            _turn(replayed_opening=True),
            _turn(turn_number=2, replayed_opening=True),
        ]
        failures, _ = smoke.evaluate_turns(turns)
        assert any("reciting the authored opening" in f for f in failures)

    def test_one_turn_reciting_the_opening_only_warns(self) -> None:
        # Observed behaviour on CI: the starter model recites the opening back
        # on the first player turn. One such turn degrades the run without
        # making it worthless, so it warns — the same policy as one fallback.
        turns = [
            _turn(replayed_opening=True),
            _turn(turn_number=2),
            _turn(turn_number=3),
        ]
        failures, warnings = smoke.evaluate_turns(turns)
        assert failures == []
        assert any("reciting the authored opening" in w for w in warnings)

    def test_a_conversation_split_between_the_two_anomalies_still_fails(self) -> None:
        # Neither "all fell back" nor "all recited" fires, and yet not one turn
        # was a reply. Each check warns on its own because recovering from a bad
        # turn is the product working; together they leave nothing recovered.
        turns = [
            _turn(replayed_opening=True),
            _turn(turn_number=2, used_fallback=True),
            _turn(turn_number=3, used_fallback=True),
        ]
        failures, _ = smoke.evaluate_turns(turns)
        assert any("Not one of the 3" in f and "was a reply" in f for f in failures)
        # The two single-cause failures stay off: each is false here, and
        # printing them would misdescribe the run.
        assert not any("All 3" in f for f in failures)

    def test_a_single_good_turn_keeps_a_mixed_conversation_green(self) -> None:
        # One real reply among a fallback and a recital is the "the product
        # recovered" case both warnings exist for, not a failure.
        turns = [
            _turn(replayed_opening=True),
            _turn(turn_number=2, used_fallback=True),
            _turn(turn_number=3),
        ]
        failures, warnings = smoke.evaluate_turns(turns)
        assert failures == []
        assert len(warnings) == 2

    def test_the_composed_check_does_not_double_report_all_fallbacks(self) -> None:
        turns = [_turn(used_fallback=True), _turn(turn_number=2, used_fallback=True)]
        failures, _ = smoke.evaluate_turns(turns)
        assert len(failures) == 1
        assert "fell back to the canned" in failures[0]

    def test_the_composed_check_does_not_double_report_all_recitals(self) -> None:
        turns = [_turn(replayed_opening=True), _turn(turn_number=2, replayed_opening=True)]
        failures, _ = smoke.evaluate_turns(turns)
        assert len(failures) == 1
        assert "reciting the authored opening" in failures[0]

    def test_absent_parse_flags_cannot_produce_the_composed_failure(self) -> None:
        # Without the debug endpoint no turn is known to have fallen back, so
        # the only turns left are judged on replayed_opening alone — the
        # composed check must not convict a run it has no evidence about.
        turns = [
            {"label": "player_turn_1", "turn_number": 1, "model_generated": True,
             "npc_excerpt": "Go on.", "replayed_opening": True},
            {"label": "player_turn_2", "turn_number": 2, "model_generated": True,
             "npc_excerpt": "Go on.", "replayed_opening": False},
        ]
        failures, _ = smoke.evaluate_turns(turns)
        assert not any("was a reply" in f for f in failures)

    def test_a_recited_opening_is_not_mistaken_for_a_fallback(self) -> None:
        # The two have different causes and different fixes, so the verdict
        # must not describe one as the other.
        failures, warnings = smoke.evaluate_turns([_turn(replayed_opening=True)])
        assert not any("fell back" in m for m in failures + warnings)

    def test_the_authored_opening_is_not_judged_for_reciting_itself(self) -> None:
        turns = [
            {"label": "npc_opening", "turn_number": 0, "model_generated": False,
             "npc_excerpt": "Thanks for coming in.", "replayed_opening": True},
            _turn(),
        ]
        failures, warnings = smoke.evaluate_turns(turns)
        assert failures == []
        assert warnings == []


class TestReplaysOpening:
    """Reciting the authored opening is real model output that is not a reply.

    Every nightly run of the previous single-turn harness logged an NPC reply
    whose leading characters were byte-identical to the scenario's
    ``opening_npc_says``. ``used_fallback`` stays false for those turns — the
    utterance is neither empty nor the canned safe one — so without this check
    "the model produced real NPC turns" rests on the reply being non-empty.
    """

    OPENING = (
        "Thanks for coming in today. I'm Alex Chen from HR. Tell me a little "
        "about yourself and why you're interested in this role."
    )

    def test_a_verbatim_copy_is_caught(self) -> None:
        assert smoke._replays_opening(self.OPENING, self.OPENING)

    def test_a_copy_that_carries_on_into_fresh_prose_is_caught(self) -> None:
        # What the nightly logs actually showed: the recital, then more text.
        # Equality would have missed it.
        assert smoke._replays_opening(
            self.OPENING + " So, tell me about a time you shipped something.",
            self.OPENING,
        )

    def test_a_recital_that_veers_off_partway_is_caught(self) -> None:
        # The evidence this check was built from is the old harness's log line,
        # which printed npc_text[:80] against a 122-character opening: the
        # nightlies establish the first 80 characters matched and say nothing
        # about the rest.  Demanding the entire opening would have made the
        # guard silently unreachable for a recital that breaks off early, which
        # is just as much "not a reply".
        assert smoke._replays_opening(
            "Thanks for coming in today. I'm Alex Chen from HR. Tell me a little "
            "about your background in software development.",
            self.OPENING,
        )

    def test_reformatted_whitespace_does_not_hide_a_copy(self) -> None:
        assert smoke._replays_opening(
            "Thanks for coming in today.\n  I'm Alex Chen from HR.\tTell me a "
            "little\nabout yourself and why you're interested in this role.",
            self.OPENING,
        )

    def test_a_real_reply_passes(self) -> None:
        assert not smoke._replays_opening(
            "Five years is a solid run. Walk me through the hardest trade-off "
            "you made on that API platform.",
            self.OPENING,
        )

    def test_a_reply_merely_echoing_a_few_words_passes(self) -> None:
        # Only a leading recital long enough to be the scenario's own text
        # counts (REPLAY_PREFIX_CHARS); sharing an opening phrase does not.
        assert not smoke._replays_opening(
            "Thanks for coming in today was my line, not yours — but go on.",
            self.OPENING,
        )

    def test_a_short_opening_still_has_to_be_recited_in_full(self) -> None:
        # The prefix threshold is capped at the opening's own length, so it
        # only ever loosens the check for openings longer than it — a scenario
        # with a terse opening keeps the strict whole-opening semantics and
        # gains no new way to false-positive.
        short = "Hello. Begin when ready."
        assert len(short) < smoke.REPLAY_PREFIX_CHARS
        assert smoke._replays_opening(short + " So, your background?", short)
        assert not smoke._replays_opening("Hello. Five years in software.", short)

    def test_an_empty_reply_is_not_convicted_of_reciting(self) -> None:
        # An empty utterance is already a failure in its own right
        # (evaluate_turns); it must not also be reported as a recital.
        assert not smoke._replays_opening("", self.OPENING)

    def test_an_unreadable_opening_cannot_convict_a_turn(self) -> None:
        # _npc_turn_content returns '' when the opening event is missing or
        # malformed. Every reply startswith('') is True, so an absent opening
        # would otherwise fail the whole conversation.
        assert not smoke._replays_opening("A perfectly good reply.", "")
        assert not smoke._replays_opening("A perfectly good reply.", "   \n ")


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

    def test_unscored_debrief_carries_its_own_note_not_the_class_remedy(self) -> None:
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

    def test_no_observations_anywhere_is_named_and_still_worth_chasing(self) -> None:
        # The run checked, and the model volunteered nothing to score: the
        # failure can state that outright instead of listing both possibilities.
        # It must not go on to excuse itself, though — the thin prompt coverage
        # makes this reachable, but the real starter model answers the schema's
        # bare hint on every turn, so a run that hits it changed something. A
        # note that read "product gap, not a regression" would close the
        # investigation the nightly exists to open.
        failures, _ = smoke.evaluate_debrief(
            _debrief(scores={}), rubric_observations_seen=0
        )
        no_scores = next(f for f in failures if "no rubric dimension scores" in f)
        assert "no NPC turn carried a rubric_observation" in no_scores
        assert smoke.UNSCORED_DEBRIEF_NOTE in no_scores
        assert smoke.UNSCORED_WITH_OBSERVATIONS_NOTE not in no_scores
        assert "not the normal outcome" in no_scores
        assert "before writing this off" in no_scores

    def test_a_zero_caused_by_fallbacks_is_not_blamed_on_rubric_prompting(self) -> None:
        # A turn that fell back carries the canned safe utterance and an empty
        # rubric_observations list whatever the prompt asked for, so this zero
        # says nothing about rubric coverage. UNSCORED_DEBRIEF_NOTE would send
        # triage after "the OUTPUT_SCHEMA layer, the starter model pin,
        # sampling" while the fallback failure in the same verdict points
        # somewhere else entirely.
        failures, _ = smoke.evaluate_debrief(
            _debrief(scores={}), rubric_observations_seen=0, turns_all_fell_back=True
        )
        no_scores = next(f for f in failures if "no rubric dimension scores" in f)
        assert smoke.UNSCORED_AFTER_FALLBACK_NOTE in no_scores
        assert smoke.UNSCORED_DEBRIEF_NOTE not in no_scores
        assert smoke.UNSCORED_WITH_OBSERVATIONS_NOTE not in no_scores
        assert "consequence of the fallback failure above" in no_scores

    def test_observations_despite_fallbacks_still_blame_the_debrief_engine(self) -> None:
        # Some turns fell back but the rest carried observations: the debrief
        # still had something to accumulate, so the fallbacks are not the
        # explanation and the regression note is the right one.
        failures, _ = smoke.evaluate_debrief(
            _debrief(scores={}), rubric_observations_seen=2, turns_all_fell_back=True
        )
        no_scores = next(f for f in failures if "no rubric dimension scores" in f)
        assert smoke.UNSCORED_WITH_OBSERVATIONS_NOTE in no_scores
        assert smoke.UNSCORED_AFTER_FALLBACK_NOTE not in no_scores

    def test_an_unknown_observation_count_claims_neither_cause(self) -> None:
        # The count is what tells the two causes apart, so without it the
        # failure has to quote both. It must not state one as fact: a message
        # that said "could not tell" and then "No NPC turn volunteered a single
        # rubric observation" sends triage after the product weakness when the
        # debrief engine dropping validated observations is just as open.
        failures, _ = smoke.evaluate_debrief(_debrief(scores={}))
        no_scores = next(f for f in failures if "no rubric dimension scores" in f)
        assert "cannot be told apart" in no_scores
        assert smoke.UNSCORED_DEBRIEF_NOTE in no_scores
        assert smoke.UNSCORED_WITH_OBSERVATIONS_NOTE in no_scores
        assert "No NPC turn volunteered" not in no_scores

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

    def test_an_absent_summary_is_still_measured_as_too_short(self) -> None:
        failures, _ = smoke.evaluate_debrief(_debrief(summary=None))
        assert any("summary is shorter" in f for f in failures)

    @pytest.mark.parametrize(
        "summary",
        [
            # Long enough that a repr would clear MIN_SUMMARY_CHARS, so the type
            # check cannot be mistaken for the length check passing.
            {"text": "You gave concrete examples but hedged on the trade-off."},
            ["You gave concrete examples but hedged on the trade-off."],
            42,
        ],
    )
    def test_a_summary_that_is_not_text_is_a_product_failure_not_a_harness_bug(
        self, summary: object
    ) -> None:
        # len(summary.strip()) raises AttributeError on all of these, and an
        # AttributeError out of the assertion layer reaches run_smoke's catch-all,
        # which reports "most likely a bug in the smoke harness" -- the one
        # verdict that is certainly wrong for a changed response contract.
        failures, _ = smoke.evaluate_debrief(_debrief(summary=summary))
        assert any("summary is not a string" in f for f in failures)
        # Named as a type, and the value shown, so triage does not have to go and
        # fetch the artifact to find out what arrived.
        assert any(type(summary).__name__ in f for f in failures)
        # And never reported as a length problem: nothing here is about brevity.
        assert not any("summary is shorter" in f for f in failures)

    def test_fallback_narrative_only_warns_because_scores_are_still_real(self) -> None:
        failures, warnings = smoke.evaluate_debrief(_debrief(used_fallback=True))
        assert failures == []
        fallback = next(w for w in warnings if "fallback" in w)
        # The debrief is generated once, so a fallback means no model-written
        # debrief prose was produced at all and this is the only job that would
        # notice. The run still passes -- the scores do not come from this
        # generation -- so the warning has to say what the green verdict did not
        # prove, or the limitation is invisible.
        assert "proves nothing about real-model debrief generation" in fallback
        assert "Recurring across nightlies" in fallback

    def test_absent_turning_points_only_warn(self) -> None:
        failures, warnings = smoke.evaluate_debrief(_debrief(turning_points=[]))
        assert failures == []
        assert any("turning points" in w for w in warnings)


class TestUnscoredDebriefRemedyIsStillTrue:
    """The unscored-debrief note explains *why* nothing asks for observations.

    That explanation is the whole value of the note -- it is what keeps triage
    off the two wrong tracks (a parse failure, or a different scenario) -- and it
    is a claim about product source this harness does not import. If the product
    grows a rubric route into the turn prompt, the note starts handing out advice
    for a weakness that no longer exists, and nothing else in this file notices.
    """

    _PROMPT_SRC = REPO_ROOT / "packages" / "prompt-composer" / "src" / "convsim_prompt"

    def test_no_prompt_layer_names_a_rubric_dimension(self) -> None:
        layers = (self._PROMPT_SRC / "layers.py").read_text(encoding="utf-8")
        assert "rubric" not in layers.lower(), (
            "a prompt layer now mentions a rubric, so UNSCORED_DEBRIEF_NOTE's "
            "'no prompt layer names the rubric dimensions' may no longer hold"
        )

    def test_a_scenario_cannot_carry_a_rubric_into_the_turn_prompt(self) -> None:
        # Why the note must NOT say "or play a scenario that defines one": the
        # official job-interview-basic pack's behavioral_interview does define a
        # rubric, and composing a turn prompt from it would change nothing,
        # because the dataclass the composer is handed has nowhere to put it.
        types_src = (self._PROMPT_SRC / "types.py").read_text(encoding="utf-8")
        start = types_src.index("class ScenarioData:")
        body = types_src[start:types_src.index("\n@", start)]
        assert "rubric" not in body.lower(), (
            "ScenarioData now carries a rubric, so a rubric-defining scenario may "
            "reach the turn prompt after all -- revisit UNSCORED_DEBRIEF_NOTE and "
            "the 'Unscored debrief' section of docs/real-model-smoke.md"
        )


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


class TestTimeoutLatencyEvidence:
    """A `timeout` verdict must say when the real story is a latency regression.

    Three turns at the 240 s CI ceiling plus a debrief allowed twice that very
    nearly fill the 20 min wall-clock budget, so a uniform ~2x slowdown — the
    regression `budget` exists to catch — exhausts the clock before the budget
    phase ever runs.  TIMEOUT outranks it, so the measurement has to be attached
    to the verdict or the remedy ("slower, or hung?") leaves triage guessing.
    """

    @staticmethod
    def _turns(*latencies_ms: float) -> list[dict]:
        return [
            {"label": "npc_opening", "turn_number": 0, "model_generated": False,
             "latency_ms": 10},
            *[
                {"label": f"player_turn_{i}", "turn_number": i,
                 "model_generated": True, "latency_ms": ms}
                for i, ms in enumerate(latencies_ms, start=1)
            ],
        ]

    def test_turns_past_the_ceiling_are_named_as_a_likely_regression(self) -> None:
        evidence = smoke.timeout_latency_evidence(
            self._turns(250_000, 260_000, 270_000), 240_000
        )
        assert evidence is not None
        assert "260000 ms" in evidence  # the median of the completed turns
        assert "240000 ms CI ceiling" in evidence
        assert "`budget`" in evidence

    def test_turns_inside_the_ceiling_stay_a_plain_timeout(self) -> None:
        # Something hung, or a phase other than the conversation ran long:
        # claiming a latency regression here would be a guess.
        assert smoke.timeout_latency_evidence(
            self._turns(10_000, 11_000, 12_000), 240_000
        ) is None

    def test_a_run_that_timed_out_before_any_turn_says_nothing(self) -> None:
        assert smoke.timeout_latency_evidence(self._turns(), 240_000) is None

    def test_the_authored_opening_is_not_evidence_of_slow_inference(self) -> None:
        # The opening is replayed scenario text, so its latency says nothing
        # about the model -- counting it would invent evidence.
        slow_opening = [{"label": "npc_opening", "turn_number": 0,
                         "model_generated": False, "latency_ms": 10 ** 9}]
        assert smoke.timeout_latency_evidence(slow_opening, 240_000) is None

    def test_one_slow_turn_among_fast_ones_is_not_called_a_regression(self) -> None:
        # Same reason full_response_ms is a median: one unlucky turn is noise.
        assert smoke.timeout_latency_evidence(
            self._turns(10_000, 10 ** 9, 12_000), 240_000
        ) is None


class TestDocumentedBudgetAgreement:
    """BUDGETS_MS must agree with the budget the product publishes.

    The harness deliberately does not import the TypeScript constant, so the
    only thing keeping the number it enforces equal to the number the product
    promises is a hand-maintained copy. These tests make that copy load-bearing:
    a nightly that fails against a stale budget is worse than no nightly, and a
    performance doc that advertises CI coverage of a budget it no longer lists
    leaves the claim with no referent.
    """

    def test_the_shared_latency_constant_agrees_with_the_harness(self) -> None:
        import re

        metrics = (
            REPO_ROOT / "packages" / "shared" / "src" / "types" / "metrics.ts"
        ).read_text(encoding="utf-8")
        match = re.search(r"FULL_RESPONSE_MS:\s*([\d_]+)", metrics)
        assert match, "LATENCY_BUDGETS.FULL_RESPONSE_MS not found in metrics.ts"
        assert int(match.group(1).replace("_", "")) == smoke.BUDGETS_MS["full_response_ms"]

    @pytest.mark.parametrize(
        "doc_path",
        [
            ("docs", "performance.md"),
            ("docs-site", "src", "content", "docs", "play", "performance.md"),
        ],
    )
    def test_the_enforced_budget_is_published_in_the_performance_doc(
        self, doc_path: tuple
    ) -> None:
        doc = REPO_ROOT.joinpath(*doc_path).read_text(encoding="utf-8")
        seconds = smoke.BUDGETS_MS["full_response_ms"] / 1000
        assert "Full NPC response" in doc, (
            "the only budget this job enforces is missing from the latency table, "
            "so the doc's claim about CI coverage names nothing a reader can check"
        )
        assert f"< {seconds:.0f} s" in doc
        assert "real-model-smoke" in doc


# ---------------------------------------------------------------------------
# Wall-clock budget
# ---------------------------------------------------------------------------


# Allowance for the steps that burn the job's clock before the harness starts and
# so are invisible to its own deadline: checkout, three pip installs, the cache
# restore and, on a cache miss, the download plus the cache save that follows it.
#
# Deliberately far above the measurement.  Those steps total ~1 min on the
# nightlies run so far (see the measured breakdown in docs/real-model-smoke.md),
# but they are the network-bound part of the job, so this asserts the two
# ceilings stay compatible with a night on which they run several times slower.
# Lowering it to the measured ~1 min would make the assertion vacuous.
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

    def test_the_download_cannot_eat_the_margin_it_runs_in(self) -> None:
        # The download is a separate step that runs before the smoke, so it
        # spends the same margin the assertion above reserves for setup, and the
        # harness's own Deadline never sees it. Its budget therefore has to fit
        # inside that margin alongside the other pre-smoke steps, or a slow
        # Hugging Face night hands the smoke a job clock with no room left and
        # GitHub cancels the job mid-conversation — no class, no phase, no
        # remedy, which is the one outcome this whole design rules out.
        other_pre_smoke_steps_s = 120.0  # checkout, 3 pip installs, cache restore + save
        assert (
            smoke.DOWNLOAD_BUDGET_S + other_pre_smoke_steps_s
            <= PRE_SMOKE_JOB_MINUTES * 60
        ), (
            f"a {smoke.DOWNLOAD_BUDGET_S:.0f} s download budget plus the other "
            f"pre-smoke steps exceeds the ~{PRE_SMOKE_JOB_MINUTES} min margin between "
            "the harness deadline and the job timeout"
        )


def _workflow_steps() -> list:
    import yaml

    return yaml.safe_load(_workflow_text())["jobs"]["model-smoke"]["steps"]


def _step_running(fragment: str) -> dict:
    """Return the single workflow step whose ``run`` contains ``fragment``."""
    matches = [s for s in _workflow_steps() if fragment in (s.get("run") or "")]
    assert len(matches) == 1, f"expected exactly one step running {fragment!r}"
    return matches[0]


def _steps_using(prefix: str) -> list:
    return [s for s in _workflow_steps() if (s.get("uses") or "").startswith(prefix)]


def _step_index(step: dict) -> int:
    return _workflow_steps().index(step)


class TestWorkflowChecksumInvariants:
    """#457's "fail loudly on checksum drift" is enforced by the YAML, not the harness.

    Two halves of that promise live in the workflow and nowhere else, and each
    is one quiet edit away from being given up while every other test in this
    file stays green:

    * ``verify_model_checksum`` only runs on a full smoke when
      ``--model-sha256`` is passed. Drop the flag and the harness downgrades to
      a warning and loads whatever the cache restored — the exact cache-hit
      drift this job exists to catch.
    * The harness cannot keep a GGUF it rejected out of the Actions cache; only
      the step ordering can. ``actions/cache``'s post step saves even when the
      job failed, and the key is derived from the *expected* hash, so a single
      poisoned entry would be restored by every later run.
    """

    def test_the_smoke_reverifies_the_file_it_is_about_to_load(self) -> None:
        run = _step_running("--ci-hardware-factor")["run"]
        assert "--model-sha256" in run, (
            "without --model-sha256 the full smoke only warns that drift was "
            "not checked, so a corrupt cache hit is fed to the model and the "
            "run can still go green"
        )

    def test_the_cache_key_and_the_verified_hash_come_from_one_lookup(self) -> None:
        import re

        pattern = r"steps\.([A-Za-z0-9_-]+)\.outputs\.model_sha256"
        restore = _steps_using("actions/cache/restore")
        assert restore, "the model cache must be restored"
        key_sources = {m for s in restore for m in re.findall(pattern, s["with"]["key"])}
        smoke_sources = set(re.findall(pattern, _step_running("--ci-hardware-factor")["run"]))
        assert key_sources and key_sources == smoke_sources, (
            "the cache key and the hash the smoke verifies against must come "
            f"from the same registry lookup (key: {key_sources}, smoke: {smoke_sources}); "
            "two lookups can drift apart and cache a file under a hash nothing checked"
        )

    def test_an_unverified_model_is_never_written_to_the_cache(self) -> None:
        assert not _steps_using("actions/cache@"), (
            "actions/cache saves from a post step that runs even when the job "
            "failed; use the split restore/save so the save can be gated"
        )
        save = _steps_using("actions/cache/save")
        assert len(save) == 1, "exactly one step may write the model cache"
        assert "success()" in str(save[0].get("if", "")), (
            "the cache save must be gated on success(), or a GGUF that failed "
            "checksum verification is cached under its expected hash and every "
            "later run restores the same bad bytes"
        )
        download = _step_running("--download-only")
        assert _step_index(download) < _step_index(save[0]), (
            "the model must be downloaded and verified before it is cached"
        )

    def test_the_restored_and_saved_cache_entries_are_the_same(self) -> None:
        restore = _steps_using("actions/cache/restore")[0]
        save = _steps_using("actions/cache/save")[0]
        assert restore["with"]["key"] == save["with"]["key"], (
            "a save under a different key than the restore never produces a "
            "cache hit, so every nightly re-downloads 2.5 GB"
        )
        assert restore["with"]["path"] == save["with"]["path"]


_REAL_MODEL_SMOKE_DOCS = (
    REPO_ROOT / "docs" / "real-model-smoke.md",
    REPO_ROOT / "docs-site" / "src" / "content" / "docs" / "dev" / "real-model-smoke.md",
)


class TestWheelInstallInvariants:
    """llama-cpp-python must arrive as a prebuilt wheel, never as a source build.

    PyPI ships llama-cpp-python as an sdist only — the CPU wheels live on the
    extra index — and ``--extra-index-url`` does not *prefer* them: pip resolves
    the newest version across both indexes, so on any night the wheel index lags
    PyPI, pip compiles llama.cpp on the runner.  That turns the ~16 s install
    row of the runtime budget into 15+ min, which the 30 min job timeout has no
    room for next to ~11 min of inference: the job dies with exactly the
    unattributable "operation was canceled" that the harness's phase-attributed
    deadline exists to replace, on a night when nothing about the product
    changed.

    Like the checksum promises above, this lives in the YAML and nowhere else,
    and it reads as a redundant flag next to the extra index that is "obviously"
    already doing the job.
    """

    def test_the_llama_wheel_is_never_built_from_source(self) -> None:
        run = _step_running("llama-cpp-python[server]")["run"]
        assert "--only-binary llama-cpp-python" in run, (
            "--extra-index-url alone does not stop pip from picking a PyPI "
            "sdist and compiling llama.cpp on the runner, which costs more "
            "than the whole job budget allows"
        )

    @pytest.mark.parametrize("doc", _REAL_MODEL_SMOKE_DOCS, ids=lambda p: p.parts[0])
    def test_the_documented_local_repro_installs_the_same_wheel(self, doc: Path) -> None:
        # The repro block is a hand-made copy of the install step, so it drifts
        # silently. A reader who follows it and gets a 15 min source build
        # concludes the harness is the problem.
        assert "--only-binary llama-cpp-python" in doc.read_text(encoding="utf-8")


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

    def test_a_pre_run_failure_does_not_claim_a_zero_second_run(self) -> None:
        # --download-only / --verify-only and the registry lookup write a summary
        # without ever starting a clock; reporting "Wall clock: 0 s (budget 0 s)"
        # on a download verdict invents a measurement the run never took.
        text = smoke.render_step_summary({
            "verdict": "fail",
            "model_id": "qwen3-4b",
            "failure_class": smoke.FailureClass.DOWNLOAD,
            "exit_code": 2,
            "failures": ["Download failed for https://…: TimeoutError()"],
            "remedy": smoke.REMEDIES[smoke.FailureClass.DOWNLOAD],
        })
        assert "Wall clock" not in text
        assert "`download`" in text
        assert smoke.REMEDIES[smoke.FailureClass.DOWNLOAD] in text
        assert "**Model:** `qwen3-4b`" in text

    def test_a_registry_failure_does_not_name_a_model_it_never_resolved(self) -> None:
        # --print-registry-model runs before any --model-id exists, and it is
        # the mode that fails on a registry with no usable (or not yet pinned)
        # `starter` entry. Rendering `model_id` unconditionally put
        # "**Model:** `None`" at the very top of that verdict.
        text = smoke.render_step_summary({
            "verdict": "fail",
            "model_id": None,
            "failure_class": smoke.FailureClass.PIPELINE,
            "exit_code": 5,
            "failures": ["No model with role 'starter' in model-registry/registry.yaml"],
            "remedy": smoke.REGISTRY_REMEDY,
        })
        assert "Model:" not in text
        assert "None" not in text
        assert smoke.REGISTRY_REMEDY in text

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

    def test_an_empty_observation_list_counts_zero(self) -> None:
        # An empty list is a real observation of zero: the model was asked (by
        # the schema's bare hint) and volunteered nothing.
        assert smoke._rubric_observation_count(
            [{"event_type": "npc_turn", "payload": {
                "content": "x", "rubric_observations": []}}]
        ) == 0

    @pytest.mark.parametrize("payload", [
        {"content": "x"},                                  # key absent entirely
        {"content": "x", "rubric_observations": None},     # present but unusable
        {"content": "x", "rubric_observations": "two"},
    ])
    def test_an_unreadable_observation_list_is_unknown_not_zero(
        self, payload: dict
    ) -> None:
        # Counting an unreadable payload as zero would let the unscored-debrief
        # verdict assert "no NPC turn carried a rubric_observation" — sending
        # triage after the prompt layer and the model pin — when what actually
        # happened is that the turn response no longer exposes the list.
        assert smoke._rubric_observation_count(
            [{"event_type": "npc_turn", "payload": payload}]
        ) is None

    @pytest.mark.parametrize(("counts", "expected"), [
        ([0, 0, 0], 0),
        ([1, 0, 2], 3),
        ([None, None, None], None),      # nothing readable anywhere
        ([None, 0, 0], None),            # a gap with no positive evidence
        ([0, None, 0], None),            # ...wherever in the run the gap falls
        ([None, 2, 0], 2),               # observations were seen regardless
    ])
    def test_a_zero_total_is_reported_only_when_every_turn_was_readable(
        self, counts: list, expected: int | None
    ) -> None:
        # None does not mean "nothing was readable": two readable zeroes
        # alongside one unreadable turn is still None, because reporting 0 would
        # have the verdict assert the model volunteered nothing across the
        # conversation when the unread turn may have carried plenty.
        turns = [{"model_generated": False, "label": "npc_opening"}] + [
            {"model_generated": True, "rubric_observation_count": c} for c in counts
        ]
        assert smoke._total_rubric_observations(turns) == expected

    def test_a_run_with_no_generated_turns_reports_an_unknown_total(self) -> None:
        # Nothing was observed, which is not the same as observing nothing.
        assert smoke._total_rubric_observations(
            [{"model_generated": False, "label": "npc_opening"}]
        ) is None

    def test_excerpt_is_bounded_and_collapsed(self) -> None:
        excerpt = smoke._excerpt("a\n\n  b" + "x" * 500)
        assert excerpt.startswith("a b")
        assert len(excerpt) <= smoke.EXCERPT_CHARS + 1  # + the ellipsis
        assert excerpt.endswith("…")

    def test_excerpting_a_non_string_shows_its_shape_instead_of_raising(self) -> None:
        # _excerpt alone raises AttributeError here (str.split), which is why the
        # report assembly in run_smoke goes through _excerpt_any.
        assert smoke._excerpt_any({"text": "hi"}) == "{'text': 'hi'}"
        assert smoke._excerpt_any(42) == "42"

    def test_excerpting_an_absent_value_is_empty_not_the_word_none(self) -> None:
        assert smoke._excerpt_any(None) == ""

    def test_excerpting_a_string_is_unchanged_by_the_tolerant_wrapper(self) -> None:
        assert smoke._excerpt_any("a\n\n  b") == smoke._excerpt("a\n\n  b")


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
# Port ownership
# ---------------------------------------------------------------------------


@pytest.fixture()
def occupied_port():
    """A loopback port with a live listener on it, released after the test."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


@pytest.fixture()
def free_port() -> int:
    """A loopback port nothing is listening on."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestPortOwnership:
    """The smoke must own its ports, or its proof of a real model is worthless.

    Readiness is a URL poll, so a server the harness did not start answers it
    and the run proceeds against a model whose bytes were never verified. The
    child that lost the bind dies, but ``_crashed_child`` is only consulted
    once a failure has been raised, so a run that otherwise passes never
    notices -- it just reports a green verdict for the wrong model.
    """

    def test_a_free_port_is_accepted(self, free_port: int) -> None:
        assert smoke._assert_port_free(free_port, "llama-server") is None

    def test_an_occupied_port_is_a_runtime_failure(self, occupied_port: int) -> None:
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._assert_port_free(occupied_port, "llama-server")
        assert exc_info.value.failure_class == smoke.FailureClass.RUNTIME
        assert exc_info.value.exit_code == 4
        assert str(occupied_port) in str(exc_info.value)

    def test_the_remedy_does_not_send_triage_to_an_unstarted_child(
        self, occupied_port: int
    ) -> None:
        # `runtime`'s stock advice is "read the child stderr tail"; here no
        # child has been started, so the class remedy would mislead.
        with pytest.raises(smoke.SmokeFailure) as exc_info:
            smoke._assert_port_free(occupied_port, "convsim-core")
        remedy = exc_info.value.remedy
        assert "Stop whatever is listening" in remedy
        assert remedy != smoke.REMEDIES[smoke.FailureClass.RUNTIME]

    def test_a_squatter_stops_the_run_before_any_server_is_started(
        self,
        staged_model,
        occupied_port: int,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        models_dir, model_id, digest = staged_model
        started: list[str] = []

        def _record(label: str):
            def _start(*args: object, **kwargs: object) -> "_FakeProc":
                started.append(label)
                return _FakeProc()
            return _start

        monkeypatch.setattr(smoke, "LLAMA_SERVER_PORT", occupied_port)
        monkeypatch.setattr(smoke, "_start_llama_server", _record("llama"))
        monkeypatch.setattr(smoke, "_start_core", _record("core"))
        monkeypatch.setattr(smoke, "_wait_for_http", lambda *a, **k: None)
        monkeypatch.setattr(smoke, "_request_json", _fake_core(_debrief()))
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == 4
        assert started == [], "the squatter must be caught before anything is spawned"
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["failure_class"] == smoke.FailureClass.RUNTIME
        assert results["failed_phase"] == "runtime_start"
        assert "Stop whatever is listening" in results["remedy"]


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
# convsim-core always puts a rubric_observations list in the npc_turn payload
# (see the npc_event payload in routers/sessions.py), empty or not, so the
# baseline fake carries one too. A payload *without* the key is a different
# situation the harness must not read as "the model volunteered none" — see
# test_a_turn_payload_without_observations_is_not_read_as_zero.
_NPC_TURN = {"events": [{"event_type": "npc_turn",
                         "payload": {"content": "Walk me through that trade-off.",
                                     "rubric_observations": []}}],
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
    # No child is really spawned, so no port is really needed. Left live, the
    # port check would make every test below depend on whether the developer
    # happens to have a llama-server on 7356 -- which, on the machine this was
    # written on, they did. TestPortOwnership covers the check itself.
    monkeypatch.setattr(smoke, "_assert_port_free", lambda *a, **k: None)
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
        # Builds its own children rather than using fake_servers, so it has to
        # neutralise the port check the same way that fixture does.
        monkeypatch.setattr(smoke, "_assert_port_free", lambda *a, **k: None)

        exit_code = smoke.run_smoke(
            model_id, 20.0, None, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == 0
        assert seen["existed_at_terminate"] is True
        assert not seen["data_dir"].exists(), "the data directory leaked"

    def test_a_conversation_of_recited_openings_does_not_pass(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Every flag healthy, every "reply" the authored opening read back.

        This is the run the parse flags cannot fail: the utterances are real
        model output, non-empty and not the canned fallback. It must not report
        that the model produced real NPC turns.
        """
        models_dir, model_id, digest = staged_model
        opening = _OPENING["events"][0]["payload"]["content"]
        recital = {"events": [{"event_type": "npc_turn", "payload": {
            "content": f"{opening} Now, tell me about a time you disagreed.",
            "rubric_observations": [],
        }}], "ending_type": None}
        monkeypatch.setattr(
            smoke, "_request_json", _fake_core(_debrief(), turn=recital)
        )
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["failed_phase"] == "assertions"
        assert any("reciting the authored opening" in f for f in results["failures"])
        # Recorded per turn, so triage can see which turns did it without
        # re-reading the excerpts.
        assert all(t["replayed_opening"] for t in results["turns"][1:])

    def test_a_healthy_run_records_that_no_turn_recited_the_opening(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, digest = staged_model
        monkeypatch.setattr(smoke, "_request_json", _fake_core(_debrief()))
        report = tmp_path / "report.json"

        assert smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        ) == 0
        results = json.loads(report.read_text(encoding="utf-8"))
        assert all(t["replayed_opening"] is False for t in results["turns"][1:])
        assert results["warnings"] == []

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

    def test_a_debrief_summary_that_is_not_text_is_a_product_verdict(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A changed response contract must not be reported as a harness bug.

        The summary is read twice on the way to a verdict, and the *first* read is
        the report assembly in run_smoke, which runs before evaluate_debrief: a
        guard in the assertion layer alone leaves the raise reachable. Both go
        through the tolerant excerpt, so the run reaches its classified verdict
        and the artifact still shows what arrived.
        """
        models_dir, model_id, digest = staged_model
        summary = {"text": "You gave concrete examples but hedged on the trade-off."}
        monkeypatch.setattr(
            smoke, "_request_json", _fake_core(_debrief(summary=summary))
        )
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["failure_class"] == smoke.FailureClass.PIPELINE
        assert results["failed_phase"] == "assertions"
        assert any("summary is not a string" in f for f in results["failures"])
        # The product's remedy, not the harness-bug one the catch-all prints.
        assert results["remedy"] == smoke.REMEDIES[smoke.FailureClass.PIPELINE]
        assert not any("bug in the smoke harness" in f for f in results["failures"])
        # And the payload that caused it survives into the artifact.
        assert "hedged on the trade-off" in results["debrief"]["summary_excerpt"]

    def test_a_conversation_of_fallbacks_does_not_blame_the_rubric_prompt(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The failure mode a 4 B model on CPU actually produces.

        Every turn's output fails validation, so every turn returns the canned
        safe utterance with an empty rubric_observations list and the debrief
        scores nothing. Both failures land in one verdict, and the unscored one
        must not send triage after the OUTPUT_SCHEMA layer, the model pin and
        sampling settings when the fallback failure beside it already names the
        thing to read.
        """
        models_dir, model_id, digest = staged_model
        monkeypatch.setattr(
            smoke, "_request_json",
            _fake_core(
                _debrief(scores={}, overall_score=None),
                debug_turns=[
                    {"turn_number": n, "used_fallback": True,
                     "used_native_structured_output": False}
                    for n in range(1, len(smoke.SCRIPTED_PLAYER_TURNS) + 1)
                ],
            ),
        )
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["rubric_observations_seen"] == 0
        assert any("fell back to the canned" in f for f in results["failures"])
        no_scores = next(f for f in results["failures"] if "rubric dimension scores" in f)
        assert smoke.UNSCORED_AFTER_FALLBACK_NOTE in no_scores
        assert smoke.UNSCORED_DEBRIEF_NOTE not in no_scores

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

    def test_a_turn_payload_without_observations_is_not_read_as_zero(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A third case: the harness could not read what the turns volunteered.

        convsim-core always sends a rubric_observations list today, so a payload
        without one means the turn response contract changed. Scoring that as
        "the model volunteered nothing" would have the verdict confidently name
        the one cause the run has no evidence for, and send triage to the prompt
        layer and the model pin. Say both causes are open instead.
        """
        models_dir, model_id, digest = staged_model
        no_observations_key = {
            "events": [{"event_type": "npc_turn",
                        "payload": {"content": "Walk me through that trade-off."}}],
            "ending_type": None,
        }
        monkeypatch.setattr(
            smoke, "_request_json",
            _fake_core(
                _debrief(scores={}, overall_score=None),
                turn=no_observations_key,
            ),
        )
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["rubric_observations_seen"] is None
        assert all(
            t["rubric_observation_count"] is None for t in results["turns"][1:]
        ), "a null per-turn count is what tells the reader the list was unreadable"
        no_scores = next(f for f in results["failures"] if "rubric dimension" in f)
        # Names what it actually observed (an unreadable list) and keeps both
        # causes open, rather than asserting the one it has no evidence for.
        assert "unreadable" in no_scores
        assert "cannot be told apart" in no_scores
        assert smoke.UNSCORED_DEBRIEF_NOTE in no_scores
        assert smoke.UNSCORED_WITH_OBSERVATIONS_NOTE in no_scores

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

    def test_the_headline_full_response_is_the_median_not_the_worst_turn(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # One unlucky turn -- runner steal, an unusually long NPC answer -- must
        # not move the figure the budget judges, or the nightly flaps.  A real
        # regression moves every turn and so moves the median.
        import time

        models_dir, model_id, digest = staged_model
        base = _fake_core(_debrief())
        total_turns = len(smoke.SCRIPTED_PLAYER_TURNS)
        seen = {"turns": 0}

        def _one_slow_turn(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith("/turn"):
                seen["turns"] += 1
                if seen["turns"] == total_turns:  # only the last turn is slow
                    time.sleep(0.25)
            return base(url, payload=payload, timeout=timeout, expect=expect)

        monkeypatch.setattr(smoke, "_request_json", _one_slow_turn)
        report = tmp_path / "report.json"

        assert smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        ) == 0

        results = json.loads(report.read_text(encoding="utf-8"))
        per_turn = sorted(
            t["latency_ms"] for t in results["turns"] if t["model_generated"]
        )
        assert len(per_turn) == total_turns
        headline = results["measured_ms"]["full_response_ms"]
        # The median of the turns, not their worst and not their mean.
        assert abs(headline - statistics.median(per_turn)) <= 1
        assert results["measured_ms"]["full_response_max_ms"] == per_turn[-1]
        # The slow turn is still recorded -- it is just not the headline.
        assert per_turn[-1] - headline > 100

    def test_a_timeout_names_the_latency_regression_it_hides(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Three turns at the CI ceiling plus a debrief allowed twice that very
        # nearly fill the wall-clock budget, so the regression `budget` exists to
        # catch exhausts the clock before the budget phase runs.  TIMEOUT is the
        # honest class, but it has to carry the measurement or its remedy
        # ("slower, or hung?") leaves triage to guess.
        import time

        models_dir, model_id, digest = staged_model
        base = _fake_core(_debrief())

        def _slow(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            if url.endswith("/turn"):
                time.sleep(0.05)  # measurable, so a 0 ms ceiling is exceeded
            if url.endswith("/debrief"):
                time.sleep(0.6)  # outlast the budget below
                raise smoke.SmokeFailure(
                    smoke.FailureClass.RUNTIME, f"{url} did not answer with usable JSON"
                )
            return base(url, payload=payload, timeout=timeout, expect=expect)

        monkeypatch.setattr(smoke, "_request_json", _slow)
        report = tmp_path / "report.json"

        # Factor 0 => a 0 ms ceiling, so the measured turns are over it.
        exit_code = smoke.run_smoke(
            model_id, 0.0, report, model_sha256=digest, models_dir=models_dir,
            wall_clock_budget_s=0.5,
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.TIMEOUT]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["failure_class"] == smoke.FailureClass.TIMEOUT
        assert any(
            "latency regression" in f and "CI ceiling" in f
            for f in results["failures"]
        )

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

    @pytest.mark.parametrize("health", [{}, {"llm_runtime": None}])
    def test_an_unreadable_runtime_report_is_refused_not_called_a_harness_bug(
        self, health: dict, staged_model, fake_servers,
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """An absent *or null* llm_runtime must still reach the refusal verdict.

        The smoke must never play a turn without having confirmed the real
        runtime, so an unreadable /health is a refusal like any other -- and a
        `{}` default would have let an explicit null raise AttributeError and
        report a changed /health contract as a bug in the harness instead.
        """
        models_dir, model_id, digest = staged_model

        def _unreadable(url: str, *, payload=None, timeout=None, expect=(200, 201)) -> dict:
            assert url.endswith("/health"), "must not play a turn on an unknown runtime"
            return health

        monkeypatch.setattr(smoke, "_request_json", _unreadable)
        report = tmp_path / "report.json"

        exit_code = smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        )

        assert exit_code == smoke.EXIT_CODES[smoke.FailureClass.PIPELINE]
        results = json.loads(report.read_text(encoding="utf-8"))
        assert "runtime_id" in results["failures"][0]
        assert not any("bug in the smoke harness" in f for f in results["failures"])

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
        # Green, but on one turn instead of three. The job exists to play a
        # multi-turn conversation, so a short run must not read like a full one.
        assert results["scripted_turns_played"] == 1
        assert any(
            f"Only 1 of {len(smoke.SCRIPTED_PLAYER_TURNS)} scripted player turns ran" in w
            for w in results["warnings"]
        ), results["warnings"]

    def test_a_full_playthrough_does_not_warn_about_a_short_run(
        self, staged_model, fake_servers, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        models_dir, model_id, digest = staged_model
        monkeypatch.setattr(smoke, "_request_json", _fake_core(_debrief()))
        report = tmp_path / "report.json"

        assert smoke.run_smoke(
            model_id, 20.0, report, model_sha256=digest, models_dir=models_dir
        ) == 0
        results = json.loads(report.read_text(encoding="utf-8"))
        assert results["scripted_turns_played"] == len(smoke.SCRIPTED_PLAYER_TURNS)
        assert results["warnings"] == []

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


# ---------------------------------------------------------------------------
# Child stderr tails
# ---------------------------------------------------------------------------


class _LiveTail:
    """A tail that raises when iterated, the way a deque does mid-append.

    ``_dump_stderr_tails`` runs from ``run_smoke``'s except handler, before the
    finally block stops either child, so the draining thread is still appending.
    Iterating the live buffer therefore has to be impossible, not merely
    unlikely -- a ``RuntimeError`` from there escapes the handler and discards
    the classified verdict.
    """

    def __init__(self, *lines: str) -> None:
        self._lines = list(lines)

    def __iter__(self):
        raise RuntimeError("deque mutated during iteration")

    def __len__(self) -> int:
        raise RuntimeError("deque mutated during iteration")

    def snapshot(self) -> list:
        return list(self._lines)


class TestStderrTails:
    """The dump must not iterate a buffer another thread is writing to."""

    def test_the_dump_reads_a_snapshot_not_the_live_buffer(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        smoke._dump_stderr_tails((("convsim-core", _LiveTail("boom", "trace")),))
        err = capsys.readouterr().err
        assert "last 2 lines" in err
        assert "boom" in err and "trace" in err

    def test_an_empty_tail_prints_no_header(self, capsys: pytest.CaptureFixture) -> None:
        smoke._dump_stderr_tails((("llama-server", smoke.StderrTail()),))
        assert capsys.readouterr().err == ""

    def test_the_tail_keeps_only_the_most_recent_lines(self) -> None:
        tail = smoke.StderrTail(maxlen=3)
        for i in range(10):
            tail.append(f"line {i}")
        assert tail.snapshot() == ["line 7", "line 8", "line 9"]

    def test_a_snapshot_does_not_alias_the_buffer(self) -> None:
        tail = smoke.StderrTail()
        tail.append("first")
        snapshot = tail.snapshot()
        tail.append("second")
        assert snapshot == ["first"]

    def test_draining_a_byte_stream_decodes_and_strips(self) -> None:
        tail = smoke.StderrTail()
        smoke._drain(iter([b"warning: slow\n", b"\xff bad utf-8\n"]), tail)
        assert tail.snapshot() == ["warning: slow", "� bad utf-8"]

    def test_a_stream_that_breaks_mid_read_does_not_kill_the_drain_thread(self) -> None:
        # The drain runs in a daemon thread with nothing to catch for it, and a
        # pipe closed under it while the child is being terminated is routine.
        def _broken():
            yield b"last words\n"
            raise ValueError("pipe closed")

        tail = smoke.StderrTail()
        smoke._drain(_broken(), tail)
        assert tail.snapshot() == ["last words"]


# ---------------------------------------------------------------------------
# Log ordering
# ---------------------------------------------------------------------------


class TestLogOrdering:
    """The CI log has to read in the order things happened.

    CI captures the harness through a pipe, so Python block-buffers stdout
    while stderr stays unbuffered. Unfixed, that means the phase progress and
    per-turn latencies (stdout) arrive after the failure banner and child
    stderr tails (stderr) — and during the ~11 min the conversation and
    debrief phases take, nothing streams at all.
    """

    def test_progress_is_logged_before_the_banner_it_explains(
        self, tmp_path: Path
    ) -> None:
        import subprocess
        import sys

        model = tmp_path / "drifted.gguf"
        model.write_bytes(b"not the pinned bytes")

        # Piped, merged, and run with the inherited environment so that only
        # the harness's own buffering decides the order.
        proc = subprocess.run(
            [
                # The interpreter running the tests, not whatever "python3"
                # resolves to on PATH: the harness imports PyYAML, which is
                # only guaranteed in this environment.
                sys.executable, str(SCRIPT_PATH), "--verify-only",
                "--model-id", "drifted", "--model-sha256", "0" * 64,
                "--models-dir", str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )

        assert proc.returncode == smoke.EXIT_CODES[smoke.FailureClass.CHECKSUM]
        log = proc.stdout
        progress_at = log.find("Verifying cached model")
        banner_at = log.find("FAILED — class: CHECKSUM")
        assert progress_at != -1, f"progress line missing from:\n{log}"
        assert banner_at != -1, f"banner missing from:\n{log}"
        assert progress_at < banner_at, (
            "the stdout progress line arrived after the stderr banner, so the "
            f"CI log reads out of order:\n{log}"
        )

    def test_reconfiguring_a_stream_that_cannot_be_reconfigured_is_survivable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Under pytest's capture, and under contextlib.redirect_stdout, stdout
        # is not a TextIOWrapper. Buffering is then the caller's business — but
        # it must not take the harness down on the way past.
        monkeypatch.setattr("sys.stdout", io.StringIO())
        monkeypatch.setattr("sys.stderr", io.StringIO())
        smoke._use_line_buffered_output()
