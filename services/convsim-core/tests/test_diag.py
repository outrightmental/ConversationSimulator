# SPDX-License-Identifier: Apache-2.0
"""Tests for the /api/diag endpoints."""
import json
import socket
import zipfile
from pathlib import Path


def test_get_logs_folder_returns_200(client):
    response = client.get("/api/diag/logs-folder")
    assert response.status_code == 200


def test_get_logs_folder_returns_string_path(client):
    data = client.get("/api/diag/logs-folder").json()
    assert "logs_folder" in data
    assert isinstance(data["logs_folder"], str)


def test_get_logs_folder_is_absolute(client):
    data = client.get("/api/diag/logs-folder").json()
    assert Path(data["logs_folder"]).is_absolute()


def test_post_crash_bundle_returns_200(client):
    response = client.post("/api/diag/crash-bundle")
    assert response.status_code == 200


def test_post_crash_bundle_returns_bundle_path(client):
    data = client.post("/api/diag/crash-bundle").json()
    assert "bundle_path" in data
    assert isinstance(data["bundle_path"], str)


def test_post_crash_bundle_file_exists(client):
    data = client.post("/api/diag/crash-bundle").json()
    assert Path(data["bundle_path"]).exists()


def test_post_crash_bundle_is_valid_zip(client):
    data = client.post("/api/diag/crash-bundle").json()
    assert zipfile.is_zipfile(data["bundle_path"])


def test_post_crash_bundle_contains_required_files(client):
    data = client.post("/api/diag/crash-bundle").json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        names = zf.namelist()
    assert "versions.json" in names
    assert "config.json" in names
    assert "recent_errors.txt" in names
    assert "system.txt" in names
    assert "README.txt" in names


def test_post_crash_bundle_notice_present(client):
    data = client.post("/api/diag/crash-bundle").json()
    assert "notice" in data
    assert len(data["notice"]) > 0


def test_post_crash_bundle_notice_mentions_local(client):
    data = client.post("/api/diag/crash-bundle").json()
    notice = data["notice"].lower()
    assert "local" in notice or "manually" in notice


def test_post_crash_bundle_notice_not_transmitted(client):
    data = client.post("/api/diag/crash-bundle").json()
    notice = data["notice"].lower()
    assert "never" in notice or "not" in notice


def test_post_crash_bundle_versions_has_app(client):
    data = client.post("/api/diag/crash-bundle").json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        versions = json.loads(zf.read("versions.json"))
    assert "app" in versions


def test_post_crash_bundle_written_to_crash_bundles_dir(client):
    """The bundle must land in the exposed crash_bundles_dir, not the log dir.

    issue #221 exposes an 'Open Crash Bundles Folder' action; the bundles the
    user is directed to must actually be written into that folder.
    """
    crash_bundles_dir = Path(client.app.state.service_config.crash_bundles_dir).resolve()
    data = client.post("/api/diag/crash-bundle").json()
    bundle_path = Path(data["bundle_path"]).resolve()
    assert bundle_path.parent == crash_bundles_dir, (
        f"crash bundle written to {bundle_path.parent}, not crash_bundles_dir {crash_bundles_dir}"
    )


# ---------------------------------------------------------------------------
# /api/diag/beta-report
# ---------------------------------------------------------------------------

def test_post_beta_report_returns_200(client):
    response = client.post("/api/diag/beta-report", json={})
    assert response.status_code == 200


def test_post_beta_report_returns_bundle_path(client):
    data = client.post("/api/diag/beta-report", json={}).json()
    assert "bundle_path" in data
    assert isinstance(data["bundle_path"], str)


def test_post_beta_report_file_exists(client):
    data = client.post("/api/diag/beta-report", json={}).json()
    assert Path(data["bundle_path"]).exists()


def test_post_beta_report_is_valid_zip(client):
    data = client.post("/api/diag/beta-report", json={}).json()
    assert zipfile.is_zipfile(data["bundle_path"])


def test_post_beta_report_contains_required_files(client):
    data = client.post("/api/diag/beta-report", json={}).json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        names = zf.namelist()
    assert "versions.json" in names
    assert "config.json" in names
    assert "preflight.json" in names
    assert "recent_errors.txt" in names
    assert "system.txt" in names
    assert "README.txt" in names


