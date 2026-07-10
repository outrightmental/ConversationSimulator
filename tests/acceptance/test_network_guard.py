# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — Local-only network guard (issue #218).

Verifies that every player-facing path (gameplay, STT, TTS, debrief,
transcript export, pack import) completes without making outbound network
calls while a local-only guard is active.

All session states are exercised using fake workers so the suite runs in any
CI environment without model downloads:

  G-1  Text-only gameplay + debrief + transcript export.
  G-2  STT-enabled: audio upload, transcript review, player turn.
  G-3  TTS-enabled: NPC utterance synthesised to local audio.
  G-4  Pack import: zip import followed by scenario listing.
  G-5  Explicit-download always passes through LOCAL_MODE.
  G-6  The socket guard itself blocks + records a real outbound connection.

Enforcement model
-----------------
Guarded scenarios run under **two** independent guards:

1. A socket-level guard (``_SocketGuard``) patches ``socket.socket.connect``
   and ``connect_ex`` for the client's lifetime.  Any connection to a
   non-loopback host is recorded and blocked with ``OutboundNetworkAttempt``
   — this is the Python analogue of the TypeScript CLI guard that patches
   ``net.Socket.prototype.connect``.  It catches accidental cloud calls even
   when the offending code bypasses the policy gate below.

2. ``LOCAL_MODE = True`` makes ``require_network(NetworkMode.PLAY)`` raise
   ``NetworkBlockedError``, giving a labelled, defence-in-depth signal at the
   exact call site.

Tests run against the fake runtime (no LLM), FakeSttWorker (no whisper.cpp),
and FakeTtsWorker (no Kokoro), all pure in-process — so a clean run makes
neither guard fire.  If a future change adds an accidental outbound call on
any of these paths, the socket guard blocks and records it (failing the test),
and if the call site went through the policy gate the ``LOCAL_MODE`` block
fires too.

