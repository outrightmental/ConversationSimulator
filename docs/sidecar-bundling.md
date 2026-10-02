<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Sidecar bundling: Steam vs developer builds

ConversationSimulator runs four managed subprocess sidecars alongside the core
Python service. This document explains how each sidecar locates its executable
in developer builds and in packaged Steam builds.

| Sidecar | Service name | Default port | Runtime id |
|---------|-------------|-------------|------------|
| llama.cpp | `convsim-llm` | 7356 | `llama_cpp` |
| Whisper.cpp (STT) | `convsim-stt` | 7357 | `whisper_cpp` |
| Kokoro / sherpa-onnx (TTS) | `convsim-tts` | 7358 | `kokoro` |
| Silero VAD | _(in-process)_ | — | `silero_vad` |

All sidecars must bind only to `127.0.0.1` (IPv4 loopback) or `::1` (IPv6
loopback). The `assert_localhost()` guard in
`convsim_core/runtime/supervisor.py` enforces this at every `start()` call.
See [network-security.md](network-security.md) for the localhost-only policy.

---

## Executable resolution order

Each sidecar resolves its binary in this order, stopping at the first hit:

1. **Explicit override** — the environment variable `CONVSIM_<SIDECAR>_EXECUTABLE`
   (e.g. `CONVSIM_LLAMA_CPP_EXECUTABLE`), or the `executable` field in the
   `POST /api/sidecar/start` request body.
2. **Bundled path** — a platform-specific directory adjacent to the application
   binary (Steam builds only; see below).
3. **PATH lookup** — `shutil.which("llama-server")` or the equivalent name for
   each sidecar (developer builds only).

If none of the above resolves, `start()` raises `RuntimeError` with an
actionable message directing the user to install the missing binary.

---

## Developer builds

In a developer build the application is started directly from the repository
(`uvicorn convsim_core.app:app` or `python -m convsim_core`). Sidecar
binaries are expected to be on the developer's `PATH`.

**Install sidecars for development (Linux / macOS):**

```sh
# llama.cpp (llama-server)
./runtimes/llama_cpp/download-runtime.sh
# → binary at ~/.convsim/bin/llama-server; add to PATH

# Whisper.cpp
./runtimes/whisper_cpp/download-runtime.sh
# → binary at ~/.convsim/bin/whisper-cli; add to PATH

# Kokoro / sherpa-onnx
./runtimes/kokoro/download-runtime.sh
# → binary at ~/.convsim/bin/sherpa-onnx-offline-tts; add to PATH
```

**Install sidecars for development (Windows):**

```powershell
# llama.cpp (llama-server) — CPU variant (default, works on every machine)
.\runtimes\llama_cpp\download-runtime.ps1
# → binary at $HOME\.convsim\bin\llama-server.exe

# GPU-accelerated variant (optional, never required for first-run):
.\runtimes\llama_cpp\download-runtime.ps1 -Variant vulkan # NVIDIA / AMD / Intel via Vulkan

# Add to PATH (current session):
$env:PATH = "$HOME\.convsim\bin;$env:PATH"
```

The `find_executable()` function also probes `~/.convsim/bin/llama-server.exe`
directly (step 3 in the resolution order), so the binary is found immediately
after an in-app install via `POST /api/sidecar/download-runtime` without
needing a PATH change or app restart.

You can also set the explicit override variable to point to any binary:

```sh
# Linux / macOS
export CONVSIM_LLAMA_CPP_EXECUTABLE=/path/to/llama-server
```

```powershell
# Windows
$env:CONVSIM_LLAMA_CPP_EXECUTABLE = "C:\path\to\llama-server.exe"
```

---

## Steam (packaged) builds

In a Steam build the application executable and all sidecars are bundled inside
the Steam depot under a known relative layout. The Tauri/Electron wrapper
sets the environment variable `CONVSIM_BUNDLED_RUNTIME_DIR` to the absolute
path of the `runtimes/` directory inside the installed depot before launching
`convsim-core`.

### Bundled directory layout

