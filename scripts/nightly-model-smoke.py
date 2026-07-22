#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Nightly real-model smoke test for latency budget regression.

Downloads the pinned starter model (if not already cached), starts a local
llama-server (llama-cpp-python's OpenAI-compatible server) against it, starts
convsim-core wired to that server, runs a scripted end-to-end session through
convsim-core's REST API, measures full-response latency, and fails if it
exceeds the documented budget multiplied by ``--ci-hardware-factor``.

convsim-core's turn endpoint is synchronous — it returns the completed NPC
turn in a single response rather than streaming ``npc.token`` events (token
streaming is added by the ``apps/api`` gateway, which is not exercised here).
The smoke therefore measures full end-to-end turn latency (which subsumes
time-to-first-token) against the ``FULL_RESPONSE_MS`` budget.

A budget regression is defined as measured_ms > ci_budget_ms * 1.20.

Usage
-----
Download only (called from CI before the model cache is populated)::

    python scripts/nightly-model-smoke.py \\
        --download-only \\
        --model-url <url> \\
        --model-sha256 <hex> \\
        --model-id <id>

Full smoke (model already on disk)::

    python scripts/nightly-model-smoke.py \\
        --model-id qwen3-4b-instruct-q4_k_m \\
        --ci-hardware-factor 6 \\
        --report-path /tmp/smoke-report.json

Exit codes
----------
0  All latency budgets met (within 20 % CI tolerance).
1  One or more budgets exceeded, or the server failed to start / respond.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent

# Documented latency budgets (ms) from packages/shared/src/types/metrics.ts.
# Keep in sync manually; the script is intentionally not importing TS source.
# Only full_response_ms is measurable through convsim-core's synchronous REST
# turn API; TTFT requires token streaming (apps/api gateway), which this smoke
# does not stand up.
BUDGETS_MS = {
    "full_response_ms": 10_000,
}

# Regression tolerance: measured may exceed CI budget by at most this factor.
REGRESSION_TOLERANCE = 1.20

MODELS_DIR = Path.home() / ".convsim" / "models" / "llm"

# Ports for the two local processes started during a smoke run.
LLAMA_SERVER_PORT = 7356  # convsim-core's default CONVSIM_LLAMA_CPP_BASE_URL port
CORE_PORT = 7399

# A simple scripted player turn that any instruct model can answer in <30 tokens.
SMOKE_PLAYER_TURN = "Reply with exactly one sentence: Hello, I am ready."


# ── Download helpers ──────────────────────────────────────────────────────────


def _download_with_progress(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {url[:80]}…")
    req = urllib.request.Request(url, headers={"User-Agent": "convsim-smoke/1.0"})
    with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as f:
        total = int(resp.headers.get("Content-Length", 0)) or None
        downloaded = 0
        chunk = 1 << 20  # 1 MB
        while True:
            buf = resp.read(chunk)
            if not buf:
                break
            f.write(buf)
            downloaded += len(buf)
            if total:
                pct = int(downloaded / total * 100)
                print(f"\r  {pct}% ({downloaded // 1_048_576} / {total // 1_048_576} MB)", end="", flush=True)
    print()


def _verify_sha256(path: Path, expected: str) -> None:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch: expected {expected}, got {actual}")
    print(f"  SHA-256 verified: {actual[:16]}…")


def download_model(url: str, sha256: str, model_id: str) -> Path:
    dest = MODELS_DIR / f"{model_id}.gguf"
    if dest.exists():
        print(f"  Model already on disk: {dest}")
        return dest
    _download_with_progress(url, dest)
    _verify_sha256(dest, sha256)
    return dest


# ── Server helpers ────────────────────────────────────────────────────────────


def _find_model_path(model_id: str) -> Path:
    path = MODELS_DIR / f"{model_id}.gguf"
    if not path.exists():
        raise FileNotFoundError(
            f"Model file not found: {path}\n"
            "Run with --download-only first, or check that the model cache is populated."
        )
    return path


def _start_llama_server(model_path: Path, port: int) -> subprocess.Popen:
    """Start llama-cpp-python's OpenAI-compatible server on the given port.

    convsim-core's ``llama_cpp`` runtime adapter talks to this server over
    ``/v1/chat/completions`` (see services/convsim-core/.../runtime/llama_cpp.py).
    """
    proc = subprocess.Popen(
        [sys.executable, "-m", "llama_cpp.server",
         "--model", str(model_path),
         "--host", "127.0.0.1", "--port", str(port),
         "--n_ctx", "8192"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def _start_core(data_dir: Path, port: int, llama_port: int, llama_timeout_s: float) -> subprocess.Popen:
    """Start convsim-core wired to the local llama-server via env overrides."""
    env = os.environ.copy()
    env.update({
        # Select the real llama.cpp runtime (default is the deterministic fake).
        "CONVSIM_RUNTIME_ID": "llama_cpp",
        # Point the adapter at the llama-server started above.
        "CONVSIM_LLAMA_CPP_BASE_URL": f"http://127.0.0.1:{llama_port}",
        "CONVSIM_LLAMA_CPP_CONTEXT_LENGTH": "8192",
        # The adapter's per-request timeout must outlast the CI ceiling we
        # measure against, or a slow-but-passing turn on the 2-vCPU CPU-only
        # runner is killed by the adapter's 30 s default before we can time it,
        # failing the nightly spuriously instead of reporting the real latency.
        "CONVSIM_LLAMA_CPP_TIMEOUT": str(int(llama_timeout_s)),
        "CONVSIM_DATA_DIR": str(data_dir),
        "CONVSIM_LOG_DIR": str(data_dir / "logs"),
        "CONVSIM_DB_DIR": str(data_dir / "db"),
        "CONVSIM_PACKS_DIR": str(data_dir / "packs"),
        "CONVSIM_PORT": str(port),
        "CONVSIM_HOST": "127.0.0.1",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "convsim_core.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def _wait_for_http(url: str, timeout_s: float, label: str) -> None:
    """Poll ``url`` until it returns any HTTP response, or raise on timeout."""
    deadline = time.monotonic() + timeout_s
    last_err: Optional[Exception] = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except urllib.error.HTTPError:
            # A response (even 4xx) means the server is up and routing.
            return
        except Exception as exc:  # noqa: BLE001 — connection refused while booting
            last_err = exc
            time.sleep(1)
    raise TimeoutError(f"{label} did not become ready within {timeout_s:.0f} s ({last_err})")


# ── Session helpers ───────────────────────────────────────────────────────────


def _post_json(url: str, payload: dict, timeout: float = 30.0) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _get_json(url: str, timeout: float = 30.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def _npc_turn_content(events: list) -> str:
    """Return the NPC utterance from a turn/start response's events, or ''."""
    for ev in events:
        if ev.get("event_type") in ("npc_turn", "npc_opening"):
            return ev.get("payload", {}).get("content", "")
    return ""


# ── Smoke run ─────────────────────────────────────────────────────────────────


def _drain(stream: object, sink: Optional["deque"] = None) -> None:
    """Consume a subprocess pipe in the background to avoid a full-buffer deadlock.

    When ``sink`` (a bounded deque) is given, the most recent lines are retained
    so they can be surfaced if the smoke fails.  The child's stderr is otherwise
    discarded, which makes a server-side 500 undiagnosable from the CI logs — the
    client only ever sees ``HTTPError: 500`` with no server traceback.
    """
    try:
        for raw in stream:  # type: ignore[attr-defined]
            if sink is not None:
                line = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
                sink.append(line.rstrip("\n"))
    except Exception:
        pass


def run_smoke(
    model_id: str,
    ci_hardware_factor: float,
    report_path: Optional[Path],
) -> bool:
    """Run the scripted smoke session and check budgets.  Returns True on pass."""
    model_path = _find_model_path(model_id)
    # The turn must be allowed to run past the CI ceiling before we judge it, so
    # both the adapter timeout and our own POST timeout are derived from the
    # full-response ceiling with headroom rather than a fixed 30 s / 180 s.
    full_ceiling_s = (BUDGETS_MS["full_response_ms"] * ci_hardware_factor * REGRESSION_TOLERANCE) / 1000
    llama_timeout_s = max(180.0, full_ceiling_s + 60.0)
    turn_timeout_s = llama_timeout_s + 30.0
    results: dict = {
        "model_id": model_id,
        "ci_hardware_factor": ci_hardware_factor,
        "budgets_ms": BUDGETS_MS,
        "ci_budgets_ms": {k: v * ci_hardware_factor for k, v in BUDGETS_MS.items()},
        "regression_tolerance": REGRESSION_TOLERANCE,
        "measured_ms": {},
        "verdict": "pending",
        "failures": [],
    }

    with tempfile.TemporaryDirectory(prefix="convsim-smoke-") as tmp:
        data_dir = Path(tmp)
        # Bounded tails of each child's stderr, surfaced only if the smoke fails
        # so a server-side error is diagnosable from the CI logs.
        llama_stderr_tail: deque = deque(maxlen=200)
        core_stderr_tail: deque = deque(maxlen=200)

        print(f"\n[smoke] Starting llama-server on port {LLAMA_SERVER_PORT} with model: {model_path.name}")
        llama_proc = _start_llama_server(model_path, LLAMA_SERVER_PORT)
        threading.Thread(target=_drain, args=(llama_proc.stderr, llama_stderr_tail), daemon=True).start()
        threading.Thread(target=_drain, args=(llama_proc.stdout,), daemon=True).start()

        core_proc: Optional[subprocess.Popen] = None
        try:
            print("[smoke] Waiting for llama-server (model load)…")
            _wait_for_http(
                f"http://127.0.0.1:{LLAMA_SERVER_PORT}/v1/models",
                timeout_s=300.0,
                label="llama-server",
            )
            print("[smoke] llama-server ready.")

            print(f"[smoke] Starting convsim-core on port {CORE_PORT}…")
            core_proc = _start_core(data_dir, CORE_PORT, LLAMA_SERVER_PORT, llama_timeout_s)
            threading.Thread(target=_drain, args=(core_proc.stderr, core_stderr_tail), daemon=True).start()
            threading.Thread(target=_drain, args=(core_proc.stdout,), daemon=True).start()

            _wait_for_http(
                f"http://127.0.0.1:{CORE_PORT}/api/health",
                timeout_s=120.0,
                label="convsim-core",
            )
            base = f"http://127.0.0.1:{CORE_PORT}/api"

            # Sanity-check that the real runtime is wired (not the fake default).
            health = _get_json(f"{base}/health")
            runtime_id = health.get("llm_runtime", {}).get("runtime_id")
            print(f"[smoke] convsim-core ready (runtime_id={runtime_id}).")
            if runtime_id != "llama_cpp":
                raise RuntimeError(
                    f"Expected runtime_id 'llama_cpp' but core reports {runtime_id!r}. "
                    "Check CONVSIM_RUNTIME_ID wiring."
                )

            # Create → start → turn against the built-in behavioral_interview scenario.
            session = _post_json(f"{base}/sessions", {
                "scenario_id": "behavioral_interview",
                "difficulty": "standard",
                "player_role_name": "Smoke Tester",
                "language": "en",
                "input_mode": "text-only",
                "tts_enabled": False,
                "show_state_meters": False,
                "save_transcript": False,
                "seed": 42,
            })
            session_id = session["session_id"]
            print(f"[smoke] Session {session_id} created. Starting session…")
            # /start generates the NPC opening — a real model call, so it needs
            # the same generous timeout as the turn on slow CI hardware.
            _post_json(f"{base}/sessions/{session_id}/start", {}, timeout=turn_timeout_s)
            print("[smoke] NPC opening received. Submitting player turn…")

            # Submit a player turn and time the synchronous end-to-end response.
            t_start = time.monotonic()
            turn = _post_json(
                f"{base}/sessions/{session_id}/turn",
                {"content": SMOKE_PLAYER_TURN},
                timeout=turn_timeout_s,
            )
            full_ms = (time.monotonic() - t_start) * 1000
            npc_text = _npc_turn_content(turn.get("events", []))
            print(f"[smoke] Full response: {full_ms:.0f} ms | NPC said: {npc_text[:80]!r}")
            if not npc_text:
                raise RuntimeError("Turn completed but no npc_turn content was returned")

            results["measured_ms"] = {"full_response_ms": round(full_ms)}

            # Check budgets
            failures = []
            for key, budget_ms in BUDGETS_MS.items():
                measured = results["measured_ms"].get(key)
                if measured is None:
                    continue
                ci_budget = budget_ms * ci_hardware_factor
                ceiling = ci_budget * REGRESSION_TOLERANCE
                status = "PASS" if measured <= ceiling else "FAIL"
                print(
                    f"  {key}: {measured:.0f} ms "
                    f"(CI budget {ci_budget:.0f} ms × {REGRESSION_TOLERANCE} = {ceiling:.0f} ms) "
                    f"→ {status}"
                )
                if status == "FAIL":
                    failures.append(
                        f"{key} = {measured:.0f} ms exceeds CI ceiling {ceiling:.0f} ms "
                        f"(budget {budget_ms} ms × {ci_hardware_factor} × {REGRESSION_TOLERANCE})"
                    )

            results["failures"] = failures
            results["verdict"] = "pass" if not failures else "fail"

        except BaseException as exc:
            # The client-side error (e.g. HTTP 500 from a turn) says nothing about
            # what went wrong inside convsim-core.  Surface the captured stderr
            # tails so the real traceback is visible in the CI logs, then re-raise.
            print(f"\n[smoke] ERROR during run: {exc!r}", file=sys.stderr)
            for label, tail in (("convsim-core", core_stderr_tail), ("llama-server", llama_stderr_tail)):
                if tail:
                    print(f"\n[smoke] ── {label} stderr (last {len(tail)} lines) ──", file=sys.stderr)
                    for line in tail:
                        print(f"  {label[:4]}| {line}", file=sys.stderr)
            raise
        finally:
            for proc in (core_proc, llama_proc):
                if proc is None:
                    continue
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(results, indent=2))
        print(f"\n[smoke] Report written to {report_path}")

    if results["failures"]:
        print("\n[smoke] FAILED — latency budget regression detected:")
        for f in results["failures"]:
            print(f"  ✗ {f}")
        return False

    print(f"\n[smoke] PASSED — all latency budgets met on model {model_id}.")
    return True


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download-only", action="store_true",
                        help="Download and verify the model file, then exit.")
    parser.add_argument("--model-url", default=None,
                        help="Download URL (required for --download-only).")
    parser.add_argument("--model-sha256", default=None,
                        help="Expected SHA-256 hex (required for --download-only).")
    parser.add_argument("--model-id", required=True,
                        help="Registry model ID (e.g. qwen3-4b-instruct-q4_k_m).")
    parser.add_argument("--ci-hardware-factor", type=float, default=1.0,
                        help="Multiplier applied to documented budgets for CI hardware (default 1.0).")
    parser.add_argument("--report-path", default=None,
                        help="Write JSON report to this path.")

    args = parser.parse_args()

    if args.download_only:
        if not args.model_url or not args.model_sha256:
            parser.error("--model-url and --model-sha256 are required with --download-only")
        print(f"[smoke] Downloading model {args.model_id}…")
        download_model(args.model_url, args.model_sha256, args.model_id)
        return 0

    report = Path(args.report_path) if args.report_path else None
    passed = run_smoke(args.model_id, args.ci_hardware_factor, report)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
