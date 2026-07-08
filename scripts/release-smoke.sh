#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# release-smoke.sh — Cross-platform release smoke runner (bash / macOS / Linux).
#
# Runs the automated CI subset by default. Pass --full to include subsystems
# that require running services and manual confirmation.
#
# Usage:
#   ./scripts/release-smoke.sh           # CI subset (no model downloads)
#   ./scripts/release-smoke.sh --full    # Full release smoke (services must be running)
#   ./scripts/release-smoke.sh --help
#
# Subsystem labels in output:
#   [setup]        monorepo paths and developer scripts
#   [health]       backend /api/health endpoint
#   [web]          web frontend build and reachability
#   [model-mgr]    model manager in fake-runtime mode (no downloads)
#   [scenario-lib] scenario library API
#   [text-session] create a session and complete one turn
#   [debrief]      debrief report generation
#   [pack-valid]   official pack schema validation
#   [voice]        voice fallback (TTS-disabled path)
#   [offline]      no outbound network calls during a scripted play session
#
# Exit 0: all required checks passed.
# Exit 1: one or more required checks failed; see FAIL lines and artifact dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────

MODE="ci"        # ci | full
CORE_URL="${CONVSIM_CORE_URL:-http://127.0.0.1:7355}"

# Artifact directory — logs and snapshots captured here on failure.
ARTIFACT_DIR="${CONVSIM_SMOKE_ARTIFACT_DIR:-${TMPDIR:-/tmp}/convsim-release-smoke-$$}"

# ── CLI ───────────────────────────────────────────────────────────────────────

usage() {
    grep '^#' "$0" | grep -v '!/usr/bin' | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --full)  MODE="full";  shift ;;
        --ci)    MODE="ci";    shift ;;
        --help|-h) usage ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ── Status tracking ───────────────────────────────────────────────────────────

ERRORS=0
SKIPPED=0
PASSED=0
_ARTIFACTS_WRITTEN=0

pass()  { printf "  PASS  [%s] %s\n" "$1" "$2"; PASSED=$((PASSED + 1)); }
fail()  { printf "  FAIL  [%s] %s\n" "$1" "$2" >&2; ERRORS=$((ERRORS + 1)); }
skip()  { printf "  SKIP  [%s] %s\n" "$1" "$2"; SKIPPED=$((SKIPPED + 1)); }
info()  { printf "  INFO  [%s] %s\n" "$1" "$2"; }
label() { echo ""; echo "── $1 ──"; }

# ── Artifact capture ──────────────────────────────────────────────────────────

init_artifacts() {
    mkdir -p "$ARTIFACT_DIR"
    info "meta" "Artifact directory: $ARTIFACT_DIR"
    printf "platform: %s\narch: %s\nmode: %s\ndate: %s\n" \
        "$(uname -s)" "$(uname -m)" "$MODE" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
        > "$ARTIFACT_DIR/smoke-meta.txt"
}

capture_backend_logs() {
    local log_dir="${CONVSIM_LOG_DIR:-$HOME/.convsim/logs}"
    if [[ -d "$log_dir" ]]; then
        cp -r "$log_dir" "$ARTIFACT_DIR/backend-logs" 2>/dev/null || true
        _ARTIFACTS_WRITTEN=1
    fi
}

on_exit() {
    local rc=$?
    if [[ "$ERRORS" -gt 0 && "$_ARTIFACTS_WRITTEN" -eq 0 ]]; then
        capture_backend_logs
    fi
    if [[ "$_ARTIFACTS_WRITTEN" -eq 1 ]]; then
        echo ""
        echo "  Artifacts saved to: $ARTIFACT_DIR"
    fi
    exit "$rc"
}
trap on_exit EXIT

# ── [setup] monorepo structure ────────────────────────────────────────────────

