<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Flyting — the turn-scored game mode

Every other scenario in Conversation Simulator scores once, at the debrief.
A **flyting** scenario scores every player turn as a move: a *volley*, with its
own number, its own multipliers, and its own one-line verdict from the umpire.

*Flyting* is the historical name for ritualised poetic insult exchange — Norse
sagas, sixteenth-century Scottish court flytings, the ancestor of the dozens and
of battle rap. It trains the register the civility packs do not: wit under fire,
economy of language, reading the counterparty, composure when the gloves are
off. The machinery underneath it is general — gates → craft metrics → novelty →
judged rubric → composed score — and the same pipeline serves any drill where
each turn is a scored rep.

Everything here runs locally. There is no outbound call anywhere in the mode,
and the high-score table is a SQLite table on the player's own machine.

- Player-facing page on the docs site: [`play/flyting`](../docs-site/src/content/docs/play/flyting.md)
  — the same mode without the internals; change both when behaviour moves
- Engine: `services/convsim-core/convsim_core/flyting/`
- Judge prompt and verdict verification: `packages/prompt-composer/src/convsim_prompt/flyting_judge.py`
- HTTP surface: `services/convsim-core/convsim_core/routers/flyting.py`
- Launch pack: [`packs/official/flyting-school/`](../packs/official/flyting-school/README.md)

---

## 1. Two formats

### The Bout (two-way)

Player and opponent alternate volleys. `momentum` starts at 50 and shifts after
each exchange by `k · (S_player − S_npc) / 100`, applied through the ordinary
state engine so the scenario's own `max_delta_per_turn` bounds how far one
exchange can move the crowd. The player wins by carrying momentum past
`momentum_win` or by holding the higher cumulative score after `rounds`
exchanges; a tie forces one sudden-death volley, and a tie after that is a draw.

The opponent's volleys go through the same scoring pipeline and its numbers are
shown. Transparency doubles as instruction: seeing why its line scored 140
teaches more than being told yours scored 60. Countering the opponent's last line
earns the **riposte** bonus. Three difficulty tiers (`milquetoast`, `wildean`,
`unhinged_taunter`) map to a persona note plus sampling configuration.

There is no shot clock in a bout. The clock is a batting-practice mechanic (see
below), and the engine ignores a reported `elapsed_since_prompt_s` here whatever
a client sends: a bout is a contest of lines, and zeroing a considered volley
would hand the round, and the momentum swing with it, to the opponent.

### Batting Practice (solo)

A fixed target who reacts — flinches, scoffs, mutters — but never counters.
Three drills:

| Drill | Ends when |
| --- | --- |
| `timed_90` | 90 seconds have elapsed |
| `set_10` | ten volleys have been scored |
| `endless` | three whiffs (a dud, a foul, or a shot-clock expiry) |

A per-volley shot clock (default 20 s, scenario-tunable) keeps it a reflex drill
rather than an essay contest. The clock and the timed drill's elapsed time are
reported by the client that owns them (`elapsed_since_prompt_s`,
`elapsed_total_s`); the engine enforces whatever it is told and does not run its
own timer, so a client that omits them is playing untimed.

Consecutive volleys scoring 60 or above build a **heat** multiplier from ×1.0 to
×2.0 in steps of 0.1. Anything that scores less breaks the chain and the
multiplier drops straight back to ×1.0 — a dud and a foul do that, and so does a
legal volley that merely did not land. Session score is the sum of
`volley score × heat at the moment of scoring` — the multiplier in force when the
volley arrives is the one that pays, so heat is never retroactive.

An optional daily seed (`use_daily_seed`) is derived locally from the date, the
scenario id and the format. It labels the run and groups it on the board —
`GET /scenarios/{id}/high-scores?today=true` returns only the runs played under
today's seed — so two players can compare the same day's runs without a server
ever being involved. It does not yet vary the run itself: seeding the opponent's
sampling needs a seed on the runtime request, which no adapter takes today.

Heat is a batting-practice mechanic only. A bout is decided on raw cumulative
score, so heat stays at ×1.0 there rather than putting a multiplier on the board
total that the win condition never reads.

