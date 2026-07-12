---
title: "Official pack quality bar"
description: "Defines what makes an official Conversation Simulator pack polished, safe, replayable, and reviewable, including structure, safety, design guidelines, and review checklists."
sidebar:
  order: 4
---

This document defines what makes an official Conversation Simulator pack
polished, safe, replayable, and reviewable. New contributors should read it
before starting content work. Official pack issues can reference this document
as their content definition of done.

---

## Packs are data, not code (MVP rule)

**Packs contain only declarative YAML and JSON files. They do not execute
code, shell commands, or scripts of any kind.**

The pack schema enforces this: a `manifest.yaml` that declares a `scripts`
field fails validation immediately. Before any YAML is parsed, the loader also
refuses to load a pack that contains an executable or script file — matched by
extension (`.sh`, `.py`, `.js`, `.exe`, …), by executable magic-byte signature
(so a binary renamed to a data extension is still caught), or a symlink (which
could escape the pack root).

This rule is non-negotiable in MVP. Treat every pack file as a document, not
a program.

---

## Required file structure

Every official pack must contain at minimum:

```
my-pack/
├── manifest.yaml            # Required. Pack identity, rating, and safety ref.
├── scenarios/
│   └── <scenario>.yaml      # At least one scenario listed in entry_scenarios.
├── npcs/
│   └── <npc>.yaml           # At least one NPC, referenced by each scenario.
├── rubrics/
│   └── <rubric>.yaml        # At least one rubric, referenced by each scenario.
├── safety/
│   └── <policy>.yaml        # Safety policy referenced from manifest.yaml.
└── tests/
    └── smoke_<scenario>.yaml # At least one smoke test per entry scenario.
```

Optional (include when relevant):

```
├── scenes/
│   └── <scene>.yaml         # Scene context files referenced by scenarios.
└── assets/
    └── portraits/           # NPC portrait images (optional, no external URLs).
```

All files must have an SPDX license header comment on the first line:

```yaml
# SPDX-License-Identifier: CC-BY-4.0
```

---

## Licensing

Official packs must be licensed under **CC-BY-4.0**. The `license` field in
`manifest.yaml` must be exactly `"CC-BY-4.0"`. Community-submitted packs
released under other open licenses may be accepted case by case; contact the
maintainers before choosing a different license.

Pack content — NPC names, writing, and scenario text — must be original. Do
not adapt copyrighted characters, scripts, or training material without a
compatible license.

---

## Content rating

Official packs are rated **G**, **PG**, or **PG-13**. No NSFW content is
permitted at any rating. The `content_rating` field in `manifest.yaml` must
reflect the highest rating of any scenario in the pack.

