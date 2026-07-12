---
title: "Marketplace architecture (future)"
description: "Design baseline for a possible post-launch third-party community-creator content marketplace, covering the entry gate, guiding principles, distribution options, and required system changes. First-party premium DLC is already the chosen paid path (see the DLC model)."
sidebar:
  order: 40
---

> **Status: Post-launch, not launch-blocking.**
> This document describes a possible future **third-party community-creator**
> content marketplace for Conversation Simulator — the open question of letting
> outside creators sell their own packs. First-party premium DLC is a separate,
> already-chosen path (see [DLC model](/dev/dlc-model/)) and is **not** gated by
> this document. Nothing in this document is required for the $9.99 Steam
> release. No community-marketplace code, third-party payment rails, or
> creator-revenue infrastructure should be built before the criteria in the
> [entry gate](#entry-gate-for-any-marketplace-work) are satisfied. Follow-up
> implementation issues must not be created until those criteria are met.

---

## Purpose of this document

The $9.99 Steam release ships with four official packs and community packs that
players install manually (local folder or zip). That is enough for launch.
First-party premium expansion packs ship separately as Steam DLC (see
[DLC model](/dev/dlc-model/)).

This document sketches the post-launch **community-creator** distribution path —
letting outside creators sell their own packs — so that, if that demand is
confirmed after launch, the team has a shared design baseline to work from — not
a blank page. Writing the design now prevents hasty decisions made under
pressure; it does not commit anyone to building the community marketplace.

---

## Entry gate for any marketplace work

No implementation work on the third-party community-creator marketplace — outside
creators selling their own packs — may start until **all** of the following
conditions are met. (First-party Steam DLC is out of scope for this gate; it is
the already-chosen first-party paid path — see [DLC model](/dev/dlc-model/).)

1. The public $9.99 Steam release (Stage 4) has been live for **at least 90 days**.
2. Qualitative player feedback — Steam reviews, community posts, support tickets —
   confirms meaningful demand for additional paid or community content beyond
   what players can install manually today.
3. A legal review of revenue-sharing obligations, VAT/sales-tax treatment for
   digital content, and refund policy requirements is complete.
4. A Valve consultation on Steam Wallet integration and microtransaction
   approval for this title has been conducted and documented.
5. A dedicated safety moderation capacity plan exists — community pack
   review cannot be handled ad-hoc at scale.

Until all five conditions are confirmed in a written post-launch review, this
document is the only community-marketplace artifact in the repository. Do not
create implementation issues, prototypes, or schema changes in anticipation of a
community marketplace that has not yet been validated.

---

## Marketplace principles

The following principles constrain any future marketplace design. They are
written now, before any commercial pressure exists, so that they are harder
to erode under that pressure later.

### Data-only packs first

Conversation Simulator packs are declarative YAML and static assets — no code
runs from a pack. This is not an accidental constraint; it is the safety
boundary that makes community packs feasible on a platform shared with
non-technical players. Any marketplace must distribute only data packs.

The no-executable-plugins rule does not relax until a formally audited sandbox
runtime exists that can run untrusted code without affecting the host OS or
conversation state outside the sandboxed turn. A sandbox of that quality is a
significant engineering effort and is not planned within the current roadmap.
See [No executable plugins](#no-executable-plugins) below.

### Creator attribution

Every pack, paid or free, must carry machine-readable creator attribution in
its manifest. Attribution must be surfaced in-app on the pack card and in the
debrief screen. Attribution cannot be stripped or anonymised by a reseller.

The manifest already has an `author` field. A marketplace would extend this
with a canonical creator identifier (e.g. a creator profile ID) that links
back to the creator's marketplace page.

### License metadata

Every pack distributed through any channel must carry a machine-readable SPDX
license identifier. Paid packs require a commercial license that permits
redistribution via the chosen distribution channel and clarifies whether
derivative works are permitted.

The existing `license` field in `pack.schema.json` covers open-source packs.
Paid packs may use a custom proprietary license identifier; the schema would
need to accept a wider range of values or add a structured `distribution`
block that captures redistribution terms separately from the creative license.

### Safety review before distribution

Any pack distributed through an Outright Mental-operated channel — whether free
or paid — must pass safety review before it appears to players. The review
process must include:

- Automated validation (`convsim validate-pack`) passing with zero errors.
- Automated prompt-injection and content-scan checks (already implemented in
  the pack-loader; would be run server-side at submission time).
- Human review of all NPC personas, scenario goals, rubric dimensions, and
  safety policy files to confirm they meet the content rating declared by the
  pack author.
- Content rating re-verification for any update that touches personas, safety
  policies, or scenario text.

Packs distributed through channels that Outright Mental does not operate (e.g.
itch.io, GitHub) are the author's responsibility. The validator is open-source
and available for authors to run locally, but Outright Mental does not guarantee
the safety of third-party-distributed packs and must say so clearly in the UI
whenever a player loads a non-official pack.

### Pack signing

Pack signing is the mechanism that lets the app verify a pack has not been
tampered with since it was reviewed and approved. A signed pack carries a
detached cryptographic signature over its content hash. The app verifier
checks the signature at load time and refuses to load a pack whose signature
does not match.

Signing is a prerequisite for a trust-tiered pack browser (official →
Outright Mental-curated → community-reviewed → unsigned). Without signing,
there is no reliable way to distinguish a pack that was reviewed from one that
was modified after review.

The current pack-loader has no signing support. Adding it requires:

- A signing key pair managed by Outright Mental (or a delegated creator CA).
- A `signatures/` directory or embedded signature block in the pack manifest.
- A signature verification step in `loadPack()` in
  [`packages/pack-loader/src/loader.ts`](https://github.com/outrightmental/ConversationSimulator/blob/main/packages/pack-loader/src/loader.ts).
- A UI affordance that shows the pack's trust tier and, for unsigned packs,
  a clear warning.

### Versioning

Pack versioning must be explicit and semantically meaningful. The existing
`version` field (SemVer) is sufficient for community packs. A marketplace
adds the following requirements on top:

- **Changelog** — paid pack updates must include a machine-readable changelog
  entry so players can decide whether to apply an update.
- **Rollback** — players who purchased a pack must be able to roll back to the
  version they purchased if an update breaks their workflow. The distribution
  infrastructure must retain prior versions.
- **Breaking-change signalling** — a major-version bump (1.x.x → 2.x.x) must
  trigger a manual review cycle before distribution, because major version
  bumps may change safety policy or content rating.

### Refunds and support

Any paid content path requires a refund policy. Steam's refund rules apply to
all Steam purchases; Outright Mental cannot override Valve's refund window.
Beyond Steam refunds:

- Players who experience a content policy violation in a paid pack — e.g. the
  pack produces content that violates the declared content rating — must have
  a clear in-app reporting path.
- Outright Mental must commit to response SLAs for content-violation reports
  before any paid pack goes live.
- Packs removed for policy violations must result in an automatic refund to all
  purchasers, regardless of whether Valve's refund window has expired.

### No executable plugins

The pack schema explicitly rejects any manifest that declares a `scripts`
field. This prohibition must remain in place indefinitely unless a formally
audited plugin sandbox ships. A plugin sandbox must:

- Run untrusted code in a fully isolated OS process with no filesystem access
  outside a designated per-session scratch directory.
- Enforce a strict API surface for the plugin to call (turn data in, turn
  data out — no direct LLM access, no session state mutation outside the
  declared API).
- Pass a third-party security audit before any plugin-capable build ships to
  players.
- Be disabled by default; players must explicitly enable plugin execution.

This is the same bar as a browser extension host. It is not a small amount
of work, and it should not be started until the core marketplace (data-only
packs) is proven.

---

## Distribution path comparison

Four distribution paths have been identified. They are not mutually exclusive,
but each carries a different set of tradeoffs. **Option A (Steam DLC) is already
the chosen path for first-party premium packs** (see [DLC model](/dev/dlc-model/));
the remaining options are compared for the still-deferred third-party
community-creator marketplace, so that when the entry gate is open the team can
choose quickly.

### Option A — Steam DLC

Steam supports paid downloadable content attached to a base game. Each DLC
is a separate Steam product with its own store page, price, and depot.

**This is the chosen, in-scope path for first-party premium content — not
deferred.** Premium scenario-pack expansions are authored in a private repo and
sold as Steam DLC, with ownership verified through Steamworks. See the
[DLC model](/dev/dlc-model/) for the full public-repo → Steam-DLC contract. The
table below and Options B–D remain the comparison for the still-deferred
third-party community-creator marketplace.

| Dimension | Assessment |
|-----------|------------|
| **Player friction** | Low — integrated into the Steam client players already have. |
| **Revenue share** | Valve takes 30% (25% above $10M LTD, 20% above $50M LTD). |
| **Approval overhead** | Each DLC requires Valve review; turnaround is days to weeks. |
| **Refund policy** | Governed by Steam's standard refund rules (2-week / 2-hour window). |
| **Content moderation** | Outright Mental reviews before submission; Valve reviews at submission. |
| **Versioning / updates** | Steam depot updates; Valve review may be required for significant content changes. |
| **Creator revenue share** | Not natively supported — Outright Mental pays creators separately. |
| **Free-tier coexistence** | DLC items are invisible to players who have not purchased them. Official packs remain free. |
| **Community packs** | Not practical — individual community creators cannot submit their own DLC. |

**Best fit for:** Outright Mental first-party expansion packs (e.g. an advanced
professional skills bundle, a language-learning expansion). Not suited to a
community creator ecosystem.

### Option B — In-game item store using Steam Wallet

Steam's in-game purchasing API lets the app sell virtual items (here: pack
licenses) using Steam Wallet funds without leaving the game client.

| Dimension | Assessment |
|-----------|------------|
| **Player friction** | Low — no external checkout; Steam Wallet is already funded for many players. |
| **Revenue share** | Valve takes 30% of all microtransaction revenue. Additional fee for the Steam Wallet API integration (~$5,000 application fee as of 2024, subject to change). |
| **Approval overhead** | Title must apply for and receive Valve's microtransaction approval before any in-game purchase is possible. Approval is not guaranteed and typically requires a live game with a player base. |
| **Refund policy** | Valve's microtransaction refund rules apply; they differ from game purchase refunds. Outright Mental must also publish its own refund policy for content violations. |
| **Content moderation** | Full Outright Mental review pipeline plus Valve's content compliance review for any items added to the store. |
| **Versioning / updates** | Decoupled from Steam depots; pack content can be updated without a Valve submission if the item listing itself does not change. |
| **Creator revenue share** | Must be implemented by Outright Mental outside Steam — Valve only settles with Outright Mental. |
| **Free-tier coexistence** | Unlocked packs appear in the player's library alongside free packs. |
| **Community packs** | Possible — Outright Mental could curate community submissions and list them in the store, paying creators their share from the Valve settlement. Complex operationally. |

**Best fit for:** A first-party curated store with a small number of premium
packs. Requires significant legal and operational infrastructure before launch.

### Option C — External open pack registry

An open pack registry is a web service (Outright Mental-operated or
community-operated) that hosts pack metadata and download URLs. Players browse
and install packs from within the app or via the CLI.

| Dimension | Assessment |
|-----------|------------|
| **Player friction** | Medium — requires an account if packs are paid; friction-free if all packs are free. |
| **Revenue share** | Outright Mental keeps 100% of Valve cut — but must handle payment processing, VAT, refunds, and fraud directly. Payment processor fee (~3%). |
| **Approval overhead** | Outright Mental controls the review pipeline entirely. Faster iteration; higher internal burden. |
| **Refund policy** | Outright Mental's own policy; must comply with applicable consumer law (EU 14-day right of withdrawal, etc.). |
| **Content moderation** | Outright Mental is the sole gatekeeper. Scale is the constraint — a successful registry may receive hundreds of pack submissions. |
| **Versioning / updates** | Fully under Outright Mental's control. Pack authors push updates; the registry notifies the app. |
| **Creator revenue share** | Configurable — Outright Mental can set any revenue split (e.g. 70/30, 80/20). Must handle tax reporting for creator payouts. |
| **Free-tier coexistence** | Free packs and paid packs coexist in the same registry. Free packs require no account. |
| **Community packs** | Native — designed for community packs. |

**Best fit for:** A community pack ecosystem with both free and paid content.
Higher operational complexity than Steam DLC but more flexibility and no Valve
cut. Requires significant infrastructure: CDN, payment processing, identity,
tax, fraud detection.

### Option D — Curated first-party packs only (no marketplace)

Outright Mental publishes additional packs as free content on GitHub, or as
low-cost purchases through Stripe or a similar checkout — one pack at a time,
manually curated, no in-app browser.

| Dimension | Assessment |
|-----------|------------|
| **Player friction** | High for paid packs (external checkout, manual install). Low for free GitHub packs. |
| **Revenue share** | Stripe fee (~2.9% + $0.30). No Valve cut. |
| **Approval overhead** | Zero — Outright Mental controls every pack. |
| **Refund policy** | Stripe and consumer law only. |
| **Content moderation** | Built into the Outright Mental content authoring process. |
| **Versioning / updates** | GitHub releases or direct file hosting. Manual player update. |
| **Creator revenue share** | Not applicable — no community creators. |
| **Free-tier coexistence** | All free. |
| **Community packs** | Not applicable. |

**Best fit for:** Deferring the marketplace problem entirely while testing
whether players will pay for additional content at all. Lowest complexity and
risk; can be done with zero infrastructure changes.

---

## What must change before any paid content ships

This section catalogues every system that would need to change before an outside
creator's paid pack could ship through a **community marketplace**, regardless of
which distribution path is chosen for it. First-party Steam DLC (see
[DLC model](/dev/dlc-model/)) is already covered and does not require this
infrastructure. It is intended as a scope estimate, not a design specification.

### Schema changes

The pack manifest schema ([`schemas/pack.schema.json`](https://github.com/outrightmental/ConversationSimulator/blob/main/schemas/pack.schema.json))
would need the following additions for marketplace-distributed packs:

| Addition | Purpose |
|----------|---------|
| `creator_id` | Canonical creator identifier linking to the registry or creator profile. |
| `marketplace_id` | Registry-assigned listing ID; used for purchase verification and update routing. |
| `signature` block | Embedded or referenced detached signature for trust verification. |
| `distribution` block | Commercial license terms: `proprietary`, `open`, or `licensed`; sublicensing rights; derivative work permission. |
| `changelog_ref` | Relative path to a machine-readable changelog file. |
| `min_app_version` | Already exists as optional. Would become required for marketplace packs to guarantee compatibility. |

The `license` field would need a broader value set or move to a structured
object to accommodate proprietary distribution licenses alongside SPDX
identifiers.

### Pack signing

New components required:

- **Signing key infrastructure** — key pair generation, rotation policy,
  revocation list. Outright Mental holds the signing key; community creators
  may receive delegated signing certificates if a creator CA is implemented.
- **`packages/pack-loader/src/verifier.ts`** — new module implementing
  signature verification over the content hash. Called from `loadPack()`.
- **CLI command `convsim sign-pack`** — for Outright Mental use in the
  release pipeline; not exposed to community creators directly.
- **Trust tier enum** — `official | curated | community | unsigned` — surfaced
  in the UI and stored in the pack index.

### Moderation infrastructure

Before community pack submissions open:

- **Submission portal** — web form or API where creators submit a pack zip
  for review. Must be authenticated (creator account required).
- **Automated pre-screening pipeline** — server-side run of `convsim validate-pack`
  and the injection scanner before a pack enters the human review queue.
- **Human review queue** — tooling for reviewers to inspect pack content, flag
  concerns, and approve or reject. Must retain audit logs of every review
  decision.
- **Review SLA** — published turnaround time. Community creators need
  predictability; an undefined SLA is a blocker for building a creator community.
- **Appeals process** — rejected packs must have a path to appeal. The appeals
  process must be documented before moderation opens.

### Payment infrastructure

For any paid path:

- **Payment processing** — Stripe, Paddle, or equivalent if using Option C or D.
  Valve handles payment for Options A and B.
- **VAT / sales tax** — Digital products sold in the EU require VAT
  collection and remittance. Paddle handles this automatically (merchant of
  record model); Stripe requires a separate tax solution.
- **Fraud detection** — Chargeback fraud on digital content is common.
  A fraud detection layer or a processor with built-in fraud tools is required.
- **Purchase verification API** — the app must verify at pack load time
  that the player has a valid licence for a paid pack. This verification must
  work offline for packs the player has already downloaded; online verification
  is only required at first install.
- **Receipts and invoices** — business players and EU consumers may require
  itemised VAT invoices.

### Revenue share

Before paying community creators:

- **Creator accounts** — identity verification sufficient for tax reporting
  (name, address, tax ID or equivalent).
- **Tax forms** — W-9 (US creators), W-8BEN (non-US creators), and equivalent
  forms for other jurisdictions.
- **Payout infrastructure** — Stripe Connect or equivalent. Minimum payout
  thresholds must be documented to avoid micro-payouts that cost more to
  process than they're worth.
- **Revenue share agreement** — a published, legally reviewed document that
  specifies the split, payment schedule, adjustment rights, and termination
  conditions. Must be accepted by creators before their packs go live.

### Reporting

For platform health and creator accountability:

- **Sales reporting for creators** — creators must be able to see install counts
  and revenue earned per pack, per time period. This requires an analytics
  pipeline that does not violate the local-first promise: aggregate purchase
  data is collected server-side at the time of purchase; no in-app telemetry
  is needed.
- **Content violation reporting** — players must be able to report a pack for
  content policy violations from within the app. Reports must route to the
  moderation queue.
- **Takedown and refund automation** — when a pack is removed for a policy
  violation, all purchasers must be automatically refunded and the pack must
  be removed from their libraries. This must be automatic, not manual.

---

## Explicitly deferred: not required for the $9.99 Steam release

The following are **confirmed out of scope** for the Milestone 4 public $9.99
Steam release. No code, schema change, or infrastructure for any of these
items may be merged before the entry gate conditions are satisfied. (First-party
Steam DLC is a separate, already-chosen path — see [DLC model](/dev/dlc-model/).)

| Item | Deferred to |
|------|-------------|
| In-app pack browser with paid listings | Stage 5 (post-launch) |
| Steam Wallet integration / microtransaction API | Stage 5, if validated |
| External pack registry with payment processing | Stage 5, if validated |
| Pack signing infrastructure | Stage 5, if validated |
| Creator accounts and revenue share agreements | Stage 5, if validated |
| Community pack submission portal | Stage 5, if validated |
| Sales and install reporting for creators | Stage 5, if validated |
| Automated refund-on-takedown pipeline | Stage 5, if validated |
| Plugin sandbox runtime | Beyond Stage 5; requires separate design and audit |

The four official packs (Job Interview Basics, Everyday Negotiation, Language
Café, Difficult Conversations) ship free and are available at launch without
any marketplace infrastructure.

---

## Follow-up issues

No follow-up implementation issues will be created from this document before
the entry gate is satisfied. The entry gate requires 90 days of public release
data plus confirmed player demand, legal review, Valve consultation, and a
moderation capacity plan.

When those conditions are met, the spike defined in
[`docs/marketplace-demand-spike.md`](/dev/marketplace-demand-spike/) is used to
collect signals, interview creators, and produce a structured recommendation.
That spike document — not this document — defines the specific work scope based
on what the data shows. Options B through D above are starting points for that
review, not committed decisions; Option A (Steam DLC) is already the committed
first-party paid path (see [DLC model](/dev/dlc-model/)).

---

## Links

- [`docs/marketplace-demand-spike.md`](/dev/marketplace-demand-spike/) — Stage 5 research spike: signal collection, creator survey, constraint revisit, and go/no-go recommendation
- [`docs/STEAM_ROADMAP.md`](/dev/steam-roadmap/) — release train: Stage 5 is the marketplace exploration milestone
- [`docs/steam-mvp-scope.md`](/dev/steam-mvp-scope/) — what is required for the $9.99 Steam release
- [`docs/DLC_MODEL.md`](/dev/dlc-model/) — the chosen first-party paid path: premium scenario-pack expansions shipped as Steam DLC from a private repo
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk SP-05: first-party Steam DLC path for premium scenario packs (IN PROGRESS); only Steam Wallet microtransactions and a third-party creator marketplace remain deferred
- [`docs/safety-policy.md`](/trust/safety-policy/) — content policy that any marketplace pack must satisfy
- [`docs/privacy.md`](/trust/privacy/) — local-first promise that marketplace infrastructure must not break
- [`schemas/pack.schema.json`](https://github.com/outrightmental/ConversationSimulator/blob/main/schemas/pack.schema.json) — current pack manifest schema; see [Schema changes](#schema-changes) above for what would be added
- [`packages/pack-loader/src/loader.ts`](https://github.com/outrightmental/ConversationSimulator/blob/main/packages/pack-loader/src/loader.ts) — pack loading and security scanning; see [Pack signing](#pack-signing) above for additions
- [`ROADMAP.md`](/project/roadmap/) — UGC ecosystem section lists in-app pack browser and pack signing as future work outside MVP