---

## 2. The volley

One volley is **the full text submitted in a single player turn**, after
normalization (NFC, trimmed, collapsed whitespace, collapsed repeated
punctuation). A multi-sentence submission is still one volley: compound
construction can earn a bonus, but three insults crammed into one turn are not
three volleys.

| Bound | Effect |
| --- | --- |
| under 3 words | a **dud** — scores 0, no foul |
| over 60 words | **run-on**: ×0.9 decay per additional 10 words, *and* the topicality bonus stops accruing |
| over 500 characters | refused at the input (HTTP 400/422) |

Every score, multiplier, bonus and foul attaches to exactly one volley, and a
session result is a pure aggregate over the volley log.

---

## 3. The pipeline

### Stage 0 — Gates (deterministic, before any model call)

The pack's own safety policy runs first, through the same `route_player_input`
every conversation turn uses: global non-overridable rules still fire first and a
flyting pack may only tighten them, never loosen them. A volley that route
refuses or stops scores nothing. Its conduct categories — a real threat, sexual
content, a demand to impersonate a real person — are charged as a Below the Belt
foul, so a second one shortens the same fuse. The one exception is
`self_harm_crisis`, which routes to `stop_with_resource_message`: that volley
scores zero and the run ends, but **no foul is recorded** and the outcome is
`safety_stop`, not `fouled_out` — the same ending the conversation loop writes
for the same route. A crisis disclosure is not a rule of the contest being
broken, and the crisis resource message is the only thing the player reads.

**A refused volley is withheld from every model.** Those three outcomes — a
deterministic Below the Belt match, a refused conduct category, and the crisis
route — are the ones whose text no model is shown at all. Every other gate still
draws the opponent's answer, because losing the exchange is what a dud or a
register foul costs and a target that stopped reacting to a two-word attempt
would read as broken. But the opponent's prompt is literally *"your opponent just
said: …, answer it with one taunt"*, so for these three the opponent says
nothing: no generation, no judge call on a counter, no volley row, no turn row,
nothing in the transcript to be re-read later. A bout still resolves the
exchange, because the round was spent — but against an opponent score of zero, so
the crowd does not move for a line nobody said and `npc_total` is not credited
with one. This is the line the conversation loop already draws, where a `refuse`
is rejected at the input and a `stop` short-circuits to a synthetic response
carrying the router's own message, with the model never called.

On top of that:

| Gate | Outcome |
| --- | --- |
| **Below the Belt** — slurs, protected-class attacks | foul, 0 points, text withheld from every model; a repeat ends the session (this deterministic gate only — see Stage 4) |
| **Out of Fiction** — aimed at the machine or the author | foul, 0 points |
| **Bribing the Ref** — addressed to the judge, or a prompt-injection pattern | foul, 0 points, and the umpire mocks the attempt |
| **Gibberish** — no recognisable words | dud, 0 points, no foul |
| **Profanity** where the pack forbids it | foul (`overt_rudeness`) |
| **Anachronism** where the scenario's `anachronism_policy` is `forbid` | foul |
| **Plagiarized Zinger** — famous material, verbatim or near | capped at 10 points and flagged |

Plagiarism detection is two-part and ships no copyrighted text: keyword
*signatures* for modern taunts, plus lexical near-identity against a bundled
corpus of stock forms and public-domain greatest hits. Quoting a famous taunt at
the character it belongs to is detected and answered with mockery.

A volley the gates zeroed is never sent to the judge.

### Stage 1 — Craft metrics (deterministic, no model)

- **Lexical rarity** — mean Zipf frequency of content words, rewarded in a
  *band* so thesaurus-vomit cannot dominate, and scaled by how much of the
  volley is recognisable words.
- **Internal variety** — type-token ratio, which is what catches
  "stupid stupid stupid".
- **Sound play** — alliteration and assonance runs always; rhyme and rough
  scansion additionally in verse scenarios, where they matter a lot.
- **Aim check** — second-person anchoring. A volley pointed at nobody is flagged
  `no_aim` on the scorecard, and earns almost no sting in the mechanical
  fallback; with a judge available the flag is a coaching signal, and the judge
  scores sting on whether the line lands.

