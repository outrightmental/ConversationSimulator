# SPDX-License-Identifier: Apache-2.0
"""Tests for convsim_core.schema_paths.

Verifies that all schema files can be located and loaded as valid JSON
without relying on the current working directory.
"""

import json
import os
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
            return
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

    def test_get_all_schemas(self):
        all_schemas = get_all_schemas()
        assert set(all_schemas.keys()) == set(SCHEMA_NAMES)
        for name, schema in all_schemas.items():
            assert isinstance(schema, dict), f"{name} must parse to a dict"


class TestUnknownSchemaRejected:
    def test_unknown_name_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown schema"):
            get_schema_text("nonexistent.schema.json")
