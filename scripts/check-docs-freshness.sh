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

# Reduce a version string to its major.minor key, stripping any pre-release
# suffix: v0.2.2 -> v0.2, v0.3.0-beta.1 -> v0.3.
minor_key() {
  local v="${1%%-*}"
  awk -F. '{print $1"."$2}' <<< "$v"
}

RELEASE_MINOR="$(minor_key "$VERSION")"
DOCS_DIR="$(dirname "$0")/../docs-site/src/content/docs"
STALE=()

while IFS= read -r -d '' file; do
  # Extract verified_against value from YAML front-matter (between first --- pair)
  value="$(awk '/^---/{count++} count==1 && /^verified_against:/{print $2; exit}' "$file")"
  if [[ -n "$value" && "$(minor_key "$value")" != "$RELEASE_MINOR" ]]; then
    STALE+=("$file (verified_against: $value)")
  fi
done < <(find "$DOCS_DIR" -name "*.md" -print0)

if [[ ${#STALE[@]} -eq 0 ]]; then
  echo "All docs pages with verified_against are current for $RELEASE_MINOR (release $VERSION)."
  exit 0
fi

echo "ERROR: The following docs pages have a verified_against version that lags"
echo "the released minor version ($RELEASE_MINOR, from release $VERSION). Re-verify"
echo "each page against the current UI and update its verified_against field:"
echo ""
for entry in "${STALE[@]}"; do
  echo "  $entry"
done
echo ""
echo "If the page content is still accurate, just bump verified_against to $VERSION."
exit 1