These also provide the mechanical fallback scoring when no judge is available.

**What the frequency table can and cannot say.** `flyting/data/word_frequency_ranks.txt`
is a bundled list of roughly 740 words rather than the `wordfreq` package, so
that the engine carries no extra tens of megabytes into the PyInstaller bundle
(`craft._zipf_for_word` is the seam to swap in a real provider). That list is
ample for the rarity *band* the reward is computed from — it separates a volley
of function words from one with content in it — but it cannot rank two words
that are both outside it. The scorecard's and the debrief's "rarest words that
landed" therefore order that tie longest-first, which is a proxy and says so:
it will surface *sterling* ahead of *worn*, and it has no way to know that
*public* is commoner than either.

**What language these stages read: English, and only English.** Nothing in the
schema says so, so it is said here. The frequency table is an English word
list; the aim check tests for English second-person pronouns (plus the archaic
*thou*/*thee*/*ye*); the onset and rime rewrites that stand in for a real
grapheme-to-phoneme pass are English spelling rules; and the
recognisable-word test behind the gibberish gate reduces every token to
`[a-z']+` before it looks at it. The consequences differ by script:

- **A Latin-script language other than English** degrades silently. Every
  content word is unknown to the frequency table, so the rarity reward is a
  flat band value rather than a measurement, and no volley ever passes the
  second-person check — so each one carries `no_aim`, the mechanical fallback
  scores it as unaimed, and the debrief reports every volley as pointed at
  nobody. The judge, which does read the language, still scores it.
- **A non-Latin script cannot be played at all.** No token survives the
  `[a-z']+` filter, so `recognizable_ratio` is zero, the gibberish gate duds
  every volley at zero, and the judge is never called — a gated volley never
  reaches a model.

`craft._zipf_for_word`, `_measurable_parts`, `_onset` and `_rime` are the four
seams a language-aware version would go through. Until then, the pack validator
warns (`FLYTING_NON_ENGLISH_SCENARIO`) when a `mode: flyting` scenario declares
no English support, rather than letting an author discover it one dudded volley
at a time.

### Stage 2 — Novelty

`s_max` is the highest similarity between this volley and (a) every prior volley
this session, the player's *and* the opponent's — so parroting the opponent
counts as redundancy — and (b) the shipped cliché corpus.

```
F = clamp(1 − s_max², 0.1, 1.0)
```

Squaring forgives family resemblance and hammers near-duplicates: sharing a
subject (0.4) keeps 84 % of value, a rephrasing (0.9) keeps 19 %.

Similarity is lemma Jaccard plus character-trigram cosine — deterministic,
offline, no download — and the method is reported on the scorecard, so a player
is never confused about why two runs scored differently.

Embeddings are a seam, not yet a feature: `novelty.EmbeddingProvider` is the
interface the scoring service accepts, and when one is supplied `s_max` becomes
cosine similarity over embeddings and the scorecard reads `embedding` instead of
`lexical`. Nothing implements it today — no runtime adapter reports embedding
support and the registry ships no embedding model — so every run uses the
lexical comparison. Adding the provider is a change in one place, which is why
the seam exists.

**Theme decay** lives here too: the *n*th volley whose primary theme has already
been used has its topicality bonus scaled by `theme_decay^(n−1)` (0.75 by
default). The third hygiene joke is visibly near-worthless — variety is the meta.

Only a volley's *primary* theme counts as a use of that well — the judge tags
three or four themes for one line, and counting all of them would decay a well
the player never actually returned to.

Each speaker is also decayed by its *own* record. The player's counter holds the
player's volleys and the opponent's holds the opponent's: parroting the opponent
is already redundancy by the freshness rule above, and a well the opponent
reached for first is not one the player returned to — nor the other way round. A
single shared counter discounted each side for the other's repeats, and in a bout
that discount lands directly on `k · (S_you − S_npc) / 100`. The debrief's
redundancy report is computed from the player's counter, so the percentage it
prints is the factor the engine applied.

