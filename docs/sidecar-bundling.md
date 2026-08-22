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

Note the floor is currently 14.0 because upstream prebuilts have targeted
macOS 14 for a long stretch of releases, while the Steam QA matrix
([QA_STEAM_PLATFORM_MATRIX.md](QA_STEAM_PLATFORM_MATRIX.md)) lists macOS 13
as the oldest supported release — closing that gap needs a source build with
`MACOSX_DEPLOYMENT_TARGET=13` (or a matrix amendment) and is tracked
separately.

---

## Localhost enforcement in packaged builds

`assert_localhost(host)` in `convsim_core/runtime/supervisor.py` is called at
the top of every sidecar `start()` method. It raises `RuntimeError` if the
requested bind host is not `127.0.0.1`, `::1`, or `localhost`. This check
cannot be disabled at runtime — there is no environment variable or config
flag to bypass it. Network binding is always localhost-only.

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

---

## Environment variable reference

| Variable | Purpose |
|---|---|
| `CONVSIM_BUNDLED_RUNTIME_DIR` | Absolute path to the bundled `runtimes/` directory (set by the Tauri/Electron wrapper in Steam builds) |
| `CONVSIM_LLAMA_CPP_EXECUTABLE` | Override path to `llama-server` |
| `CONVSIM_WHISPER_CPP_BINARY_PATH` | Override path to `whisper-cli` |
| `CONVSIM_KOKORO_EXECUTABLE` | Override path to `sherpa-onnx-offline-tts` |

---

## Related documents

- [network-security.md](network-security.md) — localhost-only binding policy
- [runtime-adapters.md](runtime-adapters.md) — ChatRuntime interface and built-in adapters
- [architecture.md](architecture.md) — service topology and port assignments
- [runtimes/llama_cpp/README.md](../runtimes/llama_cpp/README.md) — llama.cpp setup
