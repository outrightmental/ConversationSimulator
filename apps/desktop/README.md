<!-- SPDX-License-Identifier: Apache-2.0 -->
# apps/desktop

Tauri desktop wrapper for Conversation Simulator.

**Status:** Not yet implemented. Planned after the web UI and core server
reach a stable state (Milestone 5+).

The desktop app will wrap the web UI in a native shell using Tauri, providing:
- Native OS tray and window management
- Automatic sidecar process lifecycle for convsim-core and runtimes
- Bundled installers for Windows and macOS

For now, use the web UI at `apps/web` and run services via `scripts/dev.sh`.
