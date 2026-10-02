# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

import convsim_core.app as app_mod
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig


@pytest.fixture(scope="session")
def _absent_official_packs_dir(tmp_path_factory):
    """A path that does not exist, resolved once for the whole session."""
    return tmp_path_factory.mktemp("no_official_packs") / "absent"


@pytest.fixture(autouse=True)
def _default_official_packs_dir_away(_absent_official_packs_dir, monkeypatch):
    """Keep startup pack seeding out of tests that never asked for it.

    ``ServiceConfig.official_packs_dir`` defaults to the repo's bundled
    ``packs/official``, so any app built from a config that does not override it
    re-imports every official pack into that test's fresh database on startup —
    a per-test cost that grows with each pack the project ships. The shared
    ``tmp_config`` below already points the field at a throwaway path for that
    reason; this fixture extends the same default to the file-local configs that
    construct ``ServiceConfig`` themselves.

    ``CONVSIM_OFFICIAL_PACKS_DIR`` is the env override for the field, and
    pydantic-settings ranks explicit constructor arguments above the
    environment, so a test that genuinely needs the bundled packs (test_edition,
    test_pack_seeder, the flyting end-to-end tests) still gets them by passing
    ``official_packs_dir=`` and is unaffected.
    """
    monkeypatch.setenv("CONVSIM_OFFICIAL_PACKS_DIR", str(_absent_official_packs_dir))


@pytest.fixture(autouse=True)
def _isolate_data_migration(tmp_path_factory, monkeypatch):
    """Keep create_app()'s legacy-data migration from touching the real HOME.

    create_app() resolves the platform data root and legacy ~/.convsim
    directory directly via convsim_core.paths — independent of the injected
    ServiceConfig — to decide whether to migrate. Without isolation, running the
    suite on a developer machine that still has a populated ~/.convsim and an
    empty platform root would trigger a real, on-disk migration into the user's
    real application-data directory. Redirect both to throwaway tmp locations
    (the legacy dir intentionally left absent) so needs_migration() is always a
    no-op during tests. Individual tests that exercise migration explicitly
    re-patch these on app_mod inside the test body, which overrides this
    fixture.
    """
    isolated_root = tmp_path_factory.mktemp("isolated_platform_root")
    isolated_legacy = tmp_path_factory.mktemp("isolated_legacy_home") / ".convsim"
    monkeypatch.setattr(app_mod, "platform_data_root", lambda: isolated_root)
    monkeypatch.setattr(app_mod, "legacy_convsim_dir", lambda: isolated_legacy)


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
        cache_dir=str(tmp_path / "cache"),
        crash_bundles_dir=str(tmp_path / "crashes"),
        # Isolate models_dir to tmp_path so eager directory creation on startup
        # does not touch the real platform models directory under the home dir.
        models_dir=str(tmp_path / "models" / "llm"),
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
