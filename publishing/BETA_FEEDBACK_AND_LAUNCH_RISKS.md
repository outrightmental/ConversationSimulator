<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Private Beta Feedback Summary and Accepted Launch Risks

> **Purpose:** Record the private beta tester feedback collected during Stage 3,
> summarise what was fixed, what was deferred, and document all risks formally
> accepted for the v1 public launch. This document is the sign-off evidence for
> gate SR-09 (private beta sign-off) and feeds directly into the known-issues
> table in [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md).
>
> **Audience:** Platform team, launch commander, Outright Mental. Outright Mental
> must review and sign the [Accepted risks sign-off](#accepted-risks-sign-off)
> section before the `default` branch is set live.
>
> **When to complete:** After the Stage 3 beta verification report is signed off
> and before the Stage 4 gate check in the launch day runbook.

---

## Beta tester coverage

Record each tester who participated in the private beta and the platforms they
covered. The minimum coverage requirement is ≥ 5 testers with ≥ 1 per platform
(gate G3-06 / SR-09).

| Tester ID | Platform(s) tested | Sessions completed | Sign-off date |
|-----------|-------------------|-------------------|--------------|
| *(tester-01)* | Windows 11 | | |
| *(tester-02)* | macOS 14 (Apple Silicon) | | |
| *(tester-03)* | Linux (Ubuntu 24.04) | | |
| *(tester-04)* | Steam Deck (SteamOS 3.x) | | |
| *(tester-05)* | Windows 10 | | |
| *(add rows as needed)* | | | |

**Total testers:** ___  
**Windows coverage:** ___  
**macOS coverage:** ___  
**Linux / SteamOS coverage:** ___  
**Steam Deck coverage:** ___

Tester identity is kept within the team. Do not publish individual tester
names or contact details.

---

## Feedback summary

### How feedback was collected

- One-click redacted diagnostics bundle via the in-app "Send beta report" button
  (see [`docs/beta-testing.md`](../docs/beta-testing.md) and
  `services/convsim-core/convsim_core/beta_report.py`).
- Manual GitHub issues filed by testers using the
  `.github/ISSUE_TEMPLATE/beta-report.yml` template.
- Direct tester communication recorded by the platform lead.

### Aggregate feedback statistics

| Category | Reports received | Fixed before launch | Deferred | Won't fix |
|----------|-----------------|--------------------|---------|---------:|
| Platform / installation | | | | |
| Session flow / NPC behaviour | | | | |
| Model download and management | | | | |
| Voice / microphone | | | | |
| Steam Deck / controller | | | | |
| Privacy / data handling | | | | |
| UI / UX | | | | |
| Performance | | | | |
| Other | | | | |
| **Total** | | | | |

### Themes from feedback

Document the top 3–5 themes that emerged across multiple testers. These inform
both the accepted risks below and future post-launch milestones.

1. *(summarise after beta)*
2. *(summarise after beta)*
3. *(summarise after beta)*

### What was fixed

List GitHub issues fixed as a result of private beta feedback that are included
in the launch build.

| Issue | Description | Platform | Fix included in tag |
|-------|-------------|----------|-------------------|
| *(#nnn)* | | | |

### What was deferred

List GitHub issues filed during private beta that are **not** fixed in the
launch build and are deferred to a post-launch milestone. Each deferred item
must appear in the accepted risks table or the known-issues table in
[`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md).

| Issue | Description | Platform | Deferred to milestone | Severity |
|-------|-------------|----------|----------------------|---------|
| *(#nnn)* | | | | |

---

## Accepted launch risks

These risks are formally accepted by Outright Mental as present at public
launch. Each risk must have a mitigation or workaround documented and must not
be a release-blocking risk that is `OPEN` in the compliance register.

For compliance register risks (e.g. AU-01, SP-01), the `Status` column in
[`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md)
must be updated to `ACCEPTED` once this sign-off is complete.

### Functional risks accepted for v1

| Risk ID | Description | Mitigation / workaround | Player impact | Tracking |
|---------|-------------|------------------------|--------------|---------|
| AR-01 | *(document accepted functional risks here)* | | | |

### Platform risks accepted for v1

| Risk ID | Description | Platform | Mitigation / workaround | Tracking |
|---------|-------------|---------|------------------------|---------|
| AP-01 | *(document accepted platform risks here)* | | | |

### Known limitations documented for players

These limitations are communicated to players via the store page, in-app text,
or the Steam community hub FAQ. They are not bugs — they are intentional
constraints of the v1 release.

| Limitation | How communicated | Notes |
|-----------|-----------------|-------|
| Model weights are not included in the installer; the player must download a model before starting a session | Onboarding wizard, first-launch screen, store page system requirements | By design — avoids model license distribution restrictions |
| Voice input requires an external USB or Bluetooth microphone on Steam Deck | Steam store page (system requirements), Steam Deck installation note | AU-03; text-only mode available without a microphone |
| No cloud sync of conversations or transcripts; progress does not transfer between machines | Store page, in-app privacy screen | Local-first by design; only `steam_cloud_settings.json` syncs |
| Community pack import requires manual file placement; no in-app pack browser | In-app Settings → Packs screen | Pack browser deferred to post-launch Stage 5 |
| *(add further known limitations here)* | | |

---

## Accepted risks sign-off

All parties listed below must sign this section before the launch day runbook
proceeds to the Stage 4 gate check.

| Role | Name | Signature / date | Notes |
|------|------|-----------------|-------|
| Launch commander (Outright Mental) | | | |
| Platform lead | | | |
| Privacy fast-path owner | | | |

By signing, each party confirms:

1. They have reviewed the beta feedback summary and the accepted risks table.
2. They agree that the accepted risks are tolerable for a free public release
   and that adequate mitigations or workarounds are in place.
3. They understand that compliance register risks marked `ACCEPTED` here will
   be updated to `ACCEPTED` status in
   [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md).
4. No `OPEN` release-blocking risk in the compliance register is being silently
   ignored — every such risk is either `MITIGATED`, `ACCEPTED` with sign-off
   here, or `DEFERRED` with a post-launch milestone assigned.

---

## Post-launch risk monitoring

After launch, the following risks require active monitoring during the 72-hour
window defined in [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md):

| Risk | Monitor via | Escalation if triggered |
|------|------------|------------------------|
| Privacy regression (any data leaving the machine) | Steam reviews, GitHub issues — privacy fast-path keywords | Immediate rollback; notify launch commander |
| Microphone permission crash (AU-01) | GitHub issues `label:steam+platform-bug`, Steam reviews | Hotfix or patch deployment within 48 hours |
| Steam Deck controller navigation blocking home screen (SP-02 related) | GitHub issues `label:steam+platform-bug` | Patch or rollback within 24 hours |
| Valve review rejection risk materialising post-launch | Steamworks notices, Valve developer support email | Launch commander escalation; consult legal |

---

## Links

- [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md) — launch-day operations and known issues table
- [`publishing/ROLLBACK_AND_SUPPORT_MESSAGING.md`](ROLLBACK_AND_SUPPORT_MESSAGING.md) — rollback procedure and player messaging
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — full compliance risk register (update status after sign-off)
- [`docs/STEAM_BETA_VERIFICATION_REPORT.md`](../docs/STEAM_BETA_VERIFICATION_REPORT.md) — aggregate beta verification report (SR-09)
- [`docs/QA_STEAM_PLATFORM_MATRIX.md`](../docs/QA_STEAM_PLATFORM_MATRIX.md) — QA test matrix and tester sign-offs
- [`docs/beta-testing.md`](../docs/beta-testing.md) — beta tester guide (diagnostics bundle, reporting)
- [`docs/steam-triage.md`](../docs/steam-triage.md) — triage routing and SLA policy
- [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) — Stage 3 and Stage 4 gate criteria
