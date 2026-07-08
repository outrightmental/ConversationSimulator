<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Safety policy

This document covers the local layered safety system that routes, refuses, or
stops unsafe content without relying on cloud moderation.

For the JSON schema definition, see [`schemas/safety.schema.json`](../schemas/safety.schema.json).  
For the full technical specification, see [`SPEC.md`](SPEC.md) — section 13 covers content safety.

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
[`schemas/safety.schema.json`](../schemas/safety.schema.json) at load time.

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