For the TypeScript CLI path the network guard is enforced at the TCP
socket level — see ``packages/convsim-cli/tests/offline-smoke-test.test.ts``.
"""
from __future__ import annotations

import io
import socket
import zipfile

import pytest
from fastapi.testclient import TestClient

import convsim_core.network_policy as _np
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.network_policy import NetworkBlockedError, NetworkMode


# ---------------------------------------------------------------------------
# Socket-level outbound guard
# ---------------------------------------------------------------------------
#
# ``LOCAL_MODE`` alone only catches call sites that voluntarily invoke
# ``require_network(PLAY)``.  To actually *block or record* outbound network
# attempts (issue #218 definition-of-done), we patch ``socket.socket.connect``
# and ``connect_ex`` for the lifetime of the guarded client — the Python
# equivalent of the TypeScript CLI guard that patches
# ``net.Socket.prototype.connect``.  Any connection to a non-loopback host is
# recorded and blocked; loopback and AF_UNIX (local IPC / sidecar) connections
# pass through untouched.

_LOOPBACK_HOSTS = frozenset({"localhost", "::1", "[::1]", "0.0.0.0", "::"})


def _is_local_address(family: int, address) -> bool:
    """True if *address* is loopback / local IPC and must not be blocked."""
    if family == getattr(socket, "AF_UNIX", object()):
        return True  # Unix-domain socket — local IPC only.
    if not isinstance(address, tuple) or not address:
        return True  # Unparseable form — don't block (mirrors the TS guard).
    host = str(address[0]).lower()
    if host in _LOOPBACK_HOSTS or host.endswith(".localhost"):
        return True
    return host.startswith("127.")  # 127.0.0.0/8 loopback range.


class OutboundNetworkAttempt(OSError):
    """Raised (and recorded) when play-mode code opens a non-loopback socket."""

    def __init__(self, address) -> None:
        super().__init__(
            f"Outbound network connection to {address!r} blocked by the "
            "local-only guard. Play, debrief, transcript, telemetry, and crash "
            "paths must not contact remote hosts."
        )
        self.address = address


class _SocketGuard:
    """Patches ``socket.socket.connect``/``connect_ex`` to block outbound calls."""

    def __init__(self) -> None:
        self.attempts: list = []
        self._orig_connect = socket.socket.connect
        self._orig_connect_ex = socket.socket.connect_ex

    def install(self) -> None:
        guard = self
        orig_connect = self._orig_connect
        orig_connect_ex = self._orig_connect_ex

        def connect(self, address, *args, **kwargs):  # noqa: ANN001
            if not _is_local_address(self.family, address):
                guard.attempts.append(address)
                raise OutboundNetworkAttempt(address)
            return orig_connect(self, address, *args, **kwargs)

        def connect_ex(self, address, *args, **kwargs):  # noqa: ANN001
            if not _is_local_address(self.family, address):
                guard.attempts.append(address)
                raise OutboundNetworkAttempt(address)
            return orig_connect_ex(self, address, *args, **kwargs)

        socket.socket.connect = connect
        socket.socket.connect_ex = connect_ex

    def restore(self) -> None:
        socket.socket.connect = self._orig_connect
        socket.socket.connect_ex = self._orig_connect_ex


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _voice_config(tmp_path, monkeypatch):
    """ServiceConfig wired with fake STT and TTS workers.

    Keeps the runtime, STT worker, and TTS worker all in-process so the guard
    tests run in CI without model downloads.
    """
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper"))
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        local_dev_packs_dir=str(tmp_path),
        runtime_id="fake",
        stt_worker_id="fake",
        tts_worker_id="fake",
    )


@pytest.fixture()
def _guard_client(_voice_config):
    """TestClient whose entire lifetime runs under LOCAL_MODE + socket guard.

    Two independent guards are active for the client's lifetime:

    * ``LOCAL_MODE = True`` — any call site that invokes
      ``require_network(PLAY)`` raises ``NetworkBlockedError``.
    * A socket-level guard that blocks and records any outbound (non-loopback)
      TCP/UDP connection, catching accidental cloud calls that bypass the
      policy gate entirely (e.g. a stray ``requests``/``httpx`` call).

    The recorded outbound attempts are exposed as ``client.outbound_attempts``.
    ``create_app`` runs *before* the socket guard is installed so app startup
    (which may legitimately bind local sockets) is never mistaken for a
    play-mode outbound call.
    """
    app = create_app(_voice_config)
    original = _np.LOCAL_MODE
    _np.LOCAL_MODE = True
    guard = _SocketGuard()
    guard.install()
    try:
        with TestClient(app) as c:
            c.outbound_attempts = guard.attempts
            yield c
    finally:
        guard.restore()
        _np.LOCAL_MODE = original


# Minimal silent WAV: 44-byte RIFF header with 0 PCM samples (22 050 Hz, 16-bit, mono).
_SILENT_WAV: bytes = (
    b"RIFF"
    + (36).to_bytes(4, "little")
    + b"WAVE"
    + b"fmt "
    + (16).to_bytes(4, "little")
    + (1).to_bytes(2, "little")
    + (1).to_bytes(2, "little")
    + (22050).to_bytes(4, "little")
    + (44100).to_bytes(4, "little")
    + (2).to_bytes(2, "little")
    + (16).to_bytes(2, "little")
    + b"data"
    + (0).to_bytes(4, "little")
)

_TEXT_TURN = "I reduced on-call incidents by forty percent by improving our runbook coverage."
_SETUP_TEXT = {
    "scenario_id": "behavioral_interview",
    "difficulty": "normal",
    "player_role_name": "Guard Tester",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": True,
    "seed": None,
}
_SETUP_VOICE = {
    **_SETUP_TEXT,
    "input_mode": "push-to-talk",
    "tts_enabled": True,
    "tts_voice_id": "af_heart",
}


def _start(client: TestClient, setup: dict) -> str:
    """Create and start a session; return the session_id."""
    res = client.post("/api/sessions", json=setup)
    assert res.status_code == 201, res.text
    sid = res.json()["session_id"]
    start = client.post(f"/api/sessions/{sid}/start")
    assert start.status_code == 200, start.text
    return sid


def _make_minimal_zip() -> bytes:
    """Build the smallest valid installable pack zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("guard-pack/manifest.yaml", (
            'schema_version: "0.1"\n'
            'pack_id: guard.network_test\n'
            'name: Network Guard Test Pack\n'
            'version: 1.0.0\n'
            'description: Minimal pack for network guard acceptance testing.\n'
            'author: Guard Test Suite\n'
            'license: CC-BY-4.0\n'
            'content_rating: G\n'
            'tags:\n  - acceptance\n'
            'supported_languages:\n  - en\n'
            'entry_scenarios:\n  - scenarios/guard_scenario.yaml\n'
            'assets:\n  allow_external_urls: false\n'
            'safety:\n  policy: safety/policy.yaml\n'
        ))
        zf.writestr("guard-pack/safety/policy.yaml", (
            'schema_version: "0.1"\n'
            'policy_id: guard_policy\n'
            'content_rating_cap: G\n'
            'content_categories:\n'
            '  nsfw_sexual: block\n'
            '  real_person_impersonation: block\n'
            '  instructional_criminal: block\n'
            '  crisis_content: redirect\n'
            'redirect_message: "Redirected."\n'
        ))
        zf.writestr("guard-pack/npcs/guide.yaml", (
            'schema_version: "0.1"\n'
            'npc_id: guard_guide\n'
            'display_name: Guard Guide\n'
            'archetype: generic\n'
            'fictional: true\n'
            'age_band: adult\n'
            'public_persona:\n'
            '  occupation: Test Facilitator\n'
            '  speaking_style: Neutral\n'
            '  demeanor: Professional\n'
            'private_persona: {}\n'
        ))
        zf.writestr("guard-pack/rubrics/guard.yaml", (
            'schema_version: "0.1"\n'
            'rubric_id: guard_rubric\n'
            'title: Guard Rubric\n'
            'dimensions:\n'
            '  - id: clarity\n'
            '    name: Clarity\n'
            '    description: How clearly the player communicates.\n'
            '    scoring:\n'
            '      low: Unclear\n'
            '      medium: Adequate\n'
            '      high: Excellent\n'
        ))
        zf.writestr("guard-pack/scenarios/guard_scenario.yaml", (
            'schema_version: "0.1"\n'
            'scenario_id: guard_scenario\n'
            'title: Network Guard Scenario\n'
            'summary: Minimal scenario for network guard testing.\n'
            'player_role:\n'
            '  label: Participant\n'
            '  brief: Verifying no outbound network access occurs.\n'
            'npc:\n'
            '  ref: ../npcs/guide.yaml\n'
            'rubric:\n'
            '  ref: ../rubrics/guard.yaml\n'
            'duration:\n'
            '  max_turns: 4\n'
            'opening:\n'
            '  npc_says: "Welcome. Let us verify local-only operation."\n'
            'goals:\n'
            '  player_visible:\n'
            '    - Complete without outbound network access\n'
        ))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# G-1: Text-only path
