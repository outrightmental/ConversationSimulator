<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Quickstart

This guide walks through your first conversation. Complete [installation](install.md) before starting.

The steps describe the full app. The Steam Next Fest demo is the same app
narrowed to one model and five conversations; where it differs, the step says
so.

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

Open <http://127.0.0.1:7354> in your browser. On a fresh install the app opens
the welcome screen (next step).

---

## 2. First-run setup (first run only)

The welcome screen is headed **Practice conversations that matter.**

It asks **How familiar are you with AI language models?** and offers three
answers: **New to this**, **I have used AI chat apps** and **I work with them**.
Answering is one click and leaving it unanswered is fine: it only sets how much
of the app's machinery you see. **I work with them** turns on technical
wording, which shows session ids, internal state names and event flags. The
other two answers, or no answer, keep plain wording. You can change it at any
time under **Settings → Wording**, and in the full app the debrief of the
**First Words** tutorial asks the question once more.

Click **Set me up**. The card shows the model's download size and license
before you click. The app first checks that it can write to its data folder and
that the disk has room for the model; if either needs your attention it shows
**Getting things ready**, otherwise the download starts. The **Setting up your
AI** screen lists each installation stage under an overall progress bar, and
while the model downloads it explains how to play and previews your first
missions. **Cancel and go home** stops the install.

When every stage is done, the app opens the **Scenario Library**. The demo
opens its Home screen instead.

The recommended model is **Qwen3 4B Instruct Q4_K_M** (2.5 GB, Apache-2.0). The
model registry gives 4 GB of GPU memory as its minimum, and it also runs on the
CPU alone, more slowly. No internet connection is needed after this one-time
download. To use Ollama or your own GGUF file instead, expand **Advanced: use
Ollama or a local GGUF file** on the welcome screen. The demo installs its one
model and has no **Advanced** option. See [local-models.md](local-models.md)
for all available models and hardware recommendations.

### The Home screen

Home's **Status** panel lists the **AI engine** and the **AI model**. Each shows
a green badge once it is ready, and the AI model badge shows the model's name.
If Home cannot reach the engine it shows **The conversation engine is not
responding** with a **Restart the app** button; if the engine reported an error
it shows the error with **Restart conversation engine**. See
[troubleshooting](troubleshooting.md) if the problem persists.

---

## 3. Choose a scenario

The Scenario Library lists each installed pack with its scenarios, under a
search box and filters. You can also reach it from Home with **Start a
scenario**, or with **Scenarios** in the header. Click **Launch** on a scenario
to open its brief.

Some scenarios to get started:

| Pack | Scenario | What it practices |
|---|---|---|
| Job Interview Basics | The Behavioral Interview | Specific, structured answers using the STAR method |
| Everyday Negotiation | The Used Car Deal | Anchoring early, citing your research, closing a fair deal |
| Language Café | Coffee at Café Sol | Ordering and small talk in Spanish |
| Difficult Conversations | The Feedback Conversation | Honest, specific feedback to a peer that keeps the working relationship intact |

**In the demo** there is no library. Home lists **Your five conversations**:
The Behavioral Interview, The Used Car Deal, Making the Case (Difficult
Conversations), The Coffee Cart and Coffee at Café Sol. Each card has a
**Start** button that opens the brief. If the demo's model is not installed
yet, Home first shows **One download and you're in** with **Install the demo
model →**.

---

## 4. Read the Conversation Brief

The brief sits between choosing a scenario and talking to the character, and
it leads with the mission. Beside the pack, title and situation is **Your
objective**: the scenario's goals as a numbered list. Under them a row of facts
gives **You play**, **Estimated length**, **Turn limit**, **Content rating** and
**Voice**.

Next come the two decisions that change the conversation:

- **Difficulty**: how the character will behave. Each level says what it does
  and draws its traits as meters (**Patience**, **Disclosure**, **Volatility**,
  **Time pressure**). The scenario's default level is marked **recommended**.
- **Your role**: who you are in the conversation, and **Name to use in this
  session**.

**Session setup** groups the mechanical settings in one quieter card: **Input
mode**, **Audio output**, **Language**, **Privacy** and an optional **Variation
seed**. Under **Privacy**, **Save transcript locally** keeps the transcript for
the debrief, and **Show the conversation meters** is on wherever the scenario
allows meters. Beside the cards, **Runtime readiness** shows whether the model
and the voice services are loaded, followed by **What this practises** and the
**Safety summary**.

The launch bar stays pinned to the bottom of the window. It says whether the
conversation can start (**Ready to start**, or how many items need attention),
sums up your setup (for example *Standard · English · Text · Voice off*), and
carries **Start conversation**. If no model is loaded, the brief shows **Cannot
start yet** with an **Open the Model Manager** button. **Back** returns to the
screen you came from.

---

## 5. Play through a conversation

The conversation screen shows, from the top:

- The scenario's title, with **End session** beside it. Under the title, plain
  wording says what the session is doing (for example *Your turn*); technical
  wording shows the session id and state instead.
- The character's panel, with their name and, when it is not neutral, their
  **Mood**. Beside it, a card with the scenario's title and summary.
- **Conversation meters**, when the brief left them on and the scenario has
  any: one bar per meter on a scale of 0 to 100, each marked with how far the
  last turn moved it, for example *▲ +5 this turn*. The panel notes that the
  meters are not moods.
