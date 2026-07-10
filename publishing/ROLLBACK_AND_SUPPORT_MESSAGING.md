<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Rollback and Support Messaging

> **Purpose:** Define the rollback path from the current live build back to the
> previous known-good beta build, and provide the player-facing support messages
> to use when a rollback occurs or when players ask about incidents.
>
> **Audience:** Platform team member performing the rollback, support
> communications owner drafting player messages, launch commander authorising
> the rollback decision.
>
> **Related document:** The launch-day rollback decision criteria and trigger
> thresholds are in
> [`publishing/LAUNCH_DAY_RUNBOOK.md` — Rollback](LAUNCH_DAY_RUNBOOK.md#rollback).
> The SteamPipe branch operations are in
> [`publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md).

---

## Rollback path overview

The rollback target is the **previous build that was live on the `beta` branch**
during Stage 3. This build has been verified against the full Steam beta
verification matrix (all four platforms) and its sign-off is recorded in
[`docs/STEAM_BETA_VERIFICATION_REPORT.md`](../docs/STEAM_BETA_VERIFICATION_REPORT.md).

There is no automated rollback. The platform team member must perform the steps
below manually in the Steamworks partner portal.

| State | Description |
|-------|-------------|
| **Pre-rollback (broken)** | Current `default` build — the launch build with the defect |
| **Rollback target (known good)** | Previous `beta` build — Stage 3 verified build |

### Before rolling back

Confirm the following before starting:

- [ ] The launch commander has authorised the rollback.
- [ ] The defect is confirmed to affect the live `default` build (not just a
      test environment).
- [ ] The rollback target build ID is identified in Steamworks App Admin → Builds
      (record it below before proceeding).

**Broken build ID / version:** ___________  
**Rollback target build ID / version:** ___________

---

## Rollback procedure

### Step 1 — Identify the rollback target

1. Open **Steamworks partner portal** → App Admin → Builds.
2. Locate the previous known-good build in the build history. This is the build
   that was previously set live on the `beta` branch during Stage 3.
3. Note the build ID (six-digit number visible in the build row) and the build
   description.

If there is uncertainty about which build is the correct rollback target, check
the signed-off
[`docs/STEAM_BETA_VERIFICATION_REPORT.md`](../docs/STEAM_BETA_VERIFICATION_REPORT.md)
for the build version recorded there — that version is the last formally verified
build.

### Step 2 — Set the rollback target live on `default`

1. In the Steamworks Builds list, click the row for the rollback target build.
2. Under **Set build live on branch**, select `default`.
3. Click **Set Live**.
4. Steamworks will show a confirmation dialog. Confirm the action.

This immediately queues the rollback build for all players on the `default`
branch. The change propagates to the Steam CDN within 10–15 minutes.

### Step 3 — Verify the rollback

1. Wait 10–15 minutes for CDN propagation.
2. From a non-partner Steam account, install or update the game and confirm the
   version shown in the app matches the rollback target version.
3. Run a basic smoke check: launch the app, start a text session, verify the
   debrief screen is reachable.

- [ ] Rollback build live and verified.

### Step 4 — Open a critical GitHub issue

Open a new GitHub issue immediately after the rollback is confirmed:

- **Title:** `[Rollback] <affected version> reverted on default — <brief reason>`
- **Labels:** `steam`, `platform-bug`, `severity:critical`
- **Body must include:**
  - The defect that triggered the rollback (one paragraph, factual)
  - The build rolled back from (version and Steamworks build ID)
  - The build rolled back to (version and Steamworks build ID)
  - The time the rollback was initiated (UTC)
  - The time the rollback was verified live (UTC)
  - The owner assigned to investigating and fixing the defect
  - A checkbox for: "Do not re-promote the broken build until this issue is
    closed with a fix."

### Step 5 — Communicate to players (see templates below)

Post the appropriate player-facing message using the templates in the
[Support messaging](#support-messaging) section. Posting must happen within
30 minutes of the rollback being confirmed live.

### Step 6 — Notify all triage owners

Send an internal notification to all triage owners listed in
[`publishing/LAUNCH_DAY_RUNBOOK.md` — Triage owners](LAUNCH_DAY_RUNBOOK.md#triage-owners)
with:

- Which build is now live on `default`
- The GitHub issue number tracking the defect
- The current status of the investigation

---

## Re-promotion criteria

Do not re-promote the broken build — or any build based on it — to `default`
until all of the following are satisfied:

- [ ] The root cause of the defect is identified and fixed in source.
- [ ] The fixed build has passed `scripts/depot-audit.sh` on all three platforms.
- [ ] For a **privacy regression**: the fix has been independently reviewed by a
      second engineer who confirms the regression is resolved.
- [ ] The fixed build has passed a targeted smoke test on the affected platform(s).
- [ ] The launch commander and platform lead have both signed off on the fix.
- [ ] The GitHub issue opened in Step 4 is closed with a reference to the fixed
      build tag.

---

## Support messaging

Use these templates for player-facing communication when a rollback occurs or
when players report an incident. All messages must be reviewed and approved by
Outright Mental before posting to a public Steam channel.

### Template: Rollback notice (Steam community post)

Use this template for a Steam Community Hub announcement post after a rollback.

---

**Subject:** Brief update on today's release

We pushed an update to Conversation Simulator earlier today and quickly
identified an issue affecting [**describe the symptom in plain language, e.g.
"some players on Windows 10"**]. We've reverted to the previous stable version
while we investigate.

**What this means for you:**
- If you have already installed today's update, Steam will automatically
  downgrade to the stable version the next time you open the Steam client.
- If you haven't installed yet, you'll get the stable version directly.

No conversation data, transcripts, or settings are affected by this update.
Everything stays on your machine.

We'll post another update here once a fixed version is available. Thank you
for your patience — and for any reports you sent our way.

— The Conversation Simulator team

---

### Template: Privacy incident notice (Steam community post)

Use this template **only** if the rollback was triggered by a confirmed privacy
regression (conversation data leaving a player's machine). Do not speculate
or use this template for non-privacy issues. This message must be approved by
the launch commander and by Outright Mental legal before posting.

---

**Subject:** Important update about data handling

We identified a defect in today's release of Conversation Simulator that could
have caused [**describe specifically what happened — e.g. "session metadata to
be written to a location outside the app's data directory"**]. We have reverted
to the previous stable version while we fix this.

**What you should know:**
- Conversation Simulator is designed so that your practice sessions stay
  entirely on your machine. Today's defect is an unintended deviation from
  that design.
- [**Include specifics about scope if known — e.g. "This affected users who
  completed a voice session since the update was released (approximately
  HH:MM–HH:MM UTC today)."**]
- [**State whether any data actually left the machine, or whether the risk was
  potential but unconfirmed.**]
- We have reverted the update. The stable version does not contain this defect.

If you have any concerns about your data, you can clear all local session data
at any time from Settings → Privacy → Clear all data.

We apologise for this. We take the local-first promise seriously and we will
post a full explanation of what happened and what we fixed once the corrected
version is available.

— The Conversation Simulator team

---

### Template: Issue acknowledgement (GitHub issue reply)

Use this template when replying to a player who has filed a GitHub issue about
a defect that is already being investigated.

---

Thank you for reporting this. We're aware of the issue and it's being
investigated. I've tagged this report as `tracked` so it feeds into the fix.

> **Note:** Please don't include conversation transcripts or personal details
> in this issue. If we need more information, we'll ask specifically for
> diagnostics that exclude personal content.

We'll update this issue when a fix is ready. If you'd like to be notified,
use the **Subscribe** button at the bottom of the issue.

---

### Template: "Is my data safe?" reply (Steam discussion or GitHub)

Use this template when a player asks whether their data was affected by an
incident, even before a full investigation is complete.

---

Your conversation data is stored locally on your machine and is never
transmitted to our servers or any third party during normal play.

[**If an incident is being investigated, add:**]
We are currently investigating a reported issue and will post an update here
once we have a clear picture of what happened. Until then, you can review your
local data at `~/.convsim/` (macOS / Linux) or
`%LOCALAPPDATA%\outrightmental\convsim\` (Windows), and you can delete it at
any time from Settings → Privacy → Clear all data.

---

### Template: "What happened?" post-incident summary

Use this template once the investigation is complete and a fixed version is
available. Post it as a Steam Community Hub announcement.

---

**Subject:** What happened, what we fixed, and what's next

Earlier this week we rolled back a Conversation Simulator update due to
[**describe the incident briefly**]. Here's what we found and what we've done.

**What happened**

[**Plain-language explanation of the root cause. One to two paragraphs. Avoid
technical jargon where possible.**]

**What we fixed**

[**Describe the fix. One paragraph.**]

**Who was affected and how**

[**Be specific. E.g.: "Players who completed a voice session between HH:MM and
HH:MM UTC on DATE." If no data left any machine, say so clearly.**]

**The fix is now live**

Version [X.Y.Z] is now available on Steam. It replaces the reverted build.
Steam will update automatically the next time you open the client.

If you have any further concerns, please open a new GitHub issue or post in
this discussion.

— The Conversation Simulator team

---

## Links

- [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md) — rollback trigger criteria and launch day operations
- [`publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md`](STEAM_PUBLISHING_AND_DEPLOYMENT.md) — SteamPipe branch promotion and troubleshooting
- [`publishing/BETA_FEEDBACK_AND_LAUNCH_RISKS.md`](BETA_FEEDBACK_AND_LAUNCH_RISKS.md) — accepted launch risks and beta feedback summary
- [`docs/steam-triage.md`](../docs/steam-triage.md) — issue triage routing and SLA policy
- [`docs/STEAM_BETA_VERIFICATION_REPORT.md`](../docs/STEAM_BETA_VERIFICATION_REPORT.md) — last known-good verified build reference
