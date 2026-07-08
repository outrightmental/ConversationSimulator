<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Scenario authoring — creator workbench tutorial

This guide walks you through creating your first scenario pack by following
the actual product workflow: open the Creator Workbench, copy an official
pack, edit the NPC and scenario, validate, quick-test in the browser,
export, and share. Concrete examples use fictional characters throughout.

For the content quality bar — what makes a pack ready for the official
repository — see [`docs/official-pack-quality-bar.md`](official-pack-quality-bar.md).

---

## What you will build

By the end of this guide you will have a working scenario pack called
**Workplace Conversations**, containing:

- One fictional NPC: **Morgan Okafor**, HR Manager at a fictional company
- One scenario: **The Raise Conversation** — practice asking your manager
  for a merit increase
- A rubric with two scored dimensions
- A safety policy
- A smoke test that passes `convsim validate-pack` and `convsim test-pack`

The exported pack is a `.zip` file you can share, import into a fresh
installation, and play immediately.

---

## Before you start

You need:

1. The app running locally — `./scripts/dev.sh` or `scripts\dev.ps1` on
   Windows. The Creator Workbench works without a language model installed;
   you can author and validate packs without LLM inference.
2. A browser open at **http://127.0.0.1:7354**.
3. At least one official pack installed (they ship with the repo under
   `packs/official/`).

> **CLI fallback.** Every step in this guide has a CLI equivalent.
> CLI commands are shown in `code blocks` throughout.

---

## Step 1: Open the Creator Workbench

In the top navigation, click **Workbench**, or navigate directly to
`http://127.0.0.1:7354/workbench`. The screen's heading reads
**Creator Workbench**.

[![Creator Workbench — three-panel view showing the pack list on the left,
file tree below it, and the YAML editor on the right with a green validation
banner.](assets/screenshots/05-creator-workbench.svg)](assets/screenshots/05-creator-workbench.svg)

The screen has three areas:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Creator Workbench                                                       │
│  ─────────────────────────────────────────────────────────────────────  │
│  ✓ Pack is valid                                            [Revalidate] │
│                                                                          │
│  ┌─ Packs ──────────┐  ┌─ Edit │ Test Chat ─────────── ⬇ Export .zip ─┐│
│  │  OFFICIAL        │  │                                               ││
│  │  · job-interview │  │  Select a YAML or Markdown file from          ││
│  │  LOCAL DEV       │  │  the tree.                                    ││
│  │  · my-new-pack   │  │                                               ││
│  │  ─────────────── │  │                                               ││
│  │  ⬆ Import Pack   │  │                                               ││
│  └──────────────────┘  └───────────────────────────────────────────────┘│
│  ┌─ Files ──────────┐                                                   │
│  │  ▼ scenarios     │                                                   │
│  │    📄 my.yaml    │                                                   │
│  │  ▼ npcs          │                                                   │
│  │    📄 my.yaml    │                                                   │
│  └──────────────────┘                                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

| Panel | What it does |
|-------|-------------|
| **Packs** (top-left) | Lists all installed packs grouped by **Official** and **Local Dev**. Click a pack name to select it. |
| **Files** (bottom-left) | File tree for the selected pack. Click a `.yaml` or `.md` file to open it in the editor. |
| **Edit** tab (right) | Plain YAML / Markdown editor. Saves trigger automatic revalidation. |
| **Test Chat** tab (right) | Run a live text-only test session against the current pack without leaving the workbench. |
| Validation banner (above panels) | Shows `✓ Pack is valid` or lists errors and warnings. Updates after every save. |
| **⬇ Export .zip** (top-right) | Downloads the selected pack as a zip archive you can share or import elsewhere. |
| **⬆ Import Pack (.zip)** (bottom of Packs panel) | Imports a `.zip` pack archive into Local Dev. |

---

## Step 2: Copy an official pack to start from

Official packs are **read-only** in the workbench. Clicking a file in an
official pack opens it with a **Read-only** badge and a
**"Create local copy to edit"** button in the editor toolbar.

**In the UI:**

1. In the **Packs** panel, click **job-interview-basic** under **Official**.
2. The **Files** panel fills with the pack's file tree.
3. Click any `.yaml` file — for example `manifest.yaml`.
4. In the editor toolbar, click **"Create local copy to edit"**.

The workbench copies the pack to `packs/local-dev/`, switches to the copy
automatically, and makes all files editable. The copy appears under
**Local Dev** in the Packs panel.

