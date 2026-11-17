<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Mac App Store

Conversation Simulator on the Mac App Store is the macOS app, **$9.99 USD,
one-time**, the same price as on Steam and the Microsoft Store: the full
edition, built for the App Sandbox and signed with the store's certificates.
This is the reference for what App Store Connect should say and how a build
gets there. It follows UmlautHero's Mac App Store lane (fastlane match for
signing, TestFlight for Mac for delivery), adapted to an app that starts its
own engine processes.

## What the Mac App Store edition is

| | Steam (macOS) | Mac App Store |
|---|---|---|
| Signature | Developer ID, notarized | Apple Distribution + Mac Installer Distribution, provisioning profile inside |
| Sandbox | none (Steam needs to reach the app) | **App Sandbox**; the engine and llama-server inherit it |
| Engine (convsim-core) | PyInstaller one file | PyInstaller **one folder** (`CONVSIM_CORE_ONEDIR=1`): a one-file build unpacks libraries at launch, and the sandbox will not load those |
| AI runtime | llama-server, Metal | the same |
| Updates | Steam | the App Store (in-app updater off) |
| Data folder | `~/Library/Application Support/com.outrightmental.convsim` | the same path inside the app's container, `~/Library/Containers/com.outrightmental.convsim/Data/…` |
| Voice | downloaded on request | **not available** (below) |
| Category (`LSApplicationCategoryType`) | Games | Education |

Same bundle identifier, `com.outrightmental.convsim`, so a Mac has one
Conversation Simulator whichever store it came from.

### Voice

The speech engine (sherpa-onnx) is downloaded when a player asks for voice.
Inside the App Sandbox that cannot happen: App Review forbids an app to
download a program and run it (guideline 2.5.2), and the sandbox quarantines
what the app writes. So in the sandbox the core reports voice as unavailable
(`in_macos_app_sandbox()` in `convsim_core/voice/catalog.py`), and the
first-run screen does not offer it.

The way to voice on this store is to ship the engine in the app, which the
code already supports: an engine laid out as an install under
`<bundled runtimes>/voice-engine/` (bin/, lib/ and the install marker of the
pinned version) is used and never downloaded. **It is not shipped yet because
the engine includes eSpeak NG, licensed GPL-3.0-or-later**, and distributing
GPL-3.0 code through the App Store is widely held to conflict with the store's
terms. That is a licensing decision for Outright Mental, not a build step.

### The demo

