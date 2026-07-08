#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# first-run-check.sh — Report system readiness for Conversation Simulator.
#
# Checks: OS version, CPU architecture, RAM, disk space, audio devices,
#         and local port availability (7354-7358).
#
# Usage:   ./scripts/first-run-check.sh
# Exit 0:  all required checks passed (warnings may be present)
# Exit 1:  one or more required checks failed
set -uo pipefail

# ── Status helpers ────────────────────────────────────────────────────────────

ERRORS=0
WARNINGS=0

status_pass() { printf "  PASS  %s\n" "$1"; }
status_warn() { printf "  WARN  %s\n" "$1"; WARNINGS=$((WARNINGS + 1)); }
status_fail() { printf "  FAIL  %s\n" "$1" >&2; ERRORS=$((ERRORS + 1)); }
status_info() { printf "  INFO  %s\n" "$1"; }

# ── OS and CPU architecture ───────────────────────────────────────────────────

check_os_arch() {
    local os arch
    os="$(uname -s)"
    arch="$(uname -m)"

    case "$os" in
        Darwin)
            local ver
            ver="$(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
            status_pass "OS: macOS $ver ($arch)"
            # macOS 12 Monterey is the minimum supported version.
            local major
            major="$(echo "$ver" | cut -d. -f1)"
            if [[ "$major" =~ ^[0-9]+$ ]] && [[ "$major" -lt 12 ]]; then
                status_fail "macOS 12 Monterey or newer required (found $ver)"
            fi
            ;;
        Linux)
            local distro_name
            distro_name="$(grep -oP '(?<=^PRETTY_NAME=").*(?=")' /etc/os-release 2>/dev/null || echo 'Linux')"
            distro_name="${distro_name:-Linux}"
            status_pass "OS: $distro_name ($arch)"
            ;;
        MINGW*|CYGWIN*|MSYS*)
            status_warn "OS: Windows shell environment — run first-run-check.ps1 instead"
            return
            ;;
        *)
            status_fail "OS: $os — unsupported platform"
            return
            ;;
    esac

    case "$arch" in
        x86_64|amd64)
            status_pass "CPU: 64-bit x86 ($arch)"
            ;;
        arm64|aarch64)
            status_pass "CPU: 64-bit ARM ($arch)"
            ;;
        *)
            status_warn "CPU: $arch — may not have a pre-built llama-server binary; build from source if needed"
            ;;
    esac
}

# ── RAM ───────────────────────────────────────────────────────────────────────

check_ram() {
    local ram_gb=0
    local os
    os="$(uname -s)"

    case "$os" in
        Darwin)
            local ram_bytes
            ram_bytes="$(sysctl -n hw.memsize 2>/dev/null || echo 0)"
            ram_bytes="${ram_bytes:-0}"
            ram_gb=$(( ram_bytes / 1073741824 ))
            ;;
        Linux)
            local ram_kb
            ram_kb="$(awk '/MemTotal/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 0)"
            ram_kb="${ram_kb:-0}"
            ram_gb=$(( ram_kb / 1048576 ))
            ;;
    esac

    if [[ "$ram_gb" -ge 16 ]]; then
        status_pass "RAM: ${ram_gb} GB (sufficient for standard-tier models)"
    elif [[ "$ram_gb" -ge 8 ]]; then
        status_warn "RAM: ${ram_gb} GB — minimum met; 16 GB recommended for smooth inference"
    elif [[ "$ram_gb" -gt 0 ]]; then
        status_fail "RAM: ${ram_gb} GB — 8 GB minimum required"
    else
        status_warn "RAM: could not detect available memory"
    fi
}

# ── Disk space ────────────────────────────────────────────────────────────────

check_disk() {
    local disk_avail_kb disk_avail_gb
    disk_avail_kb="$(df -k "$HOME" 2>/dev/null | awk 'NR==2 {print $4; exit}' || echo 0)"
    disk_avail_kb="${disk_avail_kb:-0}"
    disk_avail_gb=$(( disk_avail_kb / 1048576 ))

    if [[ "$disk_avail_gb" -ge 20 ]]; then
        status_pass "Disk: ${disk_avail_gb} GB free in \$HOME (model weights need up to 15 GB)"
    elif [[ "$disk_avail_gb" -ge 5 ]]; then
        status_warn "Disk: ${disk_avail_gb} GB free — 20 GB recommended; starter model needs ~3 GB"
    elif [[ "$disk_avail_gb" -gt 0 ]]; then
        status_fail "Disk: ${disk_avail_gb} GB free — at least 5 GB required for the starter model"
    else
        status_warn "Disk: could not determine available space in \$HOME"
    fi
}

# ── Audio devices — microphone and speaker ────────────────────────────────────

check_audio_macos() {
    local audio_info
    audio_info="$(system_profiler SPAudioDataType 2>/dev/null || true)"

    if echo "$audio_info" | grep -q "Input Channels"; then
        status_pass "Microphone: audio input device detected"
    else
        status_warn "Microphone: no audio input device found — voice input requires a microphone"
    fi

    if echo "$audio_info" | grep -q "Output Channels"; then
        status_pass "Speaker: audio output device detected"
    else
        status_warn "Speaker: no audio output device found — voice output requires speakers or headphones"
    fi
}