# ---------------------------------------------------------------------------


class TestTextOnlyNetworkGuard:
    """G-1: Full text-only session + debrief + export under LOCAL_MODE."""

    def test_gameplay_completes_without_network_call(self, _guard_client):
        """Session creation, start, turn, and end must not trigger LOCAL_MODE block."""
        sid = _start(_guard_client, _SETUP_TEXT)
        turn = _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        assert turn.status_code == 200, (
            "Player turn failed — a play-mode network call may have been blocked. "
            f"Response: {turn.text}"
        )
        end = _guard_client.post(f"/api/sessions/{sid}/end")
        assert end.status_code == 200, (
            "Session end failed — check for unexpected network call. "
            f"Response: {end.text}"
        )

    def test_debrief_completes_without_network_call(self, _guard_client):
        """Debrief generation must not make any outbound network call."""
        sid = _start(_guard_client, _SETUP_TEXT)
        _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        _guard_client.post(f"/api/sessions/{sid}/end")
        res = _guard_client.post(f"/api/sessions/{sid}/debrief")
        assert res.status_code == 200, (
            "Debrief generation failed — check for unexpected network call in debrief path. "
            f"Response: {res.text}"
        )

    def test_debrief_response_has_required_fields(self, _guard_client):
        """Debrief response structure is intact under LOCAL_MODE."""
        sid = _start(_guard_client, _SETUP_TEXT)
        _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        _guard_client.post(f"/api/sessions/{sid}/end")
        body = _guard_client.post(f"/api/sessions/{sid}/debrief").json()
        assert body.get("session_id") == sid
        assert "scores" in body
        assert "summary" in body

    def test_transcript_export_completes_without_network_call(self, _guard_client):
        """Transcript export must not make any outbound network call."""
        sid = _start(_guard_client, _SETUP_TEXT)
        _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        _guard_client.post(f"/api/sessions/{sid}/end")
        _guard_client.post(f"/api/sessions/{sid}/debrief")
        res = _guard_client.get(f"/api/sessions/{sid}/export")
        assert res.status_code == 200, (
            "Transcript export failed — check for unexpected network call in export path. "
            f"Response: {res.text}"
        )

    def test_full_text_only_path(self, _guard_client):
        """Combined gate: create → start → turn → end → debrief → export under LOCAL_MODE."""
        sid = _start(_guard_client, _SETUP_TEXT)

        turn = _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        assert turn.status_code == 200, f"[turn] {turn.text}"

        end = _guard_client.post(f"/api/sessions/{sid}/end")
        assert end.status_code == 200, f"[end] {end.text}"

        debrief = _guard_client.post(f"/api/sessions/{sid}/debrief")
        assert debrief.status_code == 200, f"[debrief] {debrief.text}"

        export = _guard_client.get(f"/api/sessions/{sid}/export")
        assert export.status_code == 200, f"[export] {export.text}"

        assert _guard_client.outbound_attempts == [], (
            f"Outbound network attempts recorded during text-only play: "
            f"{_guard_client.outbound_attempts}"
        )


