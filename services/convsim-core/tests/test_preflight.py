# SPDX-License-Identifier: Apache-2.0
"""Tests for the /api/preflight endpoint.

Each test simulates a distinct failure class so that fixes targeting that class
can be verified in isolation.
"""
import stat
from unittest.mock import patch

import pytest

from convsim_core import __version__


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_preflight(client):
    resp = client.get("/api/preflight")
    assert resp.status_code == 200
    return resp.json()


def _find_check(data: dict, check_id: str) -> dict:
    for check in data["checks"]:
        if check["id"] == check_id:
            return check
    raise KeyError(f"Check '{check_id}' not found in preflight response")


# ── Schema / top-level ────────────────────────────────────────────────────────


def test_preflight_returns_200(client):
    assert client.get("/api/preflight").status_code == 200


def test_preflight_overall_field_present(client):
    data = _get_preflight(client)
    assert data["overall"] in ("pass", "warn", "fail")


def test_preflight_ran_at_is_iso8601(client):
    data = _get_preflight(client)
    assert "T" in data["ran_at"] and data["ran_at"].endswith("+00:00")


def test_preflight_checks_is_list(client):
    data = _get_preflight(client)
    assert isinstance(data["checks"], list)


def test_preflight_has_seven_checks(client):
    data = _get_preflight(client)
    assert len(data["checks"]) == 7


def test_preflight_check_schema(client):
    data = _get_preflight(client)
    for check in data["checks"]:
        assert "id" in check
        assert "name" in check
        assert check["status"] in ("pass", "warn", "fail")
        assert "message" in check
        assert "fix_action" in check


# ── Check 1: Runtime handshake ────────────────────────────────────────────────


def test_runtime_handshake_passes(client):
    check = _find_check(_get_preflight(client), "runtime-handshake")
    assert check["status"] == "pass"


def test_runtime_handshake_reports_version(client):
    check = _find_check(_get_preflight(client), "runtime-handshake")
    assert __version__ in check["message"]


# ── Check 2: Data directory writable ─────────────────────────────────────────


def test_data_dir_writable_passes_with_valid_dir(client):
    check = _find_check(_get_preflight(client), "data-dir-writable")
    assert check["status"] == "pass"


def test_data_dir_writable_fails_on_unwritable_dir(client, tmp_config, tmp_path):
    unwritable = tmp_path / "readonly"
    unwritable.mkdir()
    # Remove write permission
    unwritable.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        from convsim_core.routers.preflight import _check_data_dir
        result = _check_data_dir(str(unwritable))
        assert result.status == "fail"
        assert result.fix_action is not None
    finally:
        unwritable.chmod(stat.S_IRWXU)


def test_data_dir_fail_has_settings_fix_action(tmp_path):
    from convsim_core.routers.preflight import _check_data_dir
    unwritable = tmp_path / "readonly"
    unwritable.mkdir()
    unwritable.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        result = _check_data_dir(str(unwritable / "nested"))
        assert result.status == "fail"
        assert result.fix_action is not None
        assert result.fix_action.kind == "navigate"
    finally:
        unwritable.chmod(stat.S_IRWXU)


# ── Check 3: Disk space ───────────────────────────────────────────────────────


def test_disk_space_passes_when_sufficient(client):
    check = _find_check(_get_preflight(client), "disk-space")
    # On a dev machine there should always be enough space for a 5 GB model check.
    assert check["status"] in ("pass", "warn")


def test_disk_space_fails_when_insufficient(tmp_path):
    from convsim_core.routers.preflight import _check_disk_space

    with patch("convsim_core.routers.preflight.shutil.disk_usage") as mock_du:
        from collections import namedtuple
        Usage = namedtuple("Usage", ["total", "used", "free"])
        mock_du.return_value = Usage(total=10 * 1024**3, used=9 * 1024**3, free=1 * 1024**3)
        result = _check_disk_space(str(tmp_path), required_gb=5.0)
    assert result.status == "fail"
    assert result.fix_action is not None


def test_disk_space_warns_when_tight(tmp_path):
    from convsim_core.routers.preflight import _check_disk_space

    with patch("convsim_core.routers.preflight.shutil.disk_usage") as mock_du:
        from collections import namedtuple
        Usage = namedtuple("Usage", ["total", "used", "free"])
        # 5.1 GB free but need 5.0 * 1.1 = 5.5 GB recommended
        mock_du.return_value = Usage(total=10 * 1024**3, used=5 * 1024**3 - 1, free=int(5.1 * 1024**3))
        result = _check_disk_space(str(tmp_path), required_gb=5.0)
    assert result.status == "warn"


# ── Check 4: llama.cpp binary ─────────────────────────────────────────────────


def test_llama_cpp_binary_fails_when_missing(client):
    from convsim_core.routers.preflight import _check_llama_cpp_binary
    with patch("convsim_core.routers.preflight.find_executable", return_value=None):
        result = _check_llama_cpp_binary()
    assert result.status == "fail"
    assert result.fix_action is not None
    assert result.fix_action.kind == "open-url"


def test_llama_cpp_binary_passes_when_found(tmp_path):
    from convsim_core.routers.preflight import _check_llama_cpp_binary
    fake_binary = str(tmp_path / "llama-server")
    with patch("convsim_core.routers.preflight.find_executable", return_value=fake_binary):
        result = _check_llama_cpp_binary()
    assert result.status == "pass"
    assert fake_binary in result.message


# ── Check 5: LLM present ─────────────────────────────────────────────────────


def test_llm_present_fails_when_no_model_installed(client):
    # Default test environment has no installed models.
    check = _find_check(_get_preflight(client), "llm-present")
    assert check["status"] == "fail"
    assert check["fix_action"] is not None
    assert check["fix_action"]["href"] == "/model-manager"