**CLI fallback:**

```sh
cp -r packs/official/job-interview-basic packs/local-dev/workplace-conversations
```

---

## Step 3: Meet the files

After copying, browse the file tree in the left panel. Official packs share
this directory structure — one folder per file type:

```
workplace-conversations/
├── manifest.yaml                        # Pack identity, rating, safety ref
├── scenarios/
│   └── behavioral_interview.yaml        # One file per scenario
├── npcs/
│   └── hiring_manager.yaml              # One file per NPC
├── rubrics/
│   └── interview_rubric.yaml            # One file per rubric
├── safety/
│   └── interview_safety.yaml            # Safety policy
├── scenes/
│   └── conference_room.yaml             # Optional — scene/setting context
├── tests/
│   └── smoke_behavioral_interview.yaml  # Smoke test per entry scenario
└── assets/
    └── portraits/                        # Optional NPC portraits
```

> **The pack you copied ships with more than one example.** `job-interview-basic`
> contains four scenarios (and their NPCs, rubrics, scenes, and smoke tests).
> This tutorial edits just one chain — `behavioral_interview` and the files it
> references — into the Raise Conversation. The extra example files stay valid,
> but you don't need them; [Trim the starter files](#trim-the-starter-files)
> before Step 9 removes them so your exported pack contains only what you built.

> Files ending in `.yaml` or `.md` are editable in the workbench. Portrait
> images in `assets/` show as **unsupported** in the file tree and cannot
> be edited in the browser — manage them directly in your filesystem.

You will rename and edit these files over the next steps to build the
Workplace Conversations pack.

---

## Step 4: Edit the NPC

In the file tree, click `npcs/hiring_manager.yaml` to open it.

Replace its contents with a new fictional NPC. The NPC name must not be an
identifiable real person — use an invented name with a plausible but clearly
fictional company.

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
npc_id: hr_manager
display_name: Morgan Okafor
archetype: professional_negotiator
fictional: true       # Required. Must always be true. Schema fails if absent.
age_band: adult       # Required. Only "adult" is allowed in MVP.
voice:
  engine: none        # kokoro | sherpa-onnx | none

public_persona:
  occupation: >-
    HR Manager at Brightfield Analytics, a 200-person B2B data firm.
    Morgan manages compensation reviews and has final say on merit increases
    up to 15 percent.
  speaking_style: >-
    Professional and measured. Asks clarifying questions before committing
    to any position. Uses precise language and avoids vague reassurances.
  demeanor: >-
    Warm but boundary-conscious. Becomes noticeably more reserved when
    asked for specific numbers without supporting evidence. Responds well
    to data-backed arguments and concrete examples of measurable impact.

private_persona:
  hidden_agenda:
    - "Assess whether the employee can justify the raise with specific, measurable impact — not just tenure or general effort"
    - "Determine whether the employee has researched market rates and can defend their ask with external data"
  biases_to_simulate:
    - "Slight skepticism toward requests framed entirely around personal financial need rather than demonstrated professional value"
    - "Increased openness when the employee acknowledges constraints on the company's side and frames the ask collaboratively"
  boundaries:
    - "Never generate sexual, violent, or graphically disturbing content"
    - "Never impersonate a real person, named public figure, or real company executive"
    - "Never make promises about compensation outcomes that contradict company policy"
    - "Never disclose other employees' salaries or performance ratings"