check_audio_linux() {
    # Microphone: look for ALSA capture (pcm *c*) entries.
    if grep -q "c$" /proc/asound/pcm 2>/dev/null; then
        status_pass "Microphone: ALSA capture device detected"
    elif command -v arecord &>/dev/null && arecord -l 2>/dev/null | grep -q "card"; then
        status_pass "Microphone: ALSA capture device detected"
    else
        status_warn "Microphone: could not detect audio input — voice input requires a microphone"
    fi

    # Speaker: look for ALSA playback (pcm *p*) entries.
    if grep -q "p$" /proc/asound/pcm 2>/dev/null; then
        status_pass "Speaker: ALSA playback device detected"
    elif command -v aplay &>/dev/null && aplay -l 2>/dev/null | grep -q "card"; then
        status_pass "Speaker: ALSA playback device detected"
    else
        status_warn "Speaker: could not detect audio output — voice output requires speakers or headphones"
    fi
}

check_audio() {
    local os
    os="$(uname -s)"
    case "$os" in
        Darwin) check_audio_macos ;;
        Linux)  check_audio_linux ;;
        *)      status_info "Audio: skipped on $os" ;;
    esac
}

# ── Port availability ─────────────────────────────────────────────────────────
# Ports used by convsim services: 7354 (web UI), 7355 (core), 7356 (LLM),
#   7357 (STT), 7358 (TTS).

check_single_port() {
    local port="$1"
    local label="$2"

    if command -v lsof &>/dev/null; then
        if lsof -ti ":$port" >/dev/null 2>&1; then
            local pid cmd
            pid="$(lsof -ti ":$port" 2>/dev/null | head -1 || true)"
            cmd="$(ps -p "$pid" -o comm= 2>/dev/null || echo 'unknown')"
            status_warn "Port $port ($label): in use by PID $pid ($cmd) — stop it before starting services"
            return
        fi
    elif command -v ss &>/dev/null; then
        if ss -tlnp 2>/dev/null | grep -qE ":${port}[[:space:]]"; then
            status_warn "Port $port ($label): in use — stop the blocking process before starting services"
            return
        fi
    fi
    status_pass "Port $port ($label): free"
}

check_ports() {
    check_single_port 7354 "convsim-ui"
    check_single_port 7355 "convsim-core"
    check_single_port 7356 "llm-runtime"
    check_single_port 7357 "stt-runtime"
    check_single_port 7358 "tts-runtime"
}

# ── Runtime health (optional — developer path only) ───────────────────────────

check_runtimes() {
    status_info "Runtime versions (developer path):"

    if command -v python3 &>/dev/null; then
        local py_ver
        py_ver="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo '?')"
        local py_major py_minor
        py_major="$(echo "$py_ver" | cut -d. -f1)"
        py_minor="$(echo "$py_ver" | cut -d. -f2)"
        if [[ "$py_major" -ge 3 ]] && [[ "$py_minor" -ge 10 ]] 2>/dev/null; then
            status_pass "Python $py_ver (convsim-core requires 3.10+)"
        else
            status_fail "Python $py_ver — 3.10+ required for convsim-core"
        fi
    else
        status_warn "Python: not found — required for the developer install path"
    fi

    if command -v node &>/dev/null; then
        local node_ver node_major
        node_ver="$(node --version 2>/dev/null | sed 's/^v//' || echo '?')"
        node_major="$(echo "$node_ver" | cut -d. -f1)"
        if [[ "$node_major" -ge 18 ]] 2>/dev/null; then
            status_pass "Node.js $node_ver (requires 18+)"
        else
            status_fail "Node.js $node_ver — 18+ required"
        fi
    else
        status_warn "Node.js: not found — required for the developer install path"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────

echo ""
echo "Conversation Simulator — first-run check"
echo "=========================================="
echo ""
echo "OS and CPU:"
check_os_arch
echo ""
echo "Memory:"
check_ram
echo ""
echo "Disk space:"
check_disk
echo ""
echo "Audio:"
check_audio
echo ""
echo "Service ports:"
check_ports
echo ""
check_runtimes
echo ""
echo "────────────────────────────────────────────"
if [[ "$ERRORS" -gt 0 ]]; then
    printf "FAIL  %d required check(s) failed — see FAIL lines above.\n" "$ERRORS" >&2
    echo "" >&2
    echo "Fix the issues above, then run this script again." >&2
    echo ""
    exit 1
elif [[ "$WARNINGS" -gt 0 ]]; then
    printf "WARN  All required checks passed. %d warning(s) noted above.\n" "$WARNINGS"
    echo ""
    echo "The app will run, but some features may be degraded."
    echo "See docs/install.md for system requirements."
    echo ""
else
    echo "PASS  All checks passed. System is ready to run Conversation Simulator."
    echo ""
fi
