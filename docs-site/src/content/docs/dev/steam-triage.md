---
title: "Steam issue triage"
description: "How incoming issues against the Steam edition are triaged, classified, and routed during private beta and after public launch."
sidebar:
  order: 34
---

> **Purpose of this document:** Define how incoming issues filed against the
> Steam edition are triaged and routed during private beta and after public
> launch. Maintainers and beta coordinators should follow this document when
> processing the issue queue.

---

## Issue templates and labels

Six issue templates cover Steam-specific report categories. Each one sets the
issue **Type** and the area labels it already knows, so a report arrives
pre-classified on the two axes a reporter cannot be asked about.

| Template | Type | Area labels | Use when |
|----------|------|-------------|----------|
| Steam — platform bug | Bug | `area:steam` | Launcher, Steam overlay, controller navigation, Steam Deck, code-signing, or platform-specific crash |
| Steam — local model install failure | Bug | `area:steam`, `area:models` | Model Manager download, checksum verification, or model-load failures |
| Steam — pack validation or content bug | Bug | `area:steam`, `area:packs` | Schema error, broken scenario, incorrect scoring, or content rating mismatch |
| Steam — performance or frame-rate issue | Bug | `area:steam` | Slow inference, high CPU/GPU usage, long load times, audio stuttering, or UI frame-rate problems |
| Steam — privacy or safety report | Bug | `area:safety`, `area:steam` | Unexpected network activity, data written outside `~/.convsim/`, or content safety violations |
| Steam — Creator Workbench bug | Bug | `area:steam`, `area:packs` | Pack authoring, scenario editing, asset management, or Workbench-specific crashes |

General (non-Steam) templates remain available for bugs that reproduce in the
open-source build.

