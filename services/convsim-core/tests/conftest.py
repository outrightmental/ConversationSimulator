# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig


@pytest.fixture()
def tmp_config(tmp_path, monkeypatch):
    # Pin whisper-cli to a nonexistent path so the default whisper_cpp worker
    # always reports UNAVAILABLE in tests, regardless of what is installed on
    # the developer's machine.
    monkeypatch.setenv("CONVSIM_WHISPER_CPP_BINARY_PATH", str(tmp_path / "no-whisper-cli"))
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        packs_dir=str(tmp_path / "packs"),
        exports_dir=str(tmp_path / "exports"),
        # Allow folder imports from tmp_path so integration tests can use
        # make_pack_dir() without placing packs inside packs_dir itself.
        local_dev_packs_dir=str(tmp_path),
        # Point away from the real official packs directory so the startup
        # seeder does not populate the test database on every test run.
        official_packs_dir=str(tmp_path / "no-official-packs"),
    )


@pytest.fixture()
def client(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        yield c
