#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# check-docs-freshness.sh — verify that every docs-site page with a
# verified_against field is current for the release's minor version.
#
# Freshness is compared at MINOR-version granularity (major.minor): a page
# stamped v0.2.2 stays fresh for any v0.2.x release, and only goes stale when
# the released minor version changes (e.g. v0.3.0). This matches the drift
# contract in issue #386 — patch/hotfix releases are not blocked by unrelated
# doc staleness, but a minor bump forces every UI-referencing page to be
# re-verified against the new UI.
#
# Usage:
#   scripts/check-docs-freshness.sh <release-version>
#   scripts/check-docs-freshness.sh v0.2.2
#
# Exit codes:
#   0 — all verified_against fields are current for this minor version
#   1 — one or more pages are stale; list printed to stdout
#
# Called by .github/workflows/release.yml on every release-tag push.
# Run locally before cutting a release:
#   bash scripts/check-docs-freshness.sh v0.2.2

set -euo pipefail

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "Usage: $0 <release-version>  (e.g. v0.2.2)" >&2
  exit 1
fi

# Reduce a version string to its major.minor key, stripping any leading "v" and
# any pre-release suffix: v0.2.2 -> 0.2, v0.3.0-beta.1 -> 0.3. The "v" is dropped
# so a page stamped "0.2.2" and a release tagged "v0.2.2" compare equal.
minor_key() {
  local v="${1#v}"
  v="${v%%-*}"
  awk -F. '{print $1"."$2}' <<< "$v"
}

# True when major.minor key $1 is strictly older than key $2.
#
# The comparison is numeric and directional, and both properties matter:
#   - numeric, because a string compare puts 0.10 before 0.9;
#   - directional, because only a page that LAGS the release is stale. A page
#     verified against a newer minor than the one being released (an epic that
#     stamps docs for the upcoming minor, then ships a patch off the same main)
#     has been verified against this UI or a later one — it is not drift.
minor_is_older() {
  local a_major="${1%%.*}" a_minor="${1#*.}"
  local b_major="${2%%.*}" b_minor="${2#*.}"
  (( a_major < b_major || ( a_major == b_major && a_minor < b_minor ) ))
}

# A stamp we cannot parse must fail loudly rather than silently pass the gate.
is_valid_key() {
  [[ "$1" =~ ^[0-9]+\.[0-9]+$ ]]
}

RELEASE_MINOR="$(minor_key "$VERSION")"
if ! is_valid_key "$RELEASE_MINOR"; then
  echo "ERROR: cannot parse a major.minor version out of release '$VERSION'." >&2
  exit 1
fi

DOCS_DIR="$(dirname "$0")/../docs-site/src/content/docs"
STALE=()
AHEAD=()
MALFORMED=()

while IFS= read -r -d '' file; do
  # Extract verified_against value from YAML front-matter (between first --- pair)
  value="$(awk '/^---/{count++} count==1 && /^verified_against:/{print $2; exit}' "$file")"
  [[ -n "$value" ]] || continue

  key="$(minor_key "$value")"
  if ! is_valid_key "$key"; then
    MALFORMED+=("$file (verified_against: $value)")
  elif minor_is_older "$key" "$RELEASE_MINOR"; then
    STALE+=("$file (verified_against: $value)")
  elif minor_is_older "$RELEASE_MINOR" "$key"; then
    AHEAD+=("$file (verified_against: $value)")
  fi
done < <(find "$DOCS_DIR" -name "*.md" -print0)

if [[ ${#MALFORMED[@]} -gt 0 ]]; then
  echo "ERROR: The following docs pages have a verified_against value that is not a"
  echo "version number. Set it to the app version the page was verified against:"
  echo ""
  for entry in "${MALFORMED[@]}"; do
    echo "  $entry"
  done
  exit 1
fi

if [[ ${#STALE[@]} -gt 0 ]]; then
  echo "ERROR: The following docs pages have a verified_against version older than"
  echo "the released minor version (v$RELEASE_MINOR, from release $VERSION). Re-verify"
  echo "each page against the current UI and update its verified_against field:"
  echo ""
  for entry in "${STALE[@]}"; do
    echo "  $entry"
  done
  echo ""
  echo "If the page content is still accurate, just bump verified_against to $VERSION."
  exit 1
fi

# Ahead-of-release stamps do not block: the page was verified against this UI or a
# later one. Surface them anyway — a page claiming verification against a minor
# that has not shipped is usually a stamp written in anticipation of a release
# that was then cut under a different number.
if [[ ${#AHEAD[@]} -gt 0 ]]; then
  echo "NOTE: The following docs pages are stamped ahead of release $VERSION."
  echo "They do not block the release, but the stamp should name the version whose"
  echo "UI the page was actually verified against:"
  echo ""
  for entry in "${AHEAD[@]}"; do
    echo "  $entry"
  done
  echo ""
fi

echo "All docs pages with verified_against are current for v$RELEASE_MINOR (release $VERSION)."
exit 0
