<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Marketplace Demand Spike — Post-Launch Validation

> **Status: Stage 5 research milestone. Not launch-blocking.**
> Complete this document after the public paid ($9.99) Steam release (Stage 4) has been
> live for at least 90 days. No implementation work on a marketplace may begin
> until the entry gate in [`docs/marketplace-architecture.md`](marketplace-architecture.md)
> is satisfied and the decision at the end of this document is made.
>
> **Scope:** This spike evaluates demand for a **third-party community-creator
> marketplace** specifically. First-party premium scenario-pack content already
> ships as paid Steam DLC (see [`docs/DLC_MODEL.md`](DLC_MODEL.md)); the question
> here is not whether any paid content should exist, but whether a community-creator
> distribution or marketplace channel is warranted.
>
> **Audience:** Outright Mental team. Share the recommendation section with
> the contributor community when the decision is ready.
>
> **When to complete:**
> - **90-day mark:** Collect all signals listed below and complete sections 1–3.
> - **Decision date:** Complete section 4 (recommendation) based on the signals.
> - **If building:** Complete section 5 (post-launch roadmap) only after the
>   recommendation is to build.

---

## Spike metadata

| Field | Value |
|-------|-------|
| Launch date (UTC) | |
| 90-day mark (UTC) | |
| Spike owner | |
| Decision date | |
| Recommendation | (fill after section 4) |

---

## 1. Telemetry-free signal review

The local-first promise means no usage telemetry is collected during play.
Signal collection is therefore limited to user-visible events and publicly
observable activity. Every signal source is listed below. Complete the counts
and summarise the themes before moving to the creator survey.

### 1.1 Pack downloads and imports

Community pack distribution happens outside the app (GitHub, itch.io, direct
links). Measure what is visible.

| Signal | Measurement method | Count / observation |
|--------|--------------------|---------------------|
| Official pack: GitHub release download count | GitHub API → release asset download count for each pack zip | |
| Community packs: GitHub repos tagged `convsim-pack` | GitHub search `topic:convsim-pack` | |
| Community packs: itch.io items tagged `conversation-simulator` | itch.io browse page | |
| Pack import issues filed on GitHub | `label:pack-bug` issue count | |
| Creator Workbench issues filed | `label:creator-workbench` issue count | |
| Discord `#pack-sharing` or equivalent channel activity | Post count + unique contributors (90-day window) | |

Summary of pack distribution signals:

-
-
-

### 1.2 Creator activity on GitHub

| Signal | Measurement method | Count / observation |
|--------|--------------------|---------------------|
| PRs proposing new official packs | Search PRs with `pack` in title | |
| Issues requesting pack distribution improvements | Label filter + keyword search | |
| Forks of the repository | GitHub fork count delta (launch → 90 days) | |
| Contributors who touched `packs/` | `git log --all -- packs/` unique authors | |
| Scenario authoring guide page views | GitHub Insights (if available) | |

Summary of creator GitHub activity:

-
-
-

### 1.3 Steam reviews and discussions

| Signal | Measurement method | Count / observation |
|--------|--------------------|---------------------|
| Reviews mentioning "pack", "content", or "scenario" | Manual review of Steam review text | |
| Reviews requesting more content | Manual review count | |
| Reviews mentioning "buy", "paid", or "DLC" | Manual review count | |
| Discussion threads on pack creation | Steam forum search | |
| Discussion threads requesting a content browser | Steam forum search | |
| Discussion threads requesting paid content | Steam forum search | |

Notable Steam review and discussion themes:

-
-
-

### 1.4 Discord and community channels

| Channel | Observation period | Summary of creator-relevant activity |
|---------|--------------------|--------------------------------------|
| | 90 days post-launch | |
| | 90 days post-launch | |

Feature requests from community channels (3+ independent voices only):

| Request | Source count | Channels |
|---------|-------------|---------|
| | | |

### 1.5 Qualitative feedback

Summarise any direct qualitative feedback (support email, private messages,
Discord DMs, GitHub issue comments) that reveals creator intent or marketplace
interest. Do not include personally identifiable information.

-
-
-

---

