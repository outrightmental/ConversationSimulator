# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path

from convsim_core import __version__


def test_health_returns_200(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_health_status_ok(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_health_version(client):
    assert client.get("/api/health").json()["version"] == __version__


def test_health_pid(client):
    assert client.get("/api/health").json()["pid"] == os.getpid()


def test_health_database_status_ok(client):
    body = client.get("/api/health").json()
    assert body["database"]["status"] == "ok"


def test_health_database_path_present(client, tmp_config):
    body = client.get("/api/health").json()
    db_path = body["database"]["path"]
    assert db_path is not None
    assert Path(db_path).exists()
    assert db_path.endswith("convsim.sqlite")


def test_health_database_migrations_applied(client):
    body = client.get("/api/health").json()
    assert body["database"]["migrations_applied"] >= 1


def test_health_llm_runtime_fields_exist(client):
    rt = client.get("/api/health").json()["llm_runtime"]
    assert rt["runtime_id"] == "fake"
    assert rt["runtime_name"] == "Fake (deterministic)"
    assert rt["status"] == "ready"
    assert "checked_at" in rt


# ── runtime readiness (shared RuntimeReadiness contract) ─────────────────────


def test_health_runtime_readiness_shape(client):
    rt = client.get("/api/health").json()["runtime"]
    for key in (
        "llm_ready",
        "llm_model_name",
        "stt_ready",
        "tts_ready",
        "tts_voice_name",
        "network_required",
        "last_error",
    ):
        assert key in rt


def test_health_readiness_defaults(client):
    rt = client.get("/api/health").json()["runtime"]
    # Default test config: fake runtime is ready, no whisper binary installed.
    assert rt["llm_ready"] is True
    assert rt["stt_ready"] is False
    assert rt["network_required"] is False
    # The LLM is ready, so no blocking error. Optional voice (STT/TTS) being
    # unavailable must NOT leak into last_error, or Home shows an error card
    # for a text-ready app.
    assert rt["last_error"] is None


def test_health_llm_ready_after_register_gguf(client, tmp_path):
    model_file = tmp_path / "my-model.gguf"
    model_file.write_bytes(b"\x00" * 16)
    resp = client.post("/api/models/register-gguf", json={"path": str(model_file)})
    assert resp.status_code == 200

    rt = client.get("/api/health").json()["runtime"]
    assert rt["llm_ready"] is True
    assert rt["llm_model_name"] == "my-model.gguf"


def test_health_llm_not_ready_when_model_file_deleted(client, tmp_path):
    model_file = tmp_path / "gone-model.gguf"
    model_file.write_bytes(b"\x00" * 16)
    resp = client.post("/api/models/register-gguf", json={"path": str(model_file)})
    assert resp.status_code == 200
    model_file.unlink()

    rt = client.get("/api/health").json()["runtime"]
    assert rt["llm_ready"] is False
    assert rt["last_error"] is not None
    assert "not found" in rt["last_error"].lower()


def test_health_config_path_present(client):
    body = client.get("/api/health").json()
    assert "config_path" in body
    assert isinstance(body["config_path"], str)


def test_health_privacy_posture_present(client):
    body = client.get("/api/health").json()
    assert "privacy" in body


def test_health_privacy_telemetry_disabled(client):
    privacy = client.get("/api/health").json()["privacy"]
    assert privacy["telemetry_enabled"] is False


def test_health_privacy_raw_audio_disabled(client):
    privacy = client.get("/api/health").json()["privacy"]
    assert privacy["save_raw_audio"] is False


def test_health_privacy_posture_has_all_fields(client):
    privacy = client.get("/api/health").json()["privacy"]
    assert "telemetry_enabled" in privacy
    assert "save_transcripts" in privacy
    assert "save_raw_audio" in privacy
    assert "crash_logging_enabled" in privacy


def test_health_stt_field_present(client):
    body = client.get("/api/health").json()
    assert "stt" in body


def test_health_stt_worker_id(client):
    stt = client.get("/api/health").json()["stt"]
    # Default config uses whisper_cpp; no binary in test env → unavailable.
    assert stt["worker_id"] == "whisper_cpp"


def test_health_stt_worker_name(client):
    stt = client.get("/api/health").json()["stt"]
    assert "whisper" in stt["worker_name"].lower()


def test_health_stt_status_unavailable_when_no_runtime(client):
    stt = client.get("/api/health").json()["stt"]
    # No binary installed in the test environment.
    assert stt["status"] == "unavailable"


def test_health_stt_checked_at_present(client):
    stt = client.get("/api/health").json()["stt"]
    assert stt["checked_at"]


def test_health_last_benchmark_null_initially(client):
    body = client.get("/api/health").json()
    assert "last_benchmark" in body
    assert body["last_benchmark"] is None


def test_health_last_benchmark_populated_after_benchmark(client):
    client.post("/api/models/benchmark", json={})
    body = client.get("/api/health").json()
    assert body["last_benchmark"] is not None
    assert "tokens_per_sec" in body["last_benchmark"]
    assert isinstance(body["last_benchmark"]["warnings"], list)
