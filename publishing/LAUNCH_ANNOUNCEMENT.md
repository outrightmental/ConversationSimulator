<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Launch Announcement — Conversation Simulator (Free Steam Edition)

> **Purpose:** Canonical draft of the public launch announcement for the free
> Steam edition of Conversation Simulator. Post this text as a Steam Community
> Hub announcement immediately after Step 5 (end-to-end install verification)
> in [`publishing/LAUNCH_DAY_RUNBOOK.md`](LAUNCH_DAY_RUNBOOK.md). Mirror it
> verbatim on any external channels (mailing list, social media) that were
> queued during the T−24 checklist.
>
> **Audience:** Platform team, Outright Mental staff. Outright Mental must
> approve the final text before it is published.
>
> **Review checklist before publishing:**
> - [ ] No therapy/diagnosis/legal-advice language (gate G4-04).
> - [ ] No implied paid marketplace or paid content (gate G4-04, SP-05).
> - [ ] Local-first privacy claims are factually accurate (PR-01–PR-03).
> - [ ] All named platforms have passed the Stage 4 gate check.
> - [ ] Model download links and pack names match the shipped build.
> - [ ] Outright Mental has approved this exact text.

---

## Steam Community Hub post

**Subject:** Conversation Simulator is live on Steam — free, local, yours

---

**Conversation Simulator is now available free on Steam.**

We built it to help you practice the conversations that matter — job interviews,
difficult talks, negotiations, language practice — in private, before they
happen for real. Today it ships to anyone who wants it.

---

### Free, and free forever

There is no base price, no subscription, and no hidden unlock. Conversation
Simulator is sponsored by [Outright Mental](https://outrightmental.com) so it
can reach players who would not otherwise have access to AI-assisted practice.

---

### Your conversations stay on your machine

Conversation Simulator is **local-first**. The AI characters run entirely on
your computer using open-source model weights that you download once and own.
Nothing you say, type, or practise is sent to any server during play.

That means:

- No account required to start a session.
- No conversation logs on our end — there are none to subpoena, leak, or sell.
- No internet required once your model is downloaded. Fly, commute, practise
  anywhere.
- Your data directory is yours: `~/.local/share/convsim/` on Linux/Steam Deck,
  `~/Library/Application Support/convsim/` on macOS, or
  `%APPDATA%\convsim\` on Windows. Move it, back it up,
  or delete it from **Settings → Privacy → Clear all data**.

---

### Supported platforms

| Platform | Status |
|----------|--------|
| Windows 10 / 11 (x86-64) | Fully supported |
| macOS 13 Ventura or later (Apple Silicon and Intel) | Fully supported |
| Linux x86-64 (Ubuntu 22.04+, Fedora 38+, Arch-based) | Fully supported |
| Steam Deck / SteamOS (Gaming Mode and Desktop Mode) | Verified — text and keyboard; voice requires an external USB or Bluetooth microphone |

---

### Getting a model

Conversation Simulator does not bundle model weights in the installer — model
files are large and each carries its own licence terms that you should see
before the bytes land on your machine. Here is how to get one:

1. Launch the app. The **Model Manager** opens on first run.
2. Choose a model from the built-in registry. We recommend starting with
   **Qwen3 4B Instruct Q4\_K\_M** (~2.5 GB) — it is the lightest model in the
   registry and the only practical choice for CPU-only machines. Larger models
   (Qwen3 8B and up) are available if your hardware has the RAM/VRAM headroom
   for them.
3. Review the model name, licence, download size, SHA-256 checksum, and
   destination path shown in the Model Manager.
4. Confirm the download. The app verifies the checksum automatically and
   will not load a model that does not match.
5. Done — select a scenario and start practising.

You can also use a model you have already downloaded via [ollama](https://ollama.com)
by pointing the runtime adapter to `http://localhost:11434`. See
[**docs/local-models.md**](../docs/local-models.md) for details.

---

### Official scenario packs

Five official packs ship with this release, covering common high-stakes
conversation types:

| Pack | What you practise |
|------|-------------------|
| **Job Interview Basics** | Answering common interview questions, handling follow-ups, reading the room |
| **Everyday Negotiation** | Salary discussions, pricing conversations, finding common ground |
| **Language Café** | Casual conversation in a second language (English focus in v1) |
| **Difficult Conversations** | Disagreements, feedback delivery, setting limits with someone you know |
| **Dating: Confidence and Limits** | Meeting new people, expressing interest, maintaining personal limits |

Each pack contains four or more fully playable scenarios with a scored debrief
at the end so you can see what went well and what you might try differently.

---

### Create your own scenarios

Conversation Simulator is open-source and designed for creators. Scenario packs
are plain YAML — no programming required.

The **Creator Workbench** (bundled in the app) lets you:

- Write and edit scenarios in a live preview editor.
- Validate your pack against the schema before sharing it.
- Export a finished pack as a zip for distribution.

For the full authoring guide, see
[**docs/scenario-authoring.md**](../docs/scenario-authoring.md). Community
packs can be shared on GitHub, itch.io, or directly — there is no approval
gate or fee. See the contribution guide for how to submit a pack for
consideration as a future official release.

---

### Report an issue

Found a bug? Use the GitHub issue templates linked from the in-app **Help →
Report a bug** menu, or visit the
[GitHub Issues page](https://github.com/outrightmental/ConversationSimulator/issues)
directly.

**Privacy reminder:** Please do not paste conversation transcripts or session
audio in a public issue. If you need to share context about a session to
reproduce a bug, use a made-up example or describe the content in general terms.

---

### What's next

The v1 launch is a starting point. The backlog includes:

- In-app community pack browser
- Additional official packs (more languages, more conversation types)
- Voice quality improvements

Follow the
[GitHub repository](https://github.com/outrightmental/ConversationSimulator)
and this Steam page to get notified of updates.

Thank you for playing.

— The Conversation Simulator team at Outright Mental

---

## External announcement (mailing list / social media)

Use this shorter version for channels with character or length limits. Trim
further as needed.

---

Conversation Simulator is now free on Steam.

Practice job interviews, negotiations, difficult talks, and language learning
with AI characters that run entirely on your machine. No account. No
subscription. No data sent anywhere. Local-first, always.

Five official scenario packs ship today. Create your own with the built-in
Creator Workbench — it's YAML, no coding needed.

Available on Windows, macOS, Linux, and Steam Deck.

[link to Steam store page]

---

## Sign-off

| Role | Name | Approved | Date |
|------|------|---------|------|
| Outright Mental (final authority) | | ☐ | |
| Platform lead | | ☐ | |
| Support communications owner | | ☐ | |

All three approvals must be recorded before this announcement is published.
