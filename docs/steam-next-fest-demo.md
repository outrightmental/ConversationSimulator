<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Next Fest Demo — Scope and Decision Record

> **Purpose of this document:** the product definition of the free demo
> edition of Conversation Simulator, built for Steam Next Fest. It records the
> decisions behind issue #495's open questions, the exact cut list, and the
> pass/fail gate a demo build must clear. The Steamworks mechanics (creating
> the demo app, depots, GitHub variables, the Next Fest registration steps)
> are in [`publishing/STEAM_NEXT_FEST_DEMO.md`](../publishing/STEAM_NEXT_FEST_DEMO.md).

The demo is **the same build, narrowed**: download one AI model, pick from
five curated conversations, and nothing else. It exists so that a first-time
player gets an out-of-the-box "WOW!" with no experience-breaking problems —
crashes, stalled downloads, failed first-run setup, incoherent NPC turns, and
missing debriefs are demo blockers, not bugs to triage later.

---

## How the edition works

There is one code base and one flag. `CONVSIM_EDITION=demo` on `convsim-core`
narrows the engine; `VITE_CONVSIM_EDITION=demo` on the web bundle trims the
UI; the demo desktop build sets both. Nothing changes unless a build opts in,
so the full app is unaffected apart from a new `edition` field in
`GET /api/health`.

