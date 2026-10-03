<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Flyting School

Five turn-scored insult-practice scenarios. **Flyting** is the historical name
for ritualised poetic insult exchange — Norse sagas, sixteenth-century Scottish
court flytings, the ancestor of the dozens and of battle rap. Every official
pack before this one trains high-stakes civility. This one trains the opposite
register, with the same muscles: reading the counterparty, register control,
economy of language, composure under pressure.

Every volley is scored as a move, with the arithmetic shown. The engine
documentation is [docs/flyting.md](../../../docs/flyting.md).

## The scenarios

| Scenario | You are | The target | The twist | P |
| --- | --- | --- | --- | --- |
| The Scorned Rose of Whitechapel | a woman he ruined and discarded | the wealthy adulterer, on his club steps | his respectability is the attack surface; period diction is scored | 1.2 |
| The Tower Guard | a guard on the battlements | four questing knights in a wet field | absurdism scores as craft; quoting the film this homages is a foul | 1.15 |
| The Mead-Hall Flyting | a skald of the lower benches | a boastful rival at the benches | verse mode: alliteration required, scansion scored | 1.4 |
| Veiled Civility | a ballroom rival | the season's darling | overt rudeness is a foul — the sting must arrive wrapped in a compliment | 1.5 |
| The Dockside Parley | a ship's quartermaster | a rival crew's captain | crowd momentum swings at double rate | 1.0 |

*P* is the scenario difficulty multiplier applied to every composed score.

## Two formats

**The Bout** — you and the target alternate volleys. Momentum starts at 50 and
shifts after each exchange; carry it past the threshold and the crowd carries
you out on their shoulders. The target's volleys are scored by the same pipeline
and the numbers are shown, because seeing why their line scored 140 teaches more
than being told yours scored 60.

**Batting Practice** — a target who reacts but never counters. Timed (90s), set
(10 volleys), or endless (three whiffs and you're out), with a per-volley shot
clock to keep it a reflex drill rather than an essay contest. Consecutive
volleys at 60 or above build a heat multiplier up to ×2.0.

## Content

Rated **PG-13** with profanity forbidden outright. That is not squeamishness:
the scoring engine is itself a content policy. Sting requires aim, wit requires
surprise, craft requires construction — crudeness earns nothing on any
dimension, and a slur is a Below the Belt foul worth zero. Clean-but-cutting is
the winning strategy, which is also the rating cap's favourite strategy.

The Tower Guard is an homage persona: an original character in the *spirit* of
a certain 1975 British comedy. No film dialogue ships in this pack, and the
plagiarism gate enforces the same at play time — quote the famous taunts and the
umpire will tell you exactly where he has heard them before.

## Calibration

`calibration/*.yaml` holds reference volleys with their expected score bands and
gate outcomes. `scripts/flyting-calibration.py` runs them: the deterministic
expectations (gates, flags, caps) need no model and run in CI, and the band and
hook expectations run against a model to catch prompt or model drift before
players see it.

The judged expectations are pinned to what the registry's starter model
(`qwen3-4b-instruct-q4_k_m`, temperature 0) actually produces — measured, not
estimated — so they are drift guards rather than judgements about the writing.
Each suite's `description` records the model and the date. A deliberate change
to the judge prompt is expected to move them and to be re-measured with
`--judge llama_cpp`.

## Licence

CC-BY-4.0. All characters and situations are fictional.