### Stage 3 — The judge

Exactly one model call per volley: temperature 0, output constrained to
`FLYTING_JUDGE_OUTPUT_SCHEMA`, rubric-anchored with three calibration examples
per dimension. Unusable output gets one repair attempt, then the volley is scored
from its mechanics and flagged `judge_unavailable` — the engine never invents
numbers no model produced.

```json
{
  "sting": 8, "wit": 7, "craft": 9, "fidelity": 9,
  "hooks":   [{"trait": "hypocrisy", "evidence": "polish your virtue"}],
  "themes":  ["appearance", "hypocrisy"],
  "devices": ["metaphor", "triple"],
  "riposte": {"is_riposte": false, "evidence": null},
  "callback": {"is_callback": false, "evidence": null},
  "fouls":   [],
  "umpire_line": "One sentence of in-character commentary."
}
```

The judge is a referee and never a performer: it is a separate call from the
NPC's own turn, so one prompt injection cannot poison both, and the referee can
be audited. `themes` and `devices` are closed vocabularies, because they drive
theme decay and the device-rotation bonus and must be stable slugs rather than
whatever phrasing the model reaches for.

**Hooks are verified, not trusted.** A hook claim must name a trait id from the
target's declared `attack_surface` *and* quote the player's own words. The engine
drops any claim whose trait is unknown or whose evidence is not actually present
in the volley, records why in `dropped_hooks`, and keeps at most four. That
verification is what makes "the insult was topical" countable rather than a
matter of the model's mood.

Each hook must also quote *different* words: a claim quoting substantially the
same span as one already accepted for this volley is dropped as
`overlapping_evidence`. Local judges really do reach for the whole volley as
evidence for every trait they can see in it, and they slide one clause along by
three words to claim it twice; without the rule, one figure collects the whole
topicality bonus two or three times over — exactly the padding the hook cap and
the decreasing bonuses exist to prevent. Two hooks means two parts of the line
did two different jobs.

A whole-volley quotation is allowed once, and only as the first hook: a
sustained figure can be the hook, and a judge that opens broad should not block
the narrower second claim that follows it.

The system prompt holds only what is constant for a whole run — rules, register,
target, anchors, output schema — so a runtime with prompt caching reuses all of
it on every volley; the session context and the volley itself are the user turn.

### Stage 4 — Composition

```
Q = Σ weight[dim] · judge[dim] / 10                 # 0 .. 1
T = 1 + Σ hook_bonus[i] · theme_decay               # doubled for a discovery
F = freshness                                       # 0.1 .. 1.0
P = scenario difficulty_multiplier                  # 0.8 .. 1.5
D = run-on decay                                    # 1.0, or 0.9^k past 60 words

S = round(100 · Q · T · F · P · D) + bonuses
```

Default weights are `sting 0.35, wit 0.25, craft 0.20, fidelity 0.20`; default
hook bonuses are `[0.15, 0.12, 0.08, 0.05]`. Bonuses: **riposte** (bout only,
scenario-configurable, 15 by default), **callback** +10, **device rotation** +5
(a device unused in the last three volleys), **compound** +5 (two independent
constructions that both land).

In a bout every one of those bonuses is open to the opponent on the same terms,
because a bonus only one side can reach is a thumb on `k · (S_you − S_npc) / 100`.
Each is checked against that speaker's own record: its own device rotation, its
own theme well, the player's line as the thing its riposte has to turn back, and
the session's earlier lines as the thing its callback has to refer to.

Two rules exist specifically to make padding worthless: past the soft cap the
run-on decay applies *and* `T` collapses to 1, and a plagiarized zinger is capped
*before* bonuses — a borrowed line with a riposte attached is still a borrowed
line.

Bands: `dud` 0 · `weak` 1–59 · `solid` 60–119 · `strong` 120–179 ·
`highlight` 180+.

A foul is resolved here too, not only in Stage 0. The register fouls only a
reader of the scene can raise arrive with the judge's verdict, and composition
promotes them to the same outcome a Stage 0 foul produces: 0 points, no bonuses,
the foul recorded, the heat reset, the whiff counted, and a foul tag on the
scorecard.