The complete label set is declared in
[`.github/project-structure.yml`](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/project-structure.yml)
and tabulated in
[CONTRIBUTING.md → Labels, fields, and milestones](https://github.com/outrightmental/ConversationSimulator/blob/main/CONTRIBUTING.md#labels-fields-and-milestones).
There are no severity or priority labels: urgency is the board's **Priority**
field, which is what the steps below set. Nothing below asks for a label
outside that declared set either — triage records its decisions in Type,
Priority, the milestone, and comments, because a new label is a change to the
manifest and has to be proposed in an issue first.

---

## Private beta triage (Stage 3)

During the Steam private beta the reporter pool is limited to invited testers:
Outright Mental developers, staff, and selected community members. The issue
volume is expected to be low and the signal-to-noise ratio high.

### Triage cadence

- **Daily:** A maintainer reviews all new `area:steam` issues filed in the past 24 hours.
- **Weekly:** A triage sync reviews all open `area:steam` issues without a milestone or assignee.

### Triage steps

1. **Confirm the template was used.** Issues filed without a Steam template
   and lacking the required fields (OS, hardware, app version) get a maintainer
   comment requesting the missing data. There is no `needs-info` label — the
   comment is the record, and the issue waits in the queue until the data
   arrives.

2. **Set the Priority.** Severity is the board's **Priority** field, not a
   label:

   | Priority | Meaning |
   |----------|---------|
   | P0 — blocker | Crash, data loss, or privacy violation — blocks beta continuation |
   | P1 — next | Core feature broken for a significant fraction of testers |
   | P2 — later | Feature degraded but a workaround exists, or a minor UI or cosmetic issue |

3. **Route to the right milestone.** Every open issue belongs to exactly one
   release train, so a beta blocker goes on the train shipping next and the
   rest are deferred to a later one; the current trains and their dates are in
   [`.github/project-structure.yml`](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/project-structure.yml).
   Issues that turn out to be pre-existing open-source bugs lose their
   `area:steam` label and move to whichever train fits.

4. **Assign an owner.** Every P0 — blocker or P1 — next issue must have a
   named assignee before the triage session closes.

5. **Privacy and safety fast-path.** Issues labelled `area:safety` skip the
   standard queue and are escalated immediately to the lead maintainer
   regardless of the triage schedule. Issues where the reporter
   selected "Private — please contact me directly" must be moved to a private
   channel (GitHub private vulnerability reporting or direct email) before
   any public response is posted.

### Beta exit criteria

The private beta may not advance to the public release gate (Stage 4) while
any of the following are open:

- Any issue at Priority P0 — blocker
- Any `area:safety` issue not yet resolved or explicitly accepted as a known
  limitation with a documented mitigation
- Any platform bug on a required platform (Windows 10/11, macOS 14+, Linux
  x86-64, Steam Deck) at Priority P1 — next or above

See [steam-mvp-scope.md](/dev/steam-mvp-scope/) for the full pass/fail release
gate checklist.

---

## Public launch triage (Stage 4+)

After the public paid Steam release ($9.99) the reporter pool is the general public.
Issue volume will be higher and the fraction of actionable reports lower.
Apply the following adjustments to the private beta flow.

### Triage cadence

- **Every 48 hours:** A maintainer reviews new `area:steam` issues to set a
  Priority and request missing data.
- **Weekly:** A triage sync reviews all open `area:steam` issues without a
  milestone or assignee and closes issues where a maintainer asked for missing
  data and none arrived within 14 days.

### Additional routing rules

| Condition | Action |
|-----------|--------|
| Duplicate of an existing open issue | Close as a duplicate with a link to the canonical issue. |
| Reproducible only on a non-required platform | Name the platform in a comment and defer to a later release train. |
| Model-install failure on a model not in the registry | Route to the model registry maintainer and link the registry issue. |
| Pack bug in a community pack (not an official Outright Mental pack) | Confirm the pack source; if community-distributed, close with a pointer to the pack's own repository. |
| Performance report with no hardware details | Comment asking for CPU/GPU/RAM and the model name and quantisation. |
| Performance report on hardware below minimum spec | Close with a note about minimum requirements and the recommended lower-quantisation model option. |
| `area:safety` escalation | Same fast-path as private beta — immediate escalation regardless of Priority. |
| Reporter discloses session transcripts or audio in the issue | Add a maintainer comment reminding the reporter that session data is private, advise them to edit the issue or close and re-file without the content, and do not quote the disclosed content in any response. |

### SLA targets (post-launch)

| Priority | First-response target | Fix-or-defer target |
|----------|-----------------------|---------------------|
| P0 — blocker | 24 hours | 72 hours (hotfix or rollback) |
| P1 — next | 48 hours | Next point release |
| P2 — later | 1 week | Next minor release, or the backlog for cosmetic reports |

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
- **Private disclosure channel.** For issues labelled `area:safety` or where the
  reporter selected "Private" in the disclosure preference field, all
  substantive discussion must move out of the public issue to GitHub private
  vulnerability reporting or direct maintainer contact.

See [privacy.md](/trust/privacy/) for the full local-first data handling policy and
[SECURITY.md](/project/security/) for the security disclosure process.

---

## Links

- [STEAM_ROADMAP.md](/dev/steam-roadmap/) — release principles and release train
- [steam-mvp-scope.md](/dev/steam-mvp-scope/) — MVP feature requirements and pass/fail gates
- [privacy.md](/trust/privacy/) — local-first data handling details
- [network-security.md](/trust/network-security/) — runtime network enforcement
- [safety-policy.md](/trust/safety-policy/) — content safety policy
- [SECURITY.md](/project/security/) — security vulnerability disclosure
- [publishing/LAUNCH_DAY_RUNBOOK.md](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/LAUNCH_DAY_RUNBOOK.md) — launch day operations, rollback criteria, hotfix workflow
- [publishing/POST_LAUNCH_FEEDBACK_SUMMARY.md](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/POST_LAUNCH_FEEDBACK_SUMMARY.md) — 72-hour feedback summary and next milestone plan
- [.github/workflows/hotfix.yml](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/workflows/hotfix.yml) — hotfix branch creation workflow
- [GitHub issue templates](https://github.com/outrightmental/ConversationSimulator/tree/main/.github/ISSUE_TEMPLATE) — all available templates