smoke_setup() {
    label "[setup] Monorepo structure and developer scripts"

    local missing=0
    local required_dirs=(
        apps packages services runtimes packs schemas model-registry docs scripts
        apps/web apps/desktop
        packages/ui packages/scenario-schema packages/shared-types
        services/convsim-core
        runtimes/llama_cpp runtimes/whisper_cpp
        packs/official
        packs/official/job-interview-basic
        packs/official/everyday-negotiation
        packs/official/language-cafe
        packs/official/difficult-conversations
    )
    local required_files=(
        README.md LICENSE NOTICE package.json
        scripts/setup.sh scripts/setup.ps1
        scripts/dev.sh scripts/dev.ps1
        scripts/dev-desktop.sh scripts/dev-desktop.ps1
        scripts/first-run-check.sh scripts/first-run-check.ps1
        scripts/smoke-check.sh scripts/smoke-check.ps1
        scripts/release-smoke.sh scripts/release-smoke.ps1
        .github/workflows/ci.yml .github/workflows/release.yml
        .github/workflows/release-smoke.yml
        docs/release-checklist.md
        docs/platform-notes.md docs/release-notes-template.md
        docs/install.md docs/voice-smoke-tests.md
        services/convsim-core/pyproject.toml
        apps/web/package.json apps/desktop/package.json
    )

    for d in "${required_dirs[@]}"; do
        if [[ ! -d "$REPO_ROOT/$d" ]]; then
            fail "setup" "Missing directory: $d"
            missing=$((missing + 1))
        fi
    done

    for f in "${required_files[@]}"; do
        if [[ ! -f "$REPO_ROOT/$f" ]]; then
            fail "setup" "Missing file: $f"
            missing=$((missing + 1))
        fi
    done

    if [[ "$missing" -eq 0 ]]; then
        pass "setup" "All expected monorepo paths present"
    fi
}

# ── [pack-valid] Pack schema validation ───────────────────────────────────────

smoke_pack_validation() {
    label "[pack-valid] Official pack schema validation"

    local schema_test="$REPO_ROOT/packages/scenario-schema/tests/validate-packs.js"
    if [[ ! -f "$schema_test" ]]; then
        skip "pack-valid" "validate-packs.js not found — skipping (run pnpm install first)"
        return
    fi

    if ! command -v node &>/dev/null; then
        skip "pack-valid" "node not found — skipping"
        return
    fi

    local node_modules="$REPO_ROOT/node_modules"
    if [[ ! -d "$node_modules" ]]; then
        skip "pack-valid" "node_modules not installed — run pnpm install first"
        return
    fi

    local out
    out="$(node "$schema_test" "$REPO_ROOT/packs/official" 2>&1)" || {
        fail "pack-valid" "Pack schema validation failed"
        echo "$out" >> "$ARTIFACT_DIR/pack-valid-error.txt"
        _ARTIFACTS_WRITTEN=1
        return
    }
    pass "pack-valid" "Official packs pass schema validation"
}

# ── [voice] Voice fallback smoke (TTS-disabled path) ─────────────────────────

smoke_voice_fallback() {
    label "[voice] Voice fallback (TTS-disabled path)"

    local test_file="$REPO_ROOT/services/convsim-core/tests/test_voice_smoke.py"
    if [[ ! -f "$test_file" ]]; then
        skip "voice" "test_voice_smoke.py not found"
        return
    fi

    if ! command -v python3 &>/dev/null; then
        skip "voice" "python3 not found"
        return
    fi

    local venv="$REPO_ROOT/services/convsim-core/.venv"
    local pytest_cmd
    if [[ -f "$venv/bin/pytest" ]]; then
        pytest_cmd="$venv/bin/pytest"
    elif command -v pytest &>/dev/null; then
        pytest_cmd="pytest"
    else
        skip "voice" "pytest not found — run setup.sh first"
        return
    fi

    # Run only the text-fallback tests; they exercise the TTS-disabled path
    # without requiring whisper-cli or a Kokoro server.
    local out
    out="$(cd "$REPO_ROOT/services/convsim-core" && \
           "$pytest_cmd" tests/test_voice_smoke.py -v -k "fallback" 2>&1)" || {
        fail "voice" "Voice fallback tests failed (TTS-disabled path)"
        echo "$out" >> "$ARTIFACT_DIR/voice-fallback-error.txt"
        _ARTIFACTS_WRITTEN=1
        capture_backend_logs
        return
    }
    pass "voice" "Voice unavailable fallback tests passed (no TTS events when tts_enabled=False)"
}

# ── [health] Backend health check ─────────────────────────────────────────────

