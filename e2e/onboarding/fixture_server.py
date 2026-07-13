# SPDX-License-Identifier: Apache-2.0
"""Local HTTP fixture server for offline onboarding e2e tests.

Serves a small deterministic model file at a localhost URL so no test depends
on Hugging Face or GitHub availability.  The SHA-256 is pre-computed from the
fixture bytes and can be injected directly into a model_registry row.

Usage (from conftest.py):

    from .fixture_server import start_fixture_server, FIXTURE_MODEL_SHA256

    srv = start_fixture_server()
    # srv.model_url  →  "http://127.0.0.1:<port>/models/fixture-model.gguf"
    # srv.sha256     →  FIXTURE_MODEL_SHA256
    srv.stop()
"""
from __future__ import annotations

import hashlib
import http.server
import threading
from dataclasses import dataclass

# 64 KB of null bytes — large enough to exercise the download-progress path,
# small enough to complete instantly in CI.
FIXTURE_MODEL_BYTES: bytes = b"\x00" * 65536
FIXTURE_MODEL_SHA256: str = hashlib.sha256(FIXTURE_MODEL_BYTES).hexdigest()
FIXTURE_MODEL_SIZE: int = len(FIXTURE_MODEL_BYTES)
FIXTURE_MODEL_SIZE_GB: float = FIXTURE_MODEL_SIZE / (1024 ** 3)

_MODEL_PATH = "/models/fixture-model.gguf"
_BAD_SHA256 = "a" * 64  # a known-wrong checksum for checksum-mismatch tests


class _FixtureHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silence request log in test output
        pass

    def do_GET(self) -> None:
        if self.path == _MODEL_PATH:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(FIXTURE_MODEL_SIZE))
            self.end_headers()
            self.wfile.write(FIXTURE_MODEL_BYTES)
        elif self.path == "/models/bad-checksum.gguf":
            # Serves valid bytes but the registry entry references a wrong SHA-256
            # so the verify stage will fail checksum-mismatch.
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(FIXTURE_MODEL_SIZE))
            self.end_headers()
            self.wfile.write(FIXTURE_MODEL_BYTES)
        else:
            self.send_response(404)
            self.end_headers()


@dataclass
class FixtureServer:
    host: str
    port: int
    _thread: threading.Thread
    _server: http.server.HTTPServer

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def model_url(self) -> str:
        return f"{self.base_url}{_MODEL_PATH}"

    @property
    def bad_checksum_url(self) -> str:
        return f"{self.base_url}/models/bad-checksum.gguf"

    @property
    def sha256(self) -> str:
        return FIXTURE_MODEL_SHA256

    @property
    def bad_sha256(self) -> str:
        return _BAD_SHA256

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)


def start_fixture_server(host: str = "127.0.0.1", port: int = 0) -> FixtureServer:
    """Start a fixture HTTP server and return its address info.

    Passing port=0 lets the OS assign a free port so tests never collide.
    """
    server = http.server.HTTPServer((host, port), _FixtureHandler)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return FixtureServer(host=host, port=actual_port, _thread=thread, _server=server)