```

Click **Save** in the editor toolbar. The Validation panel above updates.
If you see `✓ Pack is valid`, the NPC file is well-formed.

**Key NPC fields:**

| Field | Why it matters |
|-------|----------------|
| `fictional: true` | Required by schema. Validation fails immediately if absent or `false`. |
| `age_band: adult` | Only `adult` is permitted in MVP. |
| `public_persona` | Shown to the player and used in runtime prompts. Be specific — a vague occupation produces a flat, interchangeable NPC. |
| `private_persona.hidden_agenda` | System-prompt context the player never sees. Write as observable evaluation criteria the NPC applies to each player turn. |
| `private_persona.biases_to_simulate` | Tendencies that shift the NPC's tone without the player knowing they exist. These create the asymmetry that makes practice meaningful. |
| `private_persona.boundaries` | Hard rules the NPC must never violate regardless of player input. Every NPC must include the no-sexual-content and no-real-person-impersonation boundaries at minimum. |

---

## Step 5: Edit the scenario

Click `scenarios/behavioral_interview.yaml` to open it.

Replace its contents:

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
scenario_id: raise_conversation
title: The Raise Conversation
summary: >-
  You have requested a meeting with your HR Manager, Morgan Okafor, to
  discuss a merit increase. You have been with Brightfield Analytics for
  two years and believe your contributions justify a raise. This is your
  chance to make the case.

player_role:
  label: Employee
  brief: >-
    You are a mid-level analyst who has delivered measurable results over
    the past year. You want to ask for a 12 percent raise. Come prepared
    with specific examples of your impact — vague appeals to effort or
    tenure are unlikely to move Morgan.

npc:
  ref: ../npcs/hiring_manager.yaml   # The file you edited in place in Step 4

rubric:
  ref: ../rubrics/interview_rubric.yaml   # The file you edited in place in Step 6

duration:
  max_turns: 16
  soft_time_limit_minutes: 12

opening:
  npc_says: >-
    Thanks for reaching out to schedule this. I always appreciate when
    employees want to have a direct conversation about compensation.
    What would you like to discuss today?

goals:
  player_visible:
    - "Clearly state the specific raise you are asking for"
    - "Support your request with concrete examples of your contributions"
  hidden:
    - "Morgan will only take the request seriously if the player provides specific, measurable impact — general claims about working hard are not sufficient"
    - "Morgan responds better when the player acknowledges budget constraints and frames the ask around market data or role scope expansion"

state:
  variables:
    receptiveness:
      min: 0
      max: 100
      default: 50
      visibility: visible           # Player can see this in the session
      max_delta_per_turn: 12
    evidence_score:
      min: 0
      max: 100
      default: 0
      visibility: hidden            # Player cannot see this
      max_delta_per_turn: 20

events:
  - id: vague_request_nudge
    when:
      type: variable_below
      variable: evidence_score
      threshold: 20
    npc_instruction: >-
      The employee has made their request but has not provided any specific
      evidence of impact. Respond with genuine curiosity rather than
      skepticism: "That sounds like something worth discussing — can you
      walk me through a specific example of the impact you've had this year?
      Concrete numbers are always helpful when I take a case to the
      compensation committee."
    repeat: false

  - id: strong_case_acknowledgement
    when:
      type: variable_above
      variable: evidence_score
      threshold: 70
    npc_instruction: >-
      The employee has made a compelling, evidence-backed case. Acknowledge
      it directly: "You've clearly done your homework, and the results you
      described are genuinely strong. Let me take this to the compensation
      review and follow up with you by end of week."
    repeat: false

ending_conditions:
  success:
    type: variable_above
    variable: receptiveness
    threshold: 72
  failure:
    type: variable_below
    variable: receptiveness
    threshold: 15

response_style:
  max_words: 80
  verbosity: moderate
  formality: professional

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

> **Rename the file.** The file is still called `behavioral_interview.yaml`.
> Rename it in your filesystem:
> `mv scenarios/behavioral_interview.yaml scenarios/raise_conversation.yaml`.
> Then update `entry_scenarios` in `manifest.yaml` to match (Step 8).
> The workbench file tree reflects the rename after a reload.
>
> Only the scenario file needs renaming, because `manifest.yaml` references it
> by path. The NPC and rubric files keep their original names
> (`hiring_manager.yaml`, `interview_rubric.yaml`) — a file name never has to
> match the `npc_id` or `rubric_id` inside it, and the scenario's `ref:` fields
> already point at those paths. If you do rename them, update the matching
> `ref:` in the scenario or validation reports `MISSING_FILE`.

**State variables** track the NPC's internal state across turns:

| Visibility | Who can see it | When to use |
|------------|---------------|-------------|
| `visible` | Player (shown as a state meter during the session) | Variables that correspond to something the player can infer from the NPC's responses |
| `hidden` | System prompt only | NPC internal state the player has to discover through experimentation |

**Event trigger types:**

| Type | Fields | When it fires |
|------|--------|--------------|
| `variable_above` | `variable`, `threshold` | When variable > threshold |
| `variable_below` | `variable`, `threshold` | When variable < threshold |
| `max_turns` | `value` | When turn count reaches value |
| `flag` | `flag_id` | When a named flag is set |

---

## Step 6: Edit the rubric

Click `rubrics/interview_rubric.yaml`. Replace its contents with a rubric
focused on the raise scenario:

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
rubric_id: raise_rubric
title: Raise Conversation Rubric
dimensions:
  - id: evidence_quality
    name: Evidence Quality
    description: >-
      Whether the player supports their request with specific, measurable
      examples of their contributions rather than vague claims about effort
      or tenure.
    scoring:
      low: "Request is based entirely on personal need or time served ('I've been here two years'). No specific results or measurable outcomes are mentioned."
      medium: "Player mentions a real project or contribution but does not provide measurable outcomes or link it clearly to their value to the company."
      high: "Player cites at least one specific example with a measurable result (e.g. 'I reduced churn by 8 percent in Q3') and connects it to their market value or role scope."
    weight: 0.45

  - id: professional_framing
    name: Professional Framing
    description: >-
      Whether the player frames the conversation as a professional discussion
      of value rather than a personal financial request.
    scoring:
      low: "Request is framed entirely around personal financial need. No reference to market rates, role scope expansion, or company outcomes."
      medium: "Player attempts a professional framing but relies on general statements ('I work really hard') without grounding them in evidence or market context."
      high: "Player references market data, role scope expansion, or company outcomes to frame the raise as a fair exchange of value, not a personal favour."
    weight: 0.55
```

