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
| Tauri shell | `CONVSIM_EDITION=demo` at compile time (`build.rs` validates it; `lib.rs` passes it to the sidecar) and the `tauri.demo.conf.json` overlay | Product name "Conversation Simulator Demo", its own bundle identifier, its own icon set (see [Store assets](#store-assets)), and the same per-user data directory as the full app (see [Save data](#does-demo-save-data-carry-over)). |
| CI | `release.yml` → `edition: demo` (workflow_dispatch) | Builds all three platforms as the demo edition, uploads `demo-desktop-*` artifacts, publishes **no** GitHub release, and hands off to `steam-deploy.yml` with `edition: demo`, which targets `STEAM_DEMO_APP_ID` and the demo depots. |

The curated list lives in **one place**: `services/convsim-core/convsim_core/edition.py`.
The UI renders whatever the engine reports, so the five cannot drift between
the two.

To see the demo locally, run the engine with `CONVSIM_EDITION=demo` (the web
UI adopts the engine's answer; the build-time flag is optional in dev):

```sh
CONVSIM_EDITION=demo ./scripts/dev.sh
```

---

## Decisions

### Which model?

**The demo ships the registry's starter tier, Qwen3 4B Instruct 2507
Q4_K_M (2.5 GB, Apache-2.0).** The demo edition installs whatever the registry's
`role: starter` entry is, or the model named by `CONVSIM_DEMO_MODEL_ID`, so
this is a configuration decision, not a code one.

Until v0.4 the starter was the hybrid Qwen3 4B (`qwen3-4b-instruct-q4_k_m`),
run with reasoning off. Issue #580 replayed the five demo conversations
(`scripts/demo-gate-replay.py`) on both 4B models with the same code, and the
2507 instruct release was more coherent in every one. It follows Ray's counter
ladder, confirms Rosa's orders instead of offering them back, and answers the
player's direct questions where the hybrid model looped. It is the same size
and licence, and needs the same hardware. Qwen publishes no GGUF of 2507, so
the registry pins unsloth's quantisation by revision and digest. Its replies
run longer than the hybrid model's, and the replays ran on a CPU-only VM, so
D-05's latency clause on the reference hardware is still the check that it
fits the budget.

The note asked "can we use a smaller/faster Qwen model?" — evaluated, and not
for the first Next Fest build:

- A 4B is the smallest tier the nightly real-model smoke
  (`scripts/nightly-model-smoke.py`) and the release-checklist reference
  hardware have been run against (the hybrid 4B, so far). The demo's
  quality bar is defined by *incoherent NPC turns* and *missing debriefs*
  being blockers; the turn pipeline asks the model for structured output
  (state deltas, event evaluation) and the debrief asks for a rubric-scored
  analysis. 1.7B-class
  models are markedly less reliable at both, and a 0.6B model is out of the
  question for this product. A stalled 2.5 GB download is recoverable (the
  pipeline resumes it); an incoherent character is the demo lost.
- On the reference tier the hybrid 4B already hit the documented latency
  budget, so "faster" buys little that a player would notice at Next Fest.

**How to revisit it, cheaply.** `scripts/pin-model.py` prints a policy-compliant
registry entry (commit-pinned URL, SHA-256 from the Hub's LFS metadata) for
any Hugging Face GGUF. The gate for a smaller tier is:

1. Add the entry with `pin-model.py` (candidate: `Qwen/Qwen3-1.7B-GGUF`,
   `Qwen3-1.7B-Q4_K_M.gguf`, ~1.1 GB; or the Q8_0 quant at ~1.8 GB if quality
   needs the headroom) and validate with `scripts/validate-registry.py --url-check`.
2. Run the nightly smoke against it (`--model-id`) on the reference hardware.
3. Play all five demo conversations to the debrief at `standard` difficulty,
   twice each; zero incoherent turns, zero template-fallback debriefs.
4. Set `CONVSIM_DEMO_MODEL_ID` in the demo build and re-run the
   [demo gate](#demo-gate). No code changes.

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

The demo plays only its own model. A full-app profile can hold other models;
one from before v0.4 has the earlier starter (`qwen3-4b-instruct-q4_k_m`)
installed and selected. In the demo only the demo model's own files count: the
engine autostart (`runtime/active.py`) starts the engine only on the demo
model's install, never on the full app's selection or its other installs, and
the setup status, the Home screen and Support's AI-model check count only that
install. Every turn and the debrief are sent with the demo model's registry
sampling (its `temperature_default` and `top_p_default`), and the turn timing
records name the demo model, whatever the full app has selected. A player who
does not have it is offered the demo's one download, as a new player is.

The demo also runs only on the managed engine (llama.cpp). Whatever runtime
the full app's saved selection names, Ollama included, the demo boots
llama.cpp (`resolve_startup_runtime_id` in `runtime/active.py`), and its
autostart loads the demo model's install. With nothing saved it boots
llama.cpp too when `CONVSIM_RUNTIME_ID` names another model runtime, and the
configured default only when that is model-free (the `fake` runtime packaged
builds start with), so a new player gets the no-model message instead of a
conversation. A session that would follow a live runtime other than
llama.cpp is refused with `EDITION_RESTRICTED`; sessions pinned to a
model-free runtime (tests, the replay's self-test) do not use the live
runtime and are not affected.

The full app's selection is left as it is. When the demo's one-click install
finishes (`routers/setup_install.py`), it saves the demo model as the
selection only when nothing is selected yet, only a model-free runtime
(`fake`, `scripted`) is, or the selection already names one of the demo
model's files. A selection that names Ollama, or llama.cpp with any other
file (the earlier starter, the player's own GGUF), is kept, so the full app
keeps playing it; the demo finds its own install without it. A llama.cpp
selection with no file is kept too, but it means "the newest ready install",
so once the demo has downloaded its model the full app plays that one. A player who installs the demo
model on a fresh profile and then the full app gets the model selected there,
and no download. The demo never deletes the full app's files.

### Store assets

The demo attaches to the base app's store page as its demo; Valve renders the
"Download Demo" button there.

**The demo has its own icon.** The Steam client lists the demo and the full
game side by side, and while they shared an icon the two entries were
indistinguishable (issue #499). The demo's mark is the same speech bubble on a
deep purple plate instead of the full game's teal, with a "DEMO" ribbon on the
frames large enough to read one.

The entry in that screenshot is Steamworks' **App Icon**: 184 × 184 JPG, which
Valve's [Community and Client Icons][steam-icons] spec describes as what the
client draws "in the library list view, 'favorites' in chat, and notifications
across the Steam client, mobile client, and Deck". There is no 32 px "client
icon" field. The App Icon carries both cues — the purple plate and the ribbon
— and Steam rescales it, so in that library row it is drawn at about 35 px,
where the ribbon still reads as a dark corner tag even though its lettering
does not. The bundle's own 16–32 px frames carry no ribbon at all and are
separated by colour alone; the OS draws those at native size in the taskbar
and Finder's list view, and a band there would only muddy the silhouette.

One generator, `publishing/assets/source/gen_icons.py`, produces the App Icon,
the 256 × 256 **Shortcut Icon** Steam puts on the desktop, and the icon set the
demo build installs, so the store entry and the app on the player's dock agree;
Steamworks' **Mac Icon** field takes `icons-demo/icon.icns` from that same set.
Upload destinations are in the runbook (§4.2).

[steam-icons]: https://partner.steamgames.com/doc/store/assets/community

**The demo has its own capsule and library art** (issue #551: without it the
demo's library entry and store presence rendered blank).
`gen_capsules.py --edition demo` draws the full game's capsules on the demo
icon's purple plate, with the player bubble white as on the icon and the
icon's "DEMO" ribbon in the lower-right corner of every asset allowed to carry
the name; the library hero, which Valve keeps free of text, gets the plate
without the ribbon. The set is committed under
`publishing/assets/capsules/demo/` and still has to be uploaded on App 5343430
(runbook §4.2).

Screenshots are demo-edition screenshots of the five
conversations (the Home picker, one conversation, one debrief) so nothing shown
is unreachable in the demo. No separate trailer: the base trailer is used.
Details in the runbook.

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
| D-10 | Demo is distinguishable in the Steam client | CI + manual | `tests/acceptance/test_demo_branding.py` passes: `tauri.demo.conf.json` overrides every `bundle.icon` entry, the demo plate is far from the base plate in colour, and the "DEMO" ribbon is on the large frames only; every demo capsule and library asset is at Valve's size, on the demo plate, ribboned where it may carry the name and not on the hero. Manual half: the demo's App Icon (184 × 184 JPG), Shortcut Icon and Mac Icon are uploaded on App 5343430 under Store Presence → Graphical Assets → Community and Client Icons, its capsules and library assets from `publishing/assets/capsules/demo/` under Store Assets and Library Assets on the same page, and the two library entries read apart at a glance. |

**D-05 has an automated pre-check.** `scripts/demo-gate-replay.py` plays each
of the five conversations to the debrief against a running convsim-core on the
real model, twice by default, with scripted player turns that press on each
NPC's hidden agenda (`tests/fixtures/demo-gate/player-turns.yaml`). On every
turn and run it asserts that the NPC repeats no 6-word run and no closing
question of 4+ words from its previous line (unless the player asked it to say
it again, as spanish_coffee's third turn does), says no 5-word run of its hidden
agenda aloud and no 3+ digit number from it (Ray's $13,800 floor, in digits or
words), never answers with the engine's canned fallback line, applies a
non-zero change to at least one variable the scenario authors, and gets a
debrief that generated without the template fallback and scored only the
rubric's own dimension ids. It plays each turn with the session's socket open,
as the conversation screen holds it, so the engine streams every line as it
does for a player and the checks read what reached the screen; a streamed
line that differs from the one committed fails the run (`--rest-only` plays
over REST alone, which is not a D-05 result). It writes a JSON record per run
and a markdown summary, and exits non-zero on a hard failure. Those checks are
blocking by default (`--warn <check>` makes one a warning): the engine scores
each demo debrief on its scenario rubric's dimensions only (issue #578), and the
turn schema requires every variable the scenario authors in each reply's state
change, with the prompt saying what each means (issue #580). One more check
is a warning by default (`--hard g` makes it blocking): the state change
reads as changes, not as the values the prompt showed. The schema's numbers
carry no bound, so a model that copies the state's values moves every
variable by its full per-turn limit, and the conversation reaches an ending
on pacing alone. The
engine must run the demo edition (`CONVSIM_EDITION=demo`), which plays the
five from their curated packs; the
replay refuses any other edition unless `--allow-full-edition` is given, and
then marks the result as not a D-05 result. Runs are kept independent: the
replay deletes each NPC's relationship-memory recap, which every debrief
writes and the next session's prompt reads, before and after every run, and
refuses to start over a recap that already existed (`--clear-npc-memory`
deletes it). The sessions themselves stay in the engine's history, so run the
engine on a throwaway `CONVSIM_DATA_ROOT`. A release candidate should pass the
pre-check before the manual D-05 run. It does not replace the manual
judgement: whether each reply makes sense, keeps its role and answers the
player is still read by a person on reference hardware.

The engine counts a repeat with the same word rules as the pre-check
(`convsim_prompt.repetition`, which the checks import), and generates once
more any reply that repeats one of the NPC's last two lines (issue #580),
unless part of it is already on screen: with the conversation screen open the
line streams, and only a repeat in its first sentence can still be retried. So
a repetition finding means that the retry did not help, or that the repeat
came after the first sentence of a streamed line. Each retry is an extra model
call on that turn; the summary counts them per run next to the turn times, to
watch against the latency budget on reference hardware.

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
