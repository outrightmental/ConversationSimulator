<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Store Assets — Production Brief

> **Purpose:** Specify the exact sizes, content requirements, and production
> briefs for every visual and video asset required on the Conversation Simulator
> Steam store page. Use this document to brief a designer or to self-produce
> assets.
>
> **Audience:** Designer, marketing, and platform team. Outright Mental must
> approve all assets before they are uploaded to Steamworks.
>
> **Source of truth for content constraints:** All assets must comply with the
> content-boundary rules in
> [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md) — Content boundaries.
> No real people, no real voices, no sensitive data.

---

## Asset inventory

| Asset | Required? | Steam specification | Status |
|-------|-----------|---------------------|--------|
| Header capsule | Yes | 460 × 215 px, JPG or PNG | Not started |
| Small capsule | Yes | 231 × 87 px, JPG or PNG | Not started |
| Main capsule (library hero) | Yes | 3840 × 1240 px, JPG or PNG | Not started |
| Library capsule | Yes | 600 × 900 px, JPG or PNG | Not started |
| Page background | Optional | 1438 × 810 px, JPG or PNG | Not started |
| Screenshots (min 5, max 20) | Yes | 1920 × 1080 px (or 1280 × 720 px min), JPG or PNG | Placeholders exist (see `docs/assets/screenshots/`) |
| Gameplay trailer | Yes | MP4, H.264, 1920 × 1080 px, 30–120 seconds | Not started |

---

## Capsule art

### Design brief

The capsule art must communicate the core concept — conversation practice with
AI — at very small sizes. The primary visual constraint is that the header
capsule is 460 × 215 px and will be viewed at 1× in a search result list.

**Core concept to convey:**
- A one-on-one conversation between a player and an AI character
- The practice/simulation context (not entertainment, not therapy)
- The local, private nature of the interaction

**Visual language guidelines:**
- Clean, modern, slightly clinical aesthetic — closer to a professional
  productivity tool than a game
- No photorealistic faces that could be mistaken for real people
- Use abstract or stylised character representations (silhouettes, icons,
  illustrated characters) to represent the NPC and player
- A speech-bubble or transcript motif can anchor the conversation theme
- Colour palette: dark neutral base (near-black) with a strong accent —
  the app UI uses deep purple (`#4C1D95` area) for player turns and dark
  green for NPC turns; either can anchor the capsule art

**Text on capsules:**
- Header capsule (460 × 215): include "Conversation Simulator" logotype
  and optionally the tagline "The simulator for conversations."
- Small capsule (231 × 87): logotype only — no tagline at this size
- Main capsule / library hero (3840 × 1240): logotype, tagline, and the
  Outright Mental publisher mark

**Prohibited:**
- Photographs of real people
- AI-generated images of recognisable individuals
- UI screenshots composited into the capsule (too small to read)
- Price or "Free" badges baked into the art — Steam overlays these
- Mature, suggestive, or violent imagery

### File requirements

| Asset | Size | Format | Colour space | Max file size |
|-------|------|--------|-------------|--------------|
| Header capsule | 460 × 215 px | JPG or PNG | sRGB | 1 MB |
| Small capsule | 231 × 87 px | JPG or PNG | sRGB | 256 KB |
| Main capsule (library hero) | 3840 × 1240 px | JPG or PNG | sRGB | 5 MB |
| Library capsule | 600 × 900 px | JPG or PNG | sRGB | 2 MB |
| Page background | 1438 × 810 px | JPG or PNG | sRGB | 2 MB |

Provide source files (Figma, Illustrator, or equivalent) alongside exported
assets so that future updates can be made without re-commissioning from scratch.

---

## Screenshots

Steam requires a minimum of five screenshots. Upload up to 20. At least three
must show actual in-game content (not capsule art or promotional text).

The placeholder SVGs in `docs/assets/screenshots/` define the six scenes that
must be covered. See [`docs/screenshots.md`](../docs/screenshots.md) for the
full inventory, alt text, and replacement checklist. This section restates the
brief in Steam-submission terms.

### Required screenshots

Capture these six screens from the live application at 1920 × 1080 px
(or 1280 × 720 px minimum). Use a macOS or Linux build for consistent rendering.
Do not use Windows-specific window chrome unless a Windows screenshot is
explicitly needed for platform coverage.

