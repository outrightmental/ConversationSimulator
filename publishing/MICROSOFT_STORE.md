<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Microsoft Store

Conversation Simulator on the Microsoft Store is the Windows app, **$9.99 USD,
one-time**, the same price as on Steam. It is the full edition, packaged as an
MSIX around the very files that go to Steam's Windows depot, with the shell
built without Steam. This is the reference for what Partner Center should say
and how a build gets there.

| | |
|---|---|
| Partner Center product | *Conversation Simulator*, product type **MSIX or PWA app**, reserved 2026-11-16 |
| Store ID | `9NTNF4X3GQ95` |
| Listing | https://apps.microsoft.com/detail/9NTNF4X3GQ95 (live once the first submission passes certification) |
| Publisher | Outright Mental (company account, seller ID in Account settings → Legal info) |

**Where it stands (2026-11-16).** Submission 1 is a complete draft: pricing
and markets, properties, the v0.4.10 package (validated; built by
microsoft-store.yml run 44035015351), the English listing with five
screenshots, the certification notes and the `runFullTrust` justification.
Three steps are left, and each is a person's: (1) Account settings → Payout and
tax: add the payout and tax profiles, without which Partner Center will not
charge money; (2) the submission → Age ratings: review the IARC preview, tick
the IARC Terms of Use and Save; (3) **Submit for certification**.

## What the Store edition is

- **The full edition**, the same as Steam's: every official pack, the Creator
  Workbench, the Model Manager, voice. It shares the data folder with every
  other edition, so a model downloaded by the Steam demo is found.
- **Without Steam.** The shell is compiled without the `steam` Cargo feature,
  so there are no Steam achievements, overlay, Workshop or Steam DLC in it.
  The premium scenario-pack DLC stays a Steam product (docs/DLC_MODEL.md); the
  Store listing must not offer it.
- **Updated by the Store.** The in-app updater is off (tauri.steam.conf.json),
  as on Steam.
- **Signed twice over.** Every binary inside carries the studio's Authenticode
  signature; the Store signs the package itself, so we do not.

Checked on 2026-11-16 with the v0.4.10 Windows files registered as a
development package (Developer Mode, `Add-AppxPackage -Register`): under the
package identity the engine starts, finds the database and the downloaded
model in the shared data folder, runs the graphics-card engine, holds a
conversation (a reply in 3.7 s), and every process exits when the window
closes. Not checked there: the microphone, which needs the `microphone`
capability the manifest declares, and voice installation.

## Partner Center settings

| Setting | Value |
|---|---|
| Pricing | **$9.99 USD** base price, no free trial, no sale |
| Markets | All markets **except China**: the PRC rules for anthropomorphic AI interaction (publishing/PRC_AI_ANTHROPOMORPHIC_INTERACTION_MEASURES.md) are why the Steam apps are not sold there either |
| Discoverability | Make this product available and discoverable in the Microsoft Store |
| Category | **Education → Language**, secondary **Entertainment**. An app product has no Games category; Steam files it under Simulation |
| Privacy policy URL | https://docs.conversationsimulator.com/trust/privacy/ |
| Website | https://www.conversationsimulator.com/ |
| Support contact | https://docs.conversationsimulator.com/start/troubleshooting/ |
| Personal information | **Yes**, with the privacy policy above: the app records the microphone and stores transcripts, all on the device |
| Product declarations | Uses generative AI: yes. Install to alternate drives: yes. OneDrive backup of app data: **no** (conversations stay on the device). Broadcast clips: no |
| System requirements | Minimum: keyboard, 8 GB memory, a 64-bit 4-core processor, no graphics card needed. Recommended: microphone, 16 GB memory, a Vulkan graphics card with 4 GB |
| Age rating | the IARC questionnaire, as type *Game*: no violence, fear, gambling, crude humour, digital purchases (the Store edition has no DLC), user interaction or location sharing; **yes** to dating (the Dating pack, not a strong focus), minor profanity (rarely, from the model) and alcohol use (rarely: the first date is at a wine bar). Result, 2026-11-16: ESRB Everyone 10+, PEGI 3, USK 12, IARC 3+. Saving it means accepting the IARC Terms of Use, which a person does |
| Restricted capability `runFullTrust` | *"Conversation Simulator is a Win32 desktop app (a Tauri shell with a local engine and llama.cpp runtimes) packaged as MSIX. It runs as a full-trust desktop application to start its local engine processes and uses no other restricted capability."* |

