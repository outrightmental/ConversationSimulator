# SPDX-License-Identifier: Apache-2.0
"""CORS tests for the packaged Tauri desktop shell.

In a bundled build the web UI is served from tauri://localhost (macOS/Linux) or
https://tauri.localhost (Windows) and calls the API cross-origin at
http://127.0.0.1:<port>. The native webview enforces CORS, so the server must
echo Access-Control-Allow-Origin for the webview origins or every API call from
the packaged app fails. These tests lock that behaviour in and confirm arbitrary
web origins are still rejected (local-first promise).
"""
import pytest

TAURI_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
]


@pytest.mark.parametrize("origin", TAURI_ORIGINS)
def test_simple_request_allows_tauri_origin(client, origin):
    resp = client.get("/api/health", headers={"Origin": origin})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize("origin", TAURI_ORIGINS)
def test_preflight_allows_tauri_origin(client, origin):
    resp = client.options(
        "/api/scenarios",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == origin


def test_disallowed_web_origin_is_not_echoed(client):
    resp = client.get(
        "/api/health",
        headers={"Origin": "https://evil.example.com"},
    )
    # The request itself still succeeds (CORS is enforced by the browser, not the
    # server), but the server must not grant the arbitrary origin access.
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"