With one exception: a judge-raised foul never *ends* the run, `below_the_belt`
included. Closing somebody's session is the costliest thing this engine does to
a player, and it rests on evidence rather than on a 4B model's reading —
measured against the registry's starter model, "You are all fools and idiots
and I despise every one of you" draws a `below_the_belt` verdict, and two of
those would have ended a run for ordinary abuse in a scenario whose whole
register is ordinary abuse. The Stage 0 pattern, which matches an actual slur
deterministically, still ends a run on its second occurrence.

Which judge fouls count is the scenario's business, because that is what the
judge was asked for. `below_the_belt` and `out_of_fiction` are never a pack's
choice. `overt_rudeness` counts only where `register.overt_rudeness_is_foul` is
true — otherwise the judge was told it costs fidelity points, not the volley —
and `anachronism` only where `anachronism_policy` is `forbid` rather than
`penalize`. A foul outside that set stays on the stored verdict as a note and
does not void the line.

#### Worked example

Victorian scenario; target's surface includes `vanity`, `hypocrisy`,
`cowardice`, `new_money`:

> "Lord B—, you polish your virtue like your carriage brass — and both are
> plate, not sterling, worn thin where the public grips them."

Judge: sting 8, wit 8, craft 9, fidelity 9 → **Q = 0.84**. Verified hooks:
`hypocrisy` ("polish your virtue") and `new_money` ("plate, not sterling").
`hypocrisy` is visible in the brief and pays its ordinary 0.15; `new_money` is
`visibility: discoverable` on this target and has not been struck before, so
this is the discovery and its 0.12 is doubled → **T = 1 + 0.15 + 0.24 = 1.39**.
Nothing in the session resembles the line and its nearest match in the shipped
cliché corpus sits at `s_max = 0.25` → **F = 0.94**. Period-diction scenario →
**P = 1.2**. Device rotation +5.

```
S = round(100 × 0.84 × 1.39 × 0.94 × 1.2) + 5 = 136
```

Two figures here a reader cannot derive from the volley and the verdict alone.
`F` is measured against the corpus and the session; this is the lexical tier's
answer, which is every run's answer today (§2), and the embedding tier would
put the same line's novelty somewhere else. And the doubling of the second hook
depends on the *run* rather than on the volley: strike `new_money` a second time
later in the same session and the same words are worth `T = 1.27` instead, which
is what the scorecard will then show.

The proposal this example comes from quoted `F = 0.97`, counted neither hook as
a discovery, and therefore arrived at 129. The numbers above are what the engine
actually produces: `test_flyting_scoring.TestWorkedExample` runs this volley and
this verdict through the real scenario, the real novelty stage and the real hook
verification, so this paragraph cannot drift away from the scorecard.

The scorecard shows this arithmetic. That is what makes it a practice tool rather
than a slot machine, and the full judge verdict is kept in SQLite so any volley
can be re-inspected months later with no model involved.

---

## 4. Authoring a flyting scenario

All of it is additive, schema-validated pack YAML. Existing packs are unaffected:
omitting `mode` means `conversation`, exactly as before.

`scenarios/*.yaml`:

```yaml
mode: flyting
flyting:
  formats: [bout, batting_practice]
  bout: { rounds: 8, momentum_win: 85, momentum_k: 4, riposte_bonus: 15, npc_tier: wildean }
  batting_practice: { shot_clock_s: 20, formats: [timed_90, set_10, endless] }
  difficulty_multiplier: 1.2
  lexicon:
    encouraged: [scoundrel, blackguard]     # surfaced as hints, never required
    discouraged: [awesome, vibe]
    anachronism_policy: penalize            # off | penalize | forbid
  register:
    require_surface_politeness: false       # true = the sting must wear gloves
    overt_rudeness_is_foul: false
    notes: "Period diction, pitched for the steps to hear."
  verse: { required: false }                # true = alliteration and scansion scored
  judge_flavor: "A retired music-hall chairman. Cockney. Unimpressable."
```