## 2. Creator interview and survey

The goal of this section is to understand creator needs before committing to a
distribution architecture. Conduct structured interviews or a survey with at
least five active pack creators (people who have built or attempted to build a
community pack). Record anonymised summaries here — do not record individual
names or identifying details.

If fewer than five creators have emerged 90 days post-launch, record that
finding explicitly; it is itself a signal that the creator community is not
yet large enough to validate a marketplace.

### 2.1 Interview recruitment

| Recruitment channel | Invites sent | Responses |
|--------------------|-------------|----------|
| Discord direct outreach | | |
| GitHub issue comments | | |
| Steam discussion board post | | |
| Announcement in contributor newsletter / README | | |
| **Total** | | |

Interviews completed: ___

If fewer than 5 interviews were completed, explain why:

### 2.2 Interview guide

Use the following questions as a structured guide. Adapt them for the format
(1:1 call, async written survey, or GitHub discussion thread). Record
anonymised responses under each question.

**Pack creation experience**

1. Describe how you built your pack. What tools did you use? What was your
   biggest friction point?
2. Did you use the `convsim validate-pack` CLI? If not, why not?
3. Did you use the Creator Workbench? What worked well and what did not?
4. How long did your first pack take to go from idea to playable?

**Distribution**

5. How are you currently distributing your pack (GitHub release, itch.io,
   direct link, not yet distributing)?
6. What would make it meaningfully easier for players to find your pack?
7. Would you want your pack listed in an in-app browser even if it remained
   free? Why or why not?

**Attribution and licensing**

8. Is your pack open-source, proprietary, or something else? Why did you
   choose that license?
9. Does the current `author` field in the pack manifest give you adequate
   attribution? What would you add?
10. Have you had any experience with someone reposting or modifying your
    pack without your permission?

**Moderation expectations**

11. If Outright Mental operated a curated pack registry, how long would you
    expect a review to take before your pack was listed?
12. What content moderation rules do you think should apply to community packs
    distributed through an official channel?

**Monetisation**

13. Would you want the option to charge for your packs? If yes, what price
    point and revenue split would make it worth the effort?
14. If you could not charge for your packs, would that stop you from creating
    them? Why or why not?
15. What would you do with revenue from pack sales — reinvest in more packs,
    cover your time, donate to the project, something else?

### 2.3 Interview summary

Complete after all interviews are done. Summarise across responses, not per
respondent.

**Pack creation experience — themes**

-
-
-

**Distribution needs — themes**

-
-
-

**Attribution and licensing — themes**

-
-
-

**Moderation expectations — themes**

-
-
-

**Monetisation interest — themes**

-
-
-

**Key findings**

(Synthesise the 3–5 most important things learned from creator interviews that
should inform the recommendation)

1.
2.
3.

---

## 3. Constraint revisit

This section revisits the constraints documented in
[`docs/marketplace-architecture.md`](marketplace-architecture.md) in light of
what is now known about the live game and the creator community. Complete after
sections 1 and 2.

### 3.1 Steam Wallet and DLC constraints

| Constraint | Status at 90 days | Notes |
|------------|-------------------|-------|
| Valve microtransaction application submitted | yes / no / not yet | |
| Valve microtransaction approval status | approved / pending / not applied | |
| DLC approval turnaround time (if applicable) | | |
| Steam Wallet integration fee confirmed | yes / no | Current fee as of review date: |
| Steam review SLA documented | | |

Findings:

-
-

### 3.2 Open-source project governance

| Question | Answer |
|----------|--------|
| Does charging for community packs conflict with the CC-BY-4.0 licence on official content? | |
| Are contributor agreements in place that would allow Outright Mental to operate a revenue-sharing marketplace without ambiguity? | |
| Has the community discussed monetisation in public channels? What was the sentiment? | |
| Would a paid marketplace create a two-tier contributor experience that undermines the open-source community? | |

Findings:

-
-

### 3.3 Revenue support goals