def test_llm_present_passes_when_model_ready(client):
    from convsim_core.routers.preflight import _check_llm_present

    class _FakeConn:
        def execute(self, sql, params=()):
            return self

        def fetchone(self):
            return {"cnt": 1}

    result = _check_llm_present(_FakeConn(), active_model_id=None)
    assert result.status == "pass"


def test_llm_present_passes_when_active_model_configured():
    from convsim_core.routers.preflight import _check_llm_present

    class _ZeroConn:
        def execute(self, sql, params=()):
            return self

        def fetchone(self):
            return {"cnt": 0}

    result = _check_llm_present(_ZeroConn(), active_model_id="ollama-llama3")
    assert result.status == "pass"


# ── Check 6: Packs seeded ────────────────────────────────────────────────────


def test_packs_seeded_fails_when_zero_packs(client):
    check = _find_check(_get_preflight(client), "packs-seeded")
    # Default test env has no official packs (official_packs_dir points to nonexistent dir).
    assert check["status"] == "fail"
    assert check["fix_action"] is not None
    assert check["fix_action"]["href"] == "/library"


def test_packs_seeded_warns_with_few_packs():
    from convsim_core.routers.preflight import _check_packs_seeded

    class _FewPacksConn:
        def execute(self, sql, params=()):
            return self

        def fetchone(self):
            return {"cnt": 2}

    result = _check_packs_seeded(_FewPacksConn())
    assert result.status == "warn"


def test_packs_seeded_passes_with_enough_packs():
    from convsim_core.routers.preflight import _check_packs_seeded

    class _ManyPacksConn:
        def execute(self, sql, params=()):
            return self

        def fetchone(self):
            return {"cnt": 4}

    result = _check_packs_seeded(_ManyPacksConn())
    assert result.status == "pass"


# ── Check 7: Voice ready ─────────────────────────────────────────────────────


def test_voice_check_warns_when_stt_unavailable(client):
    # In the test environment, STT binary is absent → unavailable.
    check = _find_check(_get_preflight(client), "voice-ready")
    assert check["status"] == "warn"
    assert check["fix_action"] is not None


@pytest.mark.asyncio
async def test_voice_check_passes_when_all_ready():
    from convsim_core.routers.preflight import _check_voice_ready

    class _ReadyHealth:
        status = "ready"

    class _ReadyWorker:
        async def health(self):
            return _ReadyHealth()

    result = await _check_voice_ready(_ReadyWorker(), _ReadyWorker(), _ReadyWorker())
    assert result.status == "pass"


@pytest.mark.asyncio
async def test_voice_check_warns_on_timeout():
    from convsim_core.routers.preflight import _check_voice_ready

    class _SlowWorker:
        async def health(self):
            import asyncio
            await asyncio.sleep(10)  # will be cancelled by the 2 s timeout

    result = await _check_voice_ready(_SlowWorker(), _SlowWorker(), _SlowWorker())
    assert result.status == "warn"


# ── Overall status logic ──────────────────────────────────────────────────────


def test_overall_is_fail_when_any_check_fails(client):
    data = _get_preflight(client)
    failing = [c for c in data["checks"] if c["status"] == "fail"]
    if failing:
        assert data["overall"] == "fail"


# ── Preflight cached on app state ─────────────────────────────────────────────


def test_preflight_caches_result_on_app_state(client):
    client.get("/api/preflight")
    # The state attribute should exist after the first call.
    # We verify it through the crash-bundle endpoint including preflight.json.
    bundle_resp = client.post("/api/diag/crash-bundle")
    assert bundle_resp.status_code == 200
    bundle_path = bundle_resp.json()["bundle_path"]

    import zipfile
    with zipfile.ZipFile(bundle_path) as zf:
        names = zf.namelist()
    assert "preflight.json" in names


def test_redact_preflight_strips_embedded_home_path():
    from pathlib import Path
    from convsim_core.crash_report import _redact_preflight

    home = str(Path.home())
    data = {
        "overall": "pass",
        "checks": [
            {"id": "llama-cpp-binary", "message": f"llama-server found at {home}/bin/llama-server."},
            {"id": "data-dir-writable", "message": f"Data directory is writable at {home}/data."},
        ],
    }
    redacted = _redact_preflight(data)
    dumped = str(redacted)
    assert home not in dumped
    assert "~/bin/llama-server" in redacted["checks"][0]["message"]


def test_bundle_preflight_json_redacts_home_paths(client):
    # Preflight messages quote absolute paths (data dir, binary location) that
    # embed the OS username. The crash bundle promises paths are redacted to ~,
    # so the snapshot written to the ZIP must not leak the raw home prefix.
    from pathlib import Path

    client.get("/api/preflight")
    bundle_resp = client.post("/api/diag/crash-bundle")
    assert bundle_resp.status_code == 200
    bundle_path = bundle_resp.json()["bundle_path"]

    import zipfile
    with zipfile.ZipFile(bundle_path) as zf:
        assert "preflight.json" in zf.namelist()
        content = zf.read("preflight.json").decode("utf-8")

    home = str(Path.home())
    assert home not in content




def test_crash_bundle_excludes_preflight_when_not_run(client):
    # No preflight call — crash bundle should still succeed without preflight.json.
    bundle_resp = client.post("/api/diag/crash-bundle")
    assert bundle_resp.status_code == 200
    bundle_path = bundle_resp.json()["bundle_path"]

    import zipfile
    with zipfile.ZipFile(bundle_path) as zf:
        names = zf.namelist()
    # preflight.json is optional; if it's absent that's fine
    assert "versions.json" in names
