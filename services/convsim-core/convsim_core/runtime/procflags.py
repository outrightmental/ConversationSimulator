# SPDX-License-Identifier: Apache-2.0
"""Platform subprocess helpers.

On Windows, console-subsystem children (llama-server.exe, whisper-cli.exe,
nvidia-smi, …) allocate a visible console window when spawned from a process
without one — the packaged app is a GUI app, so every sidecar launch flashed
a black console over the UI. CREATE_NO_WINDOW suppresses that. No-op on
other platforms.
"""
import subprocess
import sys

#: Pass as ``creationflags=`` to subprocess.run/Popen/create_subprocess_exec.
CREATE_NO_WINDOW: int = (
    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # type: ignore[attr-defined]
)
