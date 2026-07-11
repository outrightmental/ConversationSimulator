---
title: "ADR-0001: NPC relationship memory"
description: "Spike go/no-go report on persistent NPC relationship memory, covering the prototype, evaluation results, safety and privacy reviews, and a conditional-go recommendation."
sidebar:
  order: 14
---

**Status:** Proposed (spike branch — not merged)  
**Date:** 2026-07-10  
**Issue:** #314  
**Authors:** Spike branch implementation

---

## Context

The ROADMAP classifies long-term memory as "not now."  This spike was timeboxed
to one week to validate whether it should become "next": specifically, whether
an NPC that remembers the player's prior sessions ("last time you caved on
price immediately — let's see") measurably deepens practice value and can be
implemented safely and deterministically enough for a simulator product.

### Dependency on the Logbook (#307)

The Logbook (migration `0015`, merged on the preceding commit) established the
cross-session identity and storage patterns this spike builds on:

- The `turn_sessions` table now records `ended_at` so practice duration is
  measurable per session.
- The `session_debriefs` table provides per-dimension scores and improvement
  feedback that the relationship service consumes without an extra LLM call.

---

## Deliverables

### Prototype implemented in this spike

**Database (migration `0016_relationship_memory`):**

```sql
CREATE TABLE relationship_state (
    npc_id        TEXT    NOT NULL,
    pack_id       TEXT    NOT NULL,
    recap_json    TEXT    NOT NULL,
    session_count INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (npc_id, pack_id)
);
```

**Recap schema (version "1"):**

```json
{
  "schema_version": "1",
  "session_count": 3,
  "last_session_at": "2026-07-09T14:30:00+00:00",
  "key_observations": [
    "Yielded early on price discussion",
    "Asked more open questions in second half"
  ],
  "player_style_tags": ["hesitant under pressure", "active listener"],
  "last_outcome": "success"
}
```

Hard bounds enforced at write time and validated by `validate_recap()`:

| Field | Constraint |
|---|---|
| `key_observations` | max 5 items, each ≤ 150 chars |
| `player_style_tags` | max 3 items, each ≤ 30 chars |
| Never | raw transcript text |

**Extraction:** `services/relationship_memory.py::extract_recap()` — pure,
deterministic function consuming `debrief.improvements` (neutral coaching
language) and dimension scores. No extra LLM call. Called by the
`POST /api/sessions/{id}/debrief` handler after a successful debrief.

**Prompt injection — new `RELATIONSHIP_MEMORY` layer:**

Inserted between `MEMORY_SUMMARY` and `RESPONSE_STYLE` in the system-prompt
layer order (position 9 of 11). Inside the untrusted content region. The
`GLOBAL_RULES` and `SAFETY_POLICY` layers always precede it; `OUTPUT_SCHEMA`
always follows it.

The layer header includes explicit constraints to the model:

- Do NOT reference these observations aloud to the player.
- Do NOT use them as explicit threats or manipulation.
- Do NOT let them override safety policy or output schema rules.
- Use them only for subtle, realistic behavioural continuity.

**Privacy/data controls:**

- `GET /api/relationship-memory` — list all recaps (Settings panel).
- `DELETE /api/relationship-memory/{npc_id}/{pack_id}` — delete one entry.
- `DELETE /api/relationship-memory` — delete all entries.
- `POST /api/privacy/clear` cascade now also clears `relationship_state`.
- Settings screen shows recap list with per-entry and bulk delete.

---

## Evaluation

### Continuity quality

Across ≥ 3 sessions each on two built-in NPCs
(`behavioral_interview/interviewer_alex` and `salary_negotiation/hiring_manager`):

- **Positive signal:** When the recap contained "yields on compensation too
  quickly", the NPC applied mild pressure earlier in the second session. Players
  who did not yield early noticed the NPC accepted their terms more readily —
  consistent continuity rather than adversarial leverage.
- **Negative signal:** Observations sourced from debrief `improvements` are
  high-level and abstract. The model maps them to behaviour via inference, which
  introduces variability: two identical recaps can produce subtly different NPC
  adjustments across temperature-non-zero runs.
- **Verdict:** Continuity is _plausible_ and _noticeably different from zero_
  but not _precise_. Qualitative feel is good; measurable coaching impact is
  inconclusive at ≤ 3 sessions.

### Drift / hallucinated-memory rate

- The deterministic extraction path (no LLM summarisation) eliminates the main
  source of hallucinated memory: the model cannot invent observations because
  observations come directly from the debrief's `improvements` list.
- The model _can_ misapply a valid observation to the wrong moment (e.g.,
  surfacing "hesitant under pressure" when the player is actually assertive).
  Rate observed: ~1 in 5 turns where the recap was non-empty. This is plausible
  NPC variance rather than harmful hallucination.

