<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Edition Issue Triage Flow

> **Purpose of this document:** Define how incoming issues filed against the
> Steam edition are triaged and routed during private beta and after public
> launch. Maintainers and beta coordinators should follow this document when
> processing the issue queue.

---

## Issue templates and labels

Five issue templates cover Steam-specific report categories. Each template
auto-applies one or more labels via GitHub front matter.

| Template | Auto-applied labels | Use when |
|----------|---------------------|----------|
| Steam — platform bug | `steam`, `platform-bug` | Launcher, Steam overlay, controller navigation, Steam Deck, code-signing, or platform-specific crash |
| Steam — local model install failure | `steam`, `model-install` | Model Manager download, checksum verification, or model-load failures |
| Steam — pack validation or content bug | `steam`, `pack-bug` | Schema error, broken scenario, incorrect scoring, or content rating mismatch |
| Steam — performance or frame-rate issue | `steam`, `performance` | Slow inference, high CPU/GPU usage, long load times, audio stuttering, or UI frame-rate problems |
| Steam — privacy or safety report | `steam`, `privacy`, `safety` | Unexpected network activity, data written outside `~/.convsim/`, or content safety violations |
| Steam — Creator Workbench bug | `steam`, `creator-workbench` | Pack authoring, scenario editing, asset management, or Workbench-specific crashes |

General (non-Steam) templates remain available for bugs that reproduce in the
open-source build.

---

## Private beta triage (Stage 3)

During the Steam private beta the reporter pool is limited to invited testers:
Outright Mental developers, staff, and selected community members. The issue
volume is expected to be low and the signal-to-noise ratio high.

### Triage cadence

- **Daily:** A maintainer reviews all new `steam` issues filed in the past 24 hours.
- **Weekly:** A triage sync reviews all open `steam` issues without a milestone or assignee.

### Triage steps

1. **Confirm the template was used.** Issues filed without a Steam template
   and lacking the required fields (OS, hardware, app version) should be
   labelled `needs-info` and a comment should request the missing data.

2. **Classify severity.** Apply one of:

   | Label | Meaning |
   |-------|---------|
   | `severity:critical` | Crash, data loss, or privacy violation — blocks beta continuation |
   | `severity:high` | Core feature broken for a significant fraction of testers |
   | `severity:medium` | Feature degraded but workaround exists |
   | `severity:low` | Minor UI or cosmetic issue |

3. **Route to the right milestone.** Steam private beta issues belong to
   **Milestone 3**. Issues that are pre-existing open-source bugs should be
   relabelled without Steam labels and moved to the appropriate open-source
   milestone.

4. **Assign an owner.** Every `severity:critical` or `severity:high` issue
   must have a named assignee before the triage session closes.

5. **Privacy and safety fast-path.** Issues labelled `privacy` or `safety`
   skip the standard queue and are escalated immediately to the lead
   maintainer regardless of the triage schedule. Issues where the reporter
   selected "Private — please contact me directly" must be moved to a private
   channel (GitHub private vulnerability reporting or direct email) before
   any public response is posted.

### Beta exit criteria

The private beta may not advance to the public release gate (Stage 4) while
any of the following are open:

- Any issue labelled `severity:critical`
- Any `privacy` or `safety` issue not yet resolved or explicitly accepted as
  a known limitation with a documented mitigation
- Any `platform-bug` on a required platform (Windows 10/11, macOS 13+, Linux
  x86-64, Steam Deck) labelled `severity:high` or above

See [steam-mvp-scope.md](steam-mvp-scope.md) for the full pass/fail release
gate checklist.

---

## Public launch triage (Stage 4+)

After the public paid Steam release ($9.99) the reporter pool is the general public.
Issue volume will be higher and the fraction of actionable reports lower.
Apply the following adjustments to the private beta flow.

### Triage cadence

- **Every 48 hours:** A maintainer reviews new `steam` issues for severity
  classification and `needs-info` requests.
- **Weekly:** A triage sync reviews all open `steam` issues without a
  milestone or assignee and closes stale `needs-info` issues that have
  received no response in 14 days.

### Additional routing rules

| Condition | Action |
|-----------|--------|
| Duplicate of an existing open issue | Label `duplicate`, close with a link to the canonical issue. |
| Reproducible only on a non-required platform | Label `platform:unsupported`, note in a comment, defer to post-launch milestone. |
| `model-install` failure on a model not in the registry | Route to the model registry maintainer; label `triage:registry`. |
| `pack-bug` in a community pack (not an official Outright Mental pack) | Confirm the pack source; if community-distributed, close with a pointer to the pack's own repository. |
| `performance` report with no hardware details | Label `needs-info`, request CPU/GPU/RAM and model name/quantisation. |
| `performance` report on hardware below minimum spec | Label `platform:below-spec`, close with a note about minimum requirements and the recommended lower-quantisation model option. |
| `privacy` or `safety` escalation | Same fast-path as private beta — immediate escalation regardless of severity label. |
| Reporter discloses session transcripts or audio in the issue | Add a maintainer comment reminding the reporter that session data is private, advise them to edit the issue or close and re-file without the content, and do not quote the disclosed content in any response. |

### SLA targets (post-launch)

| Severity | First-response target | Fix-or-defer target |
|----------|-----------------------|---------------------|
| `severity:critical` | 24 hours | 72 hours (hotfix or rollback) |
| `severity:high` | 48 hours | Next point release |
| `severity:medium` | 1 week | Next minor release |
| `severity:low` | 2 weeks | Backlog — no hard target |

SLA targets are aspirational during the volunteer-maintained phase and will be
reviewed after 90 days of public release data.

---

## Privacy handling for all stages

Conversation Simulator's local-first promise means session transcripts, audio,
and model outputs are player-private by default. Triage must reinforce this:

- **Never ask reporters to paste transcripts.** If reproducing a bug requires
  session content, ask for a made-up example or a description in general terms.
- **Never quote transcript content** in a maintainer comment, even if the
  reporter included it.
- **Flag accidental disclosure immediately.** If a reporter pastes transcripts
  or audio, add a comment explaining the privacy concern and advise them to
  edit the issue. Do not screenshot, copy, or reference the disclosed content.
- **Private disclosure channel.** For issues labelled `privacy` or where the
  reporter selected "Private" in the disclosure preference field, all
  substantive discussion must move out of the public issue to GitHub private
  vulnerability reporting or direct maintainer contact.

See [privacy.md](privacy.md) for the full local-first data handling policy and
[SECURITY.md](../SECURITY.md) for the security disclosure process.

---

## Links

- [STEAM_ROADMAP.md](STEAM_ROADMAP.md) — release principles and release train
- [steam-mvp-scope.md](steam-mvp-scope.md) — MVP feature requirements and pass/fail gates
- [privacy.md](privacy.md) — local-first data handling details
- [network-security.md](network-security.md) — runtime network enforcement
- [safety-policy.md](safety-policy.md) — content safety policy
- [SECURITY.md](../SECURITY.md) — security vulnerability disclosure
- [publishing/LAUNCH_DAY_RUNBOOK.md](../publishing/LAUNCH_DAY_RUNBOOK.md) — launch day operations, rollback criteria, hotfix workflow
- [publishing/POST_LAUNCH_FEEDBACK_SUMMARY.md](../publishing/POST_LAUNCH_FEEDBACK_SUMMARY.md) — 72-hour feedback summary and next milestone plan
- [.github/workflows/hotfix.yml](../.github/workflows/hotfix.yml) — hotfix branch creation workflow
- [GitHub issue templates](https://github.com/outrightmental/ConversationSimulator/tree/main/.github/ISSUE_TEMPLATE) — all available templates