Rubric anchors must describe **observable behaviours** in the conversation
transcript — not abstract qualities like "good communication". An evaluator
must be able to score a transcript consistently using only the anchor text.

---

## Step 7: Edit the safety policy

Click `safety/interview_safety.yaml`. A professional workplace conversation
uses a standard PG policy:

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
policy_id: workplace_conversations_safety
content_categories:
  nsfw_sexual_content: stop
  criminal_instruction: refuse
  self_harm_crisis: stop_with_resource_message
  minors_romantic_or_sexual: stop
  harassment_extreme: redirect
  real_person_impersonation: refuse
redirect_message: >-
  That's outside the scope of what I can discuss in this context. Let's
  bring the conversation back to your compensation review — is there
  something specific about your contributions you'd like to walk me through?
allow_profanity: false
content_rating_cap: PG
```

Write `redirect_message` in the NPC's voice. A generic "This content is not
permitted" message breaks immersion and makes the session feel robotic.

**Safety actions and what they do:**

| Action | What happens |
|--------|-------------|
| `stop` | Ends the session immediately. Use for hard limits — NSFW content, content involving minors. |
| `refuse` | The NPC declines without ending the session. |
| `redirect` | The NPC steers the conversation back to topic using `redirect_message`. |
| `stop_with_resource_message` | Ends the session and shows the player real crisis resources. |

Two categories are **hardcoded in the runtime and cannot be weakened by any
pack:**

- `minors_romantic_or_sexual` → always `stop`
- `self_harm_crisis` → always `stop_with_resource_message`

Every pack must still declare them explicitly so a human reviewer can confirm
intent. See [Safety and content examples](#safety-and-content-examples) for
G, PG, and PG-13 policy templates.

---

## Step 8: Update the manifest

Click `manifest.yaml`. Update it to match your new pack:

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
pack_id: community.workplace_conversations  # reverse-domain, lowercase, underscores
name: Workplace Conversations
version: 0.1.0
description: >-
  Practise professional conversations that matter: asking for a raise,
  giving difficult feedback, and navigating workplace dynamics. All
  scenarios use fictional characters at realistic companies.
author: Your Name
license: CC-BY-4.0          # SPDX identifier — see License metadata below
content_rating: PG          # G | PG | PG-13 — use the highest in the pack
tags:
  - negotiation
  - professional
  - workplace
supported_languages:
  - en
entry_scenarios:
  - scenarios/raise_conversation.yaml   # Updated to match the renamed file
assets:
  allow_external_urls: false            # Must be false for offline-first packs
safety:
  policy: safety/interview_safety.yaml
```

---

## Trim the starter files

`job-interview-basic` shipped with four scenario chains. Your manifest now lists
only `scenarios/raise_conversation.yaml`, so the other three are dead weight —
their files still validate, but they'd ride along in your export. Delete them,
their NPCs, rubrics, scenes, and the original smoke tests. You keep only the
files you edited plus `manifest.yaml`, `safety/interview_safety.yaml`, and
`README.md`.