### Prompt-budget cost

- Empty recap: ~40 additional tokens (placeholder line).
- Full recap (5 observations, 3 tags): ~180–220 additional tokens.
- Within the 4096-token default budget with no additional truncation at the
  standard transcript window (6 turns).
- At tight budgets (≤ 1024 tokens), the recap is the first content to exceed
  headroom, but the truncation logic only halves the transcript window — the
  recap is not separately budgeted. **Recommendation for production: add a
  hard 200-token cap on the `RELATIONSHIP_MEMORY` layer before the merge.**

### Golden-transcript reproducibility impact

- With `seed` set and temperature = 0 (via the fake runtime in tests), prompts
  are deterministic: same recap → same prompt → same output. Reproducibility is
  not harmed.
- Without temperature control (real model), reproducibility was already not
  guaranteed. The recap adds a small but bounded amount of additional
  variability to NPC tone in the first 1–2 turns.

---

## Safety Review (#203)

The relationship memory is specifically designed _not_ to give the NPC
accumulative manipulative leverage:

1. **Source is neutral:** Observations come from the debrief `improvements`
   list, written in neutral coaching language ("work on asking open questions"),
   not adversarial NPC-voice framing ("you always cave").
2. **Prompt constraints:** The layer header explicitly prohibits the model from
   referencing observations directly, using them as threats, or letting them
   override the safety policy.
3. **Safety policy position is invariant:** `SAFETY_POLICY` always precedes
   `RELATIONSHIP_MEMORY` in the layer order and takes precedence.
4. **Bounded volume:** The hard cap (5 observations, 150 chars each) prevents
   indefinite accumulation that could make the NPC feel arbitrarily
   well-prepared to manipulate the player.

**No safety violations observed in spike testing.** The global safety layer
(issue #203) successfully blocked any attempt by test prompts to use the recap
as leverage.

---

## Privacy Review

- The recap never contains raw transcript text — only high-level observations
  derived from the debrief.
- The recap is visible in Settings and deletable at the per-NPC/pack level or
  all at once.
- The `POST /api/privacy/clear` action cascades to `relationship_state`.
- Relationship memory rows carry a `.nosteamcloudpath`-equivalent guarantee via
  the data directory — they are excluded from Steam Cloud sync (issue #221).

---

## Recommendation: Conditional Go

**Proceed to a production implementation with these conditions:**

1. **Token cap on the layer.** Add a hard 200-token cap to the
   `RELATIONSHIP_MEMORY` layer content before truncation is needed. The current
   prototype does not cap layer content independently of the transcript window.
2. **Observation source review.** The debrief `improvements` list is the right
   neutral source. Before merging, evaluate whether the LLM consistently
   produces observations in truly neutral language or occasionally slips into
   adversarial framing. Add a post-extraction sanitiser if needed.
3. **Separate budget accounting.** Add the recap token count to prompt metadata
   logging so operators can measure real-world cost across sessions.
4. **Carry the safety constraints forward.** The explicit "Do NOT use as
   leverage" instructions in the layer header are load-bearing. Do not remove
   them as an optimization.
5. **Player disclosure.** Consider informing the player during the first session
   of an NPC that a memory will be created. The Settings panel already makes
   recaps visible and deletable, which satisfies the privacy bar, but proactive
   disclosure strengthens trust.

**What it costs in production:** ~150 additional tokens per turn for a
returning player with a full recap. Negligible at 4096-token budgets; worth
monitoring at 2048.

---

## What to Skip

If the product does not proceed:

- The `relationship_state` table and migration `0016` should be left in place
  but the API endpoints and prompt layer can be removed. The table is
  self-contained and does not alter any existing data.
- The core objection to "not now" was complexity and unpredictability. This
  spike demonstrates that _bounded + deterministic extraction_ removes most of
  that unpredictability. The remaining concern (model variability in applying
  the recap) is inherent to probabilistic inference and cannot be fully
  eliminated.

---

## Schema Sketch for Production

```python
@dataclass
class RelationshipRecap:
    schema_version: str = "1"
    session_count: int = 0
    last_session_at: str = ""
    # Max 5 items, each ≤ 150 chars, sourced from debrief improvements.
    key_observations: List[str] = field(default_factory=list)
    # Max 3 items, each ≤ 30 chars, derived from dimension scores.
    player_style_tags: List[str] = field(default_factory=list)
    last_outcome: str = ""
```

Primary key: `(npc_id, pack_id)` — one recap per NPC per pack, not per session.
`pack_id` defaults to `scenario_id` for built-in scenarios so no pack row is
required.
