---
title: "Flyting — scored insult practice"
description: "How the turn-scored flyting mode plays: the Bout and Batting Practice, what a volley scores and why, the fouls to avoid, and where your high scores are kept."
sidebar:
  order: 5
---
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Every other scenario in Conversation Simulator scores once, at the debrief. A
**flyting** scenario scores every turn you take as a move: a *volley*, with its
own number, its own multipliers, and a one-line verdict from the umpire.

*Flyting* is the historical name for ritualised insult exchange — Norse sagas,
sixteenth-century Scottish court flytings, the ancestor of the dozens and of
battle rap. It trains the register the civility packs do not: wit under fire,
economy of language, reading your counterparty, composure when the gloves come
off.

Like the rest of the app it runs entirely on your computer. There is no
outbound call anywhere in the mode, and the high-score board is a table in the
same local database as your transcripts — see [Privacy](/trust/privacy/).

---

## Starting a run

1. Open **Browse scenarios**. A flyting scenario carries a **Flyting — scored
   every turn** chip on its card, and **Launch** opens the flyting setup screen
   instead of the usual conversation brief.
2. Read the **attack surface** — the list of things about the target that are
   fair game. This is the point of the brief: it is the only thing the judge is
   allowed to credit you for hitting. Some traits are withheld and revealed
   when you first strike them, and those are worth double on discovery.
3. Pick a format, optionally tick **Use today's seed**, and start.

The setup screen also shows the scenario's difficulty multiplier, whether verse
is scored, whether overt rudeness is a foul in this room, and your personal
best for the format you have selected.

---

## The two formats

### The Bout

You and the target alternate volleys. **Momentum** starts at 50 and shifts after
each exchange in proportion to the difference between your score and theirs. You
win by carrying momentum past the scenario's threshold — the crowd carries you
out on their shoulders — or by holding the higher cumulative score when the
rounds run out. A tie forces one sudden-death volley; a tie after that is a
draw.

The target's volleys go through the same scoring pipeline, and its numbers are
shown. That is deliberate instruction: seeing why its line scored 140 teaches
more than being told yours scored 60. Countering its last line earns a
**riposte** bonus.

There is no shot clock in a bout. It is a contest of lines, not of reflexes.

### Batting Practice

A target who reacts — flinches, scoffs, mutters — but never counters. Three
drills:

| Drill | Ends when |
|---|---|
| **Timed** | 90 seconds have passed |
| **Set** | ten volleys have been scored (the fairest run to compare) |
| **Endless** | three whiffs — a dud, a foul, or the shot clock running out |

A per-volley **shot clock** (20 seconds by default, tunable per scenario) keeps
it a reflex drill rather than an essay contest. When it expires, whatever is in
the box is submitted for you, and that counts as a whiff.

Consecutive volleys scoring 60 or more build a **heat** multiplier from ×1.0 to
×2.0 in steps of 0.1. Anything scoring less than 60 drops it straight back to
×1.0 — a dud and a foul do that, and so does a legal volley that merely did not
land. Your session score is
the sum of each volley's score times the heat in force when it landed — heat is
never applied retroactively. Heat is a batting-practice mechanic only; a bout is
decided on raw points.

---

## What counts as one volley

One volley is **everything you submit in a single turn**. A multi-sentence
submission is still one volley: two independent constructions that both land can
earn a compound bonus, but three insults crammed into one turn are not three
volleys.

| Bound | What happens |
|---|---|
| Under 3 words | a **dud** — zero points, but not a foul |
| Over 60 words | **run-on** — length is taxed, and topicality stops accruing |
| Over 500 characters | refused at the input, before anything is scored |

---

## What a volley scores

Four things are multiplied together, and bonuses are added afterwards:

| Factor | What it rewards |
|---|---|
| **Quality** | the judge's four dimensions — *sting* (does it land on **this** target), *wit* (surprise, cleverness, economy), *craft* (imagery, construction, sound), *fidelity* (in character, in register, in period) |
| **Topicality** | verified hooks into the target's attack surface, up to four, with decreasing value — and doubled for a trait you discover |
| **Freshness** | how unlike everything already said this line is, including the opponent's lines and a bundled corpus of stock insults |
| **Difficulty** | the scenario's own multiplier, printed on its setup screen |

Bonuses: **riposte** (bout only, for countering their last line), **callback**
(+10, for a verified reference to an earlier exchange), **device rotation** (+5,
for a figure you have not used in the last three volleys), and **compound** (+5,
for two independent constructions that both land).

| Band | Score |
|---|---|
| Dud | 0 |
| Weak | 1–59 |
| Solid hit | 60–119 |
| Strong | 120–179 |
| Highlight reel | 180+ |

**Hooks are verified, not taken on trust.** For a hook to count, the judge has
to name a trait the target actually declares *and* quote your own words that
exploit it — and each hook has to quote different words. The scorecard lists
every hook that was accepted, with the quotation, and every claim that was
dropped. That is what makes "the insult was topical" a countable thing rather
than a matter of the model's mood.

