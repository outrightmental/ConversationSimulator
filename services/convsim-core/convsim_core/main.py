# SPDX-License-Identifier: Apache-2.0
"""
Entry point for convsim-core.

Launch options:
  python -m convsim_core.main          (via main())
  uvicorn convsim_core.main:app        (direct ASGI import)
  convsim-core                         (installed script)
"""
import sys

import uvicorn
from uvicorn.config import STARTUP_FAILURE

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.parent_watch import watch_parent_exit

# Module-level ASGI app for `uvicorn convsim_core.main:app`.
_config = ServiceConfig()
app = create_app(_config)

#: How long a shutdown may wait for in-flight requests to drain before their
#: tasks are cancelled. Unbounded by default in uvicorn, which would let one
#: stuck connection keep the engine alive forever after the desktop shell has
#: already quit (issue #485). Three seconds is generous for a localhost API
#: whose only client — the app window — is already gone by then; the lifespan
#: teardown that stops the sidecars runs after this drain either way.
GRACEFUL_SHUTDOWN_TIMEOUT = 3.0


def request_shutdown(server: uvicorn.Server) -> None:
    """Ask a running uvicorn server to stop gracefully.

    Safe to call from any thread: uvicorn's run loop polls this flag, so no
    cross-thread signalling or event-loop handle is involved. Graceful matters
    — it is what runs the FastAPI lifespan teardown, and therefore what stops
    the supervised sidecars (``llama-server``, Kokoro) instead of orphaning
    them.
    """
    server.should_exit = True


def main() -> None:
    # The app *object*, never an import string: in a PyInstaller bundle the
    # entry script runs as __main__, so uvicorn's import of
    # "convsim_core.main" would fail (issue #352). See tests/test_main.py.
    config = uvicorn.Config(
        app,
        host=_config.host,
        port=_config.port,
        log_config=None,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_TIMEOUT,
    )
    server = uvicorn.Server(config)

    # Exit when the desktop shell that launched us does. No-op unless the
    # launcher opted in via CONVSIM_SHUTDOWN_ON_STDIN_EOF (issue #485).
    watch_parent_exit(lambda: request_shutdown(server))

    # The two things `uvicorn.run()` did for us that `Server.run()` does not.
    #
    # Ctrl-C: uvicorn's own SIGINT handler shuts the server down gracefully and
    # then re-raises the signal so the terminal sees the expected exit, which
    # surfaces here as a KeyboardInterrupt *after* teardown has already
    # finished. Letting it escape would end every interactive run with a
    # spurious traceback and exit code 130.
    try:
        server.run()
    except KeyboardInterrupt:
        pass

    # Startup failure: uvicorn exits non-zero so a launcher can tell "never
    # came up" from "ran and stopped". `started` stays True once startup
    # succeeded, so this only fires when the server never got that far.
    if not server.started:
        sys.exit(STARTUP_FAILURE)


if __name__ == "__main__":
    main()
