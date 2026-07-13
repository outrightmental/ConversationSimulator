<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Store Page Copy

> **Purpose:** Canonical store copy for the Conversation Simulator Steam page.
> All text in this document must be approved by Outright Mental before it is
> entered into the Steamworks partner portal. When the copy is live or scheduled,
> record the approval date in the [sign-off table](#sign-off) at the bottom.
>
> **Audience:** Publishing team, copywriter, Outright Mental staff, and any
> Valve reviewer who requests source copy.
>
> **Constraints enforced here:**
> - No language claiming AI therapy, diagnosis, or legal advice (gate G4-04).
> - No implied marketplace or paid content (gate G4-04, SP-05).
> - Local-first and privacy-first copy must be factually accurate (PR-01–PR-03).
> - Content-boundary statements must match the safety policy in
>   [`schemas/safety.schema.json`](../schemas/safety.schema.json).
> - Steam Deck notes must reflect the state of AU-03 (text-only fallback).

---

## App title

```
Conversation Simulator
```

---

## Short description

Steam short descriptions are displayed in search results and store capsules.
Limit: **300 characters**.

```
Conversation Simulator is the practice tool for interviews, negotiations,
difficult talks, and language skills. AI characters run entirely on your
computer. No internet needed during play. Premium scenario packs available.
```

Character count: 222. Within the 300-character limit.

---

## Long description

This is the full store page body. Enter it as HTML in the Steamworks rich text
editor. The structure mirrors Steam's recommended layout: hook → what you do →
features → privacy pitch → content boundaries → system note → free edition
statement.

```html
<h2>Conversation Simulator is the simulator for conversations.</h2>

<p>
  Conversation Simulator is a free, local-first practice tool that lets you
  rehearse real-life conversations before they happen. Choose a scenario, talk
  to an AI character running entirely on your computer, watch the situation
  evolve, and review what went well — or what you would say differently next
  time.
</p>

<p>
  No judgment. No audience. No internet connection during play. Just the
  scenario, the AI, and you.
</p>

<h2>What you do</h2>

<p>
  Pick a scenario from the built-in packs, type or speak your lines, and
  respond to an AI character whose reactions evolve based on how the conversation
  unfolds. After the session, you get a scored debrief: what you said clearly,
  where you hedged, and the moments that changed the dynamic.
</p>

<h2>Built-in scenario packs</h2>

<ul>
  <li>
    <strong>Job Interview Basics</strong> — Four interview styles from a
    friendly HR screen to a hostile executive gauntlet. Practice giving specific
    answers under real pressure without the cost of a bad first impression.
  </li>
  <li>
    <strong>Everyday Negotiation</strong> — Negotiate a used car price, push
    back on a lease renewal, handle freelance scope creep, and resolve a customer
    service dispute. Build the habit of advocating for yourself.
  </li>
  <li>
    <strong>Difficult Conversations</strong> — Give honest feedback to a
    coworker, apologise for a missed deadline, set a limit with a friend, and ask
    for a raise. Build the clarity and composure that most people only find in
    hindsight.
  </li>
  <li>
    <strong>Language Café</strong> — Practice Spanish, French, Japanese, and
    English through low-stakes everyday conversations: ordering coffee, checking
    into a hotel, shopping at a convenience store. Optional gentle correction
    included.
  </li>
</ul>

<h2>Key features</h2>

<ul>
  <li>
    <strong>Everything runs on your computer.</strong> The AI model runs locally
    using llama.cpp. No cloud inference, no API keys, no subscription required
    to use the core features. An internet connection is required only for the
    initial model download — not during play.
  </li>
  <li>
    <strong>Text and voice.</strong> Type your lines or speak them aloud using
    local speech recognition (Whisper). The AI character responds in text, or
    with synthesised speech via a local TTS engine (Kokoro). Voice is entirely
    optional — text mode works everywhere, including Steam Deck.
  </li>
  <li>
    <strong>Scored debrief after every session.</strong> Each scenario has a
    rubric. After you end a session, you get a breakdown of your performance:
    scores by dimension, key turning points, and a transcript you can review.
  </li>
  <li>
    <strong>Creator Workbench.</strong> Build your own scenario packs in YAML.
    Define the NPC, the opening situation, the state variables that evolve during
    the conversation, and the rubric by which your answers will be scored. Share
    your packs with other players.
  </li>
  <li>
    <strong>Choose your AI model.</strong> The Model Manager lets you download
    and switch between open-weight language models. Smaller models (4B parameters)
    run on most machines. Larger models produce more natural, context-aware
    responses. You pick the trade-off.
  </li>
</ul>

<h2>Your conversations stay on your computer</h2>

<p>
  Conversation Simulator is built on a local-first architecture. During play,
  nothing is transmitted to any server — no transcripts, no audio, no model
  outputs, no usage events. Your conversation history is stored only in a
  database on your own machine at <code>~/.convsim/</code>. You can clear it
  at any time from the Settings screen.
</p>

<p>
  There is no crash reporter, no analytics SDK, and no background ping in the
  release build. The offline smoke test — a CI gate that runs on every
  commit — fails the build if any outbound TCP connection occurs during a play
  session.
</p>

<h2>Content boundaries</h2>

<p>
  This tool is rated <strong>PG to PG-13</strong> across all built-in packs.
  The built-in safety policy enforces the following hard limits — they apply to
  all packs, including community packs, and cannot be disabled:
</p>

<ul>
  <li>No NSFW sexual content.</li>
  <li>No sexual or romantic content involving minors — absolute prohibition.</li>
  <li>No real-person impersonation.</li>
  <li>No voice cloning or audio deepfakes.</li>
  <li>
    No claims of clinical authority: the AI can play a professional in a
    practice context but will not position itself as a real therapist, doctor,
    or lawyer.
  </li>
  <li>
    Self-harm crisis content is intercepted and replaced with a resource
    message — this rule cannot be overridden by any pack.
  </li>
</ul>

<p>
  Conversation Simulator is a <em>practice tool</em>, not a therapy service,
  a mental-health app, or a clinical resource. If you are in crisis, please
  contact a qualified professional or a crisis helpline.
</p>

<h2>Steam Deck</h2>

<p>
  Conversation Simulator runs on Steam Deck in both Gaming Mode and Desktop
  Mode. The on-screen keyboard works for all text input. Text-only mode
  (no microphone required) is fully supported. Voice input requires an
  external USB-C or Bluetooth microphone, which is not included with the
  Steam Deck. Smaller AI models (4B parameters) are recommended for the
  Steam Deck's shared RAM configuration.
</p>

<h2>Pricing</h2>

<p>
  Conversation Simulator is $9.99. The base app includes four complete
  scenario packs — Job Interview Basics, Everyday Negotiation, Difficult
  Conversations, and Language Café — with no time limits, no subscriptions,
  and no pay-to-unlock restrictions on the included content.
</p>

<p>
  Optional premium scenario packs are available as DLC at additional cost.
  The source code is open and available on GitHub. Community-created scenario
  packs can be installed manually and shared freely.
</p>
```

---

## Feature bullets

Steam allows up to five feature bullets in the "About This Game" sidebar.
These must be short — one clause each.

```
• AI characters run entirely on your computer — no cloud, no API keys
• Practice job interviews, negotiations, and difficult conversations
• Scored debrief after every session with turn-by-turn analysis
• Text mode and optional local voice I/O (Whisper STT + Kokoro TTS)
• Premium scenario-pack DLC and free community packs supported
```

---

## Local-first privacy copy

This is the authoritative privacy statement for the store page and any
supplemental privacy notices submitted to Valve. It must remain consistent
with [`docs/privacy.md`](../docs/privacy.md).

```
During play, Conversation Simulator does not transmit data of any kind to
any server. This includes:

  - Conversation text and transcripts
  - Voice audio (raw microphone input and TTS output)
  - AI model outputs
  - Session history and scores
  - Usage events and analytics

All processing happens on your computer. Conversation history is stored in
a local SQLite database at ~/.convsim/db/sessions.db (Windows:
%USERPROFILE%\.convsim\db\sessions.db). You can view, export, or permanently delete your session history
from the Settings screen at any time.

The release build contains no crash reporter, telemetry SDK, or background
network service. An internet connection is required only for the initial
model download and for any community pack you choose to install manually —
not during play.
```

---

## Content boundaries (store page version)

This is the short-form content-boundaries statement for the store page
"Content Descriptors" and any Valve content review questionnaire.

### What this game contains

- Simulated interpersonal conflict in professional and social contexts
- Mild workplace language appropriate to the scenario (e.g. a tense
  performance-review conversation)
- Optional local voice output using a synthetic TTS voice
- Scenarios involving emotionally challenging topics (e.g. apologising for
  a mistake, delivering critical feedback) handled at a PG/PG-13 level

### What this game does not contain

- Sexual content of any kind
- Violence or depictions of physical harm
- Real people or their likenesses
- Gambling or simulated gambling
- Horror or jump-scare content
- Substances or drug references
- Clinical mental-health treatment, therapy, diagnosis, or medical advice

---

## Pricing wording

Use this copy wherever the pricing model needs to be stated explicitly
(store description, FAQ, press kit).

```
Conversation Simulator is $9.99.

The base app includes four complete scenario packs — Job Interview Basics,
Everyday Negotiation, Difficult Conversations, and Language Café — with no
time limits and no subscriptions. There is no paywall in front of the
included content after purchase.

Optional premium scenario packs are sold separately as Steam DLC. Community
packs can be installed manually and are distributed outside the app by their
authors — the app itself does not host or sell community content.
```

---

## System requirements

Enter these into the Steamworks system requirements section. Use the
Minimum column for the base requirement and the Recommended column for a
comfortable experience with larger AI models.

### Windows

| | Minimum | Recommended |
|-|---------|-------------|
| **OS** | Windows 10 (64-bit) | Windows 11 (64-bit) |
| **Processor** | Intel Core i5 (6th gen) or AMD Ryzen 5 (1000 series) | Intel Core i7 (10th gen+) or AMD Ryzen 7 (3000 series+) |
| **Memory** | 8 GB RAM | 16 GB RAM |
| **Storage** | 500 MB for the app; 2–8 GB per AI model (downloaded separately) | 500 MB for the app; 8–20 GB for a larger model |
| **Sound Card** | Not required for text mode; any microphone-capable sound card for voice input | — |
| **Additional Notes** | No dedicated GPU required. Model inference runs on CPU. A GPU with Vulkan support can accelerate some models. Internet required for initial model download only. | |

### macOS

| | Minimum | Recommended |
|-|---------|-------------|
| **OS** | macOS 13 Ventura | macOS 14 Sonoma or later |
| **Processor** | Apple M1 or Intel Core i5 (8th gen) | Apple M2 or later |
| **Memory** | 8 GB RAM | 16 GB unified memory |
| **Storage** | 500 MB for the app; 2–8 GB per AI model | 500 MB for the app; 8–20 GB for larger models |
| **Additional Notes** | Apple Silicon Macs run local models significantly faster than Intel Macs due to unified memory architecture. Gatekeeper notarisation required — install via the official .dmg only. | |

### Linux

| | Minimum | Recommended |
|-|---------|-------------|
| **OS** | Ubuntu 22.04 LTS or Fedora 40 (x86-64, glibc 2.35+) | Ubuntu 24.04 LTS or Fedora 41 |
| **Processor** | Intel Core i5 or AMD Ryzen 5 | Intel Core i7 or AMD Ryzen 7 |
| **Memory** | 8 GB RAM | 16 GB RAM |
| **Storage** | 500 MB for the app; 2–8 GB per AI model | 500 MB for the app; 8–20 GB for larger models |
| **Additional Notes** | Flatpak or AppImage distribution. No root access required during play. | |

### SteamOS / Steam Deck

> Add these as additional notes in the Linux system requirements section.

```
Steam Deck: Text mode runs without a microphone. Voice input requires an
external USB-C or Bluetooth microphone (not included). Smaller AI models
(4B parameters, approx. 2–3 GB) are recommended for the Steam Deck's shared
RAM. Models should be stored on the SD card or internal storage — a minimum
of 8 GB of free space is needed. All features, including the Creator
Workbench and Model Manager, are accessible in Gaming Mode using the
on-screen keyboard and controller navigation.
```

---

## Steam genres and tags

### Primary genre

Select **Simulation** as the primary genre. This is the most accurate
single-word description of what the app does: it simulates conversations.

### Secondary genre

Select **Casual** as the secondary genre. The app is approachable, non-violent,
and requires no prior gaming skill.

### Steam store tags

Apply the following tags in the Steamworks partner portal. Tags are listed
in priority order — apply the first ten if Valve's tag picker limits the
count.

| Priority | Tag | Rationale |
|----------|-----|-----------|
| 1 | Singleplayer | All scenarios are single-player. |
| 2 | Simulation | Core mechanic: simulated conversation. |
| 3 | Education | Explicit skill-building goal in every scenario. |
| 4 | Indie | Outright Mental is an independent studio. |
| 5 | Casual | No combat, no violence, low barrier to entry. |
| 6 | Text-Based | Text is the primary interaction mode. |
| 7 | Life Sim | Simulates real-life social situations. |
| 8 | Social Sim | Specifically simulates social interactions. |
| 9 | Artificial Intelligence | Local AI inference is a core component. |
| 10 | Interactive Fiction | Player choices drive the narrative state. |
| 11 | Language Learning | Language Café pack targets language practice. |
| 12 | Choices Matter | NPC state evolves based on player responses. |
| 13 | Relaxing | Low-stakes, no time pressure, no fail state. |

**Tags to avoid:** Action, Adventure, RPG, Strategy, Horror, Puzzle, Sports,
Racing, Multiplayer. None of these accurately describe the app, and
misapplied tags generate negative reviews from players with wrong expectations.

---

## Age and content disclosures

### IARC / Steam content questionnaire answers

Complete the Steamworks IARC questionnaire with the following answers.
These reflect the built-in safety policy (see
[`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md)
— MVP content boundaries).

| Question | Answer |
|----------|--------|
| Does the game contain violence? | No |
| Does the game contain sexual content? | No |
| Does the game contain nudity? | No |
| Does the game contain drug references? | No |
| Does the game contain gambling? | No |
| Does the game contain horror content? | No |
| Does the game contain strong language? | Mild — language appropriate to workplace and social conflict scenarios |
| Does the game involve online interaction with other players? | No |
| Is the game intended only for adults? | No |
| Does the game involve real-money purchases? | Yes — $9.99 base app and optional premium scenario-pack DLC |

**Expected rating outcome:**

| Rating body | Expected rating | Notes |
|-------------|----------------|-------|
| ESRB | E10+ or T | Mild interpersonal conflict language |
| PEGI | 7 or 12 | Social conflict, no violence or sexual content |
| USK | 0 or 6 | |
| ACB | G or PG | |
| CERO | A | All ages |

If Valve assigns a rating higher than PEGI 12 / ESRB T, review the store copy
and content questionnaire before accepting the rating — an unexpectedly high
rating may indicate that copy language needs clarification.

### Steam age gate

An 18+ age gate is **not** expected and should **not** be requested. All
built-in content is PG to PG-13. If Valve requires an age gate for any
reason, accept it rather than weakening the content policies — see risk SP-03
in the compliance register.

### Steam content descriptors

Apply the following content descriptors in the Steamworks partner portal:

- **Mild Language** — workplace and social conflict scenarios may contain
  language appropriate to those contexts (frustration, assertiveness, candid
  professional feedback).

Do **not** apply:
- Violence
- Sexual content
- Nudity
- Drug references
- Gambling

---

## Store page review checklist

Complete this checklist before submitting the store page for Valve review.
This is a supplement to the compliance checklist (SR-07) in
[`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md).

### Copy accuracy

- [ ] Short description is ≤ 300 characters and accurately describes the app.
- [ ] Long description contains no claim of AI therapy, diagnosis, or clinical
      authority.
- [ ] Long description contains no implication of a community paid marketplace
      or in-app purchase system beyond the base app price and DLC.
- [ ] Local-first privacy copy is consistent with [`docs/privacy.md`](../docs/privacy.md)
      and the runtime behaviour confirmed in SR-01 and SR-02.
- [ ] Content-boundaries list matches the safety policy schema
      ([`schemas/safety.schema.json`](../schemas/safety.schema.json)).
- [ ] Pricing wording accurately states the $9.99 base price and that
      premium scenario packs are sold as DLC.
- [ ] IARC questionnaire answer for real-money purchases is set to **Yes**.
- [ ] System requirements have been verified against actual test results from
      the platform smoke matrix ([`docs/release-checklist.md`](../docs/release-checklist.md)).
- [ ] Steam Deck notes accurately reflect the text-mode fallback (AU-03) and
      the external-microphone requirement for voice.

### Genres and tags

- [ ] Primary genre is set to **Simulation**.
- [ ] Secondary genre is set to **Casual**.
- [ ] At least five tags from the priority list above are applied.
- [ ] No misleading tags (Action, RPG, Multiplayer, Horror, etc.) are applied.

### Age and content

- [ ] IARC questionnaire is completed with the answers in the table above.
- [ ] Content descriptors applied match the list above (Mild Language only).
- [ ] No 18+ age gate is requested or accepted without Outright Mental approval.
- [ ] IARC rating received is PEGI 12 / ESRB T or lower; if higher, escalate
      for review before accepting.

### Assets

- [ ] Header capsule (460 × 215 px) uploaded and approved.
- [ ] Small capsule (231 × 87 px) uploaded and approved.
- [ ] Main capsule / library header (3840 × 1240 px) uploaded and approved.
- [ ] At least five screenshots (1280 × 720 px minimum) uploaded; at least
      three show actual in-app gameplay (conversation, debrief, scenario
      library).
- [ ] Trailer (30–120 seconds) uploaded showing actual scenario flow and
      debrief screen.
- [ ] All assets reviewed: no real faces, no real voices, no sensitive data,
      all fictional NPCs only.
- [ ] All assets reviewed for accuracy: UI shown in assets matches the current
      release build.

### Final approval

- [ ] Publishing owner (Outright Mental) has read and approved all copy.
- [ ] Platform team has verified technical claims (system requirements,
      local-first guarantee, microphone handling).
- [ ] Content team has verified pack descriptions and content-boundary
      statements.
- [ ] Legal has confirmed no claims of clinical authority or regulated
      professional advice.

---

## Sign-off

| Section | Reviewer | Date | Notes |
|---------|----------|------|-------|
| Short description | | | |
| Long description | | | |
| Feature bullets | | | |
| Privacy copy | | | |
| Content boundaries | | | |
| Free edition wording | | | |
| System requirements | | | |
| Genres and tags | | | |
| Age disclosures | | | |
| Store review checklist | | | |

All sections must be signed off before the store page is submitted to Valve
for review.

---

## Links

- [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) — app identity, depot layout, and CI credentials
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk register, MVP content boundaries, and compliance checklists SR-01 through SR-09
- [`publishing/STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md) — capsule art, screenshot, and trailer production briefs
- [`docs/STEAM_ROADMAP.md`](../docs/STEAM_ROADMAP.md) — release principles and release train
- [`docs/steam-mvp-scope.md`](../docs/steam-mvp-scope.md) — Stage 4 gate G4-04 (store page accuracy)
- [`docs/privacy.md`](../docs/privacy.md) — local-first data handling reference
- [`schemas/safety.schema.json`](../schemas/safety.schema.json) — safety policy schema (content boundaries source of truth)
- [`docs/screenshots.md`](../docs/screenshots.md) — existing screenshot and demo asset inventory