# ---------------------------------------------------------------------------
# G-2: STT-enabled path
# ---------------------------------------------------------------------------


class TestSttEnabledNetworkGuard:
    """G-2: STT audio upload and transcript round-trip under LOCAL_MODE.

    Uses FakeSttWorker — no whisper.cpp binary required.  Any future attempt
    to contact a cloud STT provider from the STT path (e.g. an OpenAI Whisper
    API call) would need to call require_network(PLAY) first, and with
    LOCAL_MODE active that raises NetworkBlockedError immediately.
    """

    def test_stt_health_reports_ready_under_local_mode(self, _guard_client):
        """FakeSttWorker must be READY before the STT upload path is exercised."""
        health = _guard_client.get("/api/health").json()
        assert health["stt"]["status"] == "ready", (
            f"FakeSttWorker not READY under LOCAL_MODE: {health['stt']}"
        )

    def test_stt_audio_upload_completes_without_network_call(self, _guard_client):
        """Audio upload must not trigger a play-mode network call."""
        res = _guard_client.post(
            "/api/stt/upload",
            files={"audio": ("recording.wav", io.BytesIO(_SILENT_WAV), "audio/wav")},
        )
        assert res.status_code == 200, (
            "STT upload failed — a play-mode network call may have been blocked. "
            f"Response: {res.text}"
        )

    def test_stt_returns_transcript_under_local_mode(self, _guard_client):
        """FakeSttWorker returns a non-empty transcript without making network calls."""
        body = _guard_client.post(
            "/api/stt/upload",
            files={"audio": ("recording.wav", io.BytesIO(_SILENT_WAV), "audio/wav")},
        ).json()
        assert body["status"] == "ok", f"STT status not ok under LOCAL_MODE: {body}"
        assert body["transcript"], f"Empty transcript under LOCAL_MODE: {body}"

    def test_stt_session_turn_completes_without_network_call(self, _guard_client):
        """Full STT path: upload → review → submit turn — no network call under LOCAL_MODE."""
        # Upload audio to STT
        stt = _guard_client.post(
            "/api/stt/upload",
            files={"audio": ("recording.wav", io.BytesIO(_SILENT_WAV), "audio/wav")},
        )
        assert stt.status_code == 200, f"[stt] {stt.text}"

        # Use corrected text as player turn (mirrors TranscriptReviewPanel flow)
        sid = _start(_guard_client, {**_SETUP_TEXT, "input_mode": "push-to-talk"})
        turn = _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        assert turn.status_code == 200, (
            "Player turn (STT path) failed — check for unexpected network call. "
            f"Response: {turn.text}"
        )
        npc = next((e for e in turn.json()["events"] if e["event_type"] == "npc_turn"), None)
        assert npc is not None, "No NPC response in STT session turn"
        assert npc["payload"].get("content"), "Empty NPC content in STT session turn"

    def test_full_stt_path(self, _guard_client):
        """Combined gate: health → STT upload → session start → turn → end under LOCAL_MODE."""
        health = _guard_client.get("/api/health").json()
        assert health["stt"]["status"] == "ready", f"[health] {health['stt']}"

        stt = _guard_client.post(
            "/api/stt/upload",
            files={"audio": ("recording.wav", io.BytesIO(_SILENT_WAV), "audio/wav")},
        )
        assert stt.status_code == 200, f"[stt] {stt.text}"
        transcript = stt.json()["transcript"]
        assert transcript, "[stt] Empty transcript"

        sid = _start(_guard_client, {**_SETUP_TEXT, "input_mode": "push-to-talk"})
        turn = _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": transcript})
        assert turn.status_code == 200, f"[turn] {turn.text}"

        end = _guard_client.post(f"/api/sessions/{sid}/end")
        assert end.status_code == 200, f"[end] {end.text}"

        assert _guard_client.outbound_attempts == [], (
            f"Outbound network attempts recorded during STT play: "
            f"{_guard_client.outbound_attempts}"
        )


