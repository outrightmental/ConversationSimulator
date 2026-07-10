#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Nightly real-model smoke test for latency budget regression.

Downloads the pinned starter model (if not already cached), spins up the
convsim-core server against it, runs a scripted two-turn session, measures
TTFT and full-response latency, and fails if any metric exceeds the
documented budget multiplied by ``--ci-hardware-factor``.

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
import urllib.request
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent

# Documented latency budgets (ms) from packages/shared/src/types/metrics.ts.
# Keep in sync manually; the script is intentionally not importing TS source.
BUDGETS_MS = {
    "ttft_ms": 2_500,
    "full_response_ms": 10_000,
}

# Regression tolerance: measured may exceed CI budget by at most this factor.
REGRESSION_TOLERANCE = 1.20

MODELS_DIR = Path.home() / ".convsim" / "models" / "llm"

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


def _start_server(model_path: Path, data_dir: Path, port: int = 7399) -> subprocess.Popen:
    """Start convsim-core with the given model via environment overrides."""
    env = os.environ.copy()
    env.update({
        "CONVSIM_LLAMA_CPP_MODEL_PATH": str(model_path),
        "CONVSIM_RUNTIME": "llama_cpp",
        "CONVSIM_DATA_DIR": str(data_dir),
        "CONVSIM_LOG_DIR": str(data_dir / "logs"),
        "CONVSIM_DB_DIR": str(data_dir / "db"),
        "CONVSIM_PACKS_DIR": str(data_dir / "packs"),
        "CONVSIM_PORT": str(port),
        "CONVSIM_HOST": "127.0.0.1",
        # Suppress verbose llama.cpp output
        "LLAMA_LOG_LEVEL": "ERROR",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "convsim_core.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def _wait_for_server(port: int, timeout_s: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2):
                return
        except Exception:
            time.sleep(1)
    raise TimeoutError(f"Server did not become ready within {timeout_s:.0f} s")


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


def _read_sse_until_final(
    url: str,
    timeout_s: float = 120.0,
) -> tuple[float, float]:
    """
    Open an SSE stream and return (ttft_ms, full_response_ms).

    The server streams ``npc.token`` events followed by a ``npc.final`` event.
    """
    req = urllib.request.Request(url, method="GET")
    ttft_ms: Optional[float] = None
    t_start = time.monotonic()

    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        for raw_line in resp:
            line = raw_line.decode(errors="replace").rstrip("\n\r")
            if not line.startswith("data:"):
                continue
            payload_str = line[5:].strip()
            if not payload_str:
                continue
            try:
                event = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type", "")
            elapsed = (time.monotonic() - t_start) * 1000
            if event_type == "npc.token" and ttft_ms is None:
                ttft_ms = elapsed
            if event_type == "npc.final":
                full_ms = elapsed
                return (ttft_ms if ttft_ms is not None else full_ms, full_ms)

    raise RuntimeError("SSE stream ended without npc.final event")


# ── Smoke run ─────────────────────────────────────────────────────────────────


def run_smoke(
    model_id: str,
    ci_hardware_factor: float,
    report_path: Optional[Path],
) -> bool:
    """Run the scripted smoke session and check budgets.  Returns True on pass."""
    model_path = _find_model_path(model_id)
    port = 7399
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
        print(f"\n[smoke] Starting convsim-core on port {port} with model: {model_path.name}")
        proc = _start_server(model_path, data_dir, port=port)

        # Drain stderr in background to avoid pipe deadlock
        def _drain(stream: object) -> None:
            try:
                for _ in stream:  # type: ignore[attr-defined]
                    pass
            except Exception:
                pass

        threading.Thread(target=_drain, args=(proc.stderr,), daemon=True).start()

        try:
            print("[smoke] Waiting for server…")
            _wait_for_server(port, timeout_s=120.0)
            print("[smoke] Server ready.")

            # Start session with the built-in behavioral_interview scenario
            base = f"http://127.0.0.1:{port}/api"
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
            print(f"[smoke] Session {session_id} created. Waiting for NPC opening…")

            # Wait for the NPC opening via SSE
            open_url = f"{base}/sessions/{session_id}/stream"
            _read_sse_until_final(open_url, timeout_s=120.0)
            print("[smoke] NPC opening received. Submitting player turn…")

            # Submit a player turn and measure TTFT + full response
            _post_json(f"{base}/sessions/{session_id}/turn", {
                "content": SMOKE_PLAYER_TURN,
                "input_mode": "text-only",
            })
            ttft_ms, full_ms = _read_sse_until_final(
                f"{base}/sessions/{session_id}/stream",
                timeout_s=120.0,
            )
            print(f"[smoke] TTFT: {ttft_ms:.0f} ms | Full response: {full_ms:.0f} ms")

            results["measured_ms"] = {
                "ttft_ms": round(ttft_ms),
                "full_response_ms": round(full_ms),
            }

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

        finally:
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