```sh
cd packs/local-dev/workplace-conversations

# Extra scenario chains (kept only behavioral_interview, now raise_conversation)
rm scenarios/hostile_executive_interview.yaml \
   scenarios/blue_collar_supervisor_interview.yaml \
   scenarios/stretch_role_interview.yaml
rm npcs/executive_interviewer.yaml npcs/product_head.yaml npcs/trade_supervisor.yaml
rm rubrics/blue_collar_rubric.yaml rubrics/executive_interview_rubric.yaml \
   rubrics/stretch_role_rubric.yaml

# Scenes — the Raise Conversation declares no scene, so remove all of them
rm scenes/*.yaml

# Original smoke/golden tests — you'll add your own below
rm tests/*.yaml
```

Do this **after** Step 8. Because the manifest no longer references any of these
files, removing them leaves the pack valid. (Removing them earlier, while
`entry_scenarios` still listed the interview scenarios, would produce
`MISSING_FILE` errors.) The leftover smoke tests would otherwise be *skipped*
rather than failed — `test-pack` still exits `0` — but a clean pack is the
whole point.

In the workbench, the file tree reflects the deletions after a reload.

---

## Step 9: Validate the pack

### In the workbench

After each **Save**, the Validation panel updates automatically.

| Banner | What it means |
|--------|--------------|
| `✓ Pack is valid` (green) | No errors or warnings. The pack is structurally correct. |
| `N validation errors, N warnings` (red/amber) | Problems to fix before testing. Click a filename in the panel to jump to that file in the editor. |
| `⛔ SECURITY` badge | A `FORBIDDEN_FILE` or `FORBIDDEN_BINARY` error was found — a script or executable is inside the pack directory. Remove it immediately. |
| `⚠ Validator unavailable` (amber) | The validator service is unreachable. Click **Retry**, or use the CLI. |

Click **Revalidate** to force a fresh check without making edits.

When there are errors, the Validation panel shows a **"Authoring guide ↗"**
link back to this document and a **"Validation rules ↗"** link to
[`docs/pack-validation.md`](pack-validation.md) for the full error reference.

### CLI

```sh
convsim validate-pack packs/local-dev/workplace-conversations/
```

Exit code `0` = valid. Errors are printed to stderr with the failing file
path and schema field. Use `--json` for machine-readable output.

---

## Step 10: Quick-test in Test Chat

Click the **Test Chat** tab in the right panel. Test Chat runs a temporary
text-only session using the current pack — no language model required for
structural checks.

1. Click **▶ Start Test Session**.
2. Read the NPC's opening line (from `opening.npc_says` in the scenario).
3. Type a player response and press **Enter** to send (or **Shift+Enter**
   for a new line, then click **Send**).
4. Watch the **State Variables** panel on the right side of the chat area
   to see how variables are declared and initialised.
5. Try different response types to verify your event logic is wired correctly.

**What the Test Chat shows:**

| UI element | What it means |
|------------|--------------|
| Green dot + **Active** | Session is running, waiting for player input. |
| **Thinking…** | Waiting for the NPC's response. |
| **Ended: success** / **Ended: failure** | The session hit an ending condition from `ending_conditions`. |
| `⚠ Safety redirect applied` (amber badge) | The safety policy fired a `redirect` action. |
| `✕ Safety stop — session ended` (red badge) | The safety policy fired a `stop` action. |
| **State Variables** panel | Live view of all state variables with their current values and turn deltas. |
| Purple event badges | Named events that fired this turn, identified by their `id` field. |

**Toolbar controls in the active session:**

- **Reset** — starts a fresh session from the beginning, clearing the
  transcript and state.
- **Discard** — ends the test session entirely and returns to the idle view.

> **Fake runtime limitation.** Test Chat uses a deterministic fake runtime
> that does not call a language model. State variables are populated at their
> declared default values but do not change dynamically based on player input.
> Event logic and ending conditions are structurally validated but not
> behaviourally simulated until a real model is wired in. Use Test Chat to
> verify structural correctness; run a full session from the Scenario Library
> for live behavioural testing once a model is installed.

If the pack has validation errors, the **▶ Start Test Session** button is
disabled and the error count is shown. Fix the errors first.

---

## Step 11: Export and share

When the pack validates (`✓ Pack is valid`) and Test Chat starts without
errors:

1. Click **⬇ Export .zip** in the top-right of the right panel.
2. The workbench downloads `workplace-conversations.zip` to your browser's
   default download folder.
3. A `✓ workplace-conversations.zip` confirmation appears next to the button.
4. Send the `.zip` to another user, or host it anywhere.

**Importing on another machine:**

