# SPDX-License-Identifier: Apache-2.0
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging(log_dir: str) -> None:
    """Configure structured JSON logging to a local log file.

    Never logs request bodies — callers must not pass raw conversation text to loggers.
    Call once at startup; subsequent calls are no-ops if handlers are already registered.
    """
    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.INFO)

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / "convsim-core.log"

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(_JsonFormatter())
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(ch)

    # Keep uvicorn access log but at INFO only — it never includes request bodies.
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