def test_post_beta_report_no_session_metadata_by_default(client):
    data = client.post("/api/diag/beta-report", json={}).json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        names = zf.namelist()
    assert "session_metadata.json" not in names


def test_post_beta_report_with_session_metadata_opt_in(client):
    data = client.post(
        "/api/diag/beta-report", json={"include_session_metadata": True}
    ).json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        names = zf.namelist()
    assert "session_metadata.json" in names


def test_post_beta_report_session_metadata_is_null_when_no_sessions(client):
    data = client.post(
        "/api/diag/beta-report", json={"include_session_metadata": True}
    ).json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        meta = json.loads(zf.read("session_metadata.json"))
    assert meta is None


def test_post_beta_report_preflight_has_runtime_key(client):
    data = client.post("/api/diag/beta-report", json={}).json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        preflight = json.loads(zf.read("preflight.json"))
    assert "runtime" in preflight


def test_post_beta_report_includes_self_test_snapshot(client):
    # Once the self-test pipeline has run, its structured 7-check snapshot must
    # be embedded in the beta report (issue #301: preflight JSON in the beta
    # report flow), not just the ad-hoc runtime/stt/tts health.
    client.get("/api/preflight")
    data = client.post("/api/diag/beta-report", json={}).json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        preflight = json.loads(zf.read("preflight.json"))
    assert "self_test" in preflight
    self_test = preflight["self_test"]
    assert self_test["overall"] in ("pass", "warn", "fail")
    assert len(self_test["checks"]) == 7


def test_post_beta_report_omits_self_test_when_not_run(client):
    # A beta report created before any self-test still succeeds and simply omits
    # the self_test key rather than failing.
    data = client.post("/api/diag/beta-report", json={}).json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        preflight = json.loads(zf.read("preflight.json"))
    assert "self_test" not in preflight


def test_post_beta_report_versions_has_app(client):
    data = client.post("/api/diag/beta-report", json={}).json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        versions = json.loads(zf.read("versions.json"))
    assert "app" in versions


def test_post_beta_report_returns_manifest(client):
    data = client.post("/api/diag/beta-report", json={}).json()
    assert "manifest" in data
    assert isinstance(data["manifest"], list)
    assert len(data["manifest"]) > 0


def test_post_beta_report_manifest_excludes_session_metadata_by_default(client):
    data = client.post("/api/diag/beta-report", json={}).json()
    assert not any("session_metadata" in item for item in data["manifest"])


def test_post_beta_report_manifest_includes_session_metadata_when_opted_in(client):
    data = client.post(
        "/api/diag/beta-report", json={"include_session_metadata": True}
    ).json()
    assert any("session_metadata" in item for item in data["manifest"])


def test_post_beta_report_notice_mentions_local(client):
    data = client.post("/api/diag/beta-report", json={}).json()
    notice = data["notice"].lower()
    assert "local" in notice or "manually" in notice


def test_post_beta_report_written_to_crash_bundles_dir(client):
    crash_bundles_dir = Path(client.app.state.service_config.crash_bundles_dir).resolve()
    data = client.post("/api/diag/beta-report", json={}).json()
    bundle_path = Path(data["bundle_path"]).resolve()
    assert bundle_path.parent == crash_bundles_dir


def test_beta_report_preflight_redacts_home_paths(tmp_path):
    """Home-directory prefixes in the preflight snapshot must be redacted.

    The STT health payload embeds an absolute model path (and error messages
    reference it) that leak the OS username unless redacted — this asserts the
    bundle honours its own privacy promise for preflight.json.
    """
    from convsim_core.beta_report import create_beta_report_bundle
    from convsim_core.models import AppSettings

    home = str(Path.home())
    leaky_path = f"{home}/.convsim/models/stt/ggml-base.en.bin"
    preflight = {
        "runtime": {"runtime_id": "fake", "status": "ready"},
        "stt": {
            "worker_id": "whisper",
            "model_path": leaky_path,
            "message": f"STT model not found at {leaky_path!r}.",
        },
        "tts": {"worker_id": "piper", "status": "ready"},
    }

    bundle_path = create_beta_report_bundle(
        log_dir=str(tmp_path),
        settings=AppSettings(data_dir=str(tmp_path), log_dir=str(tmp_path)),
        preflight=preflight,
        bundle_dir=str(tmp_path),
    )

    with zipfile.ZipFile(bundle_path) as zf:
        raw = zf.read("preflight.json").decode("utf-8")

    assert home not in raw, f"preflight.json leaked home prefix: {raw}"
    assert "~/.convsim/models/stt/ggml-base.en.bin" in raw


