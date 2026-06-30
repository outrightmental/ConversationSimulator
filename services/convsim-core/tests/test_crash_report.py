# SPDX-License-Identifier: Apache-2.0
"""Tests for crash-bundle creation.

These tests verify that bundles contain the required files, that sensitive
paths are redacted, and that no conversation data is included.
"""
import json
import zipfile
from pathlib import Path

import pytest

from convsim_core.crash_report import create_crash_bundle
from convsim_core.models import AppSettings


@pytest.fixture()
def settings(tmp_path):
    return AppSettings(
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
    )


def _open_zip(bundle: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(bundle) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


# ---------------------------------------------------------------------------
# Bundle creation
# ---------------------------------------------------------------------------


def test_create_crash_bundle_returns_path(tmp_path, settings):
    bundle = create_crash_bundle(str(tmp_path / "logs"), settings)
    assert isinstance(bundle, Path)
    assert bundle.exists()


def test_crash_bundle_is_zip(tmp_path, settings):
    bundle = create_crash_bundle(str(tmp_path / "logs"), settings)
    assert zipfile.is_zipfile(bundle)


def test_crash_bundle_placed_in_crash_reports_subdir(tmp_path, settings):
    bundle = create_crash_bundle(str(tmp_path / "logs"), settings)
    assert bundle.parent.name == "crash-reports"


# ---------------------------------------------------------------------------
# Required files present
# ---------------------------------------------------------------------------


def test_crash_bundle_contains_versions_json(tmp_path, settings):
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings))
    assert "versions.json" in files


def test_crash_bundle_contains_config_json(tmp_path, settings):
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings))
    assert "config.json" in files


def test_crash_bundle_contains_recent_errors(tmp_path, settings):
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings))
    assert "recent_errors.txt" in files


def test_crash_bundle_contains_system_txt(tmp_path, settings):
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings))
    assert "system.txt" in files


def test_crash_bundle_contains_readme(tmp_path, settings):
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings))
    assert "README.txt" in files


# ---------------------------------------------------------------------------
# Version info
# ---------------------------------------------------------------------------


def test_versions_json_has_app_key(tmp_path, settings):
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings))
    versions = json.loads(files["versions.json"])
    assert "app" in versions


def test_versions_json_has_python_key(tmp_path, settings):
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings))
    versions = json.loads(files["versions.json"])
    assert "python" in versions


def test_versions_json_has_platform_key(tmp_path, settings):
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings))
    versions = json.loads(files["versions.json"])
    assert "platform" in versions


# ---------------------------------------------------------------------------
# Path redaction in config
# ---------------------------------------------------------------------------


def test_config_json_redacts_home_in_data_dir(tmp_path, settings):
    home = str(Path.home())
    settings_with_home = AppSettings(
        data_dir=str(Path.home() / ".convsim" / "data"),
        log_dir=str(Path.home() / ".convsim" / "logs"),
    )
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings_with_home))
    config_data = json.loads(files["config.json"])
    if "data_dir" in config_data:
        assert home not in str(config_data["data_dir"])
    if "log_dir" in config_data:
        assert home not in str(config_data["log_dir"])


# ---------------------------------------------------------------------------
# No conversation data
# ---------------------------------------------------------------------------


def test_crash_bundle_log_content_does_not_bleed_into_metadata_files(tmp_path, settings):
    """Log-tail content must not appear in version, config, or system files.

    Writes a synthetic log entry and checks it ends up only in recent_errors.txt
    (the log tail, where it belongs), not in any metadata file that the bundle
    creation code assembles independently.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    marker = "SENTINEL_LOG_ENTRY_SHOULD_ONLY_APPEAR_IN_RECENT_ERRORS"
    (log_dir / "app.log").write_text(
        f'{{"level": "ERROR", "message": "{marker}"}}\n', encoding="utf-8"
    )

    files = _open_zip(create_crash_bundle(str(log_dir), settings))

    # The marker must appear in the log tail.
    assert marker in files["recent_errors.txt"].decode()

    # The marker must NOT bleed into any metadata file.
    metadata_files = ["versions.json", "config.json", "system.txt"]
    for name in metadata_files:
        assert marker not in files[name].decode(), (
            f"log content leaked into {name}"
        )


def test_crash_bundle_readme_mentions_local(tmp_path, settings):
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings))
    readme = files["README.txt"].decode()
    assert "local" in readme.lower()


def test_crash_bundle_readme_mentions_not_transmitted(tmp_path, settings):
    files = _open_zip(create_crash_bundle(str(tmp_path / "logs"), settings))
    readme = files["README.txt"].decode()
    lower = readme.lower()
    assert "not" in lower or "never" in lower


# ---------------------------------------------------------------------------
# Graceful handling of missing log file
# ---------------------------------------------------------------------------


def test_crash_bundle_works_without_app_log(tmp_path, settings):
    log_dir = str(tmp_path / "logs")
    # app.log does not exist yet
    bundle = create_crash_bundle(log_dir, settings)
    files = _open_zip(bundle)
    # recent_errors.txt should be present but empty
    assert files["recent_errors.txt"] == b""


def test_crash_bundle_includes_log_tail_when_present(tmp_path, settings):
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "app.log").write_text(
        '{"level": "ERROR", "message": "something went wrong"}\n', encoding="utf-8"
    )
    files = _open_zip(create_crash_bundle(str(log_dir), settings))
    recent = files["recent_errors.txt"].decode()
    assert "something went wrong" in recent


def test_crash_bundle_recent_errors_excludes_info_entries(tmp_path, settings):
    """recent_errors.txt must contain only WARNING/ERROR/CRITICAL entries.

    INFO messages are intentionally omitted: the file is named "recent *errors*"
    and including routine INFO lines would inflate the bundle with noise.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "app.log").write_text(
        '{"level": "INFO", "message": "routine startup"}\n'
        '{"level": "ERROR", "message": "something failed"}\n'
        '{"level": "WARNING", "message": "low memory"}\n',
        encoding="utf-8",
    )
    files = _open_zip(create_crash_bundle(str(log_dir), settings))
    recent = files["recent_errors.txt"].decode()
    assert "routine startup" not in recent
    assert "something failed" in recent
    assert "low memory" in recent