```
<steam-install-dir>/
├── convsim               # main application executable (Tauri shell)
└── runtimes/
    ├── llama-server      # llama.cpp inference server
    ├── whisper-cli       # Whisper.cpp transcription binary
    └── sherpa-onnx-offline-tts   # Kokoro TTS binary
```

On Windows the binaries include the `.exe` suffix. On macOS and Linux there is
no suffix. The bundled path resolver appends the correct suffix for the current
platform automatically.

### Bundled path lookup (Python pseudocode)

```python
import os
import sys
from pathlib import Path

def find_sidecar_executable(env_key: str, binary_name: str) -> str | None:
    """Resolve a sidecar binary using the Steam bundling convention.

    ``env_key`` is the override variable keyed on the sidecar id, e.g.
    ``CONVSIM_LLAMA_CPP_EXECUTABLE`` for the ``llama_cpp`` sidecar.
    ``binary_name`` is the on-disk filename, e.g. ``llama-server``.
    """
    # 1. Explicit env-var override always wins.
    if override := os.environ.get(env_key):
        return override

    # 2. Bundled path (Steam builds).
    bundled_dir = os.environ.get("CONVSIM_BUNDLED_RUNTIME_DIR")
    if bundled_dir:
        suffix = ".exe" if sys.platform == "win32" else ""
        candidate = Path(bundled_dir) / f"{binary_name}{suffix}"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    # 3. PATH (developer builds).
    import shutil
    return shutil.which(binary_name)
```

The actual implementation lives in each sidecar's module
(`find_executable()` in `convsim_core/runtime/sidecar.py` for llama.cpp, which
resolves `CONVSIM_LLAMA_CPP_EXECUTABLE` → `CONVSIM_BUNDLED_RUNTIME_DIR/llama-server`
→ PATH).

---

## Pinned llama.cpp version and the macOS deployment-target gate

The llama.cpp download scripts pin an exact upstream release
(`LLAMA_CPP_PINNED_VERSION` in `runtimes/llama_cpp/download-runtime.sh` and
`download-runtime.ps1`; keep the two in sync). Bumping the pin is a deliberate
act, and on macOS it must clear one extra bar: **no bundled Mach-O binary may
declare a minimum macOS newer than our supported floor** (14.0 by default,
override with `CONVSIM_MACOS_MINOS_FLOOR`).