#### Screenshot 1 — Home screen

**File:** `docs/assets/screenshots/01-home.svg` (replace with PNG)
**Steam caption (max 300 chars):**
```
Home screen showing all services ready: local AI runtime, speech recognition,
and text-to-speech — all running on your computer, no internet required.
```

**What to show:**
- The home screen with the status panel showing all services green
- Four official packs listed as installed
- Clean, uncluttered layout
- No personal data visible

---

#### Screenshot 2 — Scenario Library

**File:** `docs/assets/screenshots/02-scenario-library.svg` (replace with PNG)
**Steam caption:**
```
Choose from four built-in scenario packs covering job interviews, negotiations,
difficult conversations, and language practice. Each scenario shows difficulty,
duration, and content rating before you start.
```

**What to show:**
- The Scenario Library with at least two packs visible
- A scenario card expanded to show metadata (difficulty, duration, content
  rating, language, tags, Launch button)
- Use a Job Interview Basics or Everyday Negotiation scenario for the expanded
  card — these are the most universally relatable

---

#### Screenshot 3 — Active conversation (mid-session)

**File:** `docs/assets/screenshots/03-conversation.svg` (replace with PNG)
**Steam caption:**
```
A mid-session conversation with an AI interviewer. NPC state meters update in
real time as the conversation unfolds — watch the dynamic shift based on what
you say.
```

**What to show:**
- An active conversation with a fictional NPC (e.g. Victor Hargrove in the
  hostile executive interview scenario)
- Player and NPC turns visible in the transcript
- NPC state variable meters (credibility, composure, pressure_level or
  equivalent) displayed below the transcript
- A scenario event banner if one has triggered (adds visual interest)
- Do not use real personal data; use the sample/fixture data if needed

---

#### Screenshot 4 — Session Debrief

**File:** `docs/assets/screenshots/04-debrief.svg` (replace with PNG)
**Steam caption:**
```
After every session, a scored debrief breaks down your performance by rubric
dimension and highlights the moments that changed the conversation.
```

**What to show:**
- The debrief screen for a completed session
- Overall score and outcome badge (Success or Partial success)
- Scorecard with at least two or three rubric dimensions and their scores
- Key moments section with at least one positive and one negative turning
  point
- Transcript export option visible

---

#### Screenshot 5 — Model Manager

**File:** `docs/assets/screenshots/06-model-manager.svg` (replace with PNG)
**Steam caption:**
```
Download and switch between open-weight AI models. Every download shows the
model name, source, licence, size, checksum, and destination path before a
single byte transfers.
```

**What to show:**
- The Model Manager with one installed model (green "Loaded" badge) and
  at least one model available for download
- The six mandatory disclosure fields visible for a model in the registry
  (name, source, licence, size, SHA-256, destination path)
- Optionally: an in-progress download with a progress bar
- Do not show a download in progress for a model the player has not
  confirmed — this would misrepresent the model download transparency policy

---

#### Screenshot 6 — Creator Workbench (optional, recommended)

**File:** `docs/assets/screenshots/05-creator-workbench.svg` (replace with PNG)
**Steam caption:**
```
Build your own scenario packs in the Creator Workbench. Define the NPC,
scenario state, and scoring rubric — then share your pack with other players.
```

**What to show:**
- The three-panel Creator Workbench layout
- A pack file tree visible in the middle panel
- A YAML file open in the editor panel
- A green validation banner confirming the pack is valid
- Use the sample pack or fixture data — do not use any real player data

---

### Screenshot production rules

- **Resolution:** 1920 × 1080 px preferred; 1280 × 720 px minimum.
- **Format:** PNG (lossless) for screenshots with fine text; JPG (quality 90+)
  acceptable for screenshots where compression artefacts are not visible.
- **Colour profile:** sRGB.
- **Content safety:** All NPCs must be fictional. No real faces, real voices,
  or personal data. Run a content review before uploading.
- **UI accuracy:** The UI shown must match the current release build. Do not
  use mocked or outdated UI states.
- **Annotations:** Minimal or none. If annotations are added, use a consistent
  font and avoid covering UI elements.
- **File size:** Keep each screenshot under 10 MB; under 5 MB preferred for
  fast page load.