## The package

[`microsoft-store/AppxManifest.xml`](microsoft-store/AppxManifest.xml) is the
manifest, and [`microsoft-store/Assets/`](microsoft-store/Assets) its three
logos, downscaled from `apps/desktop/src-tauri/icons/128x128@2x.png`.
[`scripts/pack-msix.ps1`](../scripts/pack-msix.ps1) fills in the identity and
packs. The identity is four repository variables, set on 2026-11-16 from
Partner Center → the app → Product identity:

| Variable | Value |
|---|---|
| `MSSTORE_IDENTITY_NAME` | `OutrightMental.ConversationSimulator` |
| `MSSTORE_PUBLISHER` | `CN=D8FD94F9-AD83-4DB4-95F5-803BB1DF700E` |
| `MSSTORE_PUBLISHER_DISPLAY_NAME` | `Outright Mental` |
| `MSSTORE_PRODUCT_ID` | `9NTNF4X3GQ95` |

The release tag is the version with a fourth part of 0: `v0.4.10` is
`0.4.10.0`. A pre-release tag has no Store version and is not packed.

## Getting a build there

Every full release runs **Microsoft Store**
([`.github/workflows/microsoft-store.yml`](../.github/workflows/microsoft-store.yml))
after the Windows build: it takes that run's Steam depot, rebuilds the shell
from the tag without Steam, signs it, packs
`conversation-simulator-vX.Y.Z-windows.msix`, keeps it as the run's
**microsoft-store-msix** artifact, and, once the secrets below are set, sends
it to Partner Center as a **draft** submission. Submitting the draft for
certification is a person's click, as setting a Steam build live is.

To package a release again, or one tagged before this lane existed:

```bash
gh workflow run microsoft-store.yml --repo outrightmental/ConversationSimulator -f tag=v0.4.10 -f run_id=44007519657
```

