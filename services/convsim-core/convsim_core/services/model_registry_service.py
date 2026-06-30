# SPDX-License-Identifier: Apache-2.0
"""Service layer for loading and querying the local model registry.

The registry is sourced from model-registry/registry.yaml and validated
against the bundled JSON schema before being persisted into SQLite.

Callers must pass the registry_path explicitly; there is no hardcoded
default so that this module works in both dev and installed-package contexts.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from convsim_core.schema_paths import get_schema

logger = logging.getLogger(__name__)

_SCHEMA_NAME = "model-registry.schema.json"


class RegistryValidationError(Exception):
    """Raised when registry YAML fails schema validation."""


def load_registry_yaml(path: Path) -> dict[str, Any]:
    """Parse and return the registry YAML file."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise RegistryValidationError(f"Registry file is not valid YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RegistryValidationError(f"Registry file is not a YAML mapping: {path}")
    return data  # type: ignore[return-value]


def validate_registry(data: dict[str, Any], schema: dict[str, Any] | None = None) -> None:
    """Validate registry data against the bundled JSON schema.

    Args:
        data: Parsed registry YAML content.
        schema: Optional pre-loaded schema dict; loads from bundled schemas if not provided.

    Raises:
        RegistryValidationError: If validation fails.
    """
    if schema is None:
        schema = get_schema(_SCHEMA_NAME)
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        raise RegistryValidationError(
            f"Registry validation failed: {exc.message} (at {list(exc.absolute_path)})"
        ) from exc


def upsert_registry_models(conn: sqlite3.Connection, models: list[dict[str, Any]]) -> int:
    """Upsert all models from registry data into the model_registry table.

    Returns the number of models processed.
    """
    count = 0
    for model in models:
        download = model.get("download", {})
        hardware = model.get("hardware", {})
        runtime = model.get("runtime", {})
        role = model["role"]

        conn.execute(
            """
            INSERT INTO model_registry
                (id, name, provider, family, role, format, license_spdx, license_url,
                 source_type, download_url, sha256, size_gb,
                 min_vram_gb, recommended_vram_gb, context_length,
                 capabilities_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name                = excluded.name,
                provider            = excluded.provider,
                family              = excluded.family,
                role                = excluded.role,
                format              = excluded.format,
                license_spdx        = excluded.license_spdx,
                license_url         = excluded.license_url,
                source_type         = excluded.source_type,
                download_url        = excluded.download_url,
                sha256              = excluded.sha256,
                size_gb             = excluded.size_gb,
                min_vram_gb         = excluded.min_vram_gb,
                recommended_vram_gb = excluded.recommended_vram_gb,
                context_length      = excluded.context_length,
                capabilities_json   = excluded.capabilities_json,
                metadata_json       = excluded.metadata_json
            """,
            (
                model["id"],
                model["name"],
                download.get("provider", ""),
                model["family"],
                role,
                model["format"],
                model["license"],
                model.get("license_url"),
                "user-supplied" if role == "user-supplied" else "registry",
                download.get("url"),
                download.get("sha256"),
                model.get("size_gb"),
                hardware.get("min_vram_gb"),
                hardware.get("recommended_vram_gb"),
                runtime.get("llama_cpp", {}).get("context_length"),
                json.dumps(runtime) if runtime else None,
                json.dumps(model),
            ),
        )
        count += 1
    conn.commit()
    return count


def load_and_persist_registry(
    conn: sqlite3.Connection,
    registry_path: Path,
    schema: dict[str, Any] | None = None,
) -> int:
    """Load, validate, and persist the model registry into SQLite.

    Args:
        conn: Open SQLite connection (migrations must already be applied).
        registry_path: Path to the registry YAML file.
        schema: Optional pre-loaded schema; loaded from bundled schemas if not provided.

    Returns:
        Number of model entries loaded.

    Raises:
        RegistryValidationError: If the YAML fails schema validation.
    """
    data = load_registry_yaml(registry_path)
    validate_registry(data, schema)
    models: list[dict[str, Any]] = data.get("models", [])
    count = upsert_registry_models(conn, models)
    logger.info("Loaded %d model(s) from registry at %s", count, registry_path)
    return count


def list_registry_models(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all rows from model_registry as a list of dicts."""
    rows = conn.execute(
        """
        SELECT id, name, provider, family, role, format,
               license_spdx, license_url, source_type,
               download_url, sha256, size_gb,
               min_vram_gb, recommended_vram_gb, context_length,
               registered_at
        FROM model_registry
        ORDER BY
            CASE role
                WHEN 'starter'      THEN 0
                WHEN 'standard'     THEN 1
                WHEN 'high-quality' THEN 2
                WHEN 'user-supplied' THEN 3
                ELSE 4
            END,
            id
        """
    ).fetchall()
    return [dict(row) for row in rows]