# ---------------------------------------------------------------------------
# G-3: TTS-enabled path
# ---------------------------------------------------------------------------


class TestTtsEnabledNetworkGuard:
    """G-3: TTS synthesis under LOCAL_MODE.

    Uses FakeTtsWorker — no Kokoro server required.  Any future attempt to
    contact a cloud TTS provider would need require_network(PLAY) first;
    LOCAL_MODE active raises NetworkBlockedError immediately.
    """

    def test_tts_health_reports_ready_under_local_mode(self, _guard_client):
        """FakeTtsWorker must be READY before TTS path tests run."""
        health = _guard_client.get("/api/health").json()
        assert health["tts"]["status"] == "ready", (
            f"FakeTtsWorker not READY under LOCAL_MODE: {health['tts']}"
        )

    def test_tts_synthesis_produces_audio_chunk_without_network_call(self, _guard_client):
        """NPC utterance synthesis must complete locally without outbound calls."""
        sid = _start(_guard_client, _SETUP_VOICE)
        res = _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        assert res.status_code == 200, (
            "TTS-enabled turn failed — a play-mode network call may have been blocked. "
            f"Response: {res.text}"
        )
        tts_events = [e for e in res.json()["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, (
            "No tts_audio_chunk events under LOCAL_MODE — "
            "FakeTtsWorker should emit at least one chunk."
        )

    def test_tts_chunk_has_local_cache_path(self, _guard_client):
        """TTS audio chunk cache_path must be a local filesystem path, not a URL."""
        sid = _start(_guard_client, _SETUP_VOICE)
        res = _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        tts_events = [e for e in res.json()["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, "No TTS audio chunks under LOCAL_MODE"
        cache_path = tts_events[0]["payload"].get("cache_path", "")
        assert cache_path and not cache_path.startswith("http"), (
            f"cache_path looks like a URL instead of a local path: {cache_path!r}"
        )

    def test_tts_chunk_has_no_synthesis_error(self, _guard_client):
        """FakeTtsWorker must not report a synthesis error under LOCAL_MODE."""
        sid = _start(_guard_client, _SETUP_VOICE)
        res = _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        tts_events = [e for e in res.json()["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, "No TTS audio chunks"
        assert tts_events[0]["payload"].get("error") is None, (
            f"TTS synthesis error under LOCAL_MODE: {tts_events[0]['payload'].get('error')}"
        )

    def test_no_tts_events_when_disabled(self, _guard_client):
        """Disabling TTS in a voice session must produce no audio chunks."""
        sid = _start(_guard_client, {**_SETUP_VOICE, "tts_enabled": False})
        res = _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        tts_events = [e for e in res.json()["events"] if e["event_type"] == "tts_audio_chunk"]
        assert not tts_events, f"Unexpected TTS events when tts_enabled=False: {tts_events}"

    def test_full_tts_path(self, _guard_client):
        """Combined gate: create → start → TTS turn → end → debrief under LOCAL_MODE."""
        health = _guard_client.get("/api/health").json()
        assert health["tts"]["status"] == "ready", f"[health] {health['tts']}"

        sid = _start(_guard_client, _SETUP_VOICE)

        turn = _guard_client.post(f"/api/sessions/{sid}/turn", json={"content": _TEXT_TURN})
        assert turn.status_code == 200, f"[turn] {turn.text}"

        tts_events = [e for e in turn.json()["events"] if e["event_type"] == "tts_audio_chunk"]
        assert tts_events, "[tts] No audio chunks"
        assert tts_events[0]["payload"].get("error") is None, "[tts] Synthesis error"

        end = _guard_client.post(f"/api/sessions/{sid}/end")
        assert end.status_code == 200, f"[end] {end.text}"

        debrief = _guard_client.post(f"/api/sessions/{sid}/debrief")
        assert debrief.status_code == 200, f"[debrief] {debrief.text}"

        assert _guard_client.outbound_attempts == [], (
            f"Outbound network attempts recorded during TTS play: "
            f"{_guard_client.outbound_attempts}"
        )


# ---------------------------------------------------------------------------
# G-4: Pack import path
# ---------------------------------------------------------------------------


class TestPackImportNetworkGuard:
    """G-4: Pack import (zip install) must not make outbound network calls.

    Pack installation is a user-initiated action; it does not use
    NetworkMode.PLAY.  This test verifies that a zip import completes
    under LOCAL_MODE and the imported scenario is immediately playable
    without lifting the guard.
    """

    def test_pack_import_completes_under_local_mode(self, _guard_client):
        """Importing a pack zip must not trigger a LOCAL_MODE network block."""
        zip_bytes = _make_minimal_zip()
        res = _guard_client.post(
            "/api/packs/import/zip",
            files={"file": ("guard-pack.zip", zip_bytes, "application/zip")},
        )
        assert res.status_code == 201, (
            "Pack import failed under LOCAL_MODE — an unexpected network call may have occurred. "
            f"Response: {res.text}"
        )

    def test_imported_pack_scenario_appears_in_library(self, _guard_client):
        """Imported scenario must be listed without network access."""
        zip_bytes = _make_minimal_zip()
        _guard_client.post(
            "/api/packs/import/zip",
            files={"file": ("guard-pack.zip", zip_bytes, "application/zip")},
        )
        scenarios = _guard_client.get("/api/scenarios")
        assert scenarios.status_code == 200, f"[scenarios] {scenarios.text}"
        ids = [s["scenario_id"] for s in scenarios.json()]
        assert "guard_scenario" in ids, (
            f"Imported scenario 'guard_scenario' not in library under LOCAL_MODE: {ids}"
        )

    def test_scenario_library_query_completes_without_network_call(self, _guard_client):
        """Listing scenarios after a pack import must not trigger a network call."""
        zip_bytes = _make_minimal_zip()
        _guard_client.post(
            "/api/packs/import/zip",
            files={"file": ("guard-pack.zip", zip_bytes, "application/zip")},
        )
        res = _guard_client.get("/api/scenarios")
        assert res.status_code == 200, (
            "Scenario listing failed after pack import under LOCAL_MODE. "
            f"Response: {res.text}"
        )

    def test_full_pack_import_path(self, _guard_client):
        """Combined gate: import zip → list scenarios → pack listing under LOCAL_MODE."""
        zip_bytes = _make_minimal_zip()
        imp = _guard_client.post(
            "/api/packs/import/zip",
            files={"file": ("guard-pack.zip", zip_bytes, "application/zip")},
        )
        assert imp.status_code == 201, f"[import] {imp.text}"

        scenarios = _guard_client.get("/api/scenarios")
        assert scenarios.status_code == 200, f"[scenarios] {scenarios.text}"
        assert any(s["scenario_id"] == "guard_scenario" for s in scenarios.json()), (
            "[scenarios] guard_scenario not listed after import"
        )

        packs = _guard_client.get("/api/packs")
        assert packs.status_code == 200, f"[packs] {packs.text}"
        slugs = [p.get("slug", "") for p in packs.json()]
        assert any("guard" in slug.lower() for slug in slugs), (
            f"[packs] guard pack not found in pack slugs after import: {slugs}"
        )

        assert _guard_client.outbound_attempts == [], (
            f"Outbound network attempts recorded during pack import + play: "
            f"{_guard_client.outbound_attempts}"
        )


# ---------------------------------------------------------------------------
# G-5: Explicit-download always passes through LOCAL_MODE
# ---------------------------------------------------------------------------


class TestExplicitDownloadAlwaysPermitted:
    """G-5: NetworkMode.EXPLICIT_DOWNLOAD is never blocked by LOCAL_MODE.

    Model and pack downloads require outbound network access and are
    triggered only by explicit user action (Settings → Model Manager or
    Settings → Pack Library).  They must always be permitted regardless
    of LOCAL_MODE, since blocking them would prevent users from setting
    up new models while in a strict local-only configuration.
    """

    def test_explicit_download_does_not_raise_when_local_mode_on(self):
        """require_network(EXPLICIT_DOWNLOAD) must not raise under LOCAL_MODE."""
        from convsim_core.network_policy import NetworkMode, require_network
        _np.LOCAL_MODE = True
        try:
            require_network(NetworkMode.EXPLICIT_DOWNLOAD)  # must not raise
        except NetworkBlockedError:
            pytest.fail(
                "require_network(EXPLICIT_DOWNLOAD) raised NetworkBlockedError "
                "under LOCAL_MODE — explicit downloads must always be permitted."
            )
        finally:
            _np.LOCAL_MODE = False

    def test_play_mode_blocked_explicit_download_not_blocked(self):
        """Simultaneous confirmation: PLAY is blocked, EXPLICIT_DOWNLOAD passes."""
        from convsim_core.network_policy import NetworkMode, require_network
        _np.LOCAL_MODE = True
        try:
            with pytest.raises(NetworkBlockedError):
                require_network(NetworkMode.PLAY)
            # Must not raise:
            require_network(NetworkMode.EXPLICIT_DOWNLOAD)
        finally:
            _np.LOCAL_MODE = False


# ---------------------------------------------------------------------------
# G-6: The socket guard itself actually blocks and records outbound calls
# ---------------------------------------------------------------------------


class TestSocketGuardBlocksOutbound:
    """G-6: Verify the harness is not a silent no-op.

    The G-1..G-4 guarantees are only meaningful if the socket guard genuinely
    intercepts outbound connections.  These tests exercise the guard directly:
    a non-loopback connection must be blocked and recorded, while loopback and
    unresolved-hostname connections must pass through to the original socket.
    """

    def test_outbound_connection_is_blocked_and_recorded(self):
        guard = _SocketGuard()
        guard.install()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with pytest.raises(OutboundNetworkAttempt):
                # TEST-NET-1 (RFC 5737) — never routable, so no real packets.
                s.connect(("192.0.2.1", 443))
            s.close()
        finally:
            guard.restore()
        assert guard.attempts == [("192.0.2.1", 443)], (
            f"Outbound connection was not recorded by the guard: {guard.attempts}"
        )

    def test_connect_ex_outbound_is_blocked_and_recorded(self):
        guard = _SocketGuard()
        guard.install()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with pytest.raises(OutboundNetworkAttempt):
                s.connect_ex(("198.51.100.7", 8080))  # TEST-NET-2 (RFC 5737).
            s.close()
        finally:
            guard.restore()
        assert guard.attempts == [("198.51.100.7", 8080)]

    def test_loopback_is_not_blocked(self):
        guard = _SocketGuard()
        guard.install()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.05)
            # No server is listening; the connection fails with a normal socket
            # error — but crucially NOT OutboundNetworkAttempt, and it is not
            # recorded as a violation.
            with pytest.raises(OSError) as exc_info:
                s.connect(("127.0.0.1", 9))  # Discard port, nothing listening.
            assert not isinstance(exc_info.value, OutboundNetworkAttempt)
            s.close()
        finally:
            guard.restore()
        assert guard.attempts == [], (
            f"Loopback connection was wrongly recorded as outbound: {guard.attempts}"
        )

    def test_guard_restores_socket_connect(self):
        original = socket.socket.connect
        guard = _SocketGuard()
        guard.install()
        assert socket.socket.connect is not original
        guard.restore()
        assert socket.socket.connect is original
