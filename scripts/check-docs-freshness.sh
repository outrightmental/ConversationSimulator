#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# check-docs-freshness.sh — verify that every docs-site page with a
# verified_against field matches the current release version.
#
# Usage:
#   scripts/check-docs-freshness.sh <release-version>
#   scripts/check-docs-freshness.sh v0.2.2
#
# Exit codes:
#   0 — all verified_against fields are current
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

DOCS_DIR="$(dirname "$0")/../docs-site/src/content/docs"
STALE=()

while IFS= read -r -d '' file; do
  # Extract verified_against value from YAML front-matter (between first --- pair)
  value="$(awk '/^---/{count++} count==1 && /^verified_against:/{print $2; exit}' "$file")"
  if [[ -n "$value" && "$value" != "$VERSION" ]]; then
    STALE+=("$file (verified_against: $value)")
  fi
done < <(find "$DOCS_DIR" -name "*.md" -print0)

if [[ ${#STALE[@]} -eq 0 ]]; then
  echo "All docs pages with verified_against are current ($VERSION)."
  exit 0
fi

echo "ERROR: The following docs pages have a verified_against version that does"
echo "not match the release version ($VERSION). Update the content and"
echo "verified_against field before releasing:"
echo ""
for entry in "${STALE[@]}"; do
  echo "  $entry"
done
echo ""
echo "If the page content is still accurate, just bump verified_against to $VERSION."
exit 1