smoke_backend_health() {
    label "[health] Backend /api/health"

    if [[ "$MODE" == "ci" ]]; then
        # In CI mode, run health unit tests rather than hitting a live server.
        local test_file="$REPO_ROOT/services/convsim-core/tests/test_health.py"
        if [[ ! -f "$test_file" ]]; then
            skip "health" "test_health.py not found"
            return
        fi

        local venv="$REPO_ROOT/services/convsim-core/.venv"
        local pytest_cmd
        if [[ -f "$venv/bin/pytest" ]]; then
            pytest_cmd="$venv/bin/pytest"
        elif command -v pytest &>/dev/null; then
            pytest_cmd="pytest"
        else
            skip "health" "pytest not found — run setup.sh first"
            return
        fi

        local out
        out="$(cd "$REPO_ROOT/services/convsim-core" && \
               "$pytest_cmd" tests/test_health.py tests/test_fake_runtime.py -v 2>&1)" || {
            fail "health" "Backend health unit tests failed"
            echo "$out" >> "$ARTIFACT_DIR/health-error.txt"
            _ARTIFACTS_WRITTEN=1
            return
        }
        pass "health" "Backend health unit tests passed (fake runtime)"
        return
    fi

    # Full mode: hit the live server.
    if ! command -v curl &>/dev/null; then
        skip "health" "curl not found"
        return
    fi

    local resp http_code body
    resp="$(curl -sf --max-time 5 -w '\n%{http_code}' "$CORE_URL/api/health" 2>&1)" || {
        fail "health" "GET $CORE_URL/api/health failed — is convsim-core running?"
        return
    }
    # curl -w appends "\n<code>"; split on the final newline. Use parameter
    # expansion (not `head -n -1`, which BSD/macOS head does not support).
    http_code="${resp##*$'\n'}"
    body="${resp%$'\n'*}"

    if [[ "$http_code" != "200" ]]; then
        fail "health" "GET /api/health returned HTTP $http_code (expected 200)"
        echo "$body" >> "$ARTIFACT_DIR/health-error.txt"
        _ARTIFACTS_WRITTEN=1
        return
    fi

    local status runtime_status
    status="$(echo "$body" | python3 -c 'import sys,json; print(json.load(sys.stdin)["status"])' 2>/dev/null || echo 'unknown')"
    runtime_status="$(echo "$body" | python3 -c 'import sys,json; print(json.load(sys.stdin)["runtime"]["status"])' 2>/dev/null || echo 'unknown')"

    if [[ "$status" != "ok" ]]; then
        fail "health" "/api/health status=$status (expected ok)"
        return
    fi
    pass "health" "/api/health status=ok runtime=$runtime_status"
}

# ── [model-mgr] Model manager (fake mode) ─────────────────────────────────────

smoke_model_manager() {
    label "[model-mgr] Model manager (fake runtime, no downloads)"

    if [[ "$MODE" == "ci" ]]; then
        local test_file="$REPO_ROOT/services/convsim-core/tests/test_model_manager.py"
        if [[ ! -f "$test_file" ]]; then
            skip "model-mgr" "test_model_manager.py not found"
            return
        fi

        local venv="$REPO_ROOT/services/convsim-core/.venv"
        local pytest_cmd
        if [[ -f "$venv/bin/pytest" ]]; then
            pytest_cmd="$venv/bin/pytest"
        elif command -v pytest &>/dev/null; then
            pytest_cmd="pytest"
        else
            skip "model-mgr" "pytest not found"
            return
        fi

        local out
        out="$(cd "$REPO_ROOT/services/convsim-core" && \
               "$pytest_cmd" tests/test_model_manager.py tests/test_model_registry.py -v 2>&1)" || {
            fail "model-mgr" "Model manager unit tests failed"
            echo "$out" >> "$ARTIFACT_DIR/model-mgr-error.txt"
            _ARTIFACTS_WRITTEN=1
            return
        }
        pass "model-mgr" "Model manager unit tests passed (fake runtime, no downloads)"
        return
    fi

    # Full mode: exercise the model list endpoint.
    if ! command -v curl &>/dev/null; then
        skip "model-mgr" "curl not found"
        return
    fi

    local resp http_code
    resp="$(curl -sf --max-time 5 -w '\n%{http_code}' "$CORE_URL/api/models" 2>&1)" || {
        fail "model-mgr" "GET $CORE_URL/api/models failed"
        return
    }
    http_code="$(echo "$resp" | tail -1)"
    if [[ "$http_code" != "200" ]]; then
        fail "model-mgr" "GET /api/models returned HTTP $http_code"
        return
    fi
    pass "model-mgr" "Model list endpoint returned HTTP 200"
}

