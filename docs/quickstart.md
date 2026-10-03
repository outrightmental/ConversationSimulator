<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Quickstart

This guide walks through your first conversation. Complete [installation](install.md) before starting.

---

## 1. Start the services

**macOS / Linux:**

```bash
./scripts/dev.sh
```

**Windows (PowerShell):**

```powershell
.\scripts\dev.ps1
```

Open <http://127.0.0.1:7354> in your browser. The home screen shows green status indicators when convsim-core and the LLM runtime are ready.

---

## 2. Set up a model (first run only)

On first launch the app shows the **welcome screen**. Click **Set me up**.
The app downloads and configures a local AI model automatically. Progress is
shown per stage; you can also expand **Advanced** (*use Ollama or a local GGUF
file*) on the welcome screen to use Ollama or a custom GGUF file instead.

The welcome screen also asks **How familiar are you with AI language models?**
Answering is one click and skipping it is free — it only sets how much
machinery the app shows you. Say you work with them and the app shows session
ids, internal state names and event flags; otherwise it keeps everyday
language only, which is the default if you skip the question. You can change
it at any time under **Settings → Wording**, and the app offers to revisit it
once after you finish the tutorial.

The recommended starter is **Qwen3 4B Instruct Q4_K_M** (~2.5 GB, Apache-2.0 licensed). It works on machines with as little as 4 GB of GPU VRAM, or runs on CPU with no GPU at all.

No internet connection is needed after the model is downloaded. See [local-models.md](local-models.md) for all available models and hardware recommendations.

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

- The NPC's current dialogue, with its mood labelled beneath each reply
- The conversation meters above the transcript, if the scenario defines any —
  one bar per meter, each showing how far it moved on the last turn
- A text input at the bottom for your responses

Type your response and press **Enter** (or click **Send**). The NPC responds in one to five seconds, depending on your hardware and model.

Each exchange is labelled **Turn N**: one turn is your message plus the NPC's
reply to it, so both carry the same number. The NPC's first line is labelled
**Opening**, because it comes before the first exchange.

The scenario ends automatically when the NPC reaches a terminal state. You can also click **End conversation** at any time.

### Leaving and coming back

You do not have to finish a conversation in one sitting, and you do not have to
start over if you leave it. While a conversation is unfinished, a
**Conversation in progress** strip appears under the header on every other
screen, with a **Resume** button that takes you straight back to it — including
from Settings, so you can change something mid-scenario and return. Home lists
**Resume your conversation** as its first action, and **Settings → Your
sessions** has a **Resume** button for every unfinished conversation, not just
the most recent one.

### If replies feel slow

Open **Settings → Reply speed** and choose **Quick replies**. It takes effect
on your very next message with nothing to restart, so you can change it without
leaving the conversation behind. See
[troubleshooting](troubleshooting.md#low-vram-or-slow-inference) if that is not
enough.

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
- **Create a custom scenario** — see the [scenario authoring guide](scenario-authoring.md).
- **Tune reply speed** — if responses feel slow, **Settings → Reply speed** is the quickest fix and needs no restart.
- **Upgrade your model** — if responses feel generic, try a larger model; if they feel slow, a *smaller* one is the biggest win. See [local-models.md](local-models.md).

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| Enter | Send message |
| Shift+Enter | New line in input |

---

## Next steps

- [Local models](local-models.md) — choose the right model for your hardware
- [Troubleshooting](troubleshooting.md) — if something does not work
- [README](../README.md) — project overview
