<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Post-Launch Feedback Summary and Next Milestone Plan

> **Purpose:** Capture structured feedback from the first public support window
> (hours 0–72 post-launch and the following two weeks), triage it into the
> standard issue buckets, and convert the findings into a concrete plan for the
> next milestone. Complete this document at the end of the 72-hour monitoring
> window (Step 7 in [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md))
> and again at the two-week mark once the issue queue has stabilised.
>
> **Audience:** Platform team, Outright Mental. Share with the full contributor
> community when the next milestone plan is ready.
>
> **When to complete:**
> - **72-hour draft:** After the monitoring window closes, with raw counts and
>   the most urgent findings.
> - **Two-week final:** When the initial issue queue has stabilised; includes
>   the confirmed next milestone plan.

---

## Monitoring window summary

| Field | Value |
|-------|-------|
| Launch date (UTC) | |
| Monitoring window opened (UTC) | |
| 72-hour window closed (UTC) | |
| Platform lead | |
| Completed by | |
| Completion date | |

---

## Signal coverage

Record every channel monitored and the raw volume observed.

### Steam reviews

| Metric | Value |
|--------|-------|
| Total reviews at 72-hour mark | |
| Positive | |
| Negative | |
| Review score | |
| Reviews mentioning privacy / data concerns | |
| Reviews escalated to privacy fast-path | |

Notable review themes (summarise in bullet points — do not quote player-private content):

-
-
-

### GitHub Issues (label: steam)

| Bucket | Issues filed (72 h) | Issues filed (2 wk) | Critical open | High open |
|--------|--------------------|--------------------|--------------|----------|
| `platform-bug` (crash / blocker) | | | | |
| `model-install` (model setup) | | | | |
| `pack-bug` (pack / content) | | | | |
| `performance` | | | | |
| `privacy` / `safety` | | | | |
| `creator-workbench` | | | | |
| Other / unclassified | | | | |
| **Total** | | | | |

Issues escalated to privacy fast-path: ___ (list issue numbers below)

-

### Steam discussion board

| Metric | Value |
|--------|-------|
| Threads opened (72 h) | |
| Threads with ≥ 5 upvotes | |
| Privacy / data concern threads | |
| Threads requiring maintainer response | |
| Response SLA met (≤ 4 h for high-upvote threads) | yes / no |

Notable discussion themes:

-
-

### Discord / community channels

| Metric | Value |
|--------|-------|
| Channel(s) monitored | |
| Feedback items collected | |
| Bug reports routed to GitHub | |
| Feature requests logged | |

---

## Triage summary

### Crash / blocker (platform-bug)

List every `severity:critical` or `severity:high` platform bug, its status, and
whether a hotfix or rollback was triggered.

| Issue # | Platform | Description | Severity | Status | Action taken |
|---------|----------|-------------|----------|--------|-------------|
| | | | | | |

Rollbacks triggered: ___ (list GitHub issue numbers)
Hotfix branches created: ___ (list branch names)

### Model setup (model-install)

Summarise the most common model download / setup failure modes.

| Pattern | Count | Root cause (if identified) | Resolution |
|---------|-------|--------------------------|-----------|
| | | | |

### Pack / content (pack-bug)

| Issue # | Pack | Description | Severity | Status |
|---------|------|-------------|----------|--------|
| | | | | |

### Performance

| Issue # | Platform | Model | Description | Severity | Status |
|---------|----------|-------|-------------|----------|--------|
| | | | | | |

Common performance patterns observed:

-
-

### Privacy / safety

> Handle all `privacy` and `safety` issues through the fast-path described in
> [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md#privacy-fast-path-mandatory).
> Do not include the content of privacy reports in this document — record only
> counts, outcomes, and whether the local-first guarantee was maintained.

| Metric | Value |
|--------|-------|
| Privacy fast-path activations | |
| Confirmed privacy regressions | |
| Local-first guarantee maintained throughout window | yes / no |
| Any rollback triggered by a privacy concern | yes / no |

### Creator workflow (creator-workbench)

| Issue # | Description | Severity | Status |
|---------|-------------|----------|--------|
| | | | |

---

## What went well

List 3–5 things that worked as planned during the launch and support window.
These are candidates for keeping in the next release process.

1.
2.
3.

---

## What needs to improve

List 3–5 things that should change before the next public release or milestone.
Each item becomes an action in the next milestone plan below.

1.
2.
3.

---

## Next milestone plan

Based on the feedback above, the following items are proposed for the next
milestone. Each item must reference a GitHub issue (create one if it does not
exist) so it is tracked to completion.

### Confirmed fixes (must ship in next patch)

Items here are defects confirmed live that are not severe enough to warrant a
hotfix but must be resolved before the next minor release.

| Priority | Item | GitHub issue | Owner | Target milestone |
|----------|------|-------------|-------|-----------------|
| P1 | | | | |
| P2 | | | | |

### Deferred from launch (carry forward)

Items accepted as launch risks in
[`publishing/BETA_FEEDBACK_AND_LAUNCH_RISKS.md`](BETA_FEEDBACK_AND_LAUNCH_RISKS.md)
that were triggered in the field.

| Risk ID | Description | Triggered? | Updated status | Target milestone |
|---------|-------------|-----------|---------------|-----------------|
| AR-01 | | | | |
| AP-01 | | | | |

### New feature requests from launch feedback

Only include items supported by multiple independent signals (≥ 3 upvotes /
reports). Single-voice requests belong in the standard issue backlog, not the
milestone plan.

| Signal count | Item | GitHub issue | Priority rationale |
|-------------|------|-------------|-------------------|
| | | | |

### Process improvements

Changes to the release, triage, or support process for future releases.

| Item | Owner | Notes |
|------|-------|-------|
| | | |

---

## Sign-off

Complete before publishing the next milestone plan publicly.

| Role | Name | Signed | Date |
|------|------|--------|------|
| Platform lead | | ☐ | |
| Launch commander (Outright Mental) | | ☐ | |

---

## Links

- [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md) — launch operations and 72-hour monitoring schedule
- [`publishing/ROLLBACK_AND_SUPPORT_MESSAGING.md`](ROLLBACK_AND_SUPPORT_MESSAGING.md) — rollback procedure and player messaging templates
- [`publishing/BETA_FEEDBACK_AND_LAUNCH_RISKS.md`](BETA_FEEDBACK_AND_LAUNCH_RISKS.md) — accepted launch risks (update status after this window)
- [`docs/steam-triage.md`](../docs/steam-triage.md) — issue triage routing and SLA policy
- [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) — gate criteria reference
