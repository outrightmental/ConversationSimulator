# SPDX-License-Identifier: Apache-2.0
"""Fake llama-server builds for the graphics-card fallback tests (issue #531).

A fake build is a Python script written next to a JSON file that says how it
behaves: what ``--list-devices`` prints and exits with, whether the server
starts, what the check request (``POST /completion``) answers, and whether
the engine dies on its first chat request. Each run appends one line to
``calls.log`` beside the script (``list-devices`` or ``serve <argv>``) so a
test can see what was started and how.

The scripts are launched with the interpreter running the tests: the
:func:`run_python_scripts` fixture rewrites ``[script.py, *args]`` into
``[sys.executable, script.py, *args]`` at ``asyncio.create_subprocess_exec``,
which is the only place the app spawns the engine. Everything else — the
probe, the health poll, the check request, the fallback — runs as it does
against a real engine, on every platform including Windows.
"""
from __future__ import annotations

import asyncio
import json
import socket
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pytest

_SCRIPT = textwrap.dedent('''\
    import http.server, json, os, sys, time
    HERE = os.path.dirname(os.path.abspath(__file__))
    CFG = json.load(open(os.path.join(HERE, os.path.basename(__file__) + ".json")))

    def log(line):
        with open(os.path.join(HERE, "calls.log"), "a") as fh:
            fh.write(line + "\\n")

    args = sys.argv[1:]
    if "--list-devices" in args:
        log("list-devices")
        if CFG.get("list_hang"):
            time.sleep(600)
        sys.stdout.write(CFG.get("list_output", "Available devices:\\n"))
        sys.stdout.flush()
        sys.exit(CFG.get("list_rc", 0))

    log("serve " + json.dumps(args))
    if CFG.get("load") == "fail":
        print("llama_model_load: error loading model: vk::Device::createBuffer: ErrorOutOfDeviceMemory")
        sys.exit(1)
    port = int(args[args.index("--port") + 1])
    completion = CFG.get("completion", " 9, 10")

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self._json(200, {"status": "ok"})
            elif self.path == "/__launch":
                self._json(200, {"argv": args})
            else:
                self._json(404, {})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            if self.path == "/completion":
                if completion is None:
                    self._json(500, {"error": "vk::Queue::submit: ErrorDeviceLost"})
                else:
                    self._json(200, {"content": completion})
            elif self.path == "/v1/chat/completions":
                if CFG.get("chat") == "crash":
                    log("crash")
                    os._exit(3)
                body = ("data: " + json.dumps({"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]}) + "\\n\\n"
                        + "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}}) + "\\n\\n"
                        + "data: [DONE]\\n\\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json(404, {})

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a, **k):
            pass

    with http.server.HTTPServer(("127.0.0.1", port), H) as srv:
        srv.serve_forever()
''')

DISCRETE_AND_INTEGRATED = (
    "Available devices:\n"
    "  Vulkan0: NVIDIA GeForce RTX 4080 Laptop GPU (11995 MiB, 11227 MiB free)\n"
    "  Vulkan1: Intel(R) RaptorLake-S Mobile Graphics Controller (32629 MiB, 48107 MiB free)\n"
)
INTEGRATED_ONLY = "Available devices:\n  Vulkan0: AMD Custom GPU 0405 (RADV VANGOGH) (8192 MiB, 7800 MiB free)\n"
NO_DEVICES = "Available devices:\n"


@dataclass
class FakeBuild:
    """One fake llama-server build on disk."""

    directory: Path
    script: Path
    config: dict[str, Any] = field(default_factory=dict)

    def configure(self, **config: Any) -> None:
        self.config.update(config)
        self.script.with_name(self.script.name + ".json").write_text(json.dumps(self.config))

    def calls(self) -> list[str]:
        log = self.directory / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def probes(self) -> int:
        return sum(1 for c in self.calls() if c == "list-devices")

    def serves(self) -> list[list[str]]:
        return [json.loads(c[len("serve "):]) for c in self.calls() if c.startswith("serve ")]


def write_fake_build(directory: Path, **config: Any) -> FakeBuild:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "llama-server.py"
    script.write_text(_SCRIPT)
    build = FakeBuild(directory=directory, script=script)
    build.configure(**config)
    return build


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def run_python_scripts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Launch ``*.py`` "executables" with this interpreter (see the module doc)."""
    real = asyncio.create_subprocess_exec

    async def _exec(program: Any, *args: Any, **kwargs: Any) -> Any:
        if str(program).endswith(".py"):
            return await real(sys.executable, str(program), *args, **kwargs)
        return await real(program, *args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _exec)


def builds_for(cpu: Optional[FakeBuild], vulkan: Optional[FakeBuild]) -> Any:
    from convsim_core.runtime.engine_variant import EngineBuild, EngineBuilds

    return EngineBuilds(
        default=EngineBuild("cpu", str(cpu.script), "bundled") if cpu else None,
        vulkan=EngineBuild("vulkan", str(vulkan.script), "bundled") if vulkan else None,
    )