**Repetition is worthless by design.** Going back to a theme you have already
used decays its value — the third hygiene joke is worth a fraction of the first
— and a near-rephrasing of anything already said keeps very little of its
score.

---

## What costs you

| Foul | What it is |
|---|---|
| **Below the Belt** | a slur or an attack on who someone is. Zero points; a repeat ends the run |
| **Out of Fiction** | aimed past the character, at the machine or the author |
| **Bribing the Ref** | addressed to the scorer rather than the target — including attempts to instruct the engine. The umpire will mock you for it |
| **Overt Rudeness** | in scenarios where the sting has to wear gloves, or where the pack forbids profanity |
| **Anachronism** | in scenarios whose policy forbids it — a smartphone in 1849 |

Two more outcomes are not fouls but still cost you: **gibberish** scores as a
dud, and a **plagiarized zinger** — a famous taunt, quoted or lightly
paraphrased — is capped at 10 points and flagged, before any bonus is added. The
mode ships no copyrighted dialogue, and quoting a famous line at the character
it belongs to is detected and answered with mockery.

Crudeness is not a shortcut: sting requires aim, wit requires surprise, and
craft requires construction, so a cheap line earns little on any dimension.
Clean-but-cutting is the winning strategy. Flyting packs are rated PG-13 or
below and may forbid profanity outright; the
[safety policy](/trust/safety-policy/) is unchanged and non-overridable.

---

## Reading the scorecard

Every volley gets a scorecard that shows its own arithmetic: the dimension bars,
the verified hooks with the words that earned them, the freshness meter, the
multipliers, any gate that fired, and the umpire's one-liner in the scenario's
umpire voice. Nothing in the score is hidden from you, and the full judge
verdict is kept locally, so a volley can be re-read months later with no model
involved.

The debrief at the end of a run adds:

- **Best volley** — the line of the run, with its score.
- **Coaching notes** — what the shape of the run says, such as openers
  outscoring closers.
- **Redundancy report** — the wells you went back to, and what they had decayed
  to.
- **Devices you reached for** — a histogram of the figures you used.
- **Rarest words that landed** — vocabulary that earned its place.
- **Every volley** — the whole log, each card still inspectable.
- **Your board** — the local high-score table for this scenario and format.

---

## Your board and the daily seed

High scores are stored per scenario and per format on your own machine, and
nowhere else. Ticking **Use today's seed** labels the run with a seed derived
from the date, the scenario and the format, and marks it on the board with a ◆.
Ticking **Today's seed only** above the board hides everything else, so you and
someone else playing the same scenario on the same day are reading the same
day's runs — with no server involved, because the seed is a function of the date
and the names of the things you picked. The seed labels and groups a run; it does
not yet change what the run does.

---

## The Flyting School pack

The launch pack ships five scenarios, all PG-13, all CC BY 4.0:

| Scenario | You are | The target |
|---|---|---|
| The Scorned Rose of Whitechapel | a woman he ruined and discarded | the wealthy adulterer, on his club steps — period diction is scored |
| The Tower Guard | a guard on the battlements | four questing knights in a wet field — absurdism scores as craft |
| The Mead-Hall Flyting | a skald of the lower benches | a boastful rival — verse mode: alliteration and scansion are scored |
| Veiled Civility | a ballroom rival | the season's darling — overt rudeness is a foul, so the sting must arrive wrapped in a compliment |
| The Dockside Parley | a ship's quartermaster | a rival crew's captain — the crowd swings at double rate |

---

## Performance and the judge

The judge is a separate, temperature-zero call to your local model, with its
output constrained to a fixed schema — a referee rather than a performer, so one
line cannot both insult you and score itself. That costs model calls per turn:
two in Batting Practice (the judge, and the target's reaction) and three in a
Bout (the judge, the opponent's line, and the judge again on it). On modest
hardware a volley therefore takes noticeably longer than a conversation turn;
see [Performance & hardware](/play/performance/) for what to expect from your
machine, and consider the Set drill over the Timed one on slower setups.

A flyting run needs a model configured before it will start — without one
there is no judge, and the app says so rather than opening a run it cannot
score. If the judge then fails to answer, or answers with something unusable,
the volley is repaired once and otherwise scored from its deterministic
measurements alone, with every such scorecard reading **Scored from mechanics
only — the judge did not answer**. The engine never invents numbers no model
produced.

---

## Next steps

- [Authoring a flyting scenario](/create/scenario-authoring/#step-10b-authoring-a-flyting-scenario-optional)
  — the `mode: flyting` block, attack surfaces, and the workbench's Test Volley tab
- [The engine documentation](https://github.com/outrightmental/ConversationSimulator/blob/main/docs/flyting.md)
  — the full pipeline, the composition arithmetic, and the calibration suites
- [Safety & content policy](/trust/safety-policy/) — what the rating cap means in practice
