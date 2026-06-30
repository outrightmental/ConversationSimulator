# SPDX-License-Identifier: Apache-2.0
"""
Entry point for convsim-core.

Launch options:
  python -m convsim_core.main          (via main())
  uvicorn convsim_core.main:app        (direct ASGI import)
  convsim-core                         (installed script)
"""
import uvicorn

from convsim_core.app import create_app
from convsim_core.config import ServiceConfig

# Module-level ASGI app for `uvicorn convsim_core.main:app`.
_config = ServiceConfig()
app = create_app(_config)


def main() -> None:
    uvicorn.run(
        "convsim_core.main:app",
        host=_config.host,
        port=_config.port,
        log_config=None,
        reload=False,
    )


if __name__ == "__main__":
    main()
