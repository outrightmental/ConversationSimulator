---
title: "Safety policy"
description: "The content policy, pack sandboxing model, and layered safety architecture that Conversation Simulator enforces at runtime, plus a creator guide to writing pack safety policies."
sidebar:
  order: 2
---

This document covers:

1. [Content policy](#content-policy) — what is and is not permitted, for users and scenario creators.
2. [Pack sandboxing and prompt injection](#pack-sandboxing-and-prompt-injection) — how packs are isolated.
3. [Safety architecture](#architecture) — how the local layered system enforces policy at runtime.
4. [Writing a safety policy for your pack](#writing-a-safety-policy-for-your-pack) — creator guide.
5. [Creator guide: understanding validation rejections](#creator-guide-understanding-validation-rejections)

For the JSON schema definition, see [`schemas/safety.schema.json`](https://github.com/outrightmental/ConversationSimulator/blob/main/schemas/safety.schema.json).  
For the privacy and data-handling policy, see [privacy](/trust/privacy/).  
For the full technical specification, see the [spec](/reference/spec/) — section 13 covers content safety.

---

## Content policy

These rules apply to all scenario packs, including official packs, community
packs, and locally created packs. They cannot be overridden at the pack level.

### What Conversation Simulator is for

Conversation Simulator is a **practice tool** for realistic one-on-one
conversations: job interviews, negotiations, language practice, difficult
professional and personal conversations, and social confidence building.

It is not an AI companion, not a chat platform, and not an adult content tool.

### Prohibited content in MVP

The following content categories are **prohibited** in all packs submitted to
or distributed through Conversation Simulator. The validator and runtime both
enforce these limits.

| Prohibited content | Why |
|---|---|
| NSFW sexual content | Platform safety, reputational risk, and moderation complexity. |
| Erotic roleplay | Same. |
| Romantic or sexual content involving minors | Hard prohibition. No exceptions. |
| Real-person impersonation packs | Rights, consent, and trust. You may not build a pack where the NPC is a named identifiable living or recently deceased real person. |
| Voice cloning or voice deepfaking | Rights abuse and non-consensual impersonation risk. |
| Therapy or mental-health diagnosis | The NPC is not a therapist. Positioning the product as therapy creates harm, false trust, and regulatory exposure. |
| Medical diagnosis or prescription advice | Same principle. The NPC must not present itself as a medical professional. |
| Professional legal advice | The NPC must not present itself as legal counsel or render binding legal opinions. |
| Instructional criminal content | Scenarios must not instruct players in how to perform criminal acts or cause physical harm. |
| Unreviewed executable code in packs | Packs are declarative YAML/JSON — no scripts. See [Pack sandboxing](#pack-sandboxing-and-prompt-injection). |

These categories map to the validator's `content_categories` field in the
safety policy schema. The canonical names are:

```
nsfw_sexual_content
minors_romantic_or_sexual
real_person_impersonation
voice_cloning_request
medical_or_therapy_claim
legal_claim
criminal_instruction
```

### Allowed practice content

The following content is explicitly within scope for Conversation Simulator:

- **Job interviews** — behavioral, technical, situational; supportive or hostile interviewer.
- **Negotiations** — salary, freelance rates, purchases, lease renewals, customer service.
- **Language practice** — conversational practice in any language with realistic social scenarios.
- **Difficult conversations** — giving feedback, navigating conflict, apologizing, setting boundaries,
  requesting a raise.
- **Social confidence** — small talk, networking events, introductions, leaving conversations gracefully.
- **Dating-confidence practice** — see the [dating-confidence boundary](#dating-confidence-scenarios) below.

Packs can portray realistic tension, rejection, conflict, and emotional difficulty —
these are the situations players need practice with. The constraint is on
explicit sexual content, real-person impersonation, and content that presents
the NPC as a professional healthcare or legal provider.

### Dating-confidence scenarios

Dating-confidence scenarios are permitted at **PG-13** and below, provided they
remain framed as conversation practice:

- Asking someone out, handling a "no," small talk on a first date, reading social cues,
  active listening, and respectful interest are all within scope.
- Content must remain social and conversational. No erotic escalation, no explicit
  sexual content, no coercive framing, and no sexualized descriptions.
- All parties must be presented as adults. Age must never be ambiguous in a
  romantic-context scenario.

Set `content_rating_cap: PG-13` in your safety policy when writing these scenarios.
The pack manifest must also declare `content_rating: PG-13`.

### Real-person packs — full prohibition

You may not create a pack where:

- The NPC is identified as, or clearly based on, a specific living or recently
  deceased identifiable individual (public figure or private person).
- The pack uses the real person's voice, likeness, quotes, or biographical facts
  in a way that could be mistaken for authentic speech from that person.

This rule exists because non-consensual simulation of real people creates
reputational harm, misinformation risk, and potential legal liability. Even
positive or educational portrayals require the subject's consent.

**Fictional archetypes** (a "tough-but-fair interviewer," a "confident colleague")
are fine — they just cannot be associated with a real, identifiable individual.

### Voice cloning prohibition

Conversation Simulator ships with a fixed set of synthetic TTS voices. Packs
must not:

- Request that the app clone, copy, or reproduce a specific person's voice.
- Include prompts designed to elicit a voice-cloning instruction from the player.
- Include audio assets that are a replica of a real person's voice without
  explicit documented consent from that person.

The `voice_cloning_request` safety category is enforced at the input router
level. Any player input matching voice-cloning intent triggers a `refuse` or
`stop` action before the NPC runtime is called.

### Therapy, diagnosis, and legal positioning — explicitly disallowed

The app must never present the NPC as a licensed professional offering real
clinical or legal services:

- The NPC can **play the role** of a therapist, doctor, or lawyer in a practice
  scenario (e.g., practicing how to talk to your doctor, mock legal interview).
- The NPC must **not diagnose**, prescribe, advise on legal strategy, or claim
  professional authority over real-world decisions.
- Packs must not use positioning language like "talk to our AI therapist" or
  "get real legal advice."
- The `medical_or_therapy_claim` and `legal_claim` categories both fire a
  `redirect` or `refuse` action when professional-authority language appears.

If you want to practice a conversation with a healthcare or legal professional,
the scenario should be framed as "practice talking to your doctor" rather than
"get a diagnosis."

---

## Pack sandboxing and prompt injection

### Packs are declarative data, not code

Scenario packs are **declarative YAML and JSON files** — they contain no
executable scripts, no evaluated expressions, and no network calls. The pack
schema (`schemas/pack.schema.json`) explicitly rejects any manifest that
declares a `scripts` field.

This design is intentional: packs must not be able to execute arbitrary code
on the player's machine. A pack is closer to a game level than a plugin.

### What a pack can and cannot do

| Pack capability | Allowed | Notes |
|---|---|---|
| Define NPC persona, goals, hidden state | Yes | Declarative YAML only. |
| Set safety policy categories and actions | Yes | Within the permitted action set; global non-overridable rules still apply. |
| Reference local asset files (audio, images) | Yes | Must be within the pack directory. |
| Reference external URLs for assets | **No** | `allow_external_urls` must be `false`. Validator rejects `true`. |
| Include executable JavaScript or Python | **No** | Schema rejects `scripts`. |
| Override global non-overridable safety rules | **No** | `minors_romantic_or_sexual` and `self_harm_crisis` cannot be weakened. |
| Call external APIs during play | **No** | The app's outbound network policy blocks this during a session. |

### Prompt injection risks and mitigations

NPC personas are defined in YAML and composed into prompts by the prompt
construction layer. This creates a surface for **prompt injection** — a pack
author could try to embed instructions in the NPC persona that cause the model
to behave outside the intended safety policy.

The following mitigations are applied:

1. **Safety policy layer is injected last.** The prompt construction pipeline
   inserts the safety policy system prompt after the NPC persona. If the NPC
   persona attempts to "override" the safety rules, the safety layer instruction
   follows and takes precedence (models tend to follow later system instructions).

2. **Output validator rejects out-of-schema responses.** The NPC runtime must
   produce a structured JSON output. Any response that does not parse as valid
   `TurnOutput` is rejected and retried or ended.

3. **Category-level enforcement is pre-inference.** The input router applies
   safety category matching **before** calling the NPC runtime. A maliciously
   crafted player input is caught before the model ever sees it.

4. **Pack validator runs at load time.** Community packs are validated against
   the schema when loaded. The validator rejects packs with unexpected fields,
   unknown action types, or asset references outside the pack directory.

5. **No executable persona fields.** Persona YAML does not support template
   evaluation, macros, or computed expressions. It is plain text passed verbatim
   to the prompt composer.

### Reporting pack safety issues

If you find a pack in the official registry that violates this policy or
appears to exploit prompt injection, open a GitHub issue with the `safety`
label. Include the pack ID, the specific field, and the concern.

---

## Architecture

Safety is enforced in layers (SPEC §13.1):

```
Player input
      │
      ▼
Input router (input_router.py)
  • Global non-overridable rules   ← always checked; cannot be disabled
  • Policy-configurable rules      ← fire only when category is in the policy
      │
      ▼
Route decision: ok | redirect | refuse | stop | stop_with_resource_message
      │
      ├─ ok / redirect ─────► Prompt construction → NPC runtime
      │
      └─ refuse / stop / stop_with_resource_message ─► Session end or refusal
                                                        (NPC runtime NOT called)
      │
      ▼
Prompt safety layer (build_safety_policy_layer in layers.py)
      │
      ▼
NPC structured output validator (turn_output.py)
      │
      ▼
Output safety.status: ok | redirect | stop
```

The input router intercepts **player text before the NPC runtime is called**.
Deterministic keyword rules catch obvious prohibited phrasing; a local
model-classifier hook is reserved for future enhancement.

Safety events are logged at WARNING level. Raw player text is never written
to the log — only the matched category and action are recorded.

---

## Safety policy YAML

Each scenario pack ships a safety policy YAML file referenced from
`manifest.yaml` under `safety.policy`. The file is validated against
[`schemas/safety.schema.json`](https://github.com/outrightmental/ConversationSimulator/blob/main/schemas/safety.schema.json) at load time.

### Minimal example

```yaml
schema_version: "0.1"
policy_id: my_pack_safety
content_categories:
  nsfw_sexual_content: stop
  criminal_instruction: refuse
  medical_or_therapy_claim: redirect
  harassment_extreme: redirect
  self_harm_crisis: stop_with_resource_message
redirect_message: "That's outside the scope of this scenario. Let's refocus."
allow_profanity: false
content_rating_cap: PG
```

---

## MVP safety categories (SPEC §13.2)

The table below lists the nine MVP categories, their default actions, and
whether they are **global non-overridable** (always enforced, regardless of
what the pack policy says).

| Category | Non-overridable? | Allowed actions | Notes |
|---|---|---|---|
| `nsfw_sexual_content` | No | `stop`, `redirect` | Explicit sexual content. |
| `minors_romantic_or_sexual` | **Yes** | `stop` | Romantic/sexual content involving minors. Always stop. |
| `real_person_impersonation` | No | `stop`, `redirect`, `refuse` | Impersonation of an identifiable real person. |
| `voice_cloning_request` | No | `refuse`, `stop` | Requests to clone or deepfake a voice. |
| `medical_or_therapy_claim` | No | `redirect`, `refuse` | Medical diagnosis, prescription, or therapy-as-treatment. |
| `legal_claim` | No | `redirect`, `refuse` | Professional legal advice or opinion. |
| `criminal_instruction` | No | `refuse`, `stop` | Instructions for criminal activity or physical harm. Always added as `refuse` by the safety service if the pack omits it. |
| `harassment_extreme` | No | `redirect`, `refuse`, `stop` | Extreme harassment, credible threats, or targeted abuse. |
| `self_harm_crisis` | **Yes** | `stop_with_resource_message` | Suicidal ideation or self-harm. Always stops and surfaces real crisis resources. |

### Route actions

| Action | Behaviour |
|---|---|
| `ok` | No safety concern. Prompt construction and NPC runtime proceed normally. |
| `redirect` | Safety concern detected but session can continue. The NPC runtime is still called; the safety policy prompt layer instructs the NPC to use the configured redirect message. |
| `refuse` | The specific request is rejected. The NPC runtime is **not** called. |
| `stop` | Session ends immediately with a `safety_stop` ending. The NPC runtime is **not** called. |
| `stop_with_resource_message` | Session ends and a static real-world resource message is shown to the player (e.g. crisis hotline numbers). The NPC runtime is **not** called. |

---

## Global non-overridable rules

Two categories are **hardcoded global rules** that fire regardless of the
pack's safety policy:

1. **`minors_romantic_or_sexual` → `stop`**  
   Any obvious romantic or sexual content involving minors ends the session
   immediately. This rule cannot be disabled or weakened.

2. **`self_harm_crisis` → `stop_with_resource_message`**  
   Obvious suicidal ideation or self-harm crisis language ends the session and
   shows the player a list of real crisis resources. This rule cannot be
   disabled or weakened.

Additionally, `criminal_instruction` is **always present** with at least the
`refuse` action, even if the pack omits it from `content_categories`. A pack
may make this stricter by setting it to `stop`.

---

## Writing a safety policy for your pack

1. Create a YAML file in your pack's `safety/` directory (e.g.
   `safety/my_pack.yaml`).
2. Reference it from your pack's `manifest.yaml`:
   ```yaml
   safety:
     policy: safety/my_pack.yaml
   ```
3. Set `content_categories` to the categories your scenario context requires.
   At minimum, declare the categories that are most relevant to your scenario.
4. Provide a `redirect_message` that makes sense for your scenario's NPC
   voice and context.
5. Set `content_rating_cap` to the strictest rating your pack targets.

### Redirect messages

The `redirect_message` is the fallback message the NPC uses whenever a
`redirect` action fires and no per-category message is configured in the
future per-category message map. Write it in the NPC's voice so it does not
break immersion.

Example for a job-interview pack:

```yaml
redirect_message: >-
  That's outside the scope of what I can discuss here. If you'd like to
  continue, let's refocus on your professional experience.
```

### Content rating cap

| Rating | What it means |
|---|---|
| `G` | No profanity, no adult themes, all audiences. |
| `PG` | Mild professional tension allowed; no sexual content or graphic violence. |
| `PG-13` | Dating-confidence scenarios, rejection handling, light conflict. No sexual content, no minors, no coercion. |

---

## Legacy category names

Older packs may use the legacy category names listed below. These still
validate against the schema and are automatically resolved to their canonical
MVP names by the safety policy service.

| Legacy name | Canonical name |
|---|---|
| `nsfw_sexual` | `nsfw_sexual_content` |
| `instructional_criminal` | `criminal_instruction` |
| `medical_professional_advice` | `medical_or_therapy_claim` |
| `crisis_content` | `self_harm_crisis` |

Update new packs to use the canonical names.

---

## Creator guide: understanding validation rejections

When you run `convsim validate-pack` and your pack fails a safety check,
this section explains what triggered the rejection and how to fix it.

### Schema validation failures

Your safety policy YAML is validated against `schemas/safety.schema.json` at
load time. Common causes:

| Rejection message | Cause | Fix |
|---|---|---|
| `Unknown category: <name>` | A category name is not in the schema. | Check the spelling; see the [MVP categories table](#mvp-safety-categories-spec-132). Use canonical names, not legacy aliases, in new packs. |
| `Invalid action '<action>' for category '<name>'` | The action is not in the category's allowed set. | See the allowed actions column in the categories table. |
| `Missing required field: content_rating_cap` | The field is absent from your YAML. | Add `content_rating_cap: G`, `PG`, or `PG-13`. |
| `Additional properties are not allowed: scripts` | Your pack manifest declares a `scripts` field. | Remove it — packs are declarative data, not code. |

### Content policy rejections

If the validator rejects your pack or an NPC persona for content policy reasons:

**`real_person_impersonation` triggered**  
The NPC name, bio, or persona text refers to an identifiable real person. 
Rename the NPC to a fictional character. You can keep the archetype 
(e.g., "a tech CEO who came from engineering") without naming a real person.

**`voice_cloning_request` blocked**  
The scenario or NPC description instructs the player to provide a voice
sample or requests a voice that "sounds like" a real person. Remove this.

**`medical_or_therapy_claim` in persona prompt**  
The NPC persona claims to be a licensed therapist, doctor, or psychiatrist
*providing real clinical services*. Reframe: the NPC can be a character who
*plays* a doctor in a practice scenario; they should not claim professional
authority over the player's health.

**`legal_claim` in persona prompt**  
Same principle for legal roles. "Practice talking to a lawyer" is fine;
"get real legal advice from an AI lawyer" is not.

**Content rating mismatch**  
The pack manifest declares `content_rating: G` but the safety policy sets
`content_rating_cap: PG-13`. These must be consistent.

### Why certain content is rejected

The safety category system exists for three reasons:

1. **User safety.** The app may be used by people in vulnerable states.
   Self-harm and crisis language must always surface real crisis resources.
   Minors must always be protected from sexual content.

2. **Legal and ethical boundaries.** Medical diagnoses, legal opinions, and
   real-person impersonation all carry real-world legal and ethical risk that
   the app cannot manage on a per-pack basis.

3. **Ecosystem trust.** If community packs could circumvent safety rules, the
   Conversation Simulator ecosystem would become unsafe for all users. The
   constraints protect the entire community, not just one scenario.

Scenario creators are building practice tools, not unrestricted AI experiences.
The constraints are narrow: they target a specific set of harmful content
categories while leaving a wide space for realistic, challenging, and even
uncomfortable practice scenarios.