1. Open the Creator Workbench on the target machine.
2. Click **⬆ Import Pack (.zip)** in the Packs panel.
3. Select the `.zip` file in the file picker.
4. The pack appears under **Local Dev** and is selected automatically.
5. If the pack fails validation on import, the Packs panel shows the errors
   inline — fix them in the source and re-export.

**CLI equivalents:**

```sh
# Export as a zip archive
cd packs/local-dev && zip -r workplace-conversations.zip workplace-conversations/

# Import a zip on another machine
convsim import-pack workplace-conversations.zip

# Or copy the directory directly if you have filesystem access
cp -r workplace-conversations packs/local-dev/
```

**The exported pack is immediately playable.** After importing, it appears
in the Scenario Library under the pack's `name` field. Navigate to
**Scenario Library → Workplace Conversations → The Raise Conversation**
and start a session with any installed model.

---

## Adding a smoke test

Add one smoke test per entry scenario in `tests/`:

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
fixture_id: smoke_raise_conversation
scenario_id: raise_conversation
description: >-
  Verifies raise_conversation loads cleanly and a strong first response
  advances the session without triggering a safety stop.
seed: 42
input_mode: text
difficulty: normal
turns:
  - turn: 1
    player_input: >-
      Thanks for meeting with me, Morgan. I'd like to discuss a merit
      increase. Over the last year I led the migration to our new data
      pipeline, which cut nightly processing time from six hours to
      forty minutes — a change that unblocked three product teams. I
      believe that level of impact justifies revisiting my compensation.
    expect:
      state_delta_contains:
        - receptiveness
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

Run all tests:

```sh
convsim test-pack packs/local-dev/workplace-conversations/
```

Both `convsim validate-pack` and `convsim test-pack` must exit `0` before
the pack is ready to share or submit.

---

## Using the YAML editor

The workbench currently provides a **plain YAML editor** (a monospace
text area) for all pack files. A structured form editor that exposes
individual fields as labelled inputs is planned for a later milestone.

**The YAML editor is the right tool for:**

- Any edit to a pack file — the YAML editor is the only editor available today.
- Fine-grained control over event conditions, state variable ranges, and
  rubric anchor text.
- Reviewing the raw structure of a file before adapting it.
- Editing files a form editor would not expose, such as safety policies and
  smoke tests.

**The form editor (coming later) will be the right tool for:**

- Creating a new NPC from scratch without knowing every schema field.
- Setting required fields (`fictional: true`, `age_band: adult`) without
  risking a typo.
- Editing common scenario fields — title, summary, opening — through
  labelled inputs with inline validation feedback.

Until the form editor ships, the recommended workflow is: **save frequently,
watch the validation banner, and fix errors one file at a time.** The
validation panel links directly to the failing file.

**Tips for editing YAML in the workbench:**

- YAML requires **spaces for indentation** — never tabs. Mixing them
  produces `INVALID_YAML` errors.
- String values longer than one line should use YAML block scalars
  (`>-` for folded, `|` for literal). The `>-` style trims trailing
  newlines, which suits most prose fields.
- Use the `Revalidate` button to force a fresh check without needing to save.

---

## Pack folder structure (reference)

```
my-pack/
├── manifest.yaml              # Required. Pack identity, rating, safety ref.
├── scenarios/
│   └── my_scenario.yaml       # Required. At least one scenario.
├── npcs/
│   └── my_npc.yaml            # Required. At least one NPC per scenario.
├── rubrics/
│   └── my_rubric.yaml         # Required. At least one rubric per scenario.
├── safety/
│   └── my_policy.yaml         # Required. Referenced from manifest.yaml.
├── tests/
│   └── smoke_my_scenario.yaml # One per entry scenario (required for official packs).
├── scenes/
│   └── my_scene.yaml          # Optional. Setting context referenced by scenarios.
└── assets/
    └── portraits/             # Optional. NPC portrait images (no external URLs).
```

All YAML files must start with an SPDX license header on the first line:

```yaml
# SPDX-License-Identifier: CC-BY-4.0
```

---

## Common validation errors and fixes

Errors appear in the Validation panel with a stable error code. Click the
filename in the panel to jump to that file in the editor.

### MISSING_FILE

```
✗ MISSING_FILE: File not found: scenarios/raise_conversation.yaml
```

A file referenced in `manifest.yaml` (or via `ref:` in a scenario) does
not exist at the expected path.

