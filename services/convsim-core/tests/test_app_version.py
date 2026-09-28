# SPDX-License-Identifier: Apache-2.0
"""Tests for convsim_core.app_version — the version diagnostics report (issue #490)."""
import json
import subprocess
import sys
import zipfile

import pytest

from convsim_core import __version__
from convsim_core import app_version as app_version_module
from convsim_core.app_version import APP_VERSION_ENV, app_version
from convsim_core.beta_report import create_beta_report_bundle
from convsim_core.crash_report import create_crash_bundle
from convsim_core.log_excerpt import build_log_excerpt
from convsim_core.models import AppSettings


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """Start every test with no shell-provided version and a cold git cache."""
    monkeypatch.delenv(APP_VERSION_ENV, raising=False)
    app_version_module._source_checkout_commit.cache_clear()
    yield
    app_version_module._source_checkout_commit.cache_clear()


def _fake_git(monkeypatch, *, stdout="", returncode=0, raises=None):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(app_version_module.subprocess, "run", fake_run)
    return calls


# ── Shell-provided version (packaged builds) ─────────────────────────────────


def test_env_version_is_reported_in_tag_form(monkeypatch):
    monkeypatch.setenv(APP_VERSION_ENV, "0.2.7")
    assert app_version() == "v0.2.7"


def test_env_prerelease_version_keeps_its_suffix(monkeypatch):
    monkeypatch.setenv(APP_VERSION_ENV, "0.2.2-beta.1")
    assert app_version() == "v0.2.2-beta.1"


def test_env_version_already_in_tag_form_is_unchanged(monkeypatch):
    monkeypatch.setenv(APP_VERSION_ENV, "v0.2.9")
    assert app_version() == "v0.2.9"


def test_env_version_is_trimmed_and_single_line(monkeypatch):
    monkeypatch.setenv(APP_VERSION_ENV, "  0.2.9\n")
    assert app_version() == "v0.2.9"


def test_env_version_wins_over_source_checkout(monkeypatch):
    calls = _fake_git(monkeypatch, stdout="abc1234\n")
    monkeypatch.setenv(APP_VERSION_ENV, "0.2.9")
    assert app_version() == "v0.2.9"
    assert calls == []


@pytest.mark.parametrize("raw", ["", "   ", "9" * 65])
def test_blank_or_oversized_env_version_is_ignored(monkeypatch, raw):
    _fake_git(monkeypatch, returncode=128)
    monkeypatch.setenv(APP_VERSION_ENV, raw)
    assert app_version() == __version__


# ── Source checkout (development) ────────────────────────────────────────────


def test_source_checkout_reports_commit_hash(monkeypatch):
    calls = _fake_git(monkeypatch, stdout="abc1234\n")
    assert app_version() == "dev-abc1234"
    assert calls == [["git", "rev-parse", "--short", "HEAD"]]


def test_source_checkout_lookup_is_cached(monkeypatch):
    calls = _fake_git(monkeypatch, stdout="abc1234\n")
    app_version()
    app_version()
    assert len(calls) == 1


def test_frozen_build_does_not_shell_out(monkeypatch):
    calls = _fake_git(monkeypatch, stdout="abc1234\n")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert app_version() == __version__
    assert calls == []


# ── Fallback to the package version ──────────────────────────────────────────


def test_not_a_git_checkout_falls_back_to_package_version(monkeypatch):
    _fake_git(monkeypatch, returncode=128)
    assert app_version() == __version__


def test_git_missing_falls_back_to_package_version(monkeypatch):
    _fake_git(monkeypatch, raises=FileNotFoundError("git"))
    assert app_version() == __version__


def test_git_timeout_falls_back_to_package_version(monkeypatch):
    _fake_git(monkeypatch, raises=subprocess.TimeoutExpired("git", 2))
    assert app_version() == __version__


def test_unexpected_git_output_falls_back_to_package_version(monkeypatch):
    _fake_git(monkeypatch, stdout="fatal: something odd\n")
    assert app_version() == __version__


# ── Every diagnostics surface reports it ─────────────────────────────────────


def test_log_excerpt_header_reports_app_version(monkeypatch, tmp_path):
    monkeypatch.setenv(APP_VERSION_ENV, "0.2.7")
    lines = build_log_excerpt(str(tmp_path)).text.splitlines()
    assert "app: v0.2.7" in lines


def _versions_json(bundle) -> dict:
    with zipfile.ZipFile(bundle) as zf:
        return json.loads(zf.read("versions.json"))


def test_crash_bundle_reports_app_version(monkeypatch, tmp_path):
    monkeypatch.setenv(APP_VERSION_ENV, "0.2.7")
    settings = AppSettings(data_dir=str(tmp_path / "data"), log_dir=str(tmp_path / "logs"))
    bundle = create_crash_bundle(str(tmp_path / "logs"), settings)
    assert _versions_json(bundle)["app"] == "v0.2.7"


def test_beta_report_bundle_reports_app_version(monkeypatch, tmp_path):
    monkeypatch.setenv(APP_VERSION_ENV, "0.2.7")
    bundle = create_beta_report_bundle(
        log_dir=str(tmp_path),
        settings=AppSettings(data_dir=str(tmp_path), log_dir=str(tmp_path)),
        preflight={},
        bundle_dir=str(tmp_path),
    )
    assert _versions_json(bundle)["app"] == "v0.2.7"
