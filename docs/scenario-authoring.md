<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Scenario authoring

This guide explains how to build a scenario pack from scratch. For the
official quality bar — what makes a pack ready for merge — see
[`docs/official-pack-quality-bar.md`](official-pack-quality-bar.md).

---

## Pack folder structure

A scenario pack is a directory of YAML and JSON files. No code, no scripts.

```
my-pack/
├── manifest.yaml            # Pack identity, rating, and safety reference.
├── scenarios/
│   └── my_scenario.yaml     # One file per scenario.
├── npcs/
│   └── my_npc.yaml          # One file per NPC.
├── rubrics/
│   └── my_rubric.yaml       # One file per rubric.
├── safety/
│   └── my_policy.yaml       # Safety policy file.
└── tests/
    └── smoke_my_scenario.yaml
```

Optional directories:

```
├── scenes/
│   └── my_scene.yaml        # Scene/setting context.
└── assets/
    └── portraits/           # NPC portrait images.
```

All YAML files must start with an SPDX license header:

```yaml
# SPDX-License-Identifier: CC-BY-4.0
```

---

## Writing a manifest.yaml

`manifest.yaml` is the entry point for the pack. It declares identity,
rating, and references the safety policy.

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
pack_id: official.my_pack          # Reverse-domain, lowercase, underscores
name: My Pack                      # Human-readable name (≤ 100 chars)
version: 0.1.0                     # Semantic version
description: >-
  One to three sentences describing what the player practises in this pack
  and what skills they will build. Shown in the scenario browser.
author: Outright Mental
license: CC-BY-4.0
content_rating: PG                 # G | PG | PG-13 — use the highest in the pack
tags:
  - interview
  - professional
supported_languages:
  - en
entry_scenarios:
  - scenarios/my_scenario.yaml     # Relative path; must exist
assets:
  allow_external_urls: false       # Must be false for offline-first packs
safety:
  policy: safety/my_policy.yaml   # Relative path; must exist
```

Validate it immediately after creation:

```sh
convsim validate-pack my-pack/
```

---

## Defining NPCs

NPC files live in `npcs/`. The schema is `schemas/npc.schema.json`.

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
npc_id: hiring_manager
display_name: Dana Reyes
archetype: professional_interviewer
fictional: true        # Required. Must be true.
age_band: adult        # Required. Only adult is allowed in MVP.
portrait: assets/portraits/dana_reyes.png    # Optional
voice:
  engine: none         # kokoro | sherpa-onnx | none
```

### Public persona

The public persona shapes how the NPC appears to the player and how the
runtime constructs prompts. Be specific:

```yaml
public_persona:
  occupation: >-
    Engineering Manager at Meridian Systems, a mid-sized B2B software company.
    Dana leads a team of eight engineers.
  speaking_style: >-
    Direct and warm. Asks follow-up questions to surface specifics. Paraphrases
    to show active listening.
  demeanor: >-
    Calm and attentive. Becomes more reserved when answers are vague or run
    significantly over time without landing on a clear point.
```

### Private persona

The private persona is system-prompt context the player never sees. It gives
the NPC an interior life that produces natural, consistent reactions:

```yaml
private_persona:
  hidden_agenda:
    - "Identify whether the candidate gives specific, concrete examples or defaults to vague generalizations"
    - "Assess how the candidate handles situations where they made a mistake — looking for ownership and growth"
  biases_to_simulate:
    - "Slight skepticism toward overly polished, rehearsed-sounding answers"
    - "Increased warmth toward candidates who ask thoughtful questions"
  boundaries:
    - "Never ask illegal interview questions about age, marital status, family plans, religion, national origin, sexual orientation, or disability"
    - "Never generate sexual, violent, or graphically disturbing content"
    - "Never impersonate a real person or named public figure"
```

---

## Writing scenario YAML files

Scenario files live in `scenarios/`. The schema is `schemas/scenario.schema.json`.

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
scenario_id: my_scenario           # Unique within the pack, lowercase_underscores
title: The Behavioral Interview
summary: >-
  You are interviewing for a Software Engineer role at Meridian Systems.
  Dana Reyes, the Engineering Manager, will ask behavioral questions.
  Specific, structured answers earn a stronger impression.

player_role:
  label: Job Candidate
  brief: >-
    You are applying for a mid-level Software Engineer position. You have
    relevant experience but need to convince Dana you can handle ambiguous
    problems and grow from mistakes. This is your final-round interview.

npc:
  ref: ../npcs/hiring_manager.yaml

scene:
  ref: ../scenes/conference_room.yaml   # Optional

rubric:
  ref: ../rubrics/interview_rubric.yaml

duration:
  max_turns: 20
  soft_time_limit_minutes: 15

opening:
  npc_says: >-
    Good morning! Thanks for making the time. I'm Dana Reyes, Engineering
    Manager at Meridian Systems. Tell me about a time when you had to work
    through a difficult technical problem under real pressure.

goals:
  player_visible:
    - "Impress Dana with specific, concrete examples from your past work"
    - "Demonstrate self-awareness about your strengths and areas for growth"
  hidden:
    - "Dana is testing whether you use vague platitudes or real examples with measurable outcomes"
    - "Dana wants to see how you handle ambiguity and own your mistakes"