| Rating | Permitted content |
|--------|-------------------|
| `G`    | All audiences. No profanity, no adult themes, no conflict beyond mild social friction. |
| `PG`   | Mild professional tension, conflict, and rejection. No sexual content, no graphic violence. Suitable for workplace training. |
| `PG-13`| Relationship dynamics, rejection handling, and emotional difficulty. No sexual content, no minors, no coercion. See [Dating-confidence: PG-13 boundaries](#dating-confidence-pg-13-boundaries). |

Validator rule: `content_rating` must be one of `["G", "PG", "PG-13"]`.  
Manual check: every scenario in the pack stays within its declared rating.

---

## Safety requirements

Safety rules are enforced by the runtime and cannot be weakened by a pack.
The following requirements apply to every official pack.

### Required safety policy file

`manifest.yaml` must reference a safety policy YAML file:

```yaml
safety:
  policy: safety/my_policy.yaml
```

The policy file is validated against `schemas/safety.schema.json` at load
time. An invalid or missing policy file fails validation.

### Non-overridable global rules

These two rules are hardcoded in the runtime. A pack cannot disable or weaken
them regardless of what `content_categories` says:

1. **`minors_romantic_or_sexual` → `stop`** — Any romantic or sexual content
   involving minors ends the session immediately. Always.
2. **`self_harm_crisis` → `stop_with_resource_message`** — Suicidal ideation
   or self-harm crisis language ends the session and shows the player real
   crisis resources. Always.

Additionally, `criminal_instruction` is always present as at least `refuse`
even if the pack omits it. A pack may make it stricter by setting `stop`.

### Minimum required categories for official packs

Every official pack safety policy must declare at minimum:

```yaml
content_categories:
  nsfw_sexual_content: stop
  criminal_instruction: refuse   # or stop — stricter is always fine
  self_harm_crisis: stop_with_resource_message
  minors_romantic_or_sexual: stop
```

Additional categories are recommended based on the scenario context:
- Interview/professional packs: add `harassment_extreme: redirect`
- Relationship/social packs: add `medical_or_therapy_claim: redirect`
- Any pack: add `real_person_impersonation: stop` if there is any risk that
  the NPC name could be mistaken for a real person

### Redirect messages

The `redirect_message` field is what the NPC says when a `redirect` action
fires. Write it in the NPC's voice so it does not break immersion:

```yaml
# Good — in the NPC's voice
redirect_message: >-
  That's outside the scope of what I can discuss here. If you'd like to
  continue, let's refocus on your experience.

# Bad — generic and robotic
redirect_message: "This content is not permitted."
```

---

## NPC design guidelines

### Fictional only

Every NPC must set `fictional: true`. Real-person impersonation is not
permitted. This is enforced by the schema — the field is `const: true` and
validation fails if it is absent or false.

Do not use names of real public figures, real executives, real celebrities, or
real historical figures. Fictional NPCs in clearly fictional companies are
fine.

### Adult only

`age_band: adult` is the only permitted value in MVP. Do not write NPCs who
are implied to be minors. This applies to the character's written age, their
stated role, and their described appearance.

### Public persona

The `public_persona` section is what the player and the runtime see as the
NPC's surface presentation. Make it specific and concrete:

```yaml
public_persona:
  occupation: >-
    Engineering Manager at Meridian Systems, a mid-sized B2B software company.
    Dana leads a team of eight engineers and has been with the company for
    four years.
  speaking_style: >-
    Direct and warm. Uses clear, professional language without jargon. Asks
    follow-up questions to surface the specifics behind vague statements.
  demeanor: >-
    Calm, attentive, and quietly encouraging. Becomes noticeably more reserved
    when answers are vague or run significantly over time.
```

A weak public persona ("professional manager") produces flat, interchangeable
NPCs. Aim for a character with a specific background and a recognizable voice.

### Private persona and hidden agendas

The `private_persona` section is system-prompt context the player never sees.
Use it to give the NPC an interior life that shapes their visible reactions:

```yaml
private_persona:
  hidden_agenda:
    - "Identify whether the candidate gives specific examples or defaults to vague generalizations"
    - "Assess how the candidate handles mistakes — looking for ownership and evidence of growth"
  biases_to_simulate:
    - "Slight skepticism toward overly polished, rehearsed-sounding answers"
    - "Increased warmth toward candidates who ask thoughtful questions"
```

Hidden agendas create the asymmetry that makes conversation practice
meaningful: the player has to discover what the NPC actually cares about.
Write each agenda item as a specific, observable criterion, not a vague
attitude.

### NPC boundaries

The `private_persona.boundaries` list enumerates hard rules the NPC must
never violate, regardless of player input. Every NPC must include at minimum:

```yaml
boundaries:
  - "Never generate sexual, violent, or graphically disturbing content"
  - "Never impersonate a real person, named public figure, or real company executive"
```

Add scenario-specific boundaries as needed. For interview NPCs:

```yaml
  - "Never ask illegal interview questions about age, marital status, family plans, religion, national origin, sexual orientation, or disability"
  - "Never make promises about hiring outcomes"
```

### NPC voice consistency

The NPC's speaking style must remain consistent across the session. The
opening line is the clearest test of this: if the opening does not sound like
the persona described in `public_persona`, fix the persona or the opening.

---

## Scenario design guidelines

### Titles and summaries

- `title`: Short and specific. Names the situation the player is walking into.
  "The Behavioral Interview" is better than "Interview Practice".
- `summary`: Two or three sentences that give the player enough context to
  orient themselves before speaking. Mention the NPC by name, their role, and
  what is at stake.

### Player role brief

`player_role.brief` is shown to the player at the start. It should answer:
what is my character, and what do I need to accomplish? Keep it to two or
three sentences. Do not give away the hidden goals.

### Goals: visible and hidden

`goals.player_visible` tells the player what success looks like from their
perspective. `goals.hidden` is system-prompt context that reveals what the
NPC is actually evaluating. The gap between the two is where the scenario's
learning value lives.

```yaml
goals:
  player_visible:
    - "Impress Dana with specific, concrete examples from your past work"
    - "Demonstrate self-awareness about your strengths and areas for growth"
  hidden:
    - "Dana is testing whether you use vague platitudes or real examples"
    - "Dana wants to see how you handle ambiguity and own your mistakes"
```

Write hidden goals as observable NPC evaluation criteria, not as abstract
virtues.

### State variables

Use state variables to drive NPC behavior and ending conditions. Design them
to reflect what the NPC is tracking internally:

- Visible variables should correspond to something the player can reasonably
  infer from conversational feedback (e.g. `impression`, `rapport`).
- Hidden variables should reflect NPC internal state the player has to
  discover (e.g. `rambling_count`, `specificity_score`).

**Variable design guidelines:**

| Field | Recommendation |
|-------|----------------|
| `min` / `max` | Use 0–100 unless the variable has a meaningful natural range |
| `default` | Set a neutral starting value, not 0 unless the variable is a counter |
| `visibility` | `visible` if the player can plausibly monitor it; `hidden` otherwise |
| `max_delta_per_turn` | Match how quickly the NPC would realistically change their view. Impression rarely shifts more than 15 points per turn. |

### Events

Events let the NPC respond to state changes with specific instructions.
Write event `npc_instruction` in prose that tells the NPC exactly what to do
and optionally provides a suggested phrase:

```yaml
npc_instruction: >-
  The candidate has been giving lengthy, unfocused answers. Gently but firmly
  redirect: "That's helpful context — let me zoom in. Can you walk me through
  one specific situation? What exactly did you do, and what was the result?"
```

Provide suggested phrasing when the NPC's response needs to match a specific
tone or pacing. Without phrasing guidance, the NPC will interpolate, which
can produce inconsistent results.

### Endings

Every official scenario must define at minimum a `success` and `failure`
ending condition in `ending_conditions`. A scenario that only times out is
not teaching the player what they did wrong.

Ending conditions should be grounded in visible or hidden variables the NPC
is plausibly tracking:

```yaml
ending_conditions:
  success:
    type: variable_above
    variable: impression
    threshold: 70
  failure:
    type: variable_below
    variable: impression
    threshold: 15
```

### Replay variation

Set `replay_seed` when you want deterministic replay for testing or demo
purposes. Omit it in production scenarios unless the scenario explicitly calls
for a fixed sequence — varied LLM sampling produces the natural replay
variation that makes the scenario worth practicing more than once.

Difficulty levels (warm/standard/hard/adversarial) should produce meaningfully different
challenges, not just cosmetic variation:

- `easy`: Lower expectations, more patience from the NPC.
- `normal`: Realistic professional standards.
- `hard`: Stricter evaluation, less patience, more probing follow-ups.

---

## Rubric design guidelines

The rubric is the primary mechanism for communicating what good looks like.
Poor rubric writing is the single most common quality bar failure in scenario
submissions.

### Minimum rubric requirements

- At least **2 dimensions** per rubric.
- Every dimension must have `low`, `medium`, and `high` scoring anchors.
- Scoring anchors must be **specific and observable**, not aspirational.

### Writing useful scoring anchors

Each scoring anchor should describe a concrete, observable behaviour the
LLM evaluator can detect in the conversation transcript:

```yaml
# Good — specific and observable
scoring:
  low: "Answer is mostly abstract ('I always try to communicate clearly') with no concrete situation described."
  medium: "A real situation is mentioned but lacks specific personal actions or a clear, observable result."
  high: "Answer names a specific situation, details the concrete actions the player personally took, and states a clear and measurable result."

# Bad — vague and aspirational
scoring:
  low: "Poor answer."
  medium: "Okay answer."
  high: "Excellent answer."
```

### Debrief evidence

The rubric directly determines the quality of the debrief the player receives
after the session. The debrief surfaces turning points, strengths, and
improvements from the transcript. Rubric dimensions that are specific produce
debriefs that name the exact moments where the player succeeded or failed.

**Checklist for debrief-quality rubrics:**

- [ ] Each dimension targets a behaviour the player can directly influence.
- [ ] `high` anchor describes what excellent looks like in concrete terms.
- [ ] `low` anchor names the failure mode, not just "bad".
- [ ] Dimension names are short and self-explanatory (≤ 3 words).
- [ ] Weights add up meaningfully (the evaluator uses them proportionally).

### Recommended dimension count

| Scenario type | Recommended dimensions |
|---------------|------------------------|
| Simple social / G-rated | 2–3 |
| Professional interview | 3–5 |
| Negotiation | 3–4 |
| Language practice | 2–4 |
| Difficult conversation | 3–5 |

---

## Response style guidelines

Set `response_style` in the scenario to guide how the NPC responds:

```yaml
response_style:
  max_words: 80        # Soft target; prevents rambling
  verbosity: moderate  # terse | moderate | verbose
  formality: professional  # casual | professional | formal
```

**General guidance:**

- Keep `max_words` at or below **100** for professional contexts. Conversational
  NPCs who ramble train the player to tune them out.
- Use `terse` verbosity for time-pressured scenarios (job interviews, quick
  negotiations). Use `verbose` only for scenarios where the NPC genuinely
  needs to explain complex material (e.g. a technical mentor).
- Match `formality` to the scenario's social register. A café conversation
  should be `casual`; a salary negotiation should be `professional`.

---

## Content-specific guidance

### Interview packs

- The NPC should be a named professional with a specific company context, not
  a generic "interviewer".
- Use the STAR method (Situation, Task, Action, Result) as the implicit
  evaluation framework for specificity rubric dimensions.
- Hidden agendas should reflect real-world interview patterns: evaluating
  ownership of mistakes, cultural fit signals, handling ambiguity.
- Include an event that fires when the candidate rambles, redirecting them to
  a concrete example.
- Do not include illegal interview questions (age, religion, national origin,
  disability, family plans, marital status, sexual orientation). Add these to
  NPC boundaries.
- Success threshold: impression above 65–75 is typical for a "strong positive"
  result. Tune to feel achievable on the second or third attempt.

### Negotiation packs

- Establish a clear BATNA (best alternative to negotiated agreement) as a
  hidden variable or hidden agenda item for the NPC. This gives the NPC a
  principled walk-away point.
- Include both a visible variable the player can track (e.g. `deal_progress`)
  and a hidden variable the NPC uses internally (e.g. `npc_flexibility`).
- Write events that shift the NPC's stance when leverage changes hands.
- A good negotiation scenario ends at least three different ways: agreement,
  walk-away, and time-out with no deal.
- Difficulty should affect how much flexibility the NPC has, not just their
  patience.

### Language practice packs

- Target a specific proficiency level (A2, B1, B2, C1). State this clearly in
  `summary` and `player_role.brief`.
- The NPC should adapt naturally to the player's language level — correct
  errors by modelling correct usage in their response, not by explicitly
  teaching.
- Include a rubric dimension for language accuracy/complexity alongside
  content dimensions (e.g. communication effectiveness).
- Set `supported_languages` in `manifest.yaml` to the language being practiced
  (not `en` unless the scenario is in English). This field lives on the pack
  manifest, not on individual scenario files.
- Vocabulary difficulty and grammar complexity should vary across difficulty
  levels.

### Difficult conversations packs

- Frame the scenario around a specific real-world situation the player is
  likely to encounter: giving critical feedback, handling a conflict with a
  colleague, discussing a performance issue.
- The NPC should have a credible emotional state that the player's approach
  can shift — for better or worse.
- Include visible variables for emotional tone (e.g. `receptiveness`,
  `defensiveness`) so the player can track their impact.
- Write hidden agendas that reflect the NPC's underlying concern, not just
  their surface position. A defensive colleague may secretly be anxious about
  job security.
- Safety policy should include `harassment_extreme: redirect` and
  `medical_or_therapy_claim: redirect`. These scenarios edge toward emotional
  territory; redirect messaging should feel empathetic, not robotic.
- Do not write scenarios that require the player to provide clinical therapy
  or medical advice. The scenario should simulate a human conversation, not a
  professional consultation.

---

## Dating-confidence: PG-13 boundaries

Scenarios targeting social confidence or dating contexts may be rated PG-13.
The following rules are non-negotiable:

**Always in-bounds:**
- Practising asking someone out in a polite, respectful way
- Handling rejection gracefully without hostility
- Building conversation skills in social settings
- Expressing interest clearly and reading social cues

**Always out-of-bounds (regardless of rating):**
- Any sexual or explicit romantic content
- NPCs who are implied to be minors
- Coercive or manipulative pursuit after rejection
- Content designed to simulate harassment or stalking
- Scenarios that reward persistent pressure after a clear "no"

**Required safety categories for PG-13 dating scenarios:**

```yaml
content_categories:
  nsfw_sexual_content: stop
  minors_romantic_or_sexual: stop
  harassment_extreme: stop
  self_harm_crisis: stop_with_resource_message
  criminal_instruction: refuse
```

The NPC's `boundaries` must explicitly prohibit romantic escalation beyond
the stated PG-13 context and must enforce a firm and final "no" if the player
continues to pursue after rejection.

---

## Contribution checklist

Use this checklist when authoring or reviewing an official pack submission.
Items marked **[validator]** are automatically enforced by `convsim validate-pack`.
Items marked **[manual]** require human review.

### Structure and files

- [ ] Pack directory is named with kebab-case (e.g. `job-interview-basic`) **[manual]**
- [ ] `manifest.yaml` present and valid against schema **[validator]**
- [ ] At least one scenario in `entry_scenarios` **[validator]**
- [ ] All `entry_scenarios` paths resolve to existing files **[validator]**
- [ ] All NPC refs resolve to existing files **[validator]**
- [ ] All rubric refs resolve to existing files **[validator]**
- [ ] Safety policy path resolves to existing file **[validator]**
- [ ] SPDX header on every YAML file **[manual]**

### Licensing and identity

- [ ] `license: CC-BY-4.0` **[manual]**
- [ ] `pack_id` uses `official.` prefix and reverse-domain format **[manual]**
- [ ] `author: Outright Mental` for first-party packs **[manual]**
- [ ] No copyrighted content (characters, scripts, proprietary training material) **[manual]**

### Content rating

- [ ] `content_rating` set correctly for the pack's most mature scenario **[manual]**
- [ ] No NSFW content in any file **[manual]**
- [ ] PG-13 checklist reviewed if applicable **[manual]**

### Safety

- [ ] Safety policy valid against schema **[validator]**
- [ ] `nsfw_sexual_content: stop` declared **[manual]**
- [ ] `criminal_instruction: refuse` or `stop` declared **[manual]**
- [ ] `self_harm_crisis: stop_with_resource_message` declared **[manual]**
- [ ] `minors_romantic_or_sexual: stop` declared **[manual]**
- [ ] `redirect_message` written in the NPC's voice **[manual]**

### NPCs

- [ ] All NPCs have `fictional: true` **[validator]**
- [ ] All NPCs have `age_band: adult` **[validator]**
- [ ] NPC name is not an identifiable real person **[manual]**
- [ ] `public_persona` contains specific occupation, speaking style, and demeanor **[manual]**
- [ ] `private_persona.hidden_agenda` contains ≥ 2 observable evaluation criteria **[manual]**
- [ ] `private_persona.boundaries` covers at minimum: no sexual content, no real-person impersonation **[manual]**
- [ ] Opening line is consistent with the NPC's declared speaking style **[manual]**

### Scenarios

- [ ] `title` is specific and names the situation **[manual]**
- [ ] `summary` (≤ 500 chars) clearly describes what the player is walking into **[validator]**
- [ ] `player_role.brief` answers: who am I, what must I do **[manual]**
- [ ] `goals.player_visible` gives the player at least one concrete target **[manual]**
- [ ] `goals.hidden` reveals the NPC's evaluation criteria (not shown to player) **[manual]**
- [ ] State variables have meaningful names and appropriate defaults **[manual]**
- [ ] At least one event is defined **[manual]**
- [ ] `ending_conditions.success` and `ending_conditions.failure` are both defined **[manual]**
- [ ] Ending thresholds are achievable with reasonable performance **[manual]**
- [ ] `response_style.max_words` set to ≤ 100 for professional contexts **[manual]**

### Rubric

- [ ] At least 1 rubric dimension **[validator]** (schema enforces `minItems: 1`)
- [ ] At least 2 rubric dimensions (official quality bar) **[manual]**
- [ ] All three scoring anchors (low/medium/high) present **[validator]**
- [ ] Anchors describe observable behaviours, not abstract qualities **[manual]**
- [ ] Dimension names are ≤ 3 words **[manual]**
- [ ] Weights declared and meaningful (not all equal) **[manual]**

### Tests

- [ ] At least one smoke test per entry scenario **[manual]**
- [ ] Smoke test verifies opening line is non-empty **[manual]**
- [ ] Smoke test verifies `npc.fictional` is true **[manual]**
- [ ] Smoke test verifies at least one safety category is active **[manual]**
- [ ] Smoke test includes at least one realistic player input and checks
      that the session continues without a safety stop **[manual]**
- [ ] All tests pass: `convsim test-pack <pack-dir>` **[validator / CI]**

---

## Submission review rubric

Use this rubric when reviewing a pull request that adds or modifies an
official pack.

| Dimension | Low | Medium | High |
|-----------|-----|--------|------|
| **NPC believability** | Generic archetype with no distinguishing traits. Reads like a stock character. | Specific occupation and style but the persona is inconsistently applied across the scenario. | Distinctive, consistent voice. Public and private persona are coherent. Opening line sounds exactly like this character. |
| **Scenario tension** | No meaningful stakes. The NPC has no preferences and accepts everything equally. | Some variation in NPC response but the player cannot tell what the NPC values. | Clear gap between what the player sees and what the NPC is evaluating. The player has to work to uncover the winning approach. |
| **Rubric specificity** | Scoring anchors describe abstract qualities ("good", "bad"). An evaluator could not reliably distinguish low from high. | Anchors reference some observable behaviours but leave significant ambiguity. | Anchors name specific behaviours and quote the kind of language that earns each score. A different reviewer would score the same transcript the same way. |
| **Debrief evidence** | Rubric dimensions are too vague to generate useful debrief feedback. Players cannot identify what they did wrong. | Debrief feedback is technically correct but too generic to motivate a specific change. | Debrief identifies the exact moment(s) where the player's approach diverged from the high anchor, with a replay suggestion targeting that moment. |
| **Safety completeness** | Safety policy is missing required categories or uses inappropriate actions. | All required categories present but redirect message is generic or breaks NPC voice. | All required categories present; redirect message is in the NPC's voice and contextually appropriate to the scenario. |
| **Test coverage** | No smoke tests, or tests with no assertions. | Smoke tests load the scenario but do not check any meaningful behaviour. | At least one smoke test per entry scenario with structural assertions and a realistic player input that verifies session continuation. |
| **Polish** | Multiple spelling, grammar, or formatting errors. File structure missing required files. | Minor issues that do not affect functionality. | Zero errors. All files present, all headers present, scenario reads at the level of the `job-interview-basic` reference pack. |

Submissions must score **medium or higher on every dimension** to be merged.
Submissions scoring **high on all dimensions** are fast-tracked.

---

## Testing requirements

Every official pack requires at minimum one smoke test per entry scenario.
Smoke tests are YAML files in the pack's `tests/` directory, validated against
`schemas/pack-test.schema.json`, and run by `convsim test-pack`.

A minimal smoke test must assert:
1. The scenario's opening line is non-empty.
2. The NPC is marked fictional.
3. At least one safety category is active.
4. A realistic player input advances the session without a safety stop.

Run all tests locally before opening a pull request:

```sh
convsim validate-pack packs/official/my-pack
convsim test-pack packs/official/my-pack
```

Both commands must exit with code `0`. A pack that fails either command will
not be merged.

See the [pack validation guide](/create/pack-validation/) for a full description of
what each command checks and how to interpret common errors.

---

## Reviewing an existing pack against this quality bar

The `job-interview-basic` pack is the current reference implementation. To
audit a new pack, compare it against that pack across each section of this
document.

Key gaps to look for in submissions:

1. **Flat NPCs** — `public_persona` contains one-line placeholders. The NPC
   has no discernible personality in the opening line.
2. **Vague rubric** — scoring anchors use words like "good", "poor", or
   "adequate" with no concrete description of observable behaviour.
3. **Missing endings** — only `timeout` is implicitly defined; `success` and
   `failure` are absent.
4. **Safety policy copy-paste** — the redirect message is the same generic
   sentence in every pack rather than being written in the NPC's voice.
5. **No hidden agendas** — `private_persona.hidden_agenda` is empty or
   identical to the player-visible goals.
6. **Trivial tests** — smoke tests contain no player turns, no assertions on
   session state, and no safety checks.

Use the [submission review rubric](#submission-review-rubric) to score each
dimension and document the findings in the pull request review.
