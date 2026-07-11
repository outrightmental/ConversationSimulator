# SPDX-License-Identifier: Apache-2.0
"""Verify that main() passes the ASGI app object to uvicorn, not an import string.

In a PyInstaller bundle the entry script runs as __main__, so the module
convsim_core.main is NOT present in the frozen importer's namespace. Passing
an import string to uvicorn.run() causes uvicorn to call
importlib.import_module("convsim_core.main"), which raises ModuleNotFoundError
and kills the binary on any invocation (issue #352).

Passing the object directly avoids the frozen-importer lookup entirely and is
safe because reload=False is the default, so the indirection buys nothing.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import uvicorn
from fastapi import FastAPI

import convsim_core.main as main_mod


def test_main_passes_app_object_not_string():
    """main() must hand uvicorn.run() the ASGI app object, not an import string."""
    captured: list = []

    def fake_run(app_or_str, **kwargs):
        captured.append(app_or_str)

    with patch.object(uvicorn, "run", fake_run):
        main_mod.main()

    assert captured, "uvicorn.run was never called"
    first_arg = captured[0]
    assert not isinstance(first_arg, str), (
        f"main() passed an import string {first_arg!r} to uvicorn.run(); "
        "in a PyInstaller bundle this causes a ModuleNotFoundError. "
        "Pass the app object directly instead."
    )
    assert isinstance(first_arg, FastAPI), (
        f"Expected a FastAPI app instance, got {type(first_arg)}"
    )


def test_main_passes_correct_host_and_port():
    """main() forwards host and port from ServiceConfig to uvicorn.run()."""
    captured_kwargs: list[dict] = []

    def fake_run(app_or_str, **kwargs):
        captured_kwargs.append(kwargs)

    with patch.object(uvicorn, "run", fake_run):
        main_mod.main()

    assert captured_kwargs
    kw = captured_kwargs[0]
    assert kw["host"] == main_mod._config.host
    assert kw["port"] == main_mod._config.port
    assert kw["log_config"] is None
