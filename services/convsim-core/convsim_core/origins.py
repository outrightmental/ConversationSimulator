# SPDX-License-Identifier: Apache-2.0
"""The browser origins the local API trusts.

In a bundled build the UI loads from tauri://localhost (macOS/Linux) or
https://tauri.localhost (Windows) and calls the API cross-origin at
http://127.0.0.1:<port>, so the native webview enforces CORS and blocks the
responses unless the server opts in. In dev mode the Vite server on
127.0.0.1:7354 proxies /api and /ws, so requests arrive same-origin from the
server's point of view but carry the page's origin on WebSocket upgrades, which
CORS middleware does not cover (issue #538). Listing explicit local origins keeps
the local-first promise intact — the server still binds to 127.0.0.1 and no LAN
origin is granted access.
"""
from __future__ import annotations

#: Origins the packaged Tauri desktop shell serves its web UI from.
TAURI_WEBVIEW_ORIGINS: tuple[str, ...] = (
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
)

#: The Vite dev server (apps/web) and the same page addressed as localhost.
DEV_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:7354",
    "http://localhost:7354",
)

#: Every origin a WebSocket upgrade may carry. A request with no Origin header
#: at all is not a browser page and is allowed (local tooling, tests).
WEBSOCKET_ORIGINS: frozenset[str] = frozenset(TAURI_WEBVIEW_ORIGINS + DEV_ORIGINS)


def websocket_origin_allowed(origin: str | None) -> bool:
    """Whether a WebSocket upgrade carrying ``origin`` may be accepted."""
    if origin is None:
        return True
    return origin in WEBSOCKET_ORIGINS
