---
title: "Quickstart"
description: "Walk through your first conversation: launch the app, install a model, choose a scenario, play, and review the debrief."
sidebar:
  order: 2
---

This guide walks through your first conversation. Complete the
[installation](/start/install/) before starting.

---

## 1. Launch the app

Open Conversation Simulator. The home screen shows green status indicators
when the conversation engine and the LLM runtime are ready.

If the engine reports a problem instead, the home screen offers a restart
button — see [Troubleshooting](/start/troubleshooting/#engine-startup-failure)
if it persists.

---

## 2. Install a model (first run only)

If no model is loaded the home screen shows a **"No model loaded"** banner. Click **Install model** or go to **Settings → Models**.

The in-app model manager:

1. Lists curated models from the registry with size, license, and hardware requirements.
2. Shows the license text and asks you to accept before downloading.
3. Downloads the model file, verifies its SHA-256 checksum, and loads it.

The recommended starter is **Qwen3 4B Instruct Q4_K_M** (~2.6 GB, Apache-2.0 licensed). It works on machines with as little as 4 GB of GPU VRAM, or runs on CPU with no GPU at all.

No internet connection is needed after the model is downloaded. See [local-models.md](/play/local-models/) for all available models and hardware recommendations.

---

## 3. Choose a scenario

From the home screen, click **Browse scenarios** (or the scenario icon in the sidebar).

Some scenarios to get started:

| Pack | Scenario | What it practices |
|---|---|---|
| Job Interview Basics | Standard behavioral interview | STAR responses under pressure |
| Everyday Negotiation | Used car negotiation | Opening offers, counteroffers |
| Language Café | Spanish small talk | Casual vocabulary, greetings |
| Difficult Conversations | Giving critical feedback | Staying calm, being specific |

Click a scenario card to see its description, then click **Start conversation**.

---

## 4. Play through a conversation

The conversation screen shows:

- The NPC's current dialogue
- A text input at the bottom for your responses
- A turn counter and scenario progress bar

Type your response and press **Enter** (or click **Send**). The NPC responds in one to five seconds, depending on your hardware and model.

The scenario ends automatically when the NPC reaches a terminal state. You can also click **End conversation** at any time.

---

## 5. Review the debrief

After the conversation the debrief screen shows:

- A turn-by-turn transcript
- State changes tracked during play (e.g., *pressure +8, patience −3*)
- Rubric scores where the scenario defines them
- Suggested follow-up scenarios or remixes

You can export the transcript to a text file from the debrief screen. Transcripts are stored locally in `~/.convsim/db/` and are never uploaded anywhere.

---

## What to try next

- **Remix the scenario** — adjust NPC difficulty or starting state from the scenario setup screen before starting.
- **Create a custom scenario** — see the [scenario authoring guide](/create/scenario-authoring/).
- **Upgrade your model** — if responses feel slow or generic, try a larger model; see [local-models.md](/play/local-models/).

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| Enter | Send message |
| Shift+Enter | New line in input |

---

## Next steps

- [Local models](/play/local-models/) — choose the right model for your hardware
- [Troubleshooting](/start/troubleshooting/) — if something does not work
- [README](https://github.com/outrightmental/ConversationSimulator) — project overview