# ── [scenario-lib] Scenario library ───────────────────────────────────────────

smoke_scenario_library() {
    label "[scenario-lib] Scenario library API"

    if [[ "$MODE" == "ci" ]]; then
        local test_file="$REPO_ROOT/services/convsim-core/tests/test_scenarios_api.py"
        if [[ ! -f "$test_file" ]]; then
            skip "scenario-lib" "test_scenarios_api.py not found"
            return
        fi

        local venv="$REPO_ROOT/services/convsim-core/.venv"
        local pytest_cmd
        if [[ -f "$venv/bin/pytest" ]]; then
            pytest_cmd="$venv/bin/pytest"
        elif command -v pytest &>/dev/null; then
            pytest_cmd="pytest"
        else
            skip "scenario-lib" "pytest not found"
            return
        fi

        local out
        out="$(cd "$REPO_ROOT/services/convsim-core" && \
               "$pytest_cmd" tests/test_scenarios_api.py -v 2>&1)" || {
            fail "scenario-lib" "Scenario library API tests failed"
            echo "$out" >> "$ARTIFACT_DIR/scenario-lib-error.txt"
            _ARTIFACTS_WRITTEN=1
            return
        }
        pass "scenario-lib" "Scenario library API tests passed"
        return
    fi

    # Full mode: query live endpoint.
    if ! command -v curl &>/dev/null; then
        skip "scenario-lib" "curl not found"
        return
    fi

    local resp http_code
    resp="$(curl -sf --max-time 5 -w '\n%{http_code}' "$CORE_URL/api/scenarios" 2>&1)" || {
        fail "scenario-lib" "GET $CORE_URL/api/scenarios failed"
        return
    }
    http_code="$(echo "$resp" | tail -1)"
    if [[ "$http_code" != "200" ]]; then
        fail "scenario-lib" "GET /api/scenarios returned HTTP $http_code"
        return
    fi
    pass "scenario-lib" "Scenario library endpoint returned HTTP 200"
}

# ── [text-session] Text session (create + one turn) ───────────────────────────

