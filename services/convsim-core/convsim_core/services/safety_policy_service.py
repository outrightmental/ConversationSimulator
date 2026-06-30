# SPDX-License-Identifier: Apache-2.0
"""Safety policy loader — reads a pack's safety YAML, validates it, and produces
a SafetyPolicyConfig ready for the input router.

Usage::

    config = load_safety_policy(pack_dir / "safety" / "my_policy.yaml")
    decision = route_player_input(player_text, config)

The loaded config is *merged* with global non-overridable boundaries so that
downstream code can rely on minors_romantic_or_sexual and self_harm_crisis always
being present with their correct non-overridable actions.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import jsonschema
import yaml

from convsim_core.input_router import (
    DEFAULT_REDIRECT_MESSAGE,
    RouteAction,
    SafetyPolicyConfig,
    _LEGACY_ACTION_MAP,
    _LEGACY_CATEGORY_ALIASES,
)
from convsim_core.schema_paths import get_schema

logger = logging.getLogger(__name__)

_SCHEMA_NAME = "safety.schema.json"

# Global non-overridable category → action pairs.  These are merged into every
# loaded policy regardless of what the pack YAML says.
_GLOBAL_NON_OVERRIDABLE: Dict[str, RouteAction] = {
    "minors_romantic_or_sexual": RouteAction.STOP,
    "self_harm_crisis": RouteAction.STOP_WITH_RESOURCE,
}

# Default action for criminal_instruction if the pack omits it entirely.
_CRIMINAL_DEFAULT_ACTION = RouteAction.REFUSE


class SafetyPolicyValidationError(Exception):
    """Raised when a safety policy YAML fails schema validation or is unreadable."""


def load_safety_policy_yaml(path: Path) -> Dict[str, Any]:
    """Parse the safety policy YAML at *path* and return the raw data dict.

    Raises:
        SafetyPolicyValidationError: If the file is missing, not valid YAML,
            or not a YAML mapping.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise SafetyPolicyValidationError(
            f"Safety policy file not found: {path}"
        ) from exc
    except yaml.YAMLError as exc:
        raise SafetyPolicyValidationError(
            f"Safety policy file is not valid YAML: {path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise SafetyPolicyValidationError(
            f"Safety policy file is not a YAML mapping: {path}"
        )
    return data  # type: ignore[return-value]


def validate_safety_policy(
    data: Dict[str, Any],
    schema: Optional[Dict[str, Any]] = None,
) -> None:
    """Validate *data* against the bundled safety policy JSON schema.

    Args:
        data: Parsed YAML content.
        schema: Pre-loaded schema dict; loads from bundled schemas if not given.

    Raises:
        SafetyPolicyValidationError: If validation fails.
    """
    if schema is None:
        schema = get_schema(_SCHEMA_NAME)
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        raise SafetyPolicyValidationError(
            f"Safety policy validation failed: {exc.message} "
            f"(at {list(exc.absolute_path)})"
        ) from exc


def build_safety_policy_config(
    data: Dict[str, Any],
) -> SafetyPolicyConfig:
    """Convert validated safety policy YAML data into a SafetyPolicyConfig.

    Applies three layers:
      1. Pack YAML categories (after resolving legacy aliases).
      2. Default criminal_instruction = refuse (if pack omits it).
      3. Global non-overridable boundaries (always applied last; cannot be
         weakened by pack configuration).
    """
    raw_categories: Dict[str, str] = data.get("content_categories", {})
    categories: Dict[str, RouteAction] = {}

    for raw_name, raw_action in raw_categories.items():
        # Resolve legacy category aliases to canonical MVP names.
        canonical_name = _LEGACY_CATEGORY_ALIASES.get(raw_name, raw_name)
        action = _LEGACY_ACTION_MAP.get(str(raw_action))
        if action is None:
            try:
                action = RouteAction(str(raw_action))
            except ValueError:
                logger.warning(
                    "Unknown safety action %r for category %r; skipping",
                    raw_action,
                    raw_name,
                )
                continue
        categories[canonical_name] = action

    # Ensure criminal_instruction is always present with at least "refuse".
    if "criminal_instruction" not in categories:
        categories["criminal_instruction"] = _CRIMINAL_DEFAULT_ACTION

    # Merge global non-overridable boundaries — always enforce these regardless
    # of what the pack YAML specifies.
    for cat, action in _GLOBAL_NON_OVERRIDABLE.items():
        if cat in categories and categories[cat] != action:
            logger.warning(
                "Pack policy tried to override non-overridable category %r "
                "(pack=%r, enforced=%r)",
                cat,
                categories[cat].value,
                action.value,
            )
        categories[cat] = action

    global_redirect = data.get("redirect_message", DEFAULT_REDIRECT_MESSAGE)

    logger.debug(
        "Loaded safety policy %r with %d categories",
        data.get("policy_id", "unknown"),
        len(categories),
    )

    return SafetyPolicyConfig(
        policy_id=data.get("policy_id", "unknown"),
        content_rating=data.get("content_rating_cap", "PG"),
        categories=categories,
        global_redirect_message=global_redirect,
        allow_profanity=bool(data.get("allow_profanity", False)),
    )


def load_safety_policy(
    path: Path,
    schema: Optional[Dict[str, Any]] = None,
) -> SafetyPolicyConfig:
    """Load, validate, and build a SafetyPolicyConfig from a pack safety YAML file.

    Args:
        path: Absolute path to the safety policy YAML file.
        schema: Optional pre-loaded JSON schema; loads from bundled schemas if
            not provided.

    Returns:
        A SafetyPolicyConfig merged with global non-overridable boundaries.

    Raises:
        SafetyPolicyValidationError: If the file is missing, malformed, or
            fails schema validation.
    """
    data = load_safety_policy_yaml(path)
    validate_safety_policy(data, schema)
    config = build_safety_policy_config(data)
    return config
