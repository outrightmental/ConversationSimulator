<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Launch Day Runbook

> **Purpose:** Detailed operations checklist for the public release of
> Conversation Simulator on Steam. Covers the sequence from Valve approval
> through branch promotion, public announcement, support monitoring, rollback
> criteria, known issues, and triage owner assignments.
>
> **Audience:** Platform team, Outright Mental staff. One person from each
> group listed in [Triage owners](#triage-owners) must be available on launch
> day and for the following 72 hours.
>
> **Prerequisite:** The Steam review submission has been completed and Valve
> has approved the store page (gate G4-01). All Stage 4 gate criteria in
> [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) must be met before
> setting the `default` branch live.

---

## Triage owners

Assign a named person to each role before launch day. Each owner must confirm
their availability for the 72-hour post-launch monitoring window.

| Role | Owner | Contact | Escalation |
|------|-------|---------|-----------|
| **Launch commander** | *(assign before launch)* | | Account holder at Outright Mental |
| **Platform lead** (GitHub issues, CI, Steam) | | | Launch commander |
| **Privacy fast-path** (any privacy/data report) | | | Launch commander — escalate within 30 minutes |
| **Content / pack** (NPC behaviour, scenario bugs) | | | Platform lead |
| **Support communications** (player-facing replies, Steam discussion board) | | | Platform lead |
| **On-call (after-hours)** | | | Platform lead → launch commander |

The launch commander has final say on any rollback decision. The privacy
fast-path owner must be reachable by phone (not just Slack or email) for the
first 24 hours after launch.

---

## T−24 hours: Final checks

Complete the day before the scheduled launch.

### Build verification

- [ ] The launch build is staged in Steamworks App Admin → Builds with all three
      platform depots and is **not** yet live on `default`.
- [ ] Build description in Steamworks matches the release tag (e.g. `v0.3.0`).
- [ ] Depot audit has been run clean on the launch build: all three platform
      content directories exited 0 from `scripts/depot-audit.sh` (SR-08).
- [ ] The signed-off
      [`docs/STEAM_BETA_VERIFICATION_REPORT.md`](../docs/STEAM_BETA_VERIFICATION_REPORT.md)
      for the launch build is attached to the release issue (G3-06 / SR-09).

### Store page

- [ ] Store page has been reviewed in the Steamworks preview since Valve approval:
      no placeholder text, no wrong screenshots, and the correct `$9.99` price is shown.
- [ ] Release date field shows the correct launch date (not `Coming Soon`).
- [ ] All five screenshots show the current build UI.
- [ ] The `$9.99` price and the `Buy` button are visible in the store page preview,
      and any premium scenario-pack DLC launching alongside the base app is listed on the store page.

### CI and infrastructure

- [ ] All CI workflows are green on the release tag commit.
- [ ] GitHub Discussions or the Steam discussion board is enabled and configured.
- [ ] GitHub issue templates for Steam reports are present (`.github/ISSUE_TEMPLATE/steam_*.yml`).
- [ ] Launch commander and platform lead have Steamworks partner portal access
      confirmed (can log in now, not on launch day).

### Announcement content

Draft the announcement before launch day so it can be posted within minutes of
setting the app live. The canonical announcement text is in
[`publishing/LAUNCH_ANNOUNCEMENT.md`](LAUNCH_ANNOUNCEMENT.md).

- [ ] [`publishing/LAUNCH_ANNOUNCEMENT.md`](LAUNCH_ANNOUNCEMENT.md) reviewed
      and all three sign-offs recorded (Outright Mental, platform lead, support
      communications owner).
- [ ] Steam announcement post pasted into Steamworks → Community Hub → Post
      Announcement and saved as a draft (do not publish yet).
- [ ] Any external announcement (social media, mailing list) is queued and ready
      to publish, coordinated with the Steam announcement.

### Known issues

Complete the known issues table in the [Known issues](#known-issues) section
of this document before T−24.

---

## Launch sequence

Run these steps in order. Each step has a hard dependency on the previous one.

### Step 1 — Confirm all Stage 4 gates are green (T−2 hours)

Work through the full Stage 4 gate list in
[`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md#stage-4-gate--public-free-steam-release):

| Gate | Check |
|------|-------|
| G4-01 | Valve store page approval received (email from Valve) |
| G4-02 | Steam Deck Verified status confirmed in Steamworks |
| G4-03 | Full release checklist (Parts A–J in [`docs/release-checklist.md`](../docs/release-checklist.md)) passed on all four platforms |
| G4-04 | Store page copy accurate: no therapy/diagnosis language, no implied marketplace |
| G4-05 | Voice smoke test passed on all required platforms |

If any gate is not green, **do not proceed**. Resolve the gate failure or
escalate to the launch commander.

### Step 2 — Set the beta branch live (if not already done at Stage 3)

If the `beta` branch is not already live from Stage 3:

1. Trigger the deploy workflow (`.github/workflows/steam-deploy.yml`) with the
   launch tag and `set_live_branch: beta`.
2. Confirm the build is live on `beta` in Steamworks App Admin → Builds.
3. Install from a fresh Steam account on at least one machine per platform to
   verify the `beta` depot is reachable.

- [ ] `beta` branch is live and verified.

### Step 3 — Promote the build to the default branch (launch)

This is the point of no return. The `default` branch immediately serves all
new installs.

> **Note — the default-branch set-live is a manual App Admin action.**
> Steam does **not** let CI set the `default` branch live for a released app:
> the change requires an authorization prompt sent to the requesting account's
> Steam Mobile Authenticator (or SMS). The promote workflow therefore gates the
> release, captures the provenance record, and prints the exact App Admin steps —
> a human completes the actual Set Build Live in Steamworks.

**Preferred path — promote workflow + App Admin (build already staged):**

If the build was previously uploaded with `set_live_branch` left empty or set
to `beta` via `steam-deploy.yml`, the depot content is already on Valve's CDN,
so no re-upload is needed — only the branch pointer changes.

1. Trigger the promote workflow (`.github/workflows/steam-promote.yml`):
   - `build_id`: the Build ID shown in Steamworks → App Admin → Builds for
     the staged/beta build.
   - `release_tag`: the GitHub release tag (e.g. `v0.3.0`).
   - `previous_build_id`: the Build ID currently live on `default` (find it
     in Steamworks → App Admin → Builds → filter by branch: default).  This is
     recorded in [`publishing/STEAM_PROMOTION_LOG.md`](STEAM_PROMOTION_LOG.md)
     for rollback purposes.
   - `go_nogo_confirmed`: type exactly `YES` to confirm all Stage 4 gate
     criteria are met and the release owner has given go/no-go.
2. Approve the workflow run in the `steam-release` environment (requires a
   reviewer with the required-reviewer role).
3. Wait for the workflow to complete successfully. It verifies the go/no-go
   gate, hashes the release artifacts, and prints both the App Admin
   instructions and the "Steam Promotion Record" block.
4. In Steamworks → App Admin → Builds, set `build_id` live on the `default`
   branch and approve the authorization prompt in your Steam Mobile
   Authenticator (or via SMS), following the printed instructions.
5. Copy the "Steam Promotion Record" block from the "Record promotion details"
   step output and add it to [`publishing/STEAM_PROMOTION_LOG.md`](STEAM_PROMOTION_LOG.md).

**Fallback path — re-upload (build not yet staged):**

If the build has not been uploaded to Steamworks yet, trigger `steam-deploy.yml`
with the launch tag to stage the depot content, then set the build live on the
`default` branch manually in App Admin as in step 4 above.

- [ ] Workflow completed with exit code 0.
- [ ] `default` branch set live and shows the launch build in Steamworks App
      Admin → Builds (App Admin authorization prompt approved).
- [ ] Promotion record added to [`publishing/STEAM_PROMOTION_LOG.md`](STEAM_PROMOTION_LOG.md).

### Step 4 — Verify CDN propagation (T+15 minutes)

Wait 10–15 minutes for the Steam CDN to propagate the new build.

- [ ] The app store page is publicly visible (not returning 404).
- [ ] The store page shows the `Buy` button at `$9.99` (not `Pre-purchase`, which would
      mean the app is not yet released).
- [ ] The price shown is `$9.99`.
- [ ] Release date shown on the page matches today's date.

### Step 5 — End-to-end install verification

Install from a **fresh Steam account** (not the partner or build account) on
each required platform. Do not skip this step — CDN propagation issues and
package configuration errors sometimes only appear on non-partner accounts.

- [ ] Windows 10 or 11: fresh install, app launches, reaches home screen.
- [ ] macOS 13+: fresh install, Gatekeeper passes, app launches.
- [ ] Linux / SteamOS: fresh install, app launches, reaches home screen.
- [ ] Steam Deck (Gaming Mode): fresh install, app launches via Gaming Mode.

### Step 6 — Publish announcement

After Step 5 is complete and all platform installs are verified:

1. Publish the Steam announcement in Steamworks → Community Hub.
2. Publish any queued external announcements (social media, mailing list).
3. Record the announcement times in the [Launch log](#launch-log).

- [ ] Steam announcement published.
- [ ] External announcements published.

### Step 7 — Begin 72-hour monitoring

Immediately after announcement, all triage owners switch to active monitoring.
See [Support monitoring](#support-monitoring) below.

- [ ] All triage owners notified that monitoring has started.
- [ ] Monitoring cadence established (see schedule below).
- [ ] [`publishing/POST_LAUNCH_FEEDBACK_SUMMARY.md`](POST_LAUNCH_FEEDBACK_SUMMARY.md)
      opened and ready to record findings — complete the 72-hour draft when the
      monitoring window closes.

---

## Support monitoring

During the first 72 hours after public launch, monitor all signals on the
schedule below. All findings are logged in the [Launch log](#launch-log).

### Monitoring schedule

| Window | Cadence | Owner |
|--------|---------|-------|
| Hours 0–24 | Check every 30 minutes | Platform lead (on-call during off-hours) |
| Hours 24–48 | Check every 2 hours | Platform lead |
| Hours 48–72 | Check every 4 hours | Platform lead |
| After 72 hours | Standard GitHub issue triage cadence | Platform lead |

### Signals to monitor

| Signal | Where to check | Escalation threshold |
|--------|---------------|---------------------|
| Steam review sentiment | Steamworks App Admin → Reviews | Any review mentioning unexpected network activity, "sent my data", "privacy", "recording", or similar — **escalate to privacy fast-path owner immediately** |
| GitHub Steam issue queue | GitHub Issues, filter `label:steam` | Any `severity:critical` label — 24-hour response SLA; privacy fast-path if content matches the privacy keywords |
| Steam discussion board | Community Hub → Discussions | Any thread with more than 5 upvotes or a privacy/data concern — respond within 4 hours |
| Steamworks stats | App Admin → Stats | Abnormal install failure rate or any stat that implies connection errors during play |
| Known issue reports | GitHub Issues | Compare against the [Known issues](#known-issues) table — triage as `wont-fix` / `tracked` / `escalate` accordingly |

### Privacy fast-path (mandatory)

Any report — in GitHub Issues, Steam reviews, Steam Discussions, or email —
containing the words "transcripts", "sent my data", "network", "uploaded",
"privacy", or "recording" triggers the privacy fast-path:

1. **Immediately** notify the privacy fast-path owner by phone.
2. Privacy fast-path owner notifies the launch commander within 30 minutes.
3. Do not ask the reporter to paste conversation content in a public thread.
4. Investigate using the reporter's description only. If a code path is
   suspected, reproduce locally in a test environment.
5. If the risk is confirmed as a live privacy regression: initiate rollback
   (see [Rollback](#rollback)) before any public communication.
6. If the risk is not confirmed: reply to the reporter within 4 hours with a
   factual explanation of the local-first architecture.

See [`docs/steam-triage.md`](../docs/steam-triage.md) for the full triage
routing and SLA policy.

---

## Rollback

### When to roll back

Roll back to the previous beta build if **any** of the following are true:

| Trigger | Severity |
|---------|---------|
| Confirmed privacy regression: conversation data leaving the machine | **Immediate — do not wait** |
| App crashes on launch on any required platform for >10% of reported installs | Critical |
| Steam Deck in Gaming Mode cannot reach the home screen | Critical |
| Confirmed data loss: session transcripts deleted without player action | Critical |
| Score-breaking bug that renders a core session flow uncompletable | High — rollback within 24 hours if no hotfix is ready |
| Store page live but showing incorrect content or pricing | High — fix in Steamworks (no rollback required) |

Minor cosmetic bugs, translation issues, and single-user edge cases do not
warrant a rollback unless they are the tip of a larger regression.

### Rollback procedure

1. Open **Steamworks App Admin → Builds**.
2. Find the previous known-good build (the build that was live on `beta` during
   Stage 3).
3. Click **Set Live** → select branch `default`.
4. Confirm the rollback in Steamworks.
5. Wait 10–15 minutes for CDN propagation, then verify the previous build is
   live by installing from a fresh account.
6. Open a `severity:critical` GitHub issue:
   - Title: `[Rollback] vX.Y.Z reverted — <brief reason>`
   - Labels: `steam`, `platform-bug`, `severity:critical`
   - Body: the affected platform(s), the trigger, the build ID rolled back to,
     and the build ID rolled back from.
7. Notify all triage owners of the rollback.
8. If the rollback was triggered by a privacy regression, notify the launch
   commander immediately and draft the player support message from
   [`publishing/ROLLBACK_AND_SUPPORT_MESSAGING.md`](ROLLBACK_AND_SUPPORT_MESSAGING.md).

For the full rollback runbook and player-facing support message templates, see
[`publishing/ROLLBACK_AND_SUPPORT_MESSAGING.md`](ROLLBACK_AND_SUPPORT_MESSAGING.md).

### Hotfix branch

After the rollback is confirmed live, create a hotfix branch immediately so
the fix can be tracked and reviewed:

1. Trigger [`.github/workflows/hotfix.yml`](../.github/workflows/hotfix.yml)
   with `release_tag` set to the version that was rolled back,
   `slug` set to a short description of the defect (e.g. `privacy-regression`),
   `severity` set to the issue severity, and `defect_summary` as a one sentence
   description.
2. The workflow creates `hotfix/<tag>-<slug>` and prints the rollback record
   template. Copy the record block into
   [`publishing/ROLLBACK_AND_SUPPORT_MESSAGING.md`](ROLLBACK_AND_SUPPORT_MESSAGING.md).
3. Commit the fix to the hotfix branch and open a PR to main following the
   printed next-steps instructions.

### Do not re-promote

Do not re-promote the rolled-back build until:

- The defect is identified and fixed in source.
- The fixed build has passed the depot audit (SR-08).
- The platform lead and launch commander have both signed off.
- For a privacy regression: an independent review of the fix must confirm the
  regression is resolved before re-promoting.

---

## Known issues

Document all known issues accepted for launch before T−24. Update this table
with any new issues found during the 72-hour monitoring window.

For accepted launch risks from the private beta, see
[`publishing/BETA_FEEDBACK_AND_LAUNCH_RISKS.md`](BETA_FEEDBACK_AND_LAUNCH_RISKS.md).

| # | Issue | Affected platform | Severity | Workaround | Tracking issue | Resolution target |
|---|-------|------------------|----------|-----------|---------------|------------------|
| 1 | *(document known issues here before launch)* | | | | | |

### How to classify

| Label | Meaning |
|-------|---------|
| `known-issue-v1` | Accepted for launch; not blocking; tracked for a future patch |
| `wont-fix` | Accepted forever; documented here for player support use |
| `severity:critical` | Must trigger rollback if found live (see [Rollback](#rollback)) |

---

## Issue routing at a glance

Use these labels in GitHub Issues. The full triage flow is in
[`docs/steam-triage.md`](../docs/steam-triage.md).

| Reporter describes | Labels | Owner |
|--------------------|--------|-------|
| App does not launch, crashes, Steam overlay broken, controller broken, Steam Deck crash | `steam` + `platform-bug` | Platform lead |
| Model download fails, checksum mismatch, model not loading | `steam` + `model-install` | Platform lead |
| NPC gives wrong response, scoring incorrect, scenario broken | `steam` + `pack-bug` | Content / pack owner |
| Slow inference, high CPU/GPU, long load times, audio stutter, UI frame-rate | `steam` + `performance` | Platform lead |
| Unexpected network activity, "sent my data", privacy concern | `steam` + `privacy` + `safety` | **Privacy fast-path — escalate immediately** |
| Creator Workbench crash, pack import fails | `steam` + `creator-workbench` | Platform lead |
| Compliment / general feedback | No label needed | Support communications owner — respond and thank |

---

## Launch log

Record the timeline of key events during the launch.

| Time (UTC) | Event | Owner |
|------------|-------|-------|
| | Stage 4 gate check complete — all green | |
| | `beta` branch confirmed live | |
| | `default` branch set live | |
| | CDN propagation verified | |
| | Fresh-account install verified on Windows | |
| | Fresh-account install verified on macOS | |
| | Fresh-account install verified on Linux | |
| | Fresh-account install verified on Steam Deck | |
| | Steam announcement published | |
| | External announcements published | |
| | 72-hour monitoring window opened | |
| | 72-hour monitoring window closed | |

Add additional rows for any incidents, rollbacks, or escalations.

---

## Links

- [`publishing/LAUNCH_ANNOUNCEMENT.md`](LAUNCH_ANNOUNCEMENT.md) — launch announcement copy (Steam post and external channels)
- [`publishing/POST_LAUNCH_FEEDBACK_SUMMARY.md`](POST_LAUNCH_FEEDBACK_SUMMARY.md) — 72-hour feedback summary and next milestone plan template
- [`publishing/STEAM_REVIEW_SUBMISSION.md`](STEAM_REVIEW_SUBMISSION.md) — Steamworks store review submission runbook
- [`publishing/ROLLBACK_AND_SUPPORT_MESSAGING.md`](ROLLBACK_AND_SUPPORT_MESSAGING.md) — rollback procedure and player support messages
- [`publishing/BETA_FEEDBACK_AND_LAUNCH_RISKS.md`](BETA_FEEDBACK_AND_LAUNCH_RISKS.md) — private beta feedback summary and accepted launch risks
- [`publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md) — SteamPipe build and deploy runbook
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — compliance checklist and risk register
- [`.github/workflows/hotfix.yml`](../.github/workflows/hotfix.yml) — hotfix branch creation and validation workflow
- [`docs/steam-triage.md`](../docs/steam-triage.md) — full triage routing and SLA policy
- [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) — Stage 4 gate criteria
- [`docs/release-checklist.md`](../docs/release-checklist.md) — platform smoke matrix and beta verification