smoke_text_session() {
    label "[text-session] Text session (create session + one turn)"

    if [[ "$MODE" == "ci" ]]; then
        local test_file="$REPO_ROOT/services/convsim-core/tests/test_session_state.py"
        if [[ ! -f "$test_file" ]]; then
            skip "text-session" "test_session_state.py not found"
            return
        fi

        local venv="$REPO_ROOT/services/convsim-core/.venv"
        local pytest_cmd
        if [[ -f "$venv/bin/pytest" ]]; then
            pytest_cmd="$venv/bin/pytest"
        elif command -v pytest &>/dev/null; then
            pytest_cmd="pytest"
        else
            skip "text-session" "pytest not found"
            return
        fi

        local out
        out="$(cd "$REPO_ROOT/services/convsim-core" && \
               "$pytest_cmd" tests/test_session_state.py tests/test_turn_pipeline.py -v 2>&1)" || {
            fail "text-session" "Text session unit tests failed"
            echo "$out" >> "$ARTIFACT_DIR/text-session-error.txt"
            _ARTIFACTS_WRITTEN=1
            return
        }
        pass "text-session" "Text session unit tests passed (fake runtime)"
        return
    fi

    # Full mode: end-to-end session via live API.
    if ! command -v curl &>/dev/null; then
        skip "text-session" "curl not found"
        return
    fi

    info "text-session" "Creating session via $CORE_URL/api/sessions"
    local create_resp http_code session_id
    create_resp="$(curl -sf --max-time 10 -w '\n%{http_code}' \
        -X POST "$CORE_URL/api/sessions" \
        -H 'Content-Type: application/json' \
        -d '{"scenario_id":"job-interview-basic/behavioral_interview","tts_enabled":false}' \
        2>&1)" || {
        fail "text-session" "POST /api/sessions failed"
        return
    }
    http_code="${create_resp##*$'\n'}"
    local body
    body="${create_resp%$'\n'*}"
    if [[ "$http_code" != "201" ]]; then
        fail "text-session" "POST /api/sessions returned HTTP $http_code (expected 201)"
        echo "$body" >> "$ARTIFACT_DIR/text-session-error.txt"
        _ARTIFACTS_WRITTEN=1
        return
    fi

    session_id="$(echo "$body" | python3 -c 'import sys,json; print(json.load(sys.stdin)["session_id"])' 2>/dev/null || echo '')"
    if [[ -z "$session_id" ]]; then
        fail "text-session" "session_id missing from create response"
        return
    fi
    info "text-session" "Session created: $session_id"

    # Submit one player turn.
    local turn_resp turn_code
    turn_resp="$(curl -sf --max-time 30 -w '\n%{http_code}' \
        -X POST "$CORE_URL/api/sessions/$session_id/turns" \
        -H 'Content-Type: application/json' \
        -d '{"player_text":"Hello, I am ready to start."}' \
        2>&1)" || {
        fail "text-session" "POST /api/sessions/$session_id/turns failed"
        return
    }
    turn_code="${turn_resp##*$'\n'}"
    if [[ "$turn_code" != "200" ]]; then
        fail "text-session" "POST /api/sessions/$session_id/turns returned HTTP $turn_code"
        printf '%s\n' "${turn_resp%$'\n'*}" >> "$ARTIFACT_DIR/text-session-error.txt"
        _ARTIFACTS_WRITTEN=1
        return
    fi
    pass "text-session" "Session created and one turn completed (session_id=$session_id)"
}

# ── [debrief] Debrief report ──────────────────────────────────────────────────

smoke_debrief() {
    label "[debrief] Debrief report generation"

    if [[ "$MODE" == "ci" ]]; then
        local test_file="$REPO_ROOT/services/convsim-core/tests/test_debrief_engine.py"
        if [[ ! -f "$test_file" ]]; then
            skip "debrief" "test_debrief_engine.py not found"
            return
        fi

        local venv="$REPO_ROOT/services/convsim-core/.venv"
        local pytest_cmd
        if [[ -f "$venv/bin/pytest" ]]; then
            pytest_cmd="$venv/bin/pytest"
        elif command -v pytest &>/dev/null; then
            pytest_cmd="pytest"
        else
            skip "debrief" "pytest not found"
            return
        fi

        local out
        out="$(cd "$REPO_ROOT/services/convsim-core" && \
               "$pytest_cmd" tests/test_debrief_engine.py -v 2>&1)" || {
            fail "debrief" "Debrief engine unit tests failed"
            echo "$out" >> "$ARTIFACT_DIR/debrief-error.txt"
            _ARTIFACTS_WRITTEN=1
            return
        }
        pass "debrief" "Debrief engine unit tests passed"
        return
    fi

    skip "debrief" "Full debrief smoke requires an active session — run manually per release-checklist.md"
}

# ── [offline] Offline smoke ───────────────────────────────────────────────────

