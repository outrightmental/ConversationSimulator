#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# check-tauri-versions.sh — verify that each Tauri Rust crate and its npm
# package are locked to the same major.minor release.
#
# `tauri build` refuses to start when they differ ("Found version mismatched
# Tauri packages. Make sure the NPM package and Rust crate versions are on the
# same major/minor releases"). Only the release workflow runs `tauri build`;
# CI's desktop jobs run `cargo check`, which does not look at npm at all. So a
# Cargo.lock that moves the crate without the npm package passes every CI job
# and breaks the release. That is how v0.4.0's first release run failed on all
# three platforms: tauri 2.12.1 in Cargo.lock (committed 2026-10-02) against
# @tauri-apps/api 2.11.1 in pnpm-lock.yaml.
#
# This checks the pairs the Tauri CLI checks, read from the two lockfiles:
#   tauri                   <-> @tauri-apps/api
#   tauri-plugin-<name>     <-> @tauri-apps/plugin-<name>   (when both are locked)
# for the apps/desktop importer, which is the package `tauri build` runs in.
#
# Usage:
#   bash scripts/check-tauri-versions.sh
#
# Exit codes:
#   0 — every pair matches
#   1 — a pair differs, or a lockfile could not be read
#
# CARGO_LOCK and PNPM_LOCK override the lockfile paths (for testing).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CARGO_LOCK="${CARGO_LOCK:-$ROOT/apps/desktop/src-tauri/Cargo.lock}"
PNPM_LOCK="${PNPM_LOCK:-$ROOT/pnpm-lock.yaml}"
IMPORTER="apps/desktop"

for f in "$CARGO_LOCK" "$PNPM_LOCK"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: lockfile not found: $f" >&2
    exit 1
  fi
done

# Every locked version of a crate, one per line (Cargo.lock can hold more than
# one version of the same crate).
crate_versions() {
  awk -v name="$1" '
    /^\[\[package\]\]/ { in_pkg = 0; next }
    $0 == "name = \"" name "\"" { in_pkg = 1; next }
    in_pkg && /^version = / { v = $3; gsub(/"/, "", v); print v; in_pkg = 0 }
  ' "$CARGO_LOCK"
}

# The version the apps/desktop importer locks for an npm package, without the
# peer-dependency suffix pnpm appends ("2.12.4(react@18.3.1)" -> "2.12.4").
npm_version() {
  awk -v importer="  $IMPORTER:" -v pkg="      '$1':" '
    $0 == importer { in_imp = 1; next }
    in_imp && /^(  )?[^ ]/ { in_imp = 0 }
    in_imp && $0 == pkg { want = 1; next }
    want && /^        version: / {
      v = $2; sub(/\(.*/, "", v); print v; exit
    }
    want && /^      [^ ]/ { exit }
  ' "$PNPM_LOCK"
}

# Every @tauri-apps/plugin-* package the apps/desktop importer locks.
npm_plugins() {
  awk -v importer="  $IMPORTER:" -v q="'" '
    $0 == importer { in_imp = 1; next }
    in_imp && /^(  )?[^ ]/ { in_imp = 0 }
    in_imp && /^      .@tauri-apps\/plugin-[^:]*.:$/ {
      p = $1; gsub(q, "", p); sub(/:$/, "", p); print p
    }
  ' "$PNPM_LOCK"
}

minor() { cut -d. -f1,2 <<<"$1"; }

fail=0

check_pair() {
  local crate="$1" pkg="$2" required="$3"
  local npm crates
  npm="$(npm_version "$pkg")"
  crates="$(crate_versions "$crate")"

  if [[ -z "$npm" || -z "$crates" ]]; then
    if [[ "$required" == "required" ]]; then
      echo "ERROR: could not read the locked version of ${crate:+$crate }and $pkg" >&2
      echo "       (Cargo.lock: ${crates:-not found}; pnpm-lock.yaml $IMPORTER: ${npm:-not found})." >&2
      echo "       If a lockfile's layout changed, update this script; do not drop the check." >&2
      fail=1
    fi
    return
  fi

  local v
  while IFS= read -r v; do
    if [[ "$(minor "$v")" == "$(minor "$npm")" ]]; then
      printf '  OK        %-34s %-10s %-34s %s\n' "$crate" "$v" "$pkg" "$npm"
    else
      printf '  MISMATCH  %-34s %-10s %-34s %s\n' "$crate" "$v" "$pkg" "$npm"
      fail=1
    fi
  done <<<"$crates"
}

echo "Tauri crate <-> npm package (same major.minor required by tauri build):"
check_pair tauri @tauri-apps/api required
while IFS= read -r plugin; do
  [[ -n "$plugin" ]] || continue
  check_pair "tauri-plugin-${plugin#@tauri-apps/plugin-}" "$plugin" optional
done < <(npm_plugins)

if [[ "$fail" -ne 0 ]]; then
  cat >&2 <<'EOF'

`tauri build` refuses to run with a pair on different major.minor releases, so
the release workflow would fail at "Build Tauri desktop" on every platform.
Move the npm package to the crate's minor, e.g.
  pnpm --filter @convsim/desktop add @tauri-apps/api@^<crate major.minor>
or move the crate to the npm package's minor, e.g.
  (cd apps/desktop/src-tauri && cargo update -p tauri --precise <version>)
and commit both lockfiles.
EOF
  exit 1
fi