Why: upstream llama.cpp prebuilts started targeting the newest macOS SDK
(b9428+ declare macOS 26). Such a binary installs fine, but dyld kills it the
instant it launches on any older macOS — in the Steam depot this surfaced as
"Model loaded but could not start" with a misleading insufficient-RAM hint
(issue #469). The breakage is statically visible in the Mach-O
`LC_BUILD_VERSION` load command, so it is caught before shipping:

- `scripts/check-macho-minos.py` parses the declared minimum-OS version of
  Mach-O files (thin and universal; no dependencies; runs on any OS). Try
  `--self-test`, or point it at a directory:
  `python3 scripts/check-macho-minos.py --max 14.0 ~/.convsim/bin`.
- `download-runtime.sh` runs the checker on Darwin after extracting and
  refuses to install binaries that exceed the floor
  (`CONVSIM_SKIP_MINOS_CHECK=1` bypasses it in an emergency).
- The `llama-minos-gate` job in `.github/workflows/binary-health-check.yml`
  verifies both macOS assets (arm64 and x64) of the pinned version on every
  change under `runtimes/llama_cpp/**`. The release workflow bundles via
  `download-runtime.sh`, so it inherits the same gate.

The floor is 14.0 because upstream prebuilts have targeted macOS 14 for a
long stretch of releases (b9428+ jumped straight to 26.0). The Steam QA
matrix ([QA_STEAM_PLATFORM_MATRIX.md](QA_STEAM_PLATFORM_MATRIX.md)) was
amended to match (issue #472): macOS 14 Sonoma is the oldest supported
release. Re-adding macOS 13 would require building llama.cpp from source
with `MACOSX_DEPLOYMENT_TARGET=13`.

---

## Localhost enforcement in packaged builds

`assert_localhost(host)` in `convsim_core/runtime/supervisor.py` is called at
the top of every sidecar `start()` method. It raises `RuntimeError` if the
requested bind host is not `127.0.0.1`, `::1`, or `localhost`. This check
cannot be disabled at runtime — there is no environment variable or config
flag to bypass it. Network binding is always localhost-only.

---

## Shutting the whole tree down {#shutdown}

Quitting the app has to take every one of these processes with it. Nothing in
the tree is a direct child of the desktop shell:

```
convsim-desktop (Tauri shell)
└── convsim-core(.exe)            ← PyInstaller one-file BOOTLOADER; the only
    │                               process the shell holds a handle on
    └── convsim-core(.exe)        ← the real Python server; owns port 7355
        ├── llama-server
        └── sherpa-onnx-offline-tts (Kokoro)
```

Terminating the handle the shell holds kills the bootloader only. `SIGKILL` and
`TerminateProcess` cannot be forwarded, so the server survives — still holding
port 7355 — and its sidecars with it. On Windows that left `convsim-core.exe`
in the task list after the window closed and kept Steam reporting the game as
running (issue #485).

Teardown is therefore two steps, in `apps/desktop/src-tauri/src/core_process.rs`:

1. **Ask.** The shell spawns the engine with a pipe on stdin and holds the write
   end for its own lifetime. Closing it is the shutdown request:
   `convsim_core/parent_watch.py` reads EOF and asks uvicorn for a *graceful*
   stop, so the FastAPI lifespan teardown runs and `ProcessSupervisor.stop_all()`
   stops every registered sidecar. A pipe rather than a signal or a PID poll,
   because the kernel closes it when the shell exits for **any** reason —
   including a crash or being killed by Steam — and because PIDs get recycled.
2. **Insist.** If the tree is still up 10 seconds later, kill all of it: one
   `killpg` on Unix (the engine is spawned as its own process-group leader),
   `taskkill /T /F` on Windows.

A sidecar that honours the `SidecarProcess` contract needs nothing extra: step 1
reaches it through `stop_all()`, and step 2 reaches it because it is inside the
engine's process group / process tree. A sidecar that daemonises itself out of
both would not be stopped by either — don't.

Both steps are covered by `cargo test` in `apps/desktop/src-tauri`, which spawns
a stand-in engine with a stand-in sidecar grandchild and asserts that neither
process survives teardown. Step 2 is platform-specific, so the tests are too:
CI runs them on Linux (`killpg`) in the desktop job and on Windows (`taskkill
/T`) in the Windows job. The Python half — EOF on stdin reaching uvicorn — is
covered by `services/convsim-core/tests/test_parent_watch.py`.

---

## Adding a new sidecar

When implementing a new sidecar (e.g. `WhisperCppSidecar`):

1. Inherit from `SidecarProcess` in `convsim_core/runtime/supervisor.py`.
2. Implement `sidecar_id`, `display_name`, `stop()`, and `get_status()`.
3. Add a typed `start()` method that calls `assert_localhost(host)` before
   spawning the child process.
4. Implement executable resolution using the three-step order described above:
   `CONVSIM_<SIDECAR_ID>_EXECUTABLE` override → the bundled binary under
   `CONVSIM_BUNDLED_RUNTIME_DIR` → PATH.
5. Register the sidecar with `ProcessSupervisor` in `app.py`'s `lifespan`.
6. Add tests covering: missing binary, port conflict, crash, restart, and
   graceful shutdown. See `tests/test_sidecar.py` for the llama.cpp reference
   implementation.
7. Keep the child inside the engine's process tree — see
   [Shutting the whole tree down](#shutdown).

---

## The core itself is a sidecar of the desktop shell

Everything above is about sidecars that `convsim-core` manages. One level up,
`convsim-core` is itself a managed child of the Tauri desktop shell, built by
`scripts/build-core.sh` into a single PyInstaller executable at
`apps/desktop/src-tauri/resources/bin/convsim-core[.exe]` and packaged into the
installer by `bundle.resources` (`resources/**/*`) — which is what lets a player
install one artifact and reach the Welcome screen with no terminal involved
(issue #456).

The shell resolves it in the same four-step order the Python resolver uses:
`CONVSIM_CORE_EXECUTABLE`, then `CONVSIM_BUNDLED_RUNTIME_DIR`, then the Tauri
resource directory, then PATH. It hands the engine `CONVSIM_HOST`,
`CONVSIM_PORT`, `CONVSIM_DATA_ROOT`, `CONVSIM_APP_VERSION`, the edition, and
`CONVSIM_BUNDLED_RUNTIME_DIR` — the last of which is how the sidecars above are
found in a packaged build.

Two parts of that lifecycle matter to the sidecars in this document:

- **Readiness** is `GET /api/health`, not an open TCP port. An open port only
  says *something* is on 7355; the health body is what proves it is a
  convsim-core — and therefore that the sidecar supervisor this document
  describes exists at all.
- **Shutdown** is a request the engine can honour, not a hard kill — see
  [Shutting the whole tree down](#shutdown) above. Only a graceful stop lets
  uvicorn run the lifespan shutdown, and the lifespan shutdown is where
  `ProcessSupervisor.stop_all()` stops every sidecar in the table above. A hard
  kill of the engine orphans all of them — llama-server keeps a model resident
  in RAM and keeps port 7356 — so the shell waits out `GRACE` before
  insisting.

A crash is the same event without the choice: an engine that died never reached
its lifespan shutdown either, so every sidecar in the table above survives it.
The desktop shell restarts the engine (see "Crash restart" in
[apps/desktop/README.md](../apps/desktop/README.md)), and the replacement's
`ensure_llama_sidecar_running` then fails `_is_port_in_use` against the orphan
still holding 7356. Inference usually keeps working anyway — `LlamaCppRuntime`
reaches llama-server over HTTP at its configured `base_url` and does not care
which process started it, so `runtime.health()` and `/v1/chat/completions` both
land on the orphan — but the engine no longer *owns* that process:
`sidecar_diagnostics` reports `port_conflict`, and anything that has to restart
it (`/api/models/use`, a model switch) fails until the orphan is gone.

Nothing in the product removes it. Relaunching does not: `stop_all()` stops the
sidecars a *registered* sidecar object holds a `self._process` for, and the
replacement engine's llama-server sidecar never started one. Neither does the
shell's teardown: it reaches the *replacement* engine's process group (Unix) or
process tree (Windows), and the orphan is in neither — it belongs to the group
of the engine that died, whose pid is also its parent. It has to be ended by
hand.

`scripts/packaged-core-smoke.sh` runs the packaged engine and asserts all of
it against the real PyInstaller binary: health readiness, loopback-only binding,
and both teardown paths — stdin EOF and the SIGTERM fallback — reaching the
lifespan shutdown. See [apps/desktop/README.md](../apps/desktop/README.md), "Core sidecar
lifecycle", for the full state machine.

---

## Environment variable reference

| Variable | Purpose |
|---|---|
| `CONVSIM_BUNDLED_RUNTIME_DIR` | Absolute path to the bundled `runtimes/` directory (set by the Tauri/Electron wrapper in Steam builds) |
| `CONVSIM_LLAMA_CPP_EXECUTABLE` | Override path to `llama-server` |
| `CONVSIM_WHISPER_CPP_BINARY_PATH` | Override path to `whisper-cli` |
| `CONVSIM_KOKORO_EXECUTABLE` | Override path to `sherpa-onnx-offline-tts` |
| `CONVSIM_SHUTDOWN_ON_STDIN_EOF` | Set to `1` by a launcher that holds a pipe on the engine's stdin; EOF on it means "shut down" (see [Shutting the whole tree down](#shutdown)) |

---

## Related documents

- [network-security.md](network-security.md) — localhost-only binding policy
- [runtime-adapters.md](runtime-adapters.md) — ChatRuntime interface and built-in adapters
- [architecture.md](architecture.md) — service topology and port assignments
- [runtimes/llama_cpp/README.md](../runtimes/llama_cpp/README.md) — llama.cpp setup
- [apps/desktop/README.md](../apps/desktop/README.md) — the desktop shell's core sidecar lifecycle