`npcs/*.yaml` gains the **attack surface** — the roastable topology of the
character, and exactly what Stage 3 hooks are verified against:

```yaml
attack_surface:
  - id: hypocrisy
    brief: "Preaches temperance at chapel; owns two gin palaces through a cousin."
    visibility: visible        # in the player's brief from the start
  - id: cowardice
    brief: "Bought his way out of the Crimea; flinches at fireworks."
    visibility: discoverable   # revealed when first struck; worth double on discovery
```

A discoverable trait is counted but not named in the setup payload: a trait the
brief gives away cannot be worth double when the player finds it.

`rubrics/*.yaml` may carry a `volley_judge` block (weights, anchors,
`hook_bonus`, `theme_decay`) so a pack can rebalance the judge — a Regency pack
weights `fidelity` up and requires surface politeness. Supplying `anchors`
**replaces** the engine's defaults rather than merging with them, which is
deliberate (a pack's register is its own, and half-and-half anchors would teach
the judge two voices) but means a pack that anchors one dimension has to anchor
all four, three deep. Omit the block entirely to keep the engine's twelve. `scenes/*.yaml` may carry
an `audience` block whose reactions fire at score bands. `safety/*.yaml` is
mechanically unchanged; flyting packs pin PG-13 or below and may forbid profanity
outright.

The pack validator reports the mistakes JSON Schema cannot express: a target with
no attack surface (`FLYTING_NO_ATTACK_SURFACE`), a thin or fully visible surface,
judge weights that do not sum to 1.0, a dimension with no anchor
(`FLYTING_ANCHOR_COVERAGE`) or with fewer than three (`FLYTING_ANCHOR_DEPTH`),
a calibration
suite that names a scenario or trait that does not exist, and a scenario
declaring no English support (`FLYTING_NON_ENGLISH_SCENARIO` — see Stage 1 for
what the deterministic stages can and cannot read).

---

## 5. Calibration

`<pack>/calibration/*.yaml` holds reference volleys with the outcome each must
receive. `scripts/flyting-calibration.py` runs them:

```sh
python scripts/flyting-calibration.py                             # every official pack
python scripts/flyting-calibration.py --judge llama_cpp           # include judged tiers
python scripts/flyting-calibration.py --judge llama_cpp --limit 3 # a bounded sample
```

The **deterministic** expectations — `gate`, `foul`, `flags`, the plagiarism cap
— are pure functions of the volley and the pack, so they run in CI on every
commit (`services/convsim-core/tests/test_flyting_calibration.py`). The
**judged** expectations — `band`, `min_score`, `max_score`, `hooks` — need a
model and are skipped unless `--judge` names a runtime; that is the run that
catches prompt or model drift before players see it. One exception: a `band` on
a volley the gates zeroed is deterministic too — that volley scores 0 whatever
a judge would have said, and never reaches a model — so `band: dud` beside a
`gate: foul` is checked on every commit along with the gate it asserts.

A judged run costs one model call per volley that clears the gates: 178
reference volleys in the launch pack, 147 of which reach the judge, at around
7 s each against a warm starter model on a developer machine — a few minutes
for the pack, and far longer on a CPU CI runner, which measures a
grammar-constrained turn in minutes rather than seconds. So the judged tier is
not in the nightly by default — `--limit N` takes a bounded sample, spending it
on the volleys that actually reach the judge rather than on gated ones CI
already checks every commit (so `--limit 3` is three judge calls per suite,
fifteen for the launch pack), and `model-smoke-nightly.yml` accepts
`flyting_judged=true` on a manual dispatch to run that sample against the same
cached starter model and upload the report. The report carries every volley's dimensions, verified hooks,
dropped hooks and flags, so a band that moved is readable without a re-run.

**What the judged bands are pinned to.** The launch pack's judged expectations
record what the registry's `starter` model (`qwen3-4b-instruct-q4_k_m`,
llama.cpp, temperature 0) actually produces, measured against a live server.
Repeated runs produce identical results — same score, same dimension scores,
same verified hooks — which is the determinism the mode claims: temperature 0
plus a schema-constrained decode, in practice and not just in principle. The
expectations are drift guards, not verdicts on the writing: a deliberate change
to the judge prompt moves them and is expected to come with a re-measurement.