| Layer | Switch | What it does |
|-------|--------|--------------|
| `convsim-core` | `CONVSIM_EDITION=demo` (`ServiceConfig.edition`) | Serves exactly the five curated scenarios (and only the packs they come from), exposes exactly one registry model, refuses session creation for any other scenario, refuses model install for any other model, and refuses pack import and the Creator Workbench API with `EDITION_RESTRICTED` (HTTP 403). Reports `edition: "demo"` plus the curated `scenario_ids` and `model_id` on `/api/health`. |
| Web UI | `VITE_CONVSIM_EDITION=demo` at build time, or the engine's `/api/health` answer at run time | Home becomes the five-conversation picker plus one upsell card. Library, Logbook and Workbench are not in the navigation and their routes collapse to Home. The first-run wizard offers only "Set me up" (no Ollama, no GGUF). Settings keeps only the privacy controls. The debrief ends with the upsell instead of the voice invite. |
| Tauri shell | `CONVSIM_EDITION=demo` at compile time (`build.rs` validates it; `lib.rs` passes it to the sidecar), optionally `CONVSIM_DEMO_MODEL_ID` alongside it, and the `tauri.demo.conf.json` overlay | Product name "Conversation Simulator Demo", its own bundle identifier, the same per-user data directory as the full app (see [Save data](#does-demo-save-data-carry-over)), and the registry id of the one model the demo installs. |
| CI | `release.yml` → `edition: demo` (workflow_dispatch), with the optional `demo_model_id` input | Builds all three platforms as the demo edition, uploads `demo-desktop-*` artifacts, publishes **no** GitHub release, and hands off to `steam-deploy.yml` with `edition: demo`, which targets `STEAM_DEMO_APP_ID` and the demo depots. Validate refuses a `demo_model_id` that is not a registry id, or one given for a full build. |

The curated list lives in **one place**: `services/convsim-core/convsim_core/edition.py`.
The UI renders whatever the engine reports, so the five cannot drift between
the two.

To see the demo locally, run the engine with `CONVSIM_EDITION=demo` (the web
UI adopts the engine's answer; the build-time flag is optional in dev):

```sh
CONVSIM_EDITION=demo ./scripts/dev.sh
# …or on the smaller lightweight tier (see Which model? below):
CONVSIM_EDITION=demo CONVSIM_DEMO_MODEL_ID=qwen3-1.7b-instruct-q8_0 ./scripts/dev.sh
```

---

## Decisions

### Which model?

**The demo ships the registry's starter tier, Qwen3 4B Instruct Q4_K_M
(2.5 GB, Apache-2.0).** A smaller/faster tier is now in the registry and is one
build input away, but it does not ship until it has been played (below).

The demo edition installs whatever the registry's `role: starter` entry is, or
the model named by `CONVSIM_DEMO_MODEL_ID` — so which model the demo ships is a
configuration decision, not a code one. For a *packaged* build that variable is
baked in at compile time (`build.rs` validates it, `lib.rs` hands it to
`convsim-core` at launch): Steam starts the app with none of our environment, so
nothing set at run time would ever arrive. The demo build leg of `release.yml`
takes it as the `demo_model_id` workflow input and refuses, in Validate, an id
that is not in `model-registry/registry.yaml`.

#### The smaller/faster Qwen question

The note asked "can we use a smaller/faster Qwen model?" The answer has two
parts: there *is* one in the registry now, and it is not yet what the demo
installs.

| | Lightweight tier | Starter tier (what the demo ships) |
|---|---|---|
| Model | Qwen3 1.7B Instruct Q8_0 | Qwen3 4B Instruct Q4_K_M |
| Registry id | `qwen3-1.7b-instruct-q8_0` | `qwen3-4b-instruct-q4_k_m` |
| Download | 1.8 GB | 2.5 GB |
| VRAM floor | 3 GB | 4 GB |
| Exercised by the real-model smoke and the release checklist | **No** | Yes |

Why Q8_0 and not Q4_K_M: Qwen's own GGUF repo for the 1.7B publishes a single
quant, Q8_0 — the `Qwen3-1.7B-Q4_K_M.gguf` file this document previously named
as the candidate does not exist upstream (`curl -s
https://huggingface.co/api/models/Qwen/Qwen3-1.7B-GGUF/tree/main`). That is the
better end of the trade anyway: Q8_0 is near-lossless, so the risk is purely
1.7B-versus-4B rather than a small model *and* an aggressive quantisation. At
1.8 GB it is still a 28 % shorter first download than the starter, and its 3 GB
VRAM floor (1.83 GB of weights plus 0.94 GB of KV cache at the entry's 8192-token
context) makes it the only entry in the registry that fits in VRAM on an
integrated-graphics or sub-4 GB-GPU machine. Nothing refuses such a player the
starter today — the install card warns about the VRAM floor but does not block,
and llama.cpp offloads the layers that fit and runs the rest on the CPU — but a
partially offloaded 4B is minute-long turns, which loses the demo as surely as
an incoherent one does.

Why it is not the default yet. The demo's quality bar is defined by *incoherent
NPC turns* and *missing debriefs* being blockers: the turn pipeline asks the
model for structured output (state deltas, event evaluation) and the debrief
asks for a rubric-scored analysis. 1.7B-class models are markedly less reliable
at both, and the 4B is the only tier the nightly real-model smoke
(`scripts/nightly-model-smoke.py`) and the release-checklist reference hardware
have been run against. A stalled 2.5 GB download is recoverable (the pipeline
resumes it); an incoherent character is the demo lost. `test_edition.py` pins
this: a smaller tier existing in the registry must not become the demo's model
by itself.

A 0.6B model (Qwen also publishes `Qwen/Qwen3-0.6B-GGUF`, Q8_0, 0.6 GB) stays
out of the question for this product.

#### Qualifying the lightweight tier for the demo

Everything but the play-testing is done. The remaining gate is:

1. Measure it on the reference hardware — the nightly smoke checks latency
   budgets, nothing about coherence, so this step only rules out a model that
   is somehow *slower*:

   ```sh
   # --model-url and --model-sha256 are the entry's own `download` fields
   python scripts/nightly-model-smoke.py --download-only \
       --model-id qwen3-1.7b-instruct-q8_0 \
       --model-url '<download.url from model-registry/registry.yaml>' \
       --model-sha256 '<download.sha256 from the same entry>'
   python scripts/nightly-model-smoke.py --model-id qwen3-1.7b-instruct-q8_0
   ```

2. The actual gate: play all five demo conversations to the debrief at
   `standard` difficulty, twice each; zero incoherent turns, zero
   template-fallback debriefs. Run the engine as the demo on the candidate so
   you are playing what a player would get:
   `CONVSIM_EDITION=demo CONVSIM_DEMO_MODEL_ID=qwen3-1.7b-instruct-q8_0 ./scripts/dev.sh`.
3. Build the demo with `demo_model_id: qwen3-1.7b-instruct-q8_0` (Actions →
   Release → Run workflow) and re-run the [demo gate](#demo-gate). Update the
   download size in the demo store copy
   ([`STEAM_STORE_PAGE.md`](../publishing/STEAM_STORE_PAGE.md#demo-copy-rules)),
   which names it honestly. No code changes.

If it does not clear step 2, the demo ships on the starter and the lightweight
tier stays what it is now: a registry entry, installable through
`POST /api/setup/install` and documented for machines that cannot run the
starter, but not what either edition's setup flow offers (that flow shows the
one recommended model — the `role: starter` entry — plus Ollama and
bring-your-own-GGUF). `scripts/pin-model.py` prints a policy-compliant entry
(commit-pinned URL, SHA-256 from the Hub's LFS metadata) for any other
candidate worth trying.

### Which five conversations?

One flagship per player-facing official pack — the scenario in each pack whose
difficulty ladder carries authored labels and descriptions (the most polished
one, by construction):

| # | Conversation | Pack | Why it is in the demo |
|---|--------------|------|-----------------------|
| 1 | **The Behavioral Interview** (`behavioral_interview`) | Job Interview Basics | The most universally relatable stakes; the scenario the offline smoke gate has exercised longest. |
| 2 | **The Used Car Deal** (`used_car_negotiation`) | Everyday Negotiation | Fun, adversarial, memorable — Ray has a number he will not tell you. Shows hidden NPC agenda. |
| 3 | **Making the Case** (`ask_for_raise`) | Difficult Conversations | Asking for a raise: everyone has one of these coming. Shows state-driven pressure. |
| 4 | **The Coffee Cart** (`the_ask`) | Dating — Confidence & Boundaries | The product's most distinctive pack; reading the room is the whole game. PG-13. |
| 5 | **Coffee at Café Sol** (`spanish_coffee`) | Language Café | Shows the language-practice range in one card, with the gentlest correction ladder in the catalogue. Spanish. |

Not included, deliberately: the scripted tutorial pack (`tutorial.first_words`,
internal content per issue #473) and the sample pack. The demo does **not**
create new demo-only scenarios — every card is a real, shipped conversation.

`tests/test_edition.py` pins this list to real files in `packs/official`,
to the one-per-pack rule, and to the content-rating ceiling.

### Which Next Fest edition and deadline?

Valve runs Next Fest three times a year (February, June, October) and
registration closes weeks before each event; a game may participate once.
**Target the first edition whose registration is still open six weeks after
the demo build passes the [demo gate](#demo-gate).** As of this document's
writing (late September 2026) that is the **February 2027** edition; October
2026's registration window is closed or closing. The exact dates are
published only in Steamworks (**Marketing & Visibility → Steam Next Fest**);
the runbook has the timeline to back-plan from them. A demo that is live on
the store page early also earns wishlists before the fest, so shipping the
demo before the fest is the plan, not a fallback.

### Separate free app ID, or a branch of the base app?

**A separate free Steam app.** Steam demos are their own app (created from the
base app's Steamworks page under *Store Presence → Demo*), with their own
App ID, depots and builds; Next Fest requires a demo app attached to a base app
that is *Coming Soon* — not yet released, and never in a previous Next Fest
(Valve's rules are summarised in the runbook's eligibility section). A `demo`
branch of the paid app cannot be
free and cannot be the Next Fest demo. The demo app is registered as
`STEAM_DEMO_APP_ID` plus three `STEAM_DEMO_DEPOT_*_ID` repository variables,
kept apart from the paid app's so an upload can never cross over.

### Hidden versus disabled-with-upsell

Everything that is not the five conversations is **hidden** — the demo reads
as a complete small product, not a crippled large one. Exactly one thing
upsells: a single "Get the full game" card (on Home, and compact on the
debrief) that names what the full version adds and links to the paid app's
store page. Nothing is greyed out.

| Surface | Demo | Note |
|---------|------|------|
| Home | Five-conversation picker, engine status, one upsell card, help links | Training summary, training plan, and the primary-action links are full-app. |
| Scenario Library (`/library`) | Not present; route collapses to Home | Search, filters, folders, pack import, Workshop sync are all library features. |
| Creator Workbench (`/workbench`) | Not present; route collapses to Home; API returns 403 | |
| Logbook (`/logbook`) | Not present; route collapses to Home | Sessions still record locally; the full app shows them. |
| First-run wizard | "Set me up" only, one model, no Ollama / GGUF disclosure | Copy says "the demo's AI model"; badge says "Demo". |
| Model Manager (`/model-manager`) | Reachable (it is the repair path for an incomplete install); shows the one model | Ollama / GGUF cards are not rendered. |
| Settings | Language, transcript saving, local folders, sessions, clear local data | Runtime, voice, Steam Cloud, pack management, NPC memory, system health, advanced are full-app. Privacy controls (gate F-06) are never trimmed. |
| Conversation | Unchanged | Voice controls already fall back when STT/TTS are not installed; the demo installs neither. |
| Debrief | Unchanged, plus the compact upsell; voice invite not shown; "back" goes to Home | |
| Support | Unchanged | Crash bundles and the beta-report path are how Next Fest feedback reaches us. |
| Navigation | Home · Settings · Support, with a "Demo" badge | |

### Does demo save data carry over?

**Yes — by construction.** The demo shell keys its per-user data directory to
the *full app's* bundle identifier (`com.outrightmental.convsim`), not its own,
so the demo and the full app read and write the same `CONVSIM_DATA_ROOT`. A
player who downloads the 2.5 GB model in the demo and then buys the full game
does not download it again; their sessions, transcripts and logbook are there
on first launch. The demo never deletes or rewrites what the full app stores:
its scenario filter narrows what it *lists* (the five cards, their packs), and
the privacy controls it keeps (sessions, transcripts, clear-data) see the whole
directory. Steam
achievements and Steam Cloud stay base-app-only (a Steam demo cannot award the
base app's achievements). "Clear local data" in the demo clears the shared
directory, and its copy says so.

### Store assets

The demo attaches to the base app's store page as its demo; Valve renders the
"Download Demo" button there. The demo's own capsule set reuses the base
capsules with a "DEMO" ribbon, produced by the same
`publishing/assets/source/gen_capsules.py` pipeline; screenshots are
demo-edition screenshots of the five conversations (the Home picker, one
conversation, one debrief) so nothing shown is unreachable in the demo. No
separate trailer: the base trailer is used. Details in the runbook.

### Turn / session / time cap

**None.** Unlimited play within the five conversations, at every difficulty.
The natural cap is content, and replaying a conversation at a harder
difficulty is the hook that turns a demo into a purchase. A time or turn cap
is precisely the kind of experience-breaking moment the demo exists to avoid.

---

## Demo gate

A demo build may be submitted to Valve (and attached to the Next Fest
registration) only when every row is **PASS**. The gate is a subset of the
Stage 3 gate in [`steam-mvp-scope.md`](steam-mvp-scope.md), plus the demo's
own promise.

| Gate ID | Check | Method | Pass criterion |
|---------|-------|--------|----------------|
| D-01 | Edition is enforced server-side | CI | `services/convsim-core/tests/test_edition.py` passes: the five curated conversations resolve to real official-pack files, the demo API serves exactly them, and hidden scenarios, other models, pack import and the Workbench are refused. |
| D-02 | Edition is honoured in the UI | CI | `apps/web/src/__tests__/edition.test.tsx` and the demo cases in the Settings, Debrief and FirstRunWizard suites pass: no link to `/library`, `/workbench` or `/logbook` anywhere in the demo; the wizard has one road. |
| D-03 | One-download first run | Manual, clean OS image, all three platforms | From a fresh Steam install: launch → "Set me up" → download completes → first conversation reachable without any other choice being offered. A stalled download resumes after relaunch. |
| D-04 | Five, and only five | Manual | The demo Home shows the five cards in the curated order; every card starts; typing `/library`, `/workbench` or `/logbook` lands on Home. |
| D-05 | Coherent conversations | Manual, reference hardware | Each of the five, played to the debrief at `standard` difficulty: no incoherent NPC turn, every debrief has rubric scores (no template fallback), each turn within the documented latency budget. |
| D-06 | Save data carries over | Manual | Install the demo, download the model, play one session; install the full app on the same machine: no model download is offered, the session appears in the Logbook. |
| D-07 | Depot audit and signing | CI + manual | `steam-deploy.yml` with `edition: demo` passes the depot audit and artifact inspection for all three platforms; macOS notarised and Windows signed (G3-01) — a demo is under Valve review like any build. |
| D-08 | Offline after install | Manual | With the network disconnected after the download, all five conversations play (G2-01 / F-07 for the demo depot). |
| D-09 | No full-app claims | Manual, publishing owner | Demo store copy and the in-app upsell describe exactly what the demo has (five conversations, one model, text only) and what the full app adds; no "free" claims about the paid app. |

---

## Explicitly out of scope for the demo

- Voice input/output (an extra ~350 MB download and a second setup path — the
  demo has one download by definition).
- Premium DLC, Steam Workshop, Steam Cloud, achievements, rich presence.
- Any demo-only scenario content. Every card is a shipped conversation.
- A separate demo repository or a fork of the release pipeline: the demo is a
  workflow input on the existing one.

---

## Links

- [`publishing/STEAM_NEXT_FEST_DEMO.md`](../publishing/STEAM_NEXT_FEST_DEMO.md) — registration, build, submission runbook
- [`publishing/STEAM_APP_REGISTRATION.md`](../publishing/STEAM_APP_REGISTRATION.md) — identifiers, including the demo app's
- [`publishing/STEAM_STORE_PAGE.md`](../publishing/STEAM_STORE_PAGE.md) — store copy, including the demo section
- [`steam-mvp-scope.md`](steam-mvp-scope.md) — release gates; the demo gate sits between Stage 3 and Stage 4
- [`STEAM_ROADMAP.md`](STEAM_ROADMAP.md) — release train, with the Next Fest demo as stage 3½
- `services/convsim-core/convsim_core/edition.py` — the curated list and the server-side enforcement
- `apps/web/src/edition.tsx` — the UI edition switch
