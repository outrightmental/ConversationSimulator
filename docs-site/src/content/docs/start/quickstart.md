---
title: "Quickstart"
description: "Walk through your first conversation: complete first-run setup, choose a scenario, play, and review the debrief."
sidebar:
  order: 2
verified_against: v0.2.2
---

This guide walks through your first conversation. Complete the
[installation](/start/install/) before starting.

---

## 1. First-run setup (first launch only)

Open Conversation Simulator. On first launch the **welcome screen** appears.

Click **Set me up**. The app downloads and configures a local AI model
in the background. A progress screen shows each stage of the setup.

While the model downloads you can click **Start now** on the **Have your first
conversation** card to try the simulator right away with scripted, non-AI
responses — it teaches you the conversation UI, state meters, and the debrief
rubric without needing the AI to be ready.

When all stages complete, click **Continue to Home**.

No internet connection is needed after this one-time setup. Want to use
Ollama or a custom model instead of the default? See
[Choosing how to run the AI](/play/ai-engine/).

---

## 2. Check the home screen

The home screen shows green status indicators when the conversation engine
and LLM runtime are ready.

If the engine reports a problem, the home screen shows a remediation card
with a fix action — see
[Troubleshooting](/start/troubleshooting/#engine-startup-failure) if it persists.

---

## 3. Choose a scenario (first conversation)

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
- **Upgrade your model** — if responses feel slow or generic, try a larger model; see [Choosing how to run the AI](/play/ai-engine/).

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| Enter | Send message |
| Shift+Enter | New line in input |

---

## Next steps

- [Choosing how to run the AI](/play/ai-engine/) — built-in engine, Ollama, GGUF, hardware recommendations
- [Troubleshooting](/start/troubleshooting/) — if something does not work
- [README](https://github.com/outrightmental/ConversationSimulator) — project overview