smoke_offline() {
    label "[offline] Offline smoke (no outbound connections during play)"

    if [[ "$MODE" == "ci" ]]; then
        local test_file="$REPO_ROOT/services/convsim-core/tests/test_network_policy.py"
        if [[ ! -f "$test_file" ]]; then
            skip "offline" "test_network_policy.py not found"
            return
        fi

        local venv="$REPO_ROOT/services/convsim-core/.venv"
        local pytest_cmd
        if [[ -f "$venv/bin/pytest" ]]; then
            pytest_cmd="$venv/bin/pytest"
        elif command -v pytest &>/dev/null; then
            pytest_cmd="pytest"
        else
            skip "offline" "pytest not found"
            return
        fi

        local out
        out="$(cd "$REPO_ROOT/services/convsim-core" && \
               "$pytest_cmd" tests/test_network_policy.py -v 2>&1)" || {
            fail "offline" "Network policy tests failed — backend may attempt outbound connections"
            echo "$out" >> "$ARTIFACT_DIR/offline-error.txt"
            _ARTIFACTS_WRITTEN=1
            return
        }
        pass "offline" "Network policy tests passed — no outbound calls during fake-runtime play"
        return
    fi

    # Full mode: use the convsim CLI offline-smoke-test if available.
    local cli_bin="$REPO_ROOT/packages/convsim-cli/dist/index.js"
    if [[ -f "$cli_bin" ]]; then
        info "offline" "Running: node $cli_bin offline-smoke-test packs/official/job-interview-basic"
        local out rc=0
        out="$(node "$cli_bin" offline-smoke-test "$REPO_ROOT/packs/official/job-interview-basic" 2>&1)" || rc=$?
        if [[ "$rc" -ne 0 ]]; then
            fail "offline" "CLI offline-smoke-test exited $rc"
            echo "$out" >> "$ARTIFACT_DIR/offline-error.txt"
            _ARTIFACTS_WRITTEN=1
            capture_backend_logs
        else
            pass "offline" "CLI offline-smoke-test passed for job-interview-basic"
        fi
    else
        skip "offline" "CLI not built — run: pnpm --filter @convsim/cli build then re-run with --full"
    fi
}

# ── [web] Web frontend build and reachability ─────────────────────────────────

smoke_web() {
    label "[web] Web frontend typecheck"

    if ! command -v node &>/dev/null; then
        skip "web" "node not found"
        return
    fi

    local node_modules="$REPO_ROOT/node_modules"
    if [[ ! -d "$node_modules" ]]; then
        skip "web" "node_modules not installed — run pnpm install first"
        return
    fi

    local pkg_json="$REPO_ROOT/apps/web/package.json"
    if [[ ! -f "$pkg_json" ]]; then
        fail "web" "apps/web/package.json not found"
        return
    fi

    if ! command -v pnpm &>/dev/null; then
        skip "web" "pnpm not found"
        return
    fi

    local out
    out="$(cd "$REPO_ROOT" && pnpm --filter @convsim/web typecheck 2>&1)" || {
        fail "web" "Web frontend typecheck failed"
        echo "$out" >> "$ARTIFACT_DIR/web-error.txt"
        _ARTIFACTS_WRITTEN=1
        return
    }
    pass "web" "Web frontend typecheck passed"

    if [[ "$MODE" == "full" ]]; then
        info "web" "Full mode: confirm http://127.0.0.1:7354 loads in browser (manual step)"
    fi
}

# ── Summary ───────────────────────────────────────────────────────────────────

print_summary() {
    local platform arch
    platform="$(uname -s)"
    arch="$(uname -m)"

    echo ""
    echo "────────────────────────────────────────────────────────────────"
    printf "Platform : %s / %s   Mode : %s\n" "$platform" "$arch" "$MODE"
    printf "Passed   : %d   Failed : %d   Skipped : %d\n" "$PASSED" "$ERRORS" "$SKIPPED"
    echo "────────────────────────────────────────────────────────────────"

    if [[ "$ERRORS" -gt 0 ]]; then
        printf "FAIL  %d subsystem(s) failed — see FAIL lines above.\n" "$ERRORS" >&2
        echo "" >&2
        if [[ "$_ARTIFACTS_WRITTEN" -eq 1 ]]; then
            echo "  Error details saved to: $ARTIFACT_DIR" >&2
        fi
        echo "" >&2
        exit 1
    fi

    if [[ "$MODE" == "ci" ]]; then
        echo "PASS  CI smoke subset passed."
        echo ""
        echo "      Run with --full against a live stack for the complete release gate."
        echo "      See docs/release-checklist.md for manual steps."
    else
        echo "PASS  Full release smoke passed."
    fi
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    echo ""
    echo "Conversation Simulator — release smoke"
    echo "========================================"
    echo "Mode: $MODE   Platform: $(uname -s)/$(uname -m)"
    echo ""

    init_artifacts

    smoke_setup
    smoke_pack_validation
    smoke_voice_fallback
    smoke_backend_health
    smoke_model_manager
    smoke_scenario_library
    smoke_text_session
    smoke_debrief
    smoke_offline
    smoke_web

    print_summary
}

main "$@"