**Coverage, honestly.** Four of the five suites carry around forty reference
volleys. Veiled Civility carries twelve, and the five most recent of those are
Stage 0 outcomes only. What it ships is measured like the rest: the six entries
that reach the judge were run against the starter model, and the suite's own
`description` records the model and the date — nothing in the file claims
something nobody has checked. What is missing is depth. The rest of the batch it
was being deepened with is written but has no measured band, and pinning a band
by inspection would be worse than leaving it out, so it is not here. Finishing
it is a matter of running `--judge` against the starter model and pasting what
comes back.

Some entries deliberately pin behaviour that is wrong rather than behaviour
that is wanted, because that is what a drift guard is for. The clearest are the
volleys with no second person, no vocative and no imperative, which the judge
is told cannot score above 3 on sting and which the starter model scores 9;
`whitechapel_rose/aimed_at_nobody` is the starkest. The engine does not
reconcile the two, because `craft.second_person` reads pronouns and so cannot
tell "aimed at nobody" from "addressed by name" — `whitechapel_rose/vocative_no_pronoun`
is the counter-example that makes capping sting on it the wrong fix.

**A reference volley is measured in isolation**, which is what makes a recorded
band reproducible: a suite is a set of independent measurements, not a replay of
a session. So no run-dependent input is present — no prior volleys (freshness is
measured against the cliché corpus alone), no session theme record (theme decay
never applies), no device-rotation window, and no discovery ledger. The last of
those has a visible consequence: eight reference volleys across four suites exist
to strike a *discoverable* trait, and their bands are the **undoubled** numbers,
because `HookClaim.discovered` is false with no ledger to consult. The judged
tier therefore cannot catch a regression in the ×2 discovery bonus —
`test_flyting_scoring.py` covers that directly instead — and each of the eight
notes says so where the band is recorded. Supplying an empty ledger would
exercise it and would raise all eight bands by roughly the first hook's bonus
again, which is a re-measurement against a real model rather than an edit.

Two further limitations the measurement exposed are worth knowing before reading
a scorecard, because neither is a bug:

- A small judge rewards a **well-made line aimed at nobody**. The engine flags
  `no_aim`, the debrief says "*n* volleys never pointed at anyone", and the
  judge is told that sting requires aim — but sting stays the judge's to award,
  so an unaimed aphorism can still score like a hit on a 4B model.
- The scenario **difficulty multiplier lifts everything**, non-hits included.
  In Veiled Civility (`P = 1.5`, fidelity weighted up) a courteous line with
  nothing inside it reaches the bottom of `solid`. The bands are absolute
  across scenarios; the multiplier is not.

---

## 6. HTTP surface

| Route | Purpose |
| --- | --- |
| `GET /api/flyting/scenarios` | installed flyting scenarios, with formats and personal bests |
| `GET /api/flyting/scenarios/{id}` | setup payload: brief, visible attack surface, limits, boards |
| `GET /api/flyting/scenarios/{id}/high-scores` | the local board, narrowable by `play_format`, `batting_format`, `daily_seed`, or `today=true` |
| `POST /api/flyting/sessions` | start a run |
| `GET /api/flyting/sessions/{id}` | run state and the volley log |
| `POST /api/flyting/sessions/{id}/volley` | submit one volley, get the scorecard |
| `POST /api/flyting/sessions/{id}/end` | finish the run, get the debrief, record the board |
| `POST /api/flyting/preview` | score a draft volley with no run (Creator Workbench) |

A flyting run is an ordinary `turn_sessions` row, so transcript export, session
deletion, and the Logbook work on one without special cases. The volley log
(`flyting_volleys`) holds what each line was *worth*; the turn rows hold what was
*said*. Momentum is mirrored into the ordinary state-variable snapshot so the
existing meter UI reads it like any other meter; heat lives on the run state,
because the state engine stores integers and heat is a multiplier.

Scorecards are serialised to [`schemas/volley-score.schema.json`](../schemas/volley-score.schema.json).
