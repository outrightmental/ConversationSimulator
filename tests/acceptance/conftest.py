# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for the acceptance test suite.

Prerequisites:
  pip install -e "packages/prompt-composer[dev]"
  pip install -e "services/convsim-core[dev]"

Run from the repo root:
  python -m pytest tests/acceptance/ -v
"""
import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig


@pytest.fixture()
def tmp_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        local_dev_packs_dir=str(tmp_path),
    )


@pytest.fixture()
def client(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        yield c


_BEHAVIORAL_INTERVIEW_SETUP = {
    "scenario_id": "behavioral_interview",
    "difficulty": "normal",
    "player_role_name": "Acceptance Tester",
    "language": "en",
    "input_mode": "text-only",
    "tts_enabled": False,
    "show_state_meters": False,
    "save_transcript": True,
    "seed": None,
}
