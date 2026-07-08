<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Troubleshooting

> **Status:** Placeholder. Will be expanded as services are implemented.

## Setup issues

**`./scripts/setup.sh` fails with "Python 3.10+ is required"**

Install Python 3.10 or newer from <https://www.python.org/downloads/>.
On macOS, `brew install python@3.11` works. On Ubuntu: `sudo apt install python3.11`.

**`./scripts/setup.sh` fails with "Node.js 18+ is required"**

Install Node.js 18 LTS or newer from <https://nodejs.org/>.

## Dev server issues

> Services are not yet implemented. This section will be expanded in Milestone 1.

## Developer debug drawer

The conversation screen includes a collapsible debug drawer that shows raw model output, applied state deltas, event flags, and hidden NPC agenda fields. It is intended for developers diagnosing model drift or unexpected scenario behaviour and is **never shown to normal players**.

**How to enable:**

- **Build-time flag:** set `VITE_DEV_TOOLS=true` in your `.env.local` before running `pnpm dev`. The drawer will appear for all sessions in that build.
- **Per-device toggle:** open **Settings → Advanced → Developer debug mode**. The change takes effect after reloading the conversation screen.

**What the drawer shows per turn:**

- Raw model JSON payload (the full `npc_opening` / `npc_turn` event payload as returned by the backend).
- Applied state delta for that turn (the numeric changes actually committed to tracked NPC state variables).
- Rejected state delta (a red `⊘ rejected` badge and section) when the model requests changes to variables the simulator does not track — these are dropped, never applied. This is a common model-drift signal.
- An amber `agenda` badge and highlighted field list when the payload contains hidden NPC fields (`agenda`, `hidden_state`, `prompt_metadata`, etc.).

**Copy to clipboard:** each entry has a copy button. Raw audio fields (`audio`, `audio_data`, `tts_audio`, `raw_audio`) and `secret` fields are redacted before writing to the clipboard. A persistent warning label marks this redaction.

**Security note:** the drawer is not mounted in the DOM in normal mode — hidden NPC fields cannot be accessed through browser developer tools when the setting is off. Disable developer debug mode before sharing your screen or recording sessions.

## Where to get help

- Open a [GitHub Issue](https://github.com/outrightmental/ConversationSimulator/issues)
  for bugs or missing documentation.
- See [install.md](install.md) for installation steps.
- See [quickstart.md](quickstart.md) for first-run instructions.
