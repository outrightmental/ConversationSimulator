# SPDX-License-Identifier: Apache-2.0
"""Tests for the guided voice setup flow (issue #487).

Three concerns, in order of how much damage a regression would do:

1. the registry discloses everything the download policy requires, and never
   ships an unverifiable entry;
2. a download that does not match its checksum leaves nothing installed;
3. the plan and job endpoints describe the machine truthfully, including the
   two engines the app refuses to download.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

import convsim_core.runtime  # noqa: F401 — register built-in adapters
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.services import voice_registry
from convsim_core.services.voice_download import (
    ChecksumMismatch,
    DownloadCancelled,
    download_voice_asset,
)
from convsim_core.services.voice_setup_service import (
    get_stt_model_path,
    retire_orphaned_jobs,
)
from convsim_core.storage.database import Database

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def voice_paths(tmp_path, monkeypatch):
    """Redirect every voice path at tmp_path.

    Without this the registry resolves install paths under the developer's real
    home directory, so a test could both read their actual install state and —
    far worse — write into it.
    """
    stt_model = tmp_path / "models" / "stt" / "ggml-base.en.bin"
    vad_model = tmp_path / "models" / "vad" / "silero_vad.onnx"
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_MODEL_PATH", str(stt_model))
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    monkeypatch.setenv("CONVSIM_SILERO_VAD_MODEL_PATH", str(vad_model))
    return {"stt_dir": stt_model.parent, "stt_model": stt_model, "vad_model": vad_model}


@pytest.fixture()
def tmp_config(tmp_path):
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        exports_dir=str(tmp_path / "exports"),
        cache_dir=str(tmp_path / "cache"),
        crash_bundles_dir=str(tmp_path / "crashes"),
        models_dir=str(tmp_path / "models" / "llm"),
        official_packs_dir=str(tmp_path / "no-official-packs"),
    )


@pytest.fixture()
def client(tmp_config, voice_paths):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(tmp_path):
    database = Database.open(str(tmp_path / "jobs-db"))
    yield database
    database.close()


# ── Registry: disclosure and verifiability ────────────────────────────────────


def test_every_asset_is_fully_disclosed():
    """No asset may ship without the six fields the confirmation screen shows."""
    assert voice_registry.VOICE_ASSETS, "the registry must not be empty"
    for asset in voice_registry.VOICE_ASSETS:
        assert asset.name
        assert asset.url.startswith("https://"), asset.id
        assert _SHA256_RE.match(asset.sha256), f"{asset.id} has no usable SHA-256"
        assert asset.size_bytes > 0, asset.id
        assert asset.license
        assert asset.license_url.startswith("https://"), asset.id


def test_download_urls_are_revision_pinned():
    """A floating tag could change the bytes under a pinned checksum."""
    for asset in voice_registry.VOICE_ASSETS:
        assert "/resolve/main/" not in asset.url, asset.id
        assert "/raw/master/" not in asset.url, asset.id
        # Both hosts we use carry a 40-char commit sha in the path.
        assert re.search(r"/[0-9a-f]{40}/", asset.url), asset.id


def test_exactly_one_recommended_asset_per_capability():
    for capability in ("stt", "vad"):
        recommended = [a for a in voice_registry.assets_for(capability) if a.recommended]
        assert len(recommended) == 1, capability


def test_engine_commands_cover_every_desktop_platform():
    for engine in voice_registry.VOICE_ENGINES:
        for platform in ("darwin", "linux", "win32"):
            assert voice_registry.engine_command(engine, platform), (engine.id, platform)
    # sys.platform is "linux2"-style on some builds; the lookup must normalise.
    whisper = voice_registry.get_engine("whisper-cli")
    assert whisper is not None
    assert voice_registry.engine_command(whisper, "linux2") == whisper.commands["linux"]


def test_install_paths_follow_the_engines(voice_paths):
    """A model installed where the engine does not look is not installed at all."""
    base_en = voice_registry.get_asset("whisper-base-en")
    small_en = voice_registry.get_asset("whisper-small-en")
    silero = voice_registry.get_asset("silero-vad")
    assert base_en and small_en and silero

    assert voice_registry.install_path(base_en) == voice_paths["stt_dir"] / "ggml-base.en.bin"
    # An alternative STT model keeps its own filename beside the default one.
    assert voice_registry.install_path(small_en) == voice_paths["stt_dir"] / "ggml-small.en.bin"
    # There is only one VAD model, so it must land on the exact configured path.
    assert voice_registry.install_path(silero) == voice_paths["vad_model"]


# ── Downloader ────────────────────────────────────────────────────────────────


def _mock_client(content: bytes, *, status_code: int = 200, headers: dict | None = None):
    async def _aiter_bytes(chunk_size=None):
        yield content

    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    response.headers = {"content-length": str(len(content)), **(headers or {})}
    response.aiter_bytes = _aiter_bytes

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=None)

    client = MagicMock(spec=httpx.AsyncClient)
    client.stream = MagicMock(return_value=cm)
    client.aclose = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_download_verifies_and_installs(tmp_path):
    content = b"pretend ggml weights"
    dest = tmp_path / "stt" / "ggml-base.en.bin"
    seen: list[tuple[int, int | None]] = []

    written = await download_voice_asset(
        url="https://example.test/m.bin",
        dest_path=dest,
        expected_sha256=_sha256_of(content),
        progress_cb=lambda done, total: seen.append((done, total)),
        _client=_mock_client(content),
    )

    assert written == len(content)
    assert dest.read_bytes() == content
    assert not dest.with_name(dest.name + ".part").exists()
    assert seen[-1][0] == len(content)


@pytest.mark.asyncio
async def test_download_rejects_a_checksum_mismatch(tmp_path):
    dest = tmp_path / "stt" / "ggml-base.en.bin"

    with pytest.raises(ChecksumMismatch):
        await download_voice_asset(
            url="https://example.test/m.bin",
            dest_path=dest,
            expected_sha256="b" * 64,
            _client=_mock_client(b"tampered"),
        )

    # Neither the final file nor the partial may survive a failed verification.
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


@pytest.mark.asyncio
async def test_download_cancel_leaves_nothing_behind(tmp_path):
    dest = tmp_path / "stt" / "ggml-base.en.bin"
    cancel = asyncio.Event()
    cancel.set()

    with pytest.raises(DownloadCancelled):
        await download_voice_asset(
            url="https://example.test/m.bin",
            dest_path=dest,
            expected_sha256=_sha256_of(b"anything"),
            cancel_event=cancel,
            _client=_mock_client(b"anything"),
        )

    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


@pytest.mark.asyncio
async def test_download_resumes_from_a_partial_file(tmp_path):
    """A .part left by a killed process continues instead of restarting."""
    content = b"0123456789abcdef"
    dest = tmp_path / "stt" / "ggml-base.en.bin"
    dest.parent.mkdir(parents=True)
    part = dest.with_name(dest.name + ".part")
    part.write_bytes(content[:6])

    client = _mock_client(
        content[6:],
        status_code=206,
        headers={"content-range": f"bytes 6-{len(content) - 1}/{len(content)}"},
    )

    written = await download_voice_asset(
        url="https://example.test/m.bin",
        dest_path=dest,
        expected_sha256=_sha256_of(content),
        _client=client,
    )

    assert written == len(content)
    assert dest.read_bytes() == content
    assert client.stream.call_args.kwargs["headers"] == {"Range": "bytes=6-"}


@pytest.mark.asyncio
async def test_download_requires_the_explicit_download_network_mode(tmp_path, monkeypatch):
    """Nothing here may be reachable from play-mode code."""
    seen: list = []
    monkeypatch.setattr(
        "convsim_core.services.voice_download.require_network",
        lambda mode: seen.append(mode),
    )
    await download_voice_asset(
        url="https://example.test/m.bin",
        dest_path=tmp_path / "m.bin",
        expected_sha256=_sha256_of(b"x"),
        _client=_mock_client(b"x"),
    )
    from convsim_core.network_policy import NetworkMode

    assert seen == [NetworkMode.EXPLICIT_DOWNLOAD]


# ── Plan endpoint ─────────────────────────────────────────────────────────────


def test_plan_reports_both_capabilities_as_not_ready(client):
    body = client.get("/api/voice/setup/plan").json()

    ids = {c["id"] for c in body["capabilities"]}
    assert ids == {"stt", "tts", "vad"}
    assert all(not c["ready"] for c in body["capabilities"])
    assert body["active_job_id"] is None


def test_plan_names_the_engines_it_will_not_download(client):
    body = client.get("/api/voice/setup/plan").json()

    engines = {e["id"]: e for e in body["engines"]}
    assert set(engines) == {"whisper-cli", "kokoro-server"}
    for engine in engines.values():
        assert engine["installed"] is False
        assert engine["why_manual"]
        # The player gets a command for their own platform, not a generic link.
        assert engine["command"]
        assert engine["docs_url"].startswith("https://")
    # Only the Kokoro server is something the app can launch itself.
    assert engines["kokoro-server"]["startable"] is True
    assert engines["whisper-cli"]["startable"] is False


def test_plan_discloses_source_licence_checksum_and_destination(client):
    body = client.get("/api/voice/setup/plan").json()

    assert body["assets"], "the plan must list the downloadable assets"
    for asset in body["assets"]:
        assert asset["source_url"].startswith("https://")
        assert asset["license"] and asset["license_url"]
        assert _SHA256_RE.match(asset["sha256"])
        assert asset["size_bytes"] > 0
        assert asset["install_path"]
        assert asset["installed"] is False


def test_plan_marks_an_asset_installed_once_the_file_exists(client, voice_paths):
    voice_paths["vad_model"].parent.mkdir(parents=True, exist_ok=True)
    voice_paths["vad_model"].write_bytes(b"onnx")

    body = client.get("/api/voice/setup/plan").json()
    silero = next(a for a in body["assets"] if a["id"] == "silero-vad")
    assert silero["installed"] is True


def test_plan_default_download_size_excludes_installed_assets(client, voice_paths):
    before = client.get("/api/voice/setup/plan").json()
    assert before["default_asset_ids"] == ["whisper-base-en", "silero-vad"]

    voice_paths["vad_model"].parent.mkdir(parents=True, exist_ok=True)
    voice_paths["vad_model"].write_bytes(b"onnx")

    after = client.get("/api/voice/setup/plan").json()
    silero = voice_registry.get_asset("silero-vad")
    assert silero is not None
    assert after["default_download_bytes"] == before["default_download_bytes"] - silero.size_bytes


# ── Install job endpoints ─────────────────────────────────────────────────────


def _stub_downloads(monkeypatch, *, fail_with: Exception | None = None) -> list[Path]:
    """Replace the network download with a local file write; returns written paths."""
    written: list[Path] = []

    async def _fake_download(*, url, dest_path, expected_sha256, progress_cb=None, cancel_event=None, **_):
        if fail_with is not None:
            raise fail_with
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"downloaded")
        written.append(dest_path)
        if progress_cb is not None:
            progress_cb(10, 10)
        return 10

    monkeypatch.setattr(
        "convsim_core.routers.voice_setup.download_voice_asset", _fake_download
    )
    return written


def _await_terminal(client: TestClient, job_id: int) -> dict:
    for _ in range(100):
        body = client.get(f"/api/voice/setup/install/{job_id}").json()
        if body["status"] in ("complete", "failed", "cancelled"):
            return body
        import time

        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached a terminal state")


def test_install_downloads_the_requested_assets(client, monkeypatch, voice_paths):
    written = _stub_downloads(monkeypatch)

    started = client.post(
        "/api/voice/setup/install", json={"asset_ids": ["whisper-base-en", "silero-vad"]}
    )
    assert started.status_code == 200
    job = _await_terminal(client, started.json()["id"])

    assert job["status"] == "complete"
    assert [s["state"] for s in job["stages"]] == ["complete", "complete"]
    assert set(written) == {voice_paths["stt_model"], voice_paths["vad_model"]}


def test_install_points_the_stt_worker_at_the_model_it_fetched(client, monkeypatch, voice_paths):
    """Choosing small.en must actually switch the worker, not just drop a file."""
    _stub_downloads(monkeypatch)

    started = client.post("/api/voice/setup/install", json={"asset_ids": ["whisper-small-en"]})
    job = _await_terminal(client, started.json()["id"])
    assert job["status"] == "complete"

    expected = str(voice_paths["stt_dir"] / "ggml-small.en.bin")
    conn = client.app.state.db.connection()
    assert get_stt_model_path(conn) == expected
    assert client.app.state.stt_worker.model_path == expected


def test_install_skips_an_asset_that_is_already_present(client, monkeypatch, voice_paths):
    voice_paths["vad_model"].parent.mkdir(parents=True, exist_ok=True)
    voice_paths["vad_model"].write_bytes(b"onnx")
    written = _stub_downloads(monkeypatch)

    started = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]})
    job = _await_terminal(client, started.json()["id"])

    assert job["stages"][0]["state"] == "skipped"
    assert written == []


def test_install_surfaces_a_checksum_mismatch_as_a_failed_job(client, monkeypatch):
    _stub_downloads(monkeypatch, fail_with=ChecksumMismatch("SHA-256 did not match."))

    started = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]})
    job = _await_terminal(client, started.json()["id"])

    assert job["status"] == "failed"
    assert "SHA-256" in (job["error_message"] or "")
    assert job["stages"][0]["state"] == "failed"


def test_install_rejects_an_unknown_asset(client):
    r = client.post("/api/voice/setup/install", json={"asset_ids": ["not-a-model"]})
    assert r.status_code == 404
    assert "not-a-model" in r.json()["error"]["message"]


def test_install_defaults_to_the_recommended_assets(client, monkeypatch):
    _stub_downloads(monkeypatch)
    started = client.post("/api/voice/setup/install", json={})
    assert started.json()["asset_ids"] == ["whisper-base-en", "silero-vad"]


def test_install_reattaches_instead_of_starting_a_second_job(client, monkeypatch):
    release = asyncio.Event()

    async def _slow_download(*, dest_path, progress_cb=None, **_):
        await release.wait()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"x")
        return 1

    monkeypatch.setattr(
        "convsim_core.routers.voice_setup.download_voice_asset", _slow_download
    )

    first = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]}).json()
    second = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]}).json()
    assert second["id"] == first["id"]

    # The plan hands the same job back so a reopened screen rejoins the download.
    assert client.get("/api/voice/setup/plan").json()["active_job_id"] == first["id"]

    client.delete(f"/api/voice/setup/install/{first['id']}")


def test_cancel_marks_the_job_cancelled_not_failed(client, monkeypatch):
    """A user abort must be distinguishable from a real error."""

    async def _watch_cancel(*, cancel_event=None, **_):
        assert cancel_event is not None
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)
        raise DownloadCancelled()

    monkeypatch.setattr(
        "convsim_core.routers.voice_setup.download_voice_asset", _watch_cancel
    )

    job_id = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]}).json()["id"]
    assert client.delete(f"/api/voice/setup/install/{job_id}").status_code == 204

    assert _await_terminal(client, job_id)["status"] == "cancelled"


def test_cancelling_a_finished_job_is_a_conflict(client, monkeypatch):
    _stub_downloads(monkeypatch)
    job_id = client.post("/api/voice/setup/install", json={"asset_ids": ["silero-vad"]}).json()["id"]
    _await_terminal(client, job_id)

    r = client.delete(f"/api/voice/setup/install/{job_id}")
    assert r.status_code == 409


def test_unknown_job_is_a_404(client):
    assert client.get("/api/voice/setup/install/9999").status_code == 404
    assert client.delete("/api/voice/setup/install/9999").status_code == 404


def test_retire_orphaned_jobs_fails_rows_no_task_is_driving(db):
    conn = db.connection()
    conn.execute("INSERT INTO voice_install_jobs (status) VALUES ('running')")
    conn.execute("INSERT INTO voice_install_jobs (status) VALUES ('complete')")
    conn.commit()

    assert retire_orphaned_jobs(conn) == 1

    statuses = [r[0] for r in conn.execute("SELECT status FROM voice_install_jobs ORDER BY id")]
    assert statuses == ["failed", "complete"]


# ── Engine start ──────────────────────────────────────────────────────────────


def test_only_the_kokoro_server_is_startable(client):
    assert client.post("/api/voice/setup/engine/whisper-cli/start").status_code == 404
    assert client.post("/api/voice/setup/engine/nope/start").status_code == 404


def test_starting_kokoro_without_the_binary_explains_why(client):
    r = client.post("/api/voice/setup/engine/kokoro-server/start")
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is False
    assert "kokoro" in body["message"].lower()


def test_starting_kokoro_runs_the_sidecar(client, monkeypatch):
    from convsim_core.runtime.sidecar import SidecarState

    sidecar = client.app.state.kokoro_sidecar
    started = {"called": False}

    async def _start(**_kwargs):
        started["called"] = True
        monkeypatch.setattr(
            type(sidecar), "state", property(lambda self: SidecarState.RUNNING)
        )

    monkeypatch.setattr(sidecar, "start", _start)

    body = client.post("/api/voice/setup/engine/kokoro-server/start").json()
    assert started["called"] is True
    assert body["started"] is True
    assert body["state"] == "running"