- The transcript. The character's first line is labelled **Opening**, because
  it comes before the first exchange. After that each exchange is labelled
  **Turn N**: one turn is your message plus the reply to it, so both carry the
  same number. The brief's turn limit and the debrief count turns the same way.
- A box for your reply, with a **Submit** button.

Type your reply and press **Enter**, or click **Submit**. While the character
answers:

- A panel under the transcript says what the turn is doing, in the character's
  name: getting ready, then thinking while the engine reads the conversation
  (the bar shows how much it has read), then replying. A clock runs throughout.
  When the reply is more than about four seconds away and the app has measured
  this machine's speed, the panel adds **Reply starts in about** and a range.
  After five seconds it adds **Once this reply arrives, you can shorten the
  next ones under Reply speed, in Settings.** The demo also says **Closing other
  apps usually helps.** See
  [performance.md](performance.md#how-long-a-turn-will-take) for every line the
  panel can show.
- The reply arrives in the transcript a sentence at a time. Each sentence is
  checked before it is shown, so nothing on screen is taken back. Without a live
  connection to the engine, the reply appears whole when the turn is done.
- Once the whole line is on screen, the app finishes the turn and shows
  **Updating the scene…**. The reply box already works again: a message you
  submit now waits above it as **Queued — sends as soon as this turn is
  saved**, with a **Remove** button, and goes as soon as the turn is saved. Only
  one message waits; a second one replaces it.

How long a reply takes depends on your hardware and model. On a machine without
a GPU a turn can take minutes, and the app waits for it rather than failing it.

The conversation ends on its own when the scenario reaches an ending, such as
its goal being met or lost, or the turn limit. You can also click **End
session** between turns; the button is unavailable from the moment you send a
message until the scene has updated. Either way the screen says **Session
ended.** with the outcome, and offers **Generate debrief** and **Back to
library** (**Back to home** in the demo).

### Leaving and coming back

You do not have to finish a conversation in one sitting. While a conversation
is unfinished, a **Conversation in progress** strip appears under the header on
every screen except the conversation itself and a debrief. It names the
scenario and how many turns you have played, and has **Resume**, which takes you
straight back, and **End it**, which ends the conversation and opens its
debrief. Home lists **Resume your conversation** first among its links (not in
the demo), and **Settings → Your sessions** has a **Resume** button for every
unfinished conversation, not only the most recent one.

Leave between turns rather than during one. A conversation resumed while a
reply is still being written comes back without your pending message.

### If replies feel slow

Open **Settings → Reply speed** and choose **Quick replies** (shortest answers,
least waiting). **Balanced**, the default, keeps the scenario's own pacing, and
**Fuller replies** gives longer answers. The change takes effect on your next
message, with nothing to restart. Outside the demo, the section also says that
a smaller model is the biggest change you can make, with **Choose a model →**.
See [troubleshooting](troubleshooting.md#low-vram-or-slow-inference) if that is
not enough.

---

## 6. Review the debrief

Click **Generate debrief**. While it is written the screen says **Generating
debrief…**, then the **Session Debrief** shows:

- The scenario, the number of turns, an overall score where the scenario's
  rubric gives one, and the outcome.
- **Summary**.
- **Scorecard**: a score out of 100 for each rubric dimension, where the
  scenario defines them.
- **Telemetry**: talk ratio, words per turn and questions asked, and
  **Conversation meters across turns**, a small line for each meter with its
  final value.
- **Strengths**, **Areas for improvement**, **Missed opportunities**, **Key
  moments** (each can jump to its turn in the transcript) and **Try next
  time**, where the debrief has them.
- The **Transcript**, numbered as on the conversation screen: **Opening**, then
  **Turn N**, with the character's mood under each reply.

If the debrief came from a template rather than the model, a notice at the top
says so.

Under the debrief, **Replay variation** takes you back to the brief to change
the difficulty or the seed, **Replay same setup** starts a new session with the
same settings, **Export session JSON** and **Export transcript (Markdown)**
download the session, and **Try another scenario** returns to the library, as
does **← Back to library** at the top of the screen. A **Next up** list may
suggest what to play next. In the demo both return to Home, the button at the
top reads **← Back to conversations**, and a **Get the full game** card sits
above the buttons.

Exported files go to your download folder. The transcript itself is kept in the
session database in the app's data folder (see
[Data locations](install.md#data-locations)) and is never uploaded anywhere. If
you clear **Save transcript locally** in the brief, the transcript is not shown
on the debrief and cannot be exported or searched afterwards; the debrief says
that turn details are not available.

---

## What to try next

- **Replay with different settings.** **Replay variation** on the debrief
  reopens the brief, where you can pick another difficulty or a variation seed.
- **Create a custom scenario.** See the
  [scenario authoring guide](scenario-authoring.md).
- **Tune reply speed.** If replies feel slow, **Settings → Reply speed** is the
  quickest fix and needs no restart.
- **Upgrade your model** (not in the demo). If replies feel generic, try a
  larger model; if they feel slow, a smaller one helps most. See [local-models.md](local-models.md).

---

## Next steps

- [Local models](local-models.md): choose the right model for your hardware
- [Troubleshooting](troubleshooting.md): if something does not work
- [README](../README.md): project overview
