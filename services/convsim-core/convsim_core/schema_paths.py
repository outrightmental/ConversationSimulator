# SPDX-License-Identifier: Apache-2.0
"""Schema file path resolution for convsim-core.

Provides CWD-independent access to bundled JSON schema files.
Schema files are included in the convsim_core package under schemas/,
so importlib.resources locates them regardless of where the process
was started or whether the package is installed from a wheel.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

_SCHEMAS_PKG = files("convsim_core") / "schemas"

SCHEMA_NAMES: tuple[str, ...] = (
    "pack.schema.json",
    "scenario.schema.json",
    "npc.schema.json",
    "rubric.schema.json",
    "safety.schema.json",
    "turn-output.schema.json",
    "debrief.schema.json",
)


def get_schema_text(name: str) -> str:
    """Return the raw text content of a named schema file.

    Args:
        name: Filename, e.g. ``"pack.schema.json"``.

    Raises:
        FileNotFoundError: If ``name`` is not a known schema.
        ValueError: If ``name`` is not in SCHEMA_NAMES.
    """
    if name not in SCHEMA_NAMES:
        raise ValueError(
            f"Unknown schema {name!r}. Valid names: {', '.join(SCHEMA_NAMES)}"
        )
    return (_SCHEMAS_PKG / name).read_text(encoding="utf-8")


def get_schema(name: str) -> dict[str, Any]:
    """Parse and return a named schema as a Python dict."""
    return json.loads(get_schema_text(name))  # type: ignore[no-any-return]


def get_all_schemas() -> dict[str, dict[str, Any]]:
    """Return all schemas keyed by filename."""
    return {name: get_schema(name) for name in SCHEMA_NAMES}