---

## Gameplay trailer

### Overview

| Attribute | Value |
|-----------|-------|
| Duration | 30–120 seconds (target: 60–90 seconds) |
| Resolution | 1920 × 1080 px |
| Frame rate | 30 fps minimum; 60 fps preferred |
| Format | MP4, H.264, AAC audio |
| Audio | Optional narration or on-screen text cards; no real voices of players |
| File size | Under 500 MB (Steam limit) |

### Content structure

The trailer must show the actual application in use — not animated mockups,
not stock footage. Structure it to answer the viewer's main question ("What
do I actually do?") within the first 15 seconds.

**Recommended structure:**

| Timestamp | Content |
|-----------|---------|
| 0:00–0:05 | Title card: "Conversation Simulator" + tagline "The simulator for conversations." |
| 0:05–0:15 | Home screen → Scenario Library → scenario card selection (fast cut). Show the app is approachable and immediately understandable. |
| 0:15–0:45 | **Core loop — 30 seconds of actual conversation.** Show a mid-session exchange in one of the four built-in packs. Player types a response; NPC replies; a state meter changes; a scenario event triggers. Show at least one moment where the NPC pushes back or the dynamic shifts. |
| 0:45–1:00 | Debrief screen. Show the overall score, at least one scorecard dimension, and a key moment. Convey that the session produced useful feedback, not just a score. |
| 1:00–1:10 | Optional: 3-second cuts showing Model Manager, Creator Workbench, and voice mode in action. Convey depth without dwelling. |
| 1:10–1:20 | Closing title card: "Free forever. Everything runs on your computer." + Outright Mental mark. |

**Narration / text cards:**
- No voice-over is required. Text cards at key transitions are sufficient.
- If voice-over is used, it must be performed by a consented voice actor —
  do not use AI-synthesised voice-over for the trailer itself. (Kokoro TTS
  in the app is fine; synthetic voice-over for the marketing trailer is not.)
- Text card copy must be consistent with
  [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md).

**Music / sound:**
- Background music is optional. If used, ensure the licence permits use in
  commercial promotional content.
- In-app TTS audio (Kokoro NPC voice output) may be included in the trailer
  to demonstrate the voice feature — this is synthesised NPC audio, not a
  real person's voice, and is permitted.

### Content safety rules

- All NPC characters shown must be fictional. Do not use names or
  descriptions that could be construed as real-person impersonation.
- No real player audio. If voice input is demonstrated, use a consented
  test voice or on-screen text to represent the player's turn.
- All content shown must be within PG-13. Do not record a session where
  the conversation reaches content that approaches the safety-policy
  boundaries.
- Run a content review before submitting the trailer to Valve.

### Technical delivery

- Deliver the trailer as an MP4 (H.264 video, AAC audio).
- Deliver a still frame (1920 × 1080 px PNG) for the thumbnail — this is
  the frame Steam displays before the trailer plays. Use the mid-session
  conversation frame (NPC state meters visible, event banner triggered) as
  the thumbnail.
- Keep a lossless source export (ProRes or equivalent) for future re-edits.

---

## Placeholder asset status

The following placeholder SVGs exist in `docs/assets/screenshots/` and must
be replaced with real screenshots before the store page goes live. See
[`docs/screenshots.md`](../docs/screenshots.md) for the full replacement
checklist.

| Placeholder | Replaces with | Status |
|------------|---------------|--------|
| `01-home.svg` | Real home-screen PNG | Not started |
| `02-scenario-library.svg` | Real scenario-library PNG | Not started |
| `03-conversation.svg` | Real mid-session PNG | Not started |
| `04-debrief.svg` | Real debrief PNG | Not started |
| `05-creator-workbench.svg` | Real Creator Workbench PNG | Not started |
| `06-model-manager.svg` | Real Model Manager PNG | Not started |
| `docs/assets/demo-placeholder.svg` | Animated GIF or MP4 (README hero) | Not started |

---

## Links

- [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md) — canonical store copy and review checklist
- [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) — app identity and Steamworks partner portal setup
- [`docs/screenshots.md`](../docs/screenshots.md) — existing placeholder asset inventory and replacement checklist
- [`docs/assets/screenshots/`](../docs/assets/screenshots/) — placeholder SVG files