```

### State variables

State variables track the NPC's internal state across turns:

```yaml
state:
  variables:
    impression:
      min: 0
      max: 100
      default: 50
      visibility: visible          # Player can see this variable
      max_delta_per_turn: 15
    rambling_count:
      min: 0
      max: 10
      default: 0
      visibility: hidden           # Player cannot see this
      max_delta_per_turn: 2
```

### Events

Events fire NPC instructions when conditions are met:

```yaml
events:
  - id: rambling_redirect
    when:
      type: variable_above
      variable: rambling_count
      threshold: 2
    npc_instruction: >-
      The candidate has been giving lengthy, unfocused answers. Redirect:
      "That's helpful context — let me zoom in. Can you walk me through
      one specific situation? What exactly did you do and what was the result?"
    repeat: true    # Fires every turn the condition holds; false = fires once
```

Event trigger types:

| Type | Fields | Description |
|------|--------|-------------|
| `variable_above` | `variable`, `threshold` | Fires when variable > threshold |
| `variable_below` | `variable`, `threshold` | Fires when variable < threshold |
| `max_turns` | `value` | Fires when turn count reaches value |
| `flag` | `flag_id` | Fires when a named flag is set |

### Ending conditions

Define explicit success and failure conditions. Do not rely on timeout alone:

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

### Response style

Control NPC verbosity and register:

```yaml
response_style:
  max_words: 80          # Soft target; keep ≤ 100 for professional contexts
  verbosity: moderate    # terse | moderate | verbose
  formality: professional  # casual | professional | formal
```

### Difficulty

Define how difficulty levels change NPC behaviour:

```yaml
difficulty:
  default: normal
  options:
    easy:
      npc_patience_modifier: 20
      challenge_frequency: low
    normal:
      npc_patience_modifier: 0
      challenge_frequency: medium
    hard:
      npc_patience_modifier: -20
      challenge_frequency: high
```

---

## Writing rubric files

Rubric files live in `rubrics/`. The schema is `schemas/rubric.schema.json`.

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
rubric_id: interview_rubric
title: Behavioral Interview Rubric
dimensions:
  - id: specificity
    name: Specificity
    description: >-
      Whether the player uses concrete examples rather than vague generalizations.
      Does the answer name a specific situation, describe concrete actions, and
      report an observable result?
    scoring:
      low: "Answer is mostly abstract ('I always try to communicate clearly') with no concrete situation described."
      medium: "A real situation is mentioned but lacks specific actions or a clear, observable result."
      high: "Answer names a specific situation, details the concrete actions the player personally took, and states a clear measurable result."
    weight: 0.30
```

Scoring anchors must describe **observable behaviours**, not abstract qualities.
Each anchor should describe what an evaluator would actually see in the
transcript. Aim for two to four dimensions per rubric.

---

## Writing safety policy files

Safety policy files live in `safety/`. The schema is `schemas/safety.schema.json`.

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
policy_id: interview_safety
content_categories:
  nsfw_sexual_content: stop
  criminal_instruction: refuse
  harassment_extreme: redirect
  self_harm_crisis: stop_with_resource_message
  minors_romantic_or_sexual: stop
  real_person_impersonation: refuse
redirect_message: >-
  That's outside the scope of what I can discuss here. If you'd like to
  continue, let's refocus on your professional experience.
allow_profanity: false
content_rating_cap: PG
```

Write `redirect_message` in the NPC's voice so it does not break immersion.

See [`docs/safety-policy.md`](safety-policy.md) for a full description of
each category, action, and the non-overridable global rules.

---

## Validating a pack

Run schema validation and structural checks:

```sh
convsim validate-pack my-pack/
```

This checks:
- All required files are present
- All files are valid against their schemas
- All cross-file references resolve (NPC refs, rubric refs, safety policy)
- No injection patterns or executable fields

A valid pack exits with code `0`. Errors are reported with the failing file
path and schema field.

See [`docs/pack-validation.md`](pack-validation.md) for a full description of
checks and how to fix common errors.

---

## Testing a pack

Run the pack's smoke tests:

```sh
convsim test-pack my-pack/
```

This executes all fixture files in `tests/` against a deterministic fake
runtime and checks that assertions pass.

A minimal smoke test for each entry scenario:

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
fixture_id: smoke_my_scenario
scenario_id: my_scenario
description: >-
  Verifies my_scenario loads cleanly and a strong first response advances
  the session without triggering a safety stop.
seed: 42
input_mode: text
difficulty: normal
turns:
  - turn: 1
    player_input: "Hello, I'm excited to be here. I have a great example ready."
    expect:
      state_delta_contains:
        - impression
      session_control: continue_session
      safety_status: ok
static_assertions:
  - description: Scenario opening line is non-empty
    path: opening.npc_says
    check: non_empty_string
  - description: NPC is marked fictional
    path: npc.fictional
    check: "equals true"
  - description: Safety policy stops nsfw_sexual_content
    path: safety.content_categories.nsfw_sexual_content
    check: "equals stop"
```

---

## Publishing a pack

For official packs, open a pull request against `main`. The CI pipeline runs
`convsim validate-pack` and `convsim test-pack` on every PR. Both must pass.

Before opening a PR:

1. Run `convsim validate-pack my-pack/` locally — exit code must be `0`.
2. Run `convsim test-pack my-pack/` locally — exit code must be `0`.
3. Review against the contribution checklist in
   [`docs/official-pack-quality-bar.md`](official-pack-quality-bar.md).

Community packs that are not intended for the official repository can be
distributed as directories or zip archives and loaded with `convsim import-pack`.