(`run_id` is the full-edition Release run for that tag; 44007519657 is
v0.4.10's.)

### First submission, by hand

Partner Center's submission API only updates an app that already has a
published submission, so the first one is made in Partner Center:

1. Download the package: `gh run download <run> --repo outrightmental/ConversationSimulator --name microsoft-store-msix`.
2. Partner Center → Conversation Simulator → **Start submission**, and fill
   each section from the tables above and the listing below. Packages: upload
   the `.msix`.
3. **Submit to the Store.** Certification usually takes one to three business
   days.

A paid app also needs the account's **payout profile and tax profile**
(Account settings → Payout and tax). They hold bank and tax details, so only
a person sets them up.

### Then let releases send drafts

1. Partner Center → Account settings → User management → **Microsoft Entra
   applications** → Add → create one named `convsim-ci` with the **Manager**
   role → **Add new key**. It shows the tenant ID, the client ID and, once,
   the key.
2. Account settings → Legal info → the **Seller ID**.
3. Set the secrets:

```bash
gh secret set MSSTORE_TENANT_ID --repo outrightmental/ConversationSimulator
```
```bash
gh secret set MSSTORE_CLIENT_ID --repo outrightmental/ConversationSimulator
```
```bash
gh secret set MSSTORE_CLIENT_SECRET --repo outrightmental/ConversationSimulator
```
```bash
gh secret set MSSTORE_SELLER_ID --repo outrightmental/ConversationSimulator
```

## The listing (English)

Paste each block into Partner Center → the submission → Store listings →
English (United States).

### Product name

Conversation Simulator

### Description

```
Rehearse the conversations that matter before they happen — a job interview, a price negotiation, asking for a raise, a difficult talk with a coworker, ordering coffee in Spanish — with simulated characters who have their own background, stakes and agenda, and who will not hand you the win.

Each character is simulated from what they want, what they worry about and what they know. A language model running on your computer gives them their words, but it never drives: the scenario's rules, the character's mood and the conversation meters decide where the conversation goes. When you end it, a debrief scores you against the scenario's rubric and tells you what to try next time.

TALK OUT LOUD, OR TYPE
Speak your side into your microphone and hear each character answer in a voice of their own, all processed on your computer. Voice is an optional download, offered when you set up; every conversation works in text too.

BUILT-IN SCENARIO PACKS
• Job Interview Basics — four interview styles, from a friendly screen to a hostile executive.
• Everyday Negotiation — a used car, a lease renewal, freelance scope creep, a customer service dispute.
• Difficult Conversations — honest feedback, an apology, a limit with a friend, asking for a raise.
• Language Café — everyday conversations in Spanish, French, Japanese and English, with optional gentle correction.
• Dating — Confidence & Boundaries — ask someone out, take a no with grace, hold a boundary; honesty and respect over tactics.

MAKE YOUR OWN
The Creator Workbench lets you write your own scenarios: the character, the situation, the meters that move with every turn, and the rubric your answers are scored against.

YOUR CONVERSATIONS STAY ON YOUR COMPUTER
The AI runs on your own machine, on your graphics card when you have one. Download a model once (about 2.5 GB) and play offline. Conversations, transcripts, recordings and scores are stored only on your device. No account, no subscription, no telemetry.

OPEN SOURCE, FAIRLY PRICED
Conversation Simulator is free and open source: anyone can build it from the source on GitHub at no cost. This Store edition is that same software, ready to run, signed, and updated by the Store. The price funds its development; it does not unlock anything.

Conversation Simulator is a practice tool. It is not therapy, counselling, medical, legal or financial advice.
```

### Product features (one per line, up to 20)

```
Simulated characters with their own background, stakes and agenda
Job interviews, negotiations, difficult conversations and language practice
Talk out loud or type: voice in and out, processed on your computer
A scored debrief after every conversation, with what to try next time
Conversation meters that move with every turn
Write your own scenarios in the Creator Workbench
Runs offline on your own computer, on your graphics card when you have one
No account, no subscription, no telemetry
Free and open source; this edition is the ready-to-run package
```

### Keywords (up to seven, 21 words in all)

conversation simulator, conversation practice app, simulated conversations, role play conversations, interview practice software, job interview simulator, negotiation practice tool

(Partner Center's own suggestions for this description. Its keyword box drops
spaces typed into it, so pick suggestions rather than typing.)

### Short description

```
Rehearse job interviews, negotiations, difficult talks and language practice with simulated characters who have their own agendas. Type or talk out loud: everything runs on your computer and works offline.
```

### Copyright and developer

`© 2024–2026 Outright Mental. Open source: the engine is Apache-2.0 and the official scenario packs are CC BY 4.0.` · Developed by `Outright Mental`

### Screenshots

The five in [`assets/screenshots/microsoft-store/`](assets/screenshots/microsoft-store)
(2560 × 1440), 16:9 frames of the full-edition captures documented in
docs/screenshots.md. Captions:

| File | Caption |
|---|---|
| `01-home.png` | Start a scenario, follow your training plan, or set up a model. |
| `02-scenario-library.png` | Interviews, negotiations, difficult conversations and language practice, at four difficulty levels. |
| `03-conversation.png` | The character answers from their own stakes and mood; the meters move with every turn. |
| `04-creator-workbench.png` | Write your own scenarios: the character, the situation, the meters and the rubric. |
| `05-model-manager.png` | One click installs the recommended model; it runs on your computer, offline. |

### Store logos

Optional for an app: the 300 × 300 tile comes from the package's logo. Box art
(1:1, 1080 × 1080) and poster art (2:3, 720 × 1080) are not made yet.