Common causes:
- You renamed a file but did not update the `entry_scenarios` path in
  `manifest.yaml`.
- A `ref:` uses an absolute path or escapes the pack root.

Fix: check every `ref:` field and every path in `entry_scenarios` against
the actual file tree shown in the left panel.

### SCHEMA_VALIDATION

```
✗ SCHEMA_VALIDATION: npcs/hiring_manager.yaml
  /fictional: must be equal to one of the allowed values
```

A field value is wrong or a required field is missing. Common cases:

| Field | Valid values |
|-------|-------------|
| `schema_version` | `"0.1"` only |
| `content_rating` | `G`, `PG`, `PG-13` |
| `fictional` | must be `true` — not `false`, not absent |
| `age_band` | `adult` only |
| `allow_profanity` | `true` or `false` |

Fix: open the file named in the error, find the field at the JSON pointer
path shown (e.g. `/fictional`), and correct the value.

### INVALID_YAML

```
✗ INVALID_YAML: bad indentation of a mapping entry at line 14
```

The file is not well-formed YAML. The most common cause is mixed indentation
(tabs mixed with spaces, or a misaligned list item).

Fix: use the line number in the error. In the editor, check indentation
around that line — YAML requires spaces, not tabs.

### FORBIDDEN_FILE / FORBIDDEN_BINARY

```
✗ FORBIDDEN_FILE: scripts/setup.py — MVP packs are data, not code.
```

