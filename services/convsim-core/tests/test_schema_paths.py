# SPDX-License-Identifier: Apache-2.0
"""Tests for convsim_core.schema_paths.

Verifies that all schema files can be located and loaded as valid JSON
without relying on the current working directory.
"""

import json
import os
from pathlib import Path
import pytest

from convsim_core.schema_paths import (
    SCHEMA_NAMES,
    get_schema,
    get_schema_text,
    get_all_schemas,
)


class TestSchemaNames:
    def test_expected_schemas_present(self):
        expected = {
            "model-registry.schema.json",
            "pack.schema.json",
            "scenario.schema.json",
            "npc.schema.json",
            "rubric.schema.json",
            "safety.schema.json",
            "turn-output.schema.json",
            "debrief.schema.json",
        }
        assert set(SCHEMA_NAMES) == expected

    def test_schema_names_is_tuple(self):
        assert isinstance(SCHEMA_NAMES, tuple)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
class TestSchemaLoading:
    def test_get_schema_text_returns_string(self, name):
        text = get_schema_text(name)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_get_schema_text_is_valid_json(self, name):
        text = get_schema_text(name)
        parsed = json.loads(text)
        assert isinstance(parsed, dict)

    def test_get_schema_returns_dict(self, name):
        schema = get_schema(name)
        assert isinstance(schema, dict)

    def test_schema_has_required_fields(self, name):
        schema = get_schema(name)
        assert "$schema" in schema, f"{name}: missing $schema"
        assert "$id" in schema, f"{name}: missing $id"
        assert schema.get("type") == "object", f"{name}: root type must be 'object'"

    def test_schema_version_enum_present(self, name):
        # turn-output is a runtime LLM output format, not a pack-authored file,
        # so it intentionally omits schema_version from its properties.
        if name == "turn-output.schema.json":
            pytest.skip("turn-output.schema.json intentionally omits schema_version")
        schema = get_schema(name)
        props = schema.get("properties", {})
        sv = props.get("schema_version", {})
        assert "enum" in sv, f"{name}: schema_version must have an enum"
        assert "0.1" in sv["enum"], f"{name}: '0.1' must be a valid schema_version"


class TestCwdIndependence:
    """Confirm schema loading works regardless of the process working directory."""

    def test_load_from_different_cwd(self, tmp_path):
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # If this were CWD-dependent it would fail inside tmp_path
            schemas = get_all_schemas()
            assert len(schemas) == len(SCHEMA_NAMES)
        finally:
            os.chdir(original_cwd)


class TestNoExecutableCode:
    def test_pack_schema_blocks_scripts_field(self):
        schema = get_schema("pack.schema.json")
        not_clause = schema.get("not", {})
        required = not_clause.get("required", [])
        assert "scripts" in required, (
            "pack.schema.json must use 'not' to prohibit a top-level 'scripts' field"
        )

    def test_no_schema_references_scripts_property(self):
        """Mirror the JS load-schemas.js cross-schema scripts check.

        No schema (other than pack.schema.json) should serialise the string
        '"scripts"' anywhere in its body.  pack.schema.json is permitted to
        reference it inside the 'not' clause that explicitly blocks the field.
        """
        for name, schema in get_all_schemas().items():
            raw = json.dumps(schema)
            assert '"scripts"' not in raw or name == "pack.schema.json", (
                f"{name}: must not reference a 'scripts' property "
                "(pack.schema.json may reference it via the 'not' clause)"
            )

    def test_get_all_schemas(self):
        all_schemas = get_all_schemas()
        assert set(all_schemas.keys()) == set(SCHEMA_NAMES)
        for name, schema in all_schemas.items():
            assert isinstance(schema, dict), f"{name} must parse to a dict"


class TestUnknownSchemaRejected:
    def test_unknown_name_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown schema"):
            get_schema_text("nonexistent.schema.json")


class TestBundledSchemaSync:
    """Verify the bundled schemas/ copy is identical to the root schemas/ directory.

    The Python package bundles schemas inside convsim_core/schemas/ for
    CWD-independent access and wheel distribution. This test catches drift
    between the two copies so they cannot silently diverge.
    """

    _root_schemas = Path(__file__).parents[3] / "schemas"

    def test_root_schemas_dir_exists(self):
        if not self._root_schemas.exists():
            pytest.skip("Root schemas/ directory not found (installed package build?)")
        assert self._root_schemas.is_dir()

    @pytest.mark.parametrize("name", SCHEMA_NAMES)
    def test_bundled_matches_root(self, name):
        if not self._root_schemas.exists():
            pytest.skip("Root schemas/ directory not found (installed package build?)")
        root_path = self._root_schemas / name
        assert root_path.exists(), f"Root schemas/{name} not found"
        root_text = root_path.read_text(encoding="utf-8")
        bundled_text = get_schema_text(name)
        assert bundled_text == root_text, (
            f"Bundled convsim_core/schemas/{name} differs from root schemas/{name}. "
            "Update both copies together to prevent contract drift."
        )
