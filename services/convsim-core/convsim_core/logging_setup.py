# SPDX-License-Identifier: Apache-2.0
import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

# 5 MB per file, 3 rotated backups → ≤ 20 MB total per log channel.
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


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


class _RuntimeFilter(logging.Filter):
    """Accept only log records from the runtimes sub-package."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("convsim_core.runtimes")


def configure_logging(log_dir: str, debug: bool = False) -> None:
    """Configure structured JSON logging to local rotating log files.

    Writes two rotating files under log_dir:
    - app.log     — all application events (INFO+ by default, DEBUG if debug=True)
    - runtime.log — llm/stt/tts runtime adapter messages only

    Callers MUST NOT pass raw transcripts, prompts, or audio content to any
    logger.  Use the helpers in convsim_core.redaction when logging values that
    may be derived from user input.

    Call once at startup; subsequent calls are no-ops if handlers are already
    registered on the root logger.
    """
    root = logging.getLogger()
    if root.handlers:
        return

    level = logging.DEBUG if debug else logging.INFO
    root.setLevel(level)

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    json_fmt = _JsonFormatter()

    # app.log — receives all events from every logger.
    app_fh = logging.handlers.RotatingFileHandler(
        Path(log_dir) / "app.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    app_fh.setFormatter(json_fmt)
    root.addHandler(app_fh)

    # runtime.log — receives only convsim_core.runtimes.* events.
    rt_fh = logging.handlers.RotatingFileHandler(
        Path(log_dir) / "runtime.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    rt_fh.setFormatter(json_fmt)
    rt_fh.addFilter(_RuntimeFilter())

    # Attach to the runtimes logger so it propagates to app.log as well.
    rt_logger = logging.getLogger("convsim_core.runtimes")
    rt_logger.addHandler(rt_fh)
    rt_logger.propagate = True

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(ch)

    # Keep uvicorn access log but at INFO only — it never includes request bodies.
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