A script, executable, or symlink was found inside the pack directory.
Packs are **data only** — no code is permitted. See
[Why executable plugins are forbidden](#why-executable-plugins-are-forbidden-in-mvp).

Fix: delete the offending file from the pack directory. If you need to
include example command-line text, put it inside a YAML string field, not
in a standalone script file.

### DUPLICATE_ID

```
✗ DUPLICATE_ID: Duplicate scenario_id "raise_conversation" in pack
```

Two scenarios (or two NPCs) share the same ID. IDs must be unique within
a pack.

Fix: rename one of the duplicates in the YAML file. Update any `ref:` fields
that point to it.

### UNSUPPORTED_VERSION

```
✗ UNSUPPORTED_VERSION: schema_version "0.2" — expected "0.1"
```

A file declares a `schema_version` the loader does not support. MVP supports
`"0.1"` only.

Fix: set `schema_version: "0.1"` in every YAML file.

### PATH_TRAVERSAL

```
✗ PATH_TRAVERSAL: ref "../../etc/passwd" escapes the pack root
```

A `ref:` or other path resolves outside the pack directory. All references
must point to files inside the pack root.

Fix: rewrite the path to be relative and contained within the pack folder.

### Smoke test failure (`convsim test-pack`)

```
✗ smoke_raise_conversation: Turn 1: session_control expected "continue_session", got "end_session"
```

A turn assertion failed. The player input in the fixture may be triggering
an unexpected ending condition or safety stop.

Fix: check the `player_input` for that turn. If it matches an ending
condition threshold, adjust the input or loosen the threshold. Assert
`session_control: continue_session` and `safety_status: ok` in smoke tests —
the fake runtime always returns these for valid structural input.

---

## Safety and content examples

### G-rated policy (all audiences, no tension beyond mild social friction)

```yaml
# safety/my_policy.yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
policy_id: my_pack_safety
content_categories:
  nsfw_sexual_content: stop
  criminal_instruction: refuse
  self_harm_crisis: stop_with_resource_message
  minors_romantic_or_sexual: stop
allow_profanity: false
content_rating_cap: G
redirect_message: >-
  Let's keep things friendly — is there something specific you'd like to
  talk about?
```

### PG-rated policy (professional tension, mild conflict, rejection)

```yaml
# safety/my_policy.yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
policy_id: my_pack_safety
content_categories:
  nsfw_sexual_content: stop
  criminal_instruction: refuse
  self_harm_crisis: stop_with_resource_message
  minors_romantic_or_sexual: stop
  harassment_extreme: redirect
  real_person_impersonation: refuse
allow_profanity: false
content_rating_cap: PG
redirect_message: >-
  That's outside the scope of what I can discuss here. Let's refocus —
  what were you hoping to accomplish in this conversation?
```

### PG-13-rated policy (emotional difficulty, rejection handling)

```yaml
# safety/my_policy.yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
policy_id: my_pack_safety
content_categories:
  nsfw_sexual_content: stop
  criminal_instruction: refuse
  self_harm_crisis: stop_with_resource_message
  minors_romantic_or_sexual: stop
  harassment_extreme: stop
  medical_or_therapy_claim: redirect
  real_person_impersonation: refuse
allow_profanity: false
content_rating_cap: PG-13
redirect_message: >-
  I understand this is difficult, but that's not something I'm the right
  person to help with. Is there something else on your mind today?
```

**Non-overridable global rules** — always in effect regardless of pack config:

1. `minors_romantic_or_sexual` → `stop` (hardcoded in the runtime)
2. `self_harm_crisis` → `stop_with_resource_message` (hardcoded in the runtime)

Every pack must still declare both explicitly so intent is clear to a human
reviewer. Omitting them fails the official quality checklist.

---

## License metadata examples

Use a valid [SPDX identifier](https://spdx.org/licenses/) in the `license`
field of `manifest.yaml`. Common choices for scenario packs:

| License | SPDX identifier | When to use |
|---------|-----------------|-------------|
| Creative Commons Attribution 4.0 | `CC-BY-4.0` | Open sharing with attribution — matches all official packs |
| Creative Commons Attribution–ShareAlike 4.0 | `CC-BY-SA-4.0` | Open sharing; derivatives must use the same license |
| Creative Commons Attribution–NonCommercial 4.0 | `CC-BY-NC-4.0` | Free for non-commercial use with attribution |
| Creative Commons Zero 1.0 | `CC0-1.0` | Public domain dedication — no conditions at all |
| Proprietary | `LicenseRef-Proprietary` | Commercial or private packs not intended for redistribution |

**In manifest.yaml:**

```yaml
# Open community pack (recommended for sharing)
license: CC-BY-4.0

# ShareAlike — derivative packs must stay open
license: CC-BY-SA-4.0

# Public domain — no attribution required
license: CC0-1.0
```

Official packs use `CC-BY-4.0`. Community packs may use any open license.
Contact the maintainers before submitting a pack under a restricted license.

Pack content — NPC names, scenario writing, and rubric text — must be
original. Do not adapt copyrighted characters, scripts, or proprietary
training material without a compatible license.

---

## Why executable plugins are forbidden in MVP

Packs are **declarative data** — YAML and JSON files only. They contain no
code and cannot execute anything.

The runtime enforces this before parsing any YAML:

1. **Extension scan** — any file with an executable extension (`.sh`, `.py`,
   `.js`, `.ts`, `.exe`, `.bat`, `.rb`, `.pl`, …) causes an immediate
   `FORBIDDEN_FILE` error and the pack is rejected at load time.
2. **Magic-byte scan** — any file whose opening bytes match a known
   executable format (ELF, PE, Mach-O, shebang `#!`) triggers a
   `FORBIDDEN_BINARY` error, even if the file extension looks like a data
   file.
3. **Symlink rejection** — symlinks are refused because they can escape the
   pack root and expose arbitrary paths on the user's filesystem.
4. **Schema enforcement** — `manifest.yaml` must not declare a `scripts`
   field; the JSON Schema uses `not: { required: ["scripts"] }` to fail any
   manifest that includes one.

**Why this rule exists:**

- All inference runs on the user's local machine. A pack that could execute
  code would inherit the same filesystem permissions as the user running the
  app — an unacceptable security risk for content downloaded from community
  sources.
- Declarative packs are auditable in minutes. A reviewer can read every
  YAML file and verify the pack's full behaviour without running it. Code
  packs cannot make that guarantee.
- The rule is non-negotiable in MVP. A plugin system with appropriate
  sandboxing may be considered in a later milestone after the security model
  is fully specified.

If you need dynamic behaviour — for example, branching based on which events
have fired — model it using state variables, events, and ending conditions
in the scenario YAML, not with external code.

---

## Publishing a pack

For official packs, open a pull request against `main`. The CI pipeline runs
`convsim validate-pack` and `convsim test-pack` on every PR. Both must pass.

Before opening a PR:

1. Run `convsim validate-pack packs/official/my-pack/` — exit code must be `0`.
2. Run `convsim test-pack packs/official/my-pack/` — exit code must be `0`.
3. Review against the contribution checklist in
   [`docs/official-pack-quality-bar.md`](official-pack-quality-bar.md).

Community packs that are not intended for the official repository can be
distributed as directories or zip archives and imported with
`convsim import-pack` or the **⬆ Import Pack (.zip)** button in the
Creator Workbench.
