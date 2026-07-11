<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Default Branch Promotion Log

> **Purpose:** Permanent record of every promotion of a SteamPipe build to the
> `default` branch (public release).  Each entry captures the SteamPipe Build ID
> set live, the Build ID it replaced (for rollback), the GitHub release tag,
> the SHA-256 hashes of the promoted artifacts, release notes, and the go/no-go
> confirmation.
>
> **When to update:** Immediately after the `steam-promote.yml` CI workflow
> completes successfully.  Copy the "Steam Promotion Record" block printed by the
> "Record promotion details" step and paste it into the [Entries](#entries)
> section below.
>
> **Audience:** Platform team, launch commander, Outright Mental.  This log is
> the authoritative provenance record for every public release — do not delete
> or alter past entries.

---

## Entries

<!-- Add a new entry for every promotion.  Newest entry first. -->

---

### Entry template

Copy this section, fill in all fields, and add it above this template for each
new promotion.  Do not leave placeholder text in a completed entry.

```
## Promotion vX.Y.Z — YYYY-MM-DD

### Header

Date (UTC)        :
Release tag       :
Build ID (new)    :   ← the Build ID set live on default
Build ID (prev)   :   ← the Build ID that was live before this promotion
                       (used for rollback — do NOT delete this build from Steamworks)
Branch set live   : default
Promoted by       :   ← GitHub username
CI run            :   ← link to the steam-promote.yml workflow run

### Go/no-go confirmation

All Stage 4 gate criteria in docs/steam-mvp-scope.md were verified before
promotion:

| Gate | Status |
|------|--------|
| G4-01 Valve store page approval | ☐ PASS |
| G4-02 Steam Deck Verified tier | ☐ PASS |
| G4-03 Full release checklist (Parts A–J) | ☐ PASS |
| G4-04 Store page copy accurate | ☐ PASS |
| G4-05 Voice smoke test (or fallback) | ☐ PASS |

Additional sign-offs required before promotion:

- [ ] STEAM_BETA_VERIFICATION_REPORT.md attached to the release issue (G3-06 / SR-09)
- [ ] Release owner has given explicit launch go/no-go
- [ ] publishing/BETA_FEEDBACK_AND_LAUNCH_RISKS.md complete and signed

Release owner sign-off: ___________________________  Date: YYYY-MM-DD

### Artifact SHA-256 hashes

Computed from the GitHub release assets for the release tag above.
(Copied from the CI run "Record promotion details" step output.)

| Filename | SHA-256 |
|----------|---------|
| ConversationSimulator_vX.Y.Z_aarch64.dmg | |
| ConversationSimulator_vX.Y.Z_x64.dmg | |
| ConversationSimulator_vX.Y.Z_amd64.AppImage | |
| ConversationSimulator_vX.Y.Z_x64-setup.exe | |
| ConversationSimulator_vX.Y.Z_x64-setup.msi | |
| checksums-sha256.txt | |
| ConversationSimulator_vX.Y.Z_aarch64.app.tar.gz | |

### Release notes

Link: https://github.com/outrightmental/ConversationSimulator/releases/tag/vX.Y.Z

Summary of changes in this release (copy from RELEASE_NOTES.md or the
GitHub release body):

-
-

### Rollback reference

To roll back this promotion if a critical defect is found:

1. Open Steamworks → App Admin → Builds.
2. Find Build ID (prev) listed above.
3. Click Set Live → select branch default.
4. Confirm in Steamworks; wait 10–15 minutes for CDN propagation.
5. Verify previous build is live from a fresh account install.
6. Open a severity:critical GitHub issue:
     Title:  [Rollback] vX.Y.Z reverted — <brief reason>
     Labels: steam, platform-bug, severity:critical
7. Notify all triage owners listed in publishing/LAUNCH_DAY_RUNBOOK.md.

For the full rollback procedure see publishing/ROLLBACK_AND_SUPPORT_MESSAGING.md.
```

---

## Links

- [`.github/workflows/steam-promote.yml`](../.github/workflows/steam-promote.yml) — CI workflow that performs the promotion
- [`.github/workflows/steam-deploy.yml`](../.github/workflows/steam-deploy.yml) — CI workflow that uploads content and optionally sets a branch live
- [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md) — launch-day sequence; Step 3 triggers this promotion
- [`publishing/ROLLBACK_AND_SUPPORT_MESSAGING.md`](ROLLBACK_AND_SUPPORT_MESSAGING.md) — rollback procedure and player support messages
- [`publishing/BETA_FEEDBACK_AND_LAUNCH_RISKS.md`](BETA_FEEDBACK_AND_LAUNCH_RISKS.md) — gate SR-09 sign-off
- [`docs/STEAM_BETA_VERIFICATION_REPORT.md`](../docs/STEAM_BETA_VERIFICATION_REPORT.md) — gate G3-06 sign-off
- [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) — Stage 4 gate criteria (G4-01 through G4-05)
