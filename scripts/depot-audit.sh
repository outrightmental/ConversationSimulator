#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# depot-audit.sh — Audit a directory for files that must not ship in a
# Steam depot or release artifact.
#
# Usage:
#   ./scripts/depot-audit.sh <depot-dir> [--warn-only] [--help]
#
# Arguments:
#   <depot-dir>    Path to the directory containing the release content to audit.
#
# Options:
#   --warn-only    Print violations but exit 0 (useful for pre-flight checks).
#   --help         Print this help and exit.
#
# Audit categories (all cause exit 1 unless --warn-only):
#
#   [weights]   Large model weight files (.gguf, .safetensors, .bin, .pt, .pth,
#               .ckpt) — compliance rule MD-04.  Players must explicitly download
#               models via the in-app model registry.
#               See publishing/STEAM_DEPOT_CONTENTS.md for the approved binary
#               payload list and docs/model-download-policy.md for download rules.
#
#   [unapproved-binaries]  Serialised model payloads in less common formats that
#               may indicate accidentally bundled weight files:
#               *.pkl / *.pickle > 10 MB (serialised PyTorch / scikit-learn),
#               *.npz / *.npy > 10 MB (NumPy array formats used by some model
#               quantisers), any models/ directory (must never appear in a depot;
#               model files live in ~/.convsim/models/ on the player's machine),
#               *.onnx > 50 MB (large ONNX exports indicate a bundled LLM —
#               small ONNX files used by the TTS/VAD sidecars are < 50 MB).
#
#   [devfiles]  Developer-only artefacts that must not ship in any release:
#               .env, .venv/, __pycache__/, *.py[cod], *.egg-info/, tests/,
#               .git/, .gitignore, pytest config, coverage reports, *.spec
#               (PyInstaller spec — source file, not the built binary).
#
#   [secrets]   Common secret file patterns: *.key, *.pem, *.pfx, *.p12,
#               *_rsa, *_dsa, *_ecdsa, *_ed25519, known_hosts, api_keys.*,
#               credentials.*, steam/config.vdf.
#
#   [fixtures]  Test fixture files that may contain sample PII or generated
#               content: fixtures/, testdata/, *.fixture.*, *_fixture.*.
#
# Exit codes:
#   0  No violations found (or --warn-only).
#   1  One or more violations found.
set -uo pipefail

# ── Parse arguments ────────────────────────────────────────────────────────────

DEPOT_DIR=""
WARN_ONLY=0

for arg in "$@"; do
    case "$arg" in
        --warn-only) WARN_ONLY=1 ;;
        --help|-h)
            sed -n '2,/^set /p' "$0" | grep '^#' | sed 's/^# \?//'
            exit 0
            ;;
        -*)
            echo "Unknown option: $arg" >&2
            exit 1
            ;;
        *)
            DEPOT_DIR="$arg"
            ;;
    esac
done

if [[ -z "$DEPOT_DIR" ]]; then
    echo "Usage: $0 <depot-dir> [--warn-only]" >&2
    echo "Run $0 --help for details." >&2
    exit 1
fi

if [[ ! -d "$DEPOT_DIR" ]]; then
    echo "ERROR: depot directory not found: $DEPOT_DIR" >&2
    exit 1
fi

# ── Helpers ────────────────────────────────────────────────────────────────────

VIOLATIONS=0

violation() {
    local category="$1"
    local file="$2"
    printf "  VIOLATION  [%s]  %s\n" "$category" "$file" >&2
    VIOLATIONS=$((VIOLATIONS + 1))
}

section() {
    echo ""
    echo "── $1 ──"
}

# ── [weights] Model weight files ───────────────────────────────────────────────

section "[weights] Model weight files (compliance rule MD-04)"

while IFS= read -r -d '' f; do
    violation "weights" "$f"
done < <(find "$DEPOT_DIR" -type f \( \
    -name "*.gguf" -o -name "*.safetensors" \
    -o -name "*.pt" -o -name "*.pth" -o -name "*.ckpt" \
\) -print0 2>/dev/null)

# .bin files: only flag ones that look like weight files (> 1 MB and not a
# compiled binary ELF/PE — those are legitimate sidecar executables).
while IFS= read -r -d '' f; do
    size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
    if [[ "$size" -gt 1048576 ]]; then
        # Read the first 4 bytes as hex to detect ELF (7f454c46) or PE (4d5a).
        magic=$(xxd -l 4 -p "$f" 2>/dev/null || od -An -N4 -tx1 "$f" 2>/dev/null | tr -d ' \n')
        if [[ "$magic" != "7f454c46" && "${magic:0:4}" != "4d5a" ]]; then
            violation "weights" "$f"
        fi
    fi
done < <(find "$DEPOT_DIR" -type f -name "*.bin" -print0 2>/dev/null)

# ── [unapproved-binaries] Serialised model payloads ───────────────────────────

