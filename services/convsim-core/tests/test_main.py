# SPDX-License-Identifier: Apache-2.0
"""Entry-point guards for convsim-core's uvicorn bootstrap.

Two separate regressions are pinned here.

**Issue #352 — the app object, not an import string.** In a PyInstaller bundle
the entry script runs as ``__main__``, so the module ``convsim_core.main`` is
NOT present in the frozen importer's namespace. Handing uvicorn an import
string makes it call ``importlib.import_module("convsim_core.main")``, which
raises ModuleNotFoundError and kills the binary on any invocation. Passing the
object directly avoids the frozen-importer lookup entirely, and is safe because
reload=False is the default, so the indirection buys nothing.

**Issue #485 — a shutdown the launcher can ask for.** ``main()`` must own the
``uvicorn.Server`` instance (rather than hand everything to ``uvicorn.run()``)
so the parent-exit watch can set ``should_exit`` and get a *graceful* shutdown,
which is what runs the lifespan teardown that stops the sidecars. Owning the
server also means owning the two things ``uvicorn.run()`` did around it — a
quiet exit on Ctrl-C and a non-zero one when the server never started — so
those are pinned here too.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
import uvicorn
from fastapi import FastAPI

import convsim_core.main as main_mod
from convsim_core import parent_watch


class _FakeServer:
    """Stands in for uvicorn.Server: records the config and the run() call."""

    instances: list["_FakeServer"] = []

    #: Raised out of run(), to stand in for a real server's failure modes.
    raises: BaseException | None = None

    #: What run() reports as `started` — False stands in for a server that
    #: never came up (a bind conflict, a lifespan startup error).
    starts: bool = True

    def __init__(self, config):
        self.config = config
        self.should_exit = False
        self.ran = False
        self.started = False
        _FakeServer.instances.append(self)

    def run(self, sockets=None):
        self.ran = True
        self.started = type(self).starts
        if type(self).raises is not None:
            raise type(self).raises


def _run_main(
    env: dict[str, str] | None = None,
    *,
    raises: BaseException | None = None,
    starts: bool = True,
) -> _FakeServer:
    """Run main() against a fake server and return it."""
    _FakeServer.instances.clear()
    _FakeServer.raises = raises
    _FakeServer.starts = starts
    try:
        with patch.object(uvicorn, "Server", _FakeServer), patch.dict(
            "os.environ", env or {}, clear=False
        ):
            main_mod.main()
    finally:
        _FakeServer.raises = None
        _FakeServer.starts = True
    assert _FakeServer.instances, "main() never constructed a uvicorn.Server"
    return _FakeServer.instances[-1]


def test_main_passes_app_object_not_string():
    """main() must hand uvicorn the ASGI app object, not an import string."""
    server = _run_main()
    app_arg = server.config.app
    assert not isinstance(app_arg, str), (
        f"main() passed an import string {app_arg!r} to uvicorn; "
        "in a PyInstaller bundle this causes a ModuleNotFoundError. "
        "Pass the app object directly instead."
    )
    assert isinstance(app_arg, FastAPI), f"Expected a FastAPI app instance, got {type(app_arg)}"


def test_main_passes_correct_host_and_port():
    """main() forwards host and port from ServiceConfig to uvicorn."""
    server = _run_main()
    assert server.config.host == main_mod._config.host
    assert server.config.port == main_mod._config.port


def test_main_leaves_our_logging_alone():
    """log_config=None, so uvicorn must not reconfigure the logging tree.

    Its default LOGGING_CONFIG sets ``propagate: False`` on the ``uvicorn``
    logger, which would cut uvicorn's own records off from the root handlers
    that write app.log. Those are exactly the lines docs/troubleshooting.md
    tells a player to look for when the engine will not exit (issue #485) —
    `Shutting down`, `Application shutdown complete` — so losing them would
    silently remove the only evidence of how far teardown got.
    """
    assert _run_main().config.log_config is None


def test_main_runs_the_server():
    """main() actually starts the server it built."""
    assert _run_main().ran


def test_main_bounds_the_graceful_shutdown_drain():
    """A stuck connection must not keep the engine alive forever (issue #485)."""
    server = _run_main()
    timeout = server.config.timeout_graceful_shutdown
    assert timeout is not None, (
        "timeout_graceful_shutdown is unset, so uvicorn waits indefinitely for "
        "in-flight requests — one stuck connection would outlive the app window."
    )
    assert 0 < timeout <= 10


def test_request_shutdown_asks_for_a_graceful_stop():
    """request_shutdown() sets the flag uvicorn's run loop polls."""
    server = _FakeServer(config=None)
    assert server.should_exit is False
    main_mod.request_shutdown(server)
    assert server.should_exit is True, (
        "request_shutdown must set should_exit (graceful). force_exit would skip "
        "the lifespan teardown and orphan the sidecars."
    )


def test_main_installs_the_parent_exit_watch_when_enabled():
    """With the launcher opt-in set, main() wires the watch to a graceful stop."""
    captured: list = []
    ran_when_installed: list[bool] = []

    def fake_watch(on_parent_exit, **kwargs):
        captured.append(on_parent_exit)
        ran_when_installed.append(_FakeServer.instances[-1].ran)
        return None

    with patch.object(main_mod, "watch_parent_exit", fake_watch):
        server = _run_main({parent_watch.ENV_VAR: "1"})

    assert captured, "main() did not install a parent-exit watch"
    assert ran_when_installed == [False], (
        "the watch must be installed BEFORE server.run(), which blocks for the "
        "whole session — installed after it, the launcher could never be heard"
    )
    captured[0]()
    assert server.should_exit is True, "the watch callback must request a graceful shutdown"


# ── Behaviour `uvicorn.run()` used to provide and main() now owns ────────────


def test_ctrl_c_does_not_escape_as_a_traceback():
    """Ctrl-C must end an interactive run quietly, as uvicorn.run() did.

    uvicorn handles SIGINT itself (graceful shutdown), then re-raises the
    signal once teardown is done — which arrives here as a KeyboardInterrupt
    out of a server that has already stopped cleanly. Letting it propagate
    would print a spurious traceback and exit 130.
    """
    server = _run_main(raises=KeyboardInterrupt())
    assert server.ran


def test_a_server_that_never_started_exits_non_zero():
    """A core that failed to come up must not look like a clean run."""
    with pytest.raises(SystemExit) as exc:
        _run_main(starts=False)
    assert exc.value.code != 0, (
        "exit 0 from a server that never bound its port tells the launcher "
        "(and release smoke checks) that the engine ran and stopped normally"
    )


def test_a_normal_run_exits_zero():
    """The ordinary path must not trip the startup-failure exit."""
    assert _run_main().started is True
