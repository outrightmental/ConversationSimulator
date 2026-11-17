#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Signs the Mac App Store edition of Conversation Simulator and packs it into
# the installer package App Store Connect takes (publishing/MAC_APP_STORE.md).
#
#   scripts/sign-mac-app-store.sh APP PROFILE APP_IDENTITY INSTALLER_IDENTITY BUILD_NUMBER OUT_PKG
#
#   APP                 the .app from `tauri build --bundles app` (signed in place)
#   PROFILE             the Mac App Store provisioning profile for the app's identifier
#   APP_IDENTITY        "Apple Distribution: …" (or "3rd Party Mac Developer Application: …")
#   INSTALLER_IDENTITY  "3rd Party Mac Developer Installer: …" (Mac Installer Distribution)
#   BUILD_NUMBER        CFBundleVersion, higher than any build uploaded before
#   OUT_PKG             where to write the .pkg
#
# Signing goes inside out, never with --deep: every library first, with no
# entitlements; then every program the app starts (the engine and
# llama-server) with the two sandbox-inheriting entitlements; then the app,
# with the sandbox entitlements and the identifiers the profile grants.
set -euo pipefail

if [[ $# -ne 6 ]]; then
    sed -n '5,15p' "$0" >&2
    exit 2
fi
APP=$1 PROFILE=$2 APP_IDENTITY=$3 INSTALLER_IDENTITY=$4 BUILD_NUMBER=$5 OUT_PKG=$6
HERE="$(cd "$(dirname "$0")/.." && pwd)"
STORE_DIR="$HERE/publishing/mac-app-store"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

[[ -d "$APP/Contents/MacOS" ]] || { echo "ERROR: $APP is not an app bundle" >&2; exit 1; }
[[ -f "$PROFILE" ]] || { echo "ERROR: no provisioning profile at $PROFILE" >&2; exit 1; }
[[ "$BUILD_NUMBER" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]] || { echo "ERROR: build number '$BUILD_NUMBER' is not numeric" >&2; exit 1; }

INFO="$APP/Contents/Info.plist"
BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$INFO")"
MAIN_EXE="$APP/Contents/MacOS/$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$INFO")"

# ── The profile decides the identifiers ──────────────────────────────────────
security cms -D -i "$PROFILE" > "$WORK/profile.plist"
TEAM_ID="$(/usr/libexec/PlistBuddy -c 'Print :TeamIdentifier:0' "$WORK/profile.plist")"
PROFILE_APP_ID="$(/usr/libexec/PlistBuddy -c 'Print :Entitlements:com.apple.application-identifier' "$WORK/profile.plist")"
if [[ "$PROFILE_APP_ID" != "$TEAM_ID.$BUNDLE_ID" ]]; then
    echo "ERROR: the profile is for $PROFILE_APP_ID, the app is $TEAM_ID.$BUNDLE_ID" >&2
    exit 1
fi
sed -e "s/__TEAM_ID__/$TEAM_ID/g" -e "s/__APP_ID__/$BUNDLE_ID/g" \
    "$STORE_DIR/entitlements.app.plist" > "$WORK/app.entitlements"
cp "$PROFILE" "$APP/Contents/embedded.provisionprofile"

# ── Info.plist: the build number this upload carries ─────────────────────────
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NUMBER" "$INFO"
echo "Signing $BUNDLE_ID $(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$INFO") ($BUILD_NUMBER) for team $TEAM_ID"

# ── Every Mach-O inside the bundle except the app's own executable ───────────
LIBS=() PROGRAMS=()
while IFS= read -r -d '' f; do
    [[ "$f" == "$MAIN_EXE" ]] && continue
    desc="$(file -b "$f")"
    case "$desc" in
        *"Mach-O"*executable*) PROGRAMS+=("$f") ;;
        *"Mach-O"*) LIBS+=("$f") ;;
    esac
done < <(find "$APP/Contents" -type f -print0)
echo "Found ${#LIBS[@]} libraries and ${#PROGRAMS[@]} programs to sign"

for f in "${LIBS[@]}"; do
    codesign --force --sign "$APP_IDENTITY" "$f"
done
for f in "${PROGRAMS[@]}"; do
    codesign --force --sign "$APP_IDENTITY" --entitlements "$STORE_DIR/entitlements.helper.plist" "$f"
done
codesign --force --sign "$APP_IDENTITY" --entitlements "$WORK/app.entitlements" "$APP"

codesign --verify --deep --strict --verbose=2 "$APP"
echo "Entitlements of the app:"
codesign --display --entitlements - "$APP" 2>/dev/null | sed -n '1,40p'

# ── The installer package ────────────────────────────────────────────────────
mkdir -p "$(dirname "$OUT_PKG")"
productbuild --component "$APP" /Applications --sign "$INSTALLER_IDENTITY" "$OUT_PKG"
pkgutil --check-signature "$OUT_PKG"
echo "Packed: $OUT_PKG ($(du -h "$OUT_PKG" | cut -f1))"
