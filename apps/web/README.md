<!-- SPDX-License-Identifier: Apache-2.0 -->
# apps/web

React/TypeScript browser UI for Conversation Simulator.

**Status:** Not yet implemented. Planned in Milestone 1 (text-only simulator)
and developed further through Milestone 5.

The web UI will include:
- Scenario library and setup screens
- Conversation screen with NPC panel, transcript, and mic controls
- Debrief screen with rubric scores and replay suggestions
- Creator workbench for editing and testing scenario packs
- Settings / model manager

Runs at `http://127.0.0.1:7354` in dev mode (served by Vite).
Connects to the convsim-core server at `http://127.0.0.1:7355`.
