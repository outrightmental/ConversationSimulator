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

from convsim_core.runtime.types import SamplingDefaults
from convsim_core.schema_paths import get_schema
from convsim_core.services.model_manager_service import get_active_config

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


#: The schema's bounds for the registry's sampling defaults
#: (model-registry.schema.json, runtime.llama_cpp). A stored value outside
#: them, which only a hand-edited database could hold, is ignored.
_SAMPLING_BOUNDS = {"temperature_default": (0.0, 2.0), "top_p_default": (0.0, 1.0)}


def _sampling_value(block: dict[str, Any], key: str) -> float | None:
    value = block.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    low, high = _SAMPLING_BOUNDS[key]
    return float(value) if low <= value <= high else None


def _registry_id_for_model(conn: sqlite3.Connection, model_id: str) -> str | None:
    """The registry entry behind an active ``model_id``, or None.

    For llama.cpp, ``active_model_id`` is the model file's path (setup and the
    Settings model list both store ``installed_models.file_path``), so the file
    is mapped to its install record's ``registry_id``. A player-supplied GGUF
    has no registry id. A ``model_id`` that is itself a registry id names its
    own entry.
    """
    row = conn.execute(
        "SELECT registry_id FROM installed_models WHERE file_path = ? "
        "ORDER BY id DESC LIMIT 1",
        (model_id,),
    ).fetchone()
    if row is not None:
        return row["registry_id"] or None
    hit = conn.execute(
        "SELECT id FROM model_registry WHERE id = ? LIMIT 1", (model_id,)
    ).fetchone()
    return hit["id"] if hit is not None else None


def registry_sampling_defaults(conn: sqlite3.Connection, model_id: str | None) -> SamplingDefaults:
    """The llama.cpp sampling defaults the registry declares for ``model_id``.

    Reads ``runtime.llama_cpp.temperature_default`` and ``top_p_default`` from
    the entry's stored runtime block (``capabilities_json``). A model with no
    entry, an entry without the block, or a value that is missing or out of
    range gives None for that field, so the request keeps its own default.
    Never raises: a bookkeeping problem must not stop a turn.
    """
    if not model_id:
        return SamplingDefaults()
    try:
        registry_id = _registry_id_for_model(conn, model_id)
        if registry_id is None:
            return SamplingDefaults()
        row = conn.execute(
            "SELECT capabilities_json FROM model_registry WHERE id = ? LIMIT 1",
            (registry_id,),
        ).fetchone()
        if row is None or not row["capabilities_json"]:
            return SamplingDefaults()
        runtime = json.loads(row["capabilities_json"])
        block = runtime.get("llama_cpp") if isinstance(runtime, dict) else None
        if not isinstance(block, dict):
            return SamplingDefaults()
        return SamplingDefaults(
            temperature=_sampling_value(block, "temperature_default"),
            top_p=_sampling_value(block, "top_p_default"),
        )
    except (sqlite3.Error, ValueError, TypeError) as exc:
        logger.warning("Registry sampling lookup failed (%s); using the request defaults", exc)
        return SamplingDefaults()


def active_model_sampling(conn: sqlite3.Connection, runtime_id: str | None) -> SamplingDefaults:
    """The registry sampling for the model serving a request on ``runtime_id`` (issue #580).

    Only the llama.cpp runtime has registry sampling defaults: the registry
    declares them under ``runtime.llama_cpp``, and an Ollama model is a tag
    with no registry entry. The model is the active selection, and it counts
    only when the active runtime is the one serving the request, the same rule
    the turn timing record uses to name the model. Anything else (a scripted
    or fake runtime, no selection) gives empty defaults.
    """
    if runtime_id != "llama_cpp":
        return SamplingDefaults()
    try:
        active = get_active_config(conn)
    except sqlite3.Error as exc:
        logger.warning("Active model lookup failed (%s); using the request defaults", exc)
        return SamplingDefaults()
    if active.get("runtime_id") != runtime_id:
        return SamplingDefaults()
    return registry_sampling_defaults(conn, active.get("model_id"))


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