The free demo is its own app, as on Steam and the Microsoft Store:
*Conversation Simulator Demo*, bundle ID `com.outrightmental.convsim.demo`,
the demo edition (five conversations, one model download) built with
`tauri.demo.conf.json` by the same lane (`-f edition=demo`). Its *Get the full
game* opens the full app's App Store page, from the repository variable
`MAC_APP_STORE_FULL_APP_URL` (`https://apps.apple.com/app/id<Apple ID>`, set
once the full app's record exists; the site until then).

Two things differ from the other stores, and the demo's listing must say
neither otherwise:

- **Nothing carries over.** Each sandboxed app has its own container, so the
  demo's model and sessions are not seen by the full app; the upsell card
  leaves out its carry-over line in Mac App Store builds.
- **Review risk.** App Review guideline 2.2 says demos and trials "don't
  belong on the App Store"; Apple's own route is one free app with an in-app
  unlock. Outright Mental chose two separate apps anyway (2026-11-17), with no
  unlock built. If review rejects the demo under 2.2, that route is the
  fallback.

## The steps that are a person's

Done once, in this order. Nothing here can be done from CI.

1. **Agreements, tax and banking.** App Store Connect → Business: the *Paid
   Applications* agreement accepted, with tax forms and a bank account. A
   $9.99 app cannot be priced without it.
2. **The bundle identifiers**, one per app. developer.apple.com →
   Certificates, Identifiers & Profiles → Identifiers → **+** → App IDs → App:
   *Conversation Simulator*, explicit `com.outrightmental.convsim`; and
   *Conversation Simulator Demo*, explicit `com.outrightmental.convsim.demo`.
   No capabilities beyond the defaults.
3. **The app records**, one per app. App Store Connect → Apps → **+** → New
   App → platform **macOS**, primary language English (U.S.), full access:
   *Conversation Simulator*, bundle ID `com.outrightmental.convsim`, SKU
   `convsim-mac`, **$9.99**; and *Conversation Simulator Demo*, bundle ID
   `com.outrightmental.convsim.demo`, SKU `convsim-demo-mac`, **Free**. Then
   point the demo at the full app:

   ```bash
   gh variable set MAC_APP_STORE_FULL_APP_URL --repo outrightmental/ConversationSimulator --body "https://apps.apple.com/app/id<Apple ID of the full app>"
   ```
4. **The signing secrets**, the same values UmlautHero has (its
   `docs/CONTINUOUS_INTEGRATION.md`):

   ```bash
   gh secret set ASC_KEY_ID --repo outrightmental/ConversationSimulator
   ```
   ```bash
   gh secret set ASC_ISSUER_ID --repo outrightmental/ConversationSimulator
   ```
   ```bash
   gh secret set ASC_KEY_P8 --repo outrightmental/ConversationSimulator
   ```
   ```bash
   gh secret set MATCH_PASSWORD --repo outrightmental/ConversationSimulator
   ```
5. **Access to the shared signing branch.** The certificates live encrypted on
   UmlautHero's private `signing` branch (`fastlane/Matchfile`). Make a
   fine-grained token with *Contents: read and write* on
   outrightmental/UmlautHero only, then store
   `base64("x-access-token:<token>")`:

   ```bash
   printf 'x-access-token:%s' "$TOKEN" | base64 | gh secret set MATCH_GIT_BASIC_AUTHORIZATION --repo outrightmental/ConversationSimulator
   ```
6. **Turn the lane on for releases:**
   ```bash
   gh variable set MAC_APP_STORE --repo outrightmental/ConversationSimulator --body true
   ```

## Where it stands (2026-11-17)

The lane builds: an unsigned trial on `main` (run 44041318971) produced the
app with the one-folder engine at
`Contents/Resources/resources/bin/convsim-core/convsim-core`, llama-server and
its Metal libraries, `LSApplicationCategoryType` education,
`ITSAppUsesNonExemptEncryption` false and the microphone text; three programs
and 104 libraries for the signing script. Not yet: signing, the `.pkg`, the
TestFlight upload, and any run of the sandboxed app on a Mac. Those wait on
the steps below, which are all a person's.

## Getting a build there

[`.github/workflows/mac-app-store.yml`](../.github/workflows/mac-app-store.yml)
builds the app from a release tag, and with the secrets set it runs
`fastlane mac store` ([`mac-app-store/fastlane/Fastfile`](mac-app-store/fastlane/Fastfile)):
match fetches the two certificates and this app's Mac App Store profile
(creating the profile the first time),
[`scripts/sign-mac-app-store.sh`](../scripts/sign-mac-app-store.sh) signs
inside out and packs `conversation-simulator-vX.Y.Z-mac-app-store.pkg`, and
the package goes to **TestFlight for Mac** with the next build number. Without
the secrets it still builds the app and keeps it, unsigned, as the
`mac-app-store-app` artifact.

```bash
gh workflow run mac-app-store.yml --repo outrightmental/ConversationSimulator -f tag=vX.Y.Z
```
```bash
gh workflow run mac-app-store.yml --repo outrightmental/ConversationSimulator -f tag=vX.Y.Z -f edition=demo
```

The demo comes out as `conversation-simulator-demo-vX.Y.Z-mac-app-store.pkg`
(`mac-app-store-demo-pkg`, or `mac-app-store-demo-app` unsigned).

Releases run it on their own once `MAC_APP_STORE` is `true`: the full app
after a full release, the demo after a demo build. The tag must
contain this lane (v0.4.11 or later). Sending a build for review is a click in
App Store Connect.

Signing, inside out (never `--deep`):

1. every library (`.dylib`, `.so`, PyInstaller's `Python`): no entitlements;
2. every program the app starts (`convsim-core`, `llama-server` and the other
   llama.cpp tools): [`entitlements.helper.plist`](mac-app-store/entitlements.helper.plist),
   exactly `app-sandbox` + `inherit`;
3. the app: [`entitlements.app.plist`](mac-app-store/entitlements.app.plist),
   with the team and application identifiers read from the profile;
4. `productbuild --component … /Applications --sign "3rd Party Mac Developer Installer: …"`.

## App Store Connect settings

| Setting | Value |
|---|---|
| Price | **$9.99 USD** (the matching tier), one-time; the demo app **Free** |
| Availability | every country or region **except China mainland** (as on Steam and the Microsoft Store: publishing/PRC_AI_ANTHROPOMORPHIC_INTERACTION_MEASURES.md) |
| Categories | primary **Education**, secondary **Entertainment** |
| Age rating | Infrequent/Mild: profanity or crude humour; alcohol, tobacco or drug use or references; mature or suggestive themes (the Dating pack). Everything else None. No unrestricted web access, no user-generated content shared with others |
| App Privacy | **Data Not Collected** |
| Privacy policy URL | https://docs.conversationsimulator.com/trust/privacy/ |
| Support URL | https://docs.conversationsimulator.com/start/troubleshooting/ |
| Marketing URL | https://www.conversationsimulator.com/ |
| Copyright | © 2024–2026 Outright Mental |
| Export compliance | `ITSAppUsesNonExemptEncryption` is false in Info.plist (HTTPS only) |
| App Review notes | the first launch offers *Set me up*, which downloads the recommended model (about 2.5 GB) once; after that it runs offline. No account and no sign-in exist |

## The listing (English (U.S.))

Store copy here must not name other platforms or stores, and must not point
buyers at another way to get the app.

**Subtitle** (30 characters)

```
Rehearse real conversations
```

**Promotional text** (170)

```
Rehearse a job interview, a negotiation or a difficult talk with simulated characters who have their own agendas. Everything runs on your Mac, offline.
```

**Description**

```
Rehearse the conversations that matter before they happen — a job interview, a price negotiation, asking for a raise, a difficult talk with a coworker, ordering coffee in Spanish — with simulated characters who have their own background, stakes and agenda, and who will not hand you the win.

Each character is simulated from what they want, what they worry about and what they know. A language model running on your Mac gives them their words, but it never drives: the scenario's rules, the character's mood and the conversation meters decide where the conversation goes. When you end it, a debrief scores you against the scenario's rubric and tells you what to try next time.

BUILT-IN SCENARIO PACKS
• Job Interview Basics — four interview styles, from a friendly screen to a hostile executive.
• Everyday Negotiation — a used car, a lease renewal, freelance scope creep, a customer service dispute.
• Difficult Conversations — honest feedback, an apology, a limit with a friend, asking for a raise.
• Language Café — everyday conversations in Spanish, French, Japanese and English, with optional gentle correction.
• Dating — Confidence & Boundaries — ask someone out, take a no with grace, hold a boundary; honesty and respect over tactics.

MAKE YOUR OWN
The Creator Workbench lets you write your own scenarios: the character, the situation, the meters that move with every turn, and the rubric your answers are scored against.

YOUR CONVERSATIONS STAY ON YOUR MAC
The AI runs on your Mac's own graphics, with Metal. Download a model once (about 2.5 GB) and practise offline. Conversations, transcripts and scores are stored only on your Mac. No account, no subscription, no tracking.

Conversation Simulator is open source (Apache-2.0). It is a practice tool, not therapy, counselling, medical, legal or financial advice.

Requires a Mac with Apple silicon.
```

**Keywords** (100 characters)

```
interview,practice,negotiation,conversation,roleplay,language,speaking,social skills,simulator,job
```

**Screenshots** — the five in
[`assets/screenshots/mac-app-store/`](assets/screenshots/mac-app-store),
2560 × 1600, 16:10 frames of the full-edition captures in docs/screenshots.md.

## The demo's listing (English (U.S.))

**Subtitle**

```
Five real conversations, free
```

**Description**

```
Try five real conversations — a job interview, a car negotiation, asking for a raise, a first ask, and Spanish at a café — with simulated characters who have their own background, stakes and agenda, and who will not hand you the win.

Each one is simulated from what they want, what they worry about and what they know; a language model running on your Mac gives them their words, but it never drives. Download the demo's model once (about 2.5 GB) and everything runs on your Mac, offline. No account.

WHAT IS IN THE DEMO
• The Behavioral Interview — a final-round interview with an engineering manager who probes vague answers.
• The Used Car Deal — negotiate a price with a sales rep who has a number he will not tell you.
• Making the Case — ask your manager for the raise you have earned, with evidence.
• The Coffee Cart — start a conversation with a classmate and read the room before you ask.
• Coffee at Café Sol — order and make small talk in Spanish with a patient barista.

Every conversation ends with a debrief: rubric scores, strengths, missed opportunities, and what to try next time. Replay any of them at four difficulty levels, as often as you like.

The full Conversation Simulator adds the complete library of 20 conversations, the Creator Workbench for writing your own, and model tiers for higher-quality characters.

Conversations, transcripts and scores are stored only on your Mac. No tracking.

Conversation Simulator is a practice tool, not therapy, counselling, medical, legal or financial advice.

Requires a Mac with Apple silicon.
```

**Keywords**

```
interview,practice,negotiation,conversation,roleplay,language,speaking,social skills,demo,free
```

**Screenshots** — the five in
[`assets/screenshots/mac-app-store-demo/`](assets/screenshots/mac-app-store-demo),
1440 × 900: the demo captures in `assets/screenshots/demo/` scaled to the
width, on the app's own background.