def test_post_beta_report_makes_no_outbound_network_calls(client):
    """Creating a beta report must not make any outbound (non-loopback) calls.

    This extends the issue #218 guard suite to cover the beta report path.
    """
    _LOOPBACK = frozenset({"localhost", "::1", "[::1]", "0.0.0.0", "::"})

    def _is_local(family, address) -> bool:
        if family == getattr(socket, "AF_UNIX", object()):
            return True
        if not isinstance(address, tuple) or not address:
            return True
        host = str(address[0]).lower()
        if host in _LOOPBACK or host.endswith(".localhost"):
            return True
        return host.startswith("127.")

    attempts: list = []
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex

    def guarded_connect(self, address, *args, **kwargs):  # noqa: ANN001
        if not _is_local(self.family, address):
            attempts.append(address)
            raise OSError(f"Outbound call blocked: {address!r}")
        return orig_connect(self, address, *args, **kwargs)

    def guarded_connect_ex(self, address, *args, **kwargs):  # noqa: ANN001
        if not _is_local(self.family, address):
            attempts.append(address)
            raise OSError(f"Outbound call blocked: {address!r}")
        return orig_connect_ex(self, address, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    try:
        response = client.post("/api/diag/beta-report", json={})
    finally:
        socket.socket.connect = orig_connect
        socket.socket.connect_ex = orig_connect_ex

    assert response.status_code == 200, response.text
    assert attempts == [], (
        f"Beta report endpoint made {len(attempts)} outbound network call(s): {attempts}"
    )


# ---------------------------------------------------------------------------
# Crash-bundle embedding (#288 — "crash bundle if present")
# ---------------------------------------------------------------------------

def test_beta_report_omits_crash_bundle_when_none_present(client):
    """With no crash bundle on disk, the beta report must not contain one."""
    data = client.post("/api/diag/beta-report", json={}).json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        names = zf.namelist()
    assert "crash-bundle.zip" not in names
    assert not any("crash-bundle" in item for item in data["manifest"])


def test_beta_report_embeds_existing_crash_bundle(client):
    """When a crash bundle exists, the beta report embeds it and lists it."""
    # Create a crash bundle first — it lands in crash_bundles_dir.
    crash = client.post("/api/diag/crash-bundle").json()
    assert Path(crash["bundle_path"]).name.startswith("crash-")

    data = client.post("/api/diag/beta-report", json={}).json()
    with zipfile.ZipFile(data["bundle_path"]) as zf:
        names = zf.namelist()
        embedded = zf.read("crash-bundle.zip")
    assert "crash-bundle.zip" in names
    assert any("crash-bundle" in item for item in data["manifest"])
    # The embedded entry is a real ZIP with the same bytes as the crash bundle.
    assert embedded == Path(crash["bundle_path"]).read_bytes()


def test_latest_crash_bundle_picks_newest(tmp_path):
    """latest_crash_bundle returns the newest crash-*.zip and ignores others."""
    from convsim_core.beta_report import latest_crash_bundle

    assert latest_crash_bundle(tmp_path) is None
    (tmp_path / "crash-20260101T000000Z.zip").write_text("old")
    (tmp_path / "crash-20260709T120000Z.zip").write_text("new")
    # A beta-report ZIP in the same dir must never be selected.
    (tmp_path / "beta-report-20260709T130000Z.zip").write_text("beta")

    latest = latest_crash_bundle(tmp_path)
    assert latest is not None
    assert latest.name == "crash-20260709T120000Z.zip"