| Question | Answer |
|----------|--------|
| How well do base app ($9.99) sales and premium scenario-pack DLC revenue currently cover Outright Mental's development and distribution costs? | |
| Would revenue from a marketplace materially reduce Outright Mental's out-of-pocket distribution costs? | |
| Is there a revenue threshold below which the operational overhead of a marketplace is not worth it? If so, what is that threshold? | |
| Has Outright Mental's board or leadership set a target or constraint on marketplace revenue expectations? | |

Findings:

-
-

### 3.4 Safety review capacity

| Question | Answer |
|----------|--------|
| How many community pack submissions arrived in the first 90 days (if a submission path existed)? | |
| What is the estimated human review time per pack (based on the pack validator + manual check process)? | |
| How many reviewers does Outright Mental currently have available for pack review? | |
| At the observed submission rate, how many packs per month could be reviewed with current capacity? | |
| Would a moderation queue backlog discourage creators from submitting packs? | |

Findings:

-
-

### 3.5 Entry gate status

The five entry gate conditions from
[`docs/marketplace-architecture.md` — Entry gate](marketplace-architecture.md#entry-gate-for-any-marketplace-work)
must all be confirmed before any implementation work begins. Record the status
of each condition here.

| Condition | Status | Evidence |
|-----------|--------|----------|
| 1. Public release live for at least 90 days | met / not yet | Launch date: |
| 2. Qualitative player feedback confirms meaningful demand | confirmed / not confirmed / unclear | |
| 3. Legal review of revenue-sharing, VAT, and refund policy is complete | complete / in progress / not started | |
| 4. Valve consultation on Steam Wallet integration conducted and documented | complete / in progress / not started | |
| 5. Safety moderation capacity plan exists | complete / in progress / not started | |

**Entry gate passed:** yes / no / partial

If not all conditions are met, list what is blocking and what the estimated
completion date is for each open item.

---

## 4. Recommendation

Complete this section after sections 1–3 are done. The recommendation must be
one of the five options below. It requires sign-off from the Outright Mental
platform lead before it is communicated to the contributor community.

### 4.1 Decision framework

Use this framework to select the recommendation. Each question narrows the
option space.

| Question | Answer | Implication |
|----------|--------|-------------|
| Has the entry gate (section 3.5) fully passed? | yes / no | If no: "do not build yet" is the only available recommendation. Return here after the gate conditions are met. |
| Is there evidence of meaningful demand for discoverable content beyond what manual install provides? | yes / no | If no: "do not build yet" is the recommendation. |
| Did any creator express interest in paid content? | yes — strong / yes — weak / no | Weak or no: paid marketplace options are premature. |
| Does Outright Mental have the capacity to review 10+ pack submissions per month? | yes / no | If no: external portal or Steam DLC (no community submissions) are the safer options. |
| Has Valve microtransaction approval been received? | yes / no | Applies only to an in-game Steam Wallet marketplace (Option D). First-party Steam DLC needs Valve's standard DLC review, not microtransaction approval, and already ships. |
| Is the creator community large enough to populate a registry (≥ 10 community packs available or in progress)? | yes / no | If no: first-party options (curated free or Steam DLC) may be sufficient. |

### 4.2 Options

Select one. Options C, D, and E correspond to the paid-distribution
mechanisms analysed in
[`docs/marketplace-architecture.md` — Distribution path comparison](marketplace-architecture.md#distribution-path-comparison)
— Steam DLC, an in-game Steam Wallet store, and an external registry
respectively — but note that document labels those mechanisms differently
(its Options A–D) and does not use the same lettering as the table below.
Options A (do not build yet) and B (curated free registry) are decisions
specific to this spike and are not enumerated in that comparison.

| Option | When to choose |
|--------|---------------|
| **A — Do not build yet** | Entry gate not passed, or demand signals are unclear or weak, or operational capacity is insufficient. The status quo (manual install from GitHub/itch.io) remains in place. Revisit in 6 months. |
| **B — Curated free registry** | Demand for discoverability is confirmed but monetisation interest is weak or absent, and Outright Mental can handle review volume. A simple indexed list of community packs with validator-passed badges. No payment infrastructure required. |
| **C — More Steam DLC packs** | Demand exists for additional premium first-party content, and Outright Mental is willing to commit first-party authoring resources. Steam DLC uses Valve's standard DLC review (no Steam Wallet microtransaction approval needed) — this is the channel first-party premium packs already ship on. Community creator submissions are not part of this option. |
| **D — In-game marketplace** | Strong demand for paid community content confirmed, entry gate fully passed including legal and Valve approvals, and Outright Mental has the moderation capacity and infrastructure budget to operate a marketplace. Highest complexity and highest upside. |
| **E — External creator portal** | Similar demand profile to Option D but Outright Mental prefers to avoid Steam's 30% cut and has the infrastructure capacity to operate an external payment and distribution platform. Requires the most independent infrastructure. |

### 4.3 Selected recommendation

**Recommendation:** (A / B / C / D / E)

**Rationale:** (2–4 sentences explaining why this option was chosen over the
alternatives, citing the specific signals from sections 1–3 that drove the
decision)

**Conditions on the recommendation:** (Any conditions that must be true for
this recommendation to hold — e.g. "Option B is recommended, but if creator
submissions exceed 20/month within 6 months, revisit Option D")

**Next steps if A (do not build yet):**
- [ ] Set a revisit date: ___
- [ ] Define what change in signals would trigger a re-evaluation: ___

**Next steps if B, C, D, or E:**
- [ ] Open implementation issues only after this document is signed off
- [ ] Reference this document and
  [`docs/marketplace-architecture.md`](marketplace-architecture.md) in every
  implementation issue as the design baseline
- [ ] Complete section 5 of this document before opening implementation issues

### 4.4 Sign-off

| Role | Name | Signed | Date |
|------|------|--------|------|
| Platform lead | | ☐ | |
| Outright Mental representative | | ☐ | |

---

## 5. Post-launch roadmap (complete only if recommendation is B, C, D, or E)

If the recommendation is to build, define the next milestone here. This
section becomes the input to a new GitHub milestone and a set of implementation
issues. Do not create those issues until section 4 is signed off.

### 5.1 Milestone description

Describe in 2–3 sentences what Stage 5 will deliver, at what scope, and by
when.

### 5.2 What this milestone will and will not build

| In scope | Out of scope |
|----------|-------------|
| | |
| | |

### 5.3 Implementation issues to open

List every implementation issue that will be created to track Stage 5 work.
Each issue must reference both this document and
[`docs/marketplace-architecture.md`](marketplace-architecture.md) as its
design baseline.

| Issue title | Assigned to | Blocked by | Priority |
|-------------|------------|-----------|---------|
| | | | |
| | | | |

### 5.4 Stage 5 entry criteria

List the concrete conditions that must be true before Stage 5 implementation
begins. These are in addition to the entry gate conditions in
section 3.5, which must already be met.

- [ ]
- [ ]
- [ ]

### 5.5 Stage 5 success criteria

Define what "done" looks like for Stage 5. These become the acceptance criteria
for the Stage 5 milestone.

- [ ]
- [ ]
- [ ]

---

## Links

- [`docs/marketplace-architecture.md`](marketplace-architecture.md) — design baseline: entry gate, distribution path comparison, and scope of schema/signing/moderation/payment changes
- [`docs/STEAM_ROADMAP.md`](STEAM_ROADMAP.md) — release train: Stage 5 is the marketplace exploration milestone
- [`docs/steam-mvp-scope.md`](steam-mvp-scope.md) — what shipped in Stage 4; the post-launch baseline
- [`publishing/POST_LAUNCH_FEEDBACK_SUMMARY.md`](../publishing/POST_LAUNCH_FEEDBACK_SUMMARY.md) — 72-hour and two-week launch feedback; primary source for section 1
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk SP-05 (first-party Steam DLC path for premium scenario packs)
- [`docs/safety-policy.md`](safety-policy.md) — content policy any marketplace pack must satisfy
- [`docs/privacy.md`](privacy.md) — local-first promise that marketplace infrastructure must not break
- [`docs/scenario-authoring.md`](scenario-authoring.md) — creator documentation; starting point for section 2 recruits
- [`schemas/pack.schema.json`](../schemas/pack.schema.json) — current pack manifest schema