section "[unapproved-binaries] Serialised model payloads"

# Pickle files > 10 MB — may be serialised PyTorch or scikit-learn models.
while IFS= read -r -d '' f; do
    size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
    if [[ "$size" -gt 10485760 ]]; then
        violation "unapproved-binaries" "$f"
    fi
done < <(find "$DEPOT_DIR" -type f \( -name "*.pkl" -o -name "*.pickle" \) -print0 2>/dev/null)

# NumPy array files > 10 MB — used by some lightweight model quantisation formats.
while IFS= read -r -d '' f; do
    size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
    if [[ "$size" -gt 10485760 ]]; then
        violation "unapproved-binaries" "$f"
    fi
done < <(find "$DEPOT_DIR" -type f \( -name "*.npz" -o -name "*.npy" \) -print0 2>/dev/null)

# Any models/ subdirectory — model files must never appear in a depot; they live
# in ~/.convsim/models/ on the player's machine after an explicit download.
while IFS= read -r -d '' d; do
    violation "unapproved-binaries" "$d/"
done < <(find "$DEPOT_DIR" -type d -name "models" -print0 2>/dev/null)

# ONNX files > 50 MB — small ONNX files are legitimate sidecar dependencies
# (VAD model, TTS voice files), but large ONNX files indicate a bundled LLM
# export that should not ship in the depot.
while IFS= read -r -d '' f; do
    size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
    if [[ "$size" -gt 52428800 ]]; then
        violation "unapproved-binaries" "$f"
    fi
done < <(find "$DEPOT_DIR" -type f -name "*.onnx" -print0 2>/dev/null)

# ── [devfiles] Developer-only artefacts ───────────────────────────────────────

section "[devfiles] Developer-only artefacts"

while IFS= read -r -d '' f; do
    violation "devfiles" "$f"
done < <(find "$DEPOT_DIR" -type f \( \
    -name ".env" -o -name ".env.*" \
    -o -name "*.pyc" -o -name "*.pyo" -o -name "*.pyd" \
    -o -name "pytest.ini" -o -name "setup.cfg" -o -name "tox.ini" \
    -o -name ".coverage" -o -name "coverage.xml" \
    -o -name "convsim-core.spec" \
\) -print0 2>/dev/null)

# Prohibited directories
while IFS= read -r -d '' d; do
    violation "devfiles" "$d/"
done < <(find "$DEPOT_DIR" -type d \( \
    -name "__pycache__" -o -name ".venv" -o -name "venv" \
    -o -name ".git" -o -name ".pytest_cache" -o -name ".mypy_cache" \
    -o -name "*.egg-info" -o -name "htmlcov" \
\) -print0 2>/dev/null)

# Test directories at any depth
while IFS= read -r -d '' d; do
    violation "devfiles" "$d/"
done < <(find "$DEPOT_DIR" -type d -name "tests" -print0 2>/dev/null)

# ── [secrets] Secret file patterns ────────────────────────────────────────────

section "[secrets] Secret / credential files"

while IFS= read -r -d '' f; do
    violation "secrets" "$f"
done < <(find "$DEPOT_DIR" -type f \( \
    -name "*.key" -o -name "*.pem" -o -name "*.pfx" -o -name "*.p12" \
    -o -name "*_rsa" -o -name "*_dsa" -o -name "*_ecdsa" -o -name "*_ed25519" \
    -o -name "known_hosts" \
    -o -name "api_keys.*" -o -name "credentials.*" \
    -o -name "config.vdf" \
\) -print0 2>/dev/null)

# ── [fixtures] Test fixture files ──────────────────────────────────────────────

section "[fixtures] Test fixture files"

while IFS= read -r -d '' d; do
    violation "fixtures" "$d/"
done < <(find "$DEPOT_DIR" -type d \( \
    -name "fixtures" -o -name "testdata" -o -name "test_data" \
\) -print0 2>/dev/null)

while IFS= read -r -d '' f; do
    violation "fixtures" "$f"
done < <(find "$DEPOT_DIR" -type f \( \
    -name "*.fixture.*" -o -name "*_fixture.*" \
    -o -name "*.testdata.*" \
\) -print0 2>/dev/null)

# ── Summary ────────────────────────────────────────────────────────────────────

echo ""
echo "────────────────────────────────────────────────────────────────"

if [[ "$VIOLATIONS" -eq 0 ]]; then
    echo "PASS  Depot audit passed — no prohibited files detected."
    echo "      Directory: $DEPOT_DIR"
    echo ""
    exit 0
fi

echo "VIOLATIONS  $VIOLATIONS prohibited file(s) found in: $DEPOT_DIR" >&2
echo "" >&2

if [[ "$WARN_ONLY" -eq 1 ]]; then
    echo "  --warn-only is set; exiting 0 despite violations." >&2
    echo ""
    exit 0
fi

exit 1
