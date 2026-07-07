# SPDX-License-Identifier: Apache-2.0
"""Tests for convsim_core.services.safety_policy_service.

Test plan:
  - load_safety_policy_yaml: missing file, bad YAML, non-mapping raise errors.
  - validate_safety_policy: valid data passes, invalid data raises.
  - build_safety_policy_config: category names resolved; global non-overridable
    boundaries always applied; legacy category aliases resolved.
  - load_safety_policy: round-trips the official interview_safety.yaml.
  - Global non-overridable boundaries cannot be weakened by pack YAML.
"""
import textwrap
from pathlib import Path

import pytest
import yaml

from convsim_core.input_router import RouteAction
from convsim_core.services.safety_policy_service import (
    SafetyPolicyValidationError,
    build_safety_policy_config,
    load_safety_policy,
    load_safety_policy_yaml,
    validate_safety_policy,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_valid_yaml(tmp_path) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(
        textwrap.dedent("""\
            schema_version: "0.1"
            policy_id: test_policy
            content_categories:
              nsfw_sexual_content: stop
              criminal_instruction: refuse
            content_rating_cap: PG
        """),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def full_mvp_yaml(tmp_path) -> Path:
    path = tmp_path / "full_policy.yaml"
    path.write_text(
        textwrap.dedent("""\
            schema_version: "0.1"
            policy_id: full_policy
            content_categories:
              nsfw_sexual_content: stop
              minors_romantic_or_sexual: stop
              real_person_impersonation: refuse
              voice_cloning_request: refuse
              medical_or_therapy_claim: redirect
              legal_claim: redirect
              criminal_instruction: refuse
              harassment_extreme: redirect
              self_harm_crisis: stop_with_resource_message
            redirect_message: "That's outside scope."
            allow_profanity: false
            content_rating_cap: PG
        """),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def legacy_category_yaml(tmp_path) -> Path:
    path = tmp_path / "legacy_policy.yaml"
    path.write_text(
        textwrap.dedent("""\
            schema_version: "0.1"
            policy_id: legacy_policy
            content_categories:
              nsfw_sexual: block
              instructional_criminal: block
              medical_professional_advice: redirect
              crisis_content: redirect
            redirect_message: "Let's stay on topic."
            allow_profanity: false
            content_rating_cap: PG
        """),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def interview_safety_yaml() -> Path:
    """Path to the official job-interview-basic safety policy."""
    return (
        Path(__file__).parent.parent.parent.parent
        / "packs"
        / "official"
        / "job-interview-basic"
        / "safety"
        / "interview_safety.yaml"
    )


# ---------------------------------------------------------------------------
# load_safety_policy_yaml
# ---------------------------------------------------------------------------


class TestLoadSafetyPolicyYaml:
    def test_loads_valid_yaml(self, minimal_valid_yaml):
        data = load_safety_policy_yaml(minimal_valid_yaml)
        assert data["policy_id"] == "test_policy"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(SafetyPolicyValidationError, match="not found"):
            load_safety_policy_yaml(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("{invalid yaml: [}", encoding="utf-8")
        with pytest.raises(SafetyPolicyValidationError, match="not valid YAML"):
            load_safety_policy_yaml(path)

    def test_non_mapping_yaml_raises(self, tmp_path):
        path = tmp_path / "list.yaml"
        path.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(SafetyPolicyValidationError, match="not a YAML mapping"):
            load_safety_policy_yaml(path)


# ---------------------------------------------------------------------------
# validate_safety_policy
# ---------------------------------------------------------------------------


class TestValidateSafetyPolicy:
    def test_valid_full_mvp_passes(self, full_mvp_yaml):
        data = load_safety_policy_yaml(full_mvp_yaml)
        # Should not raise.
        validate_safety_policy(data)

    def test_valid_minimal_passes(self, minimal_valid_yaml):
        data = load_safety_policy_yaml(minimal_valid_yaml)
        validate_safety_policy(data)

    def test_missing_schema_version_raises(self):
        data = {
            "policy_id": "test",
            "content_categories": {},
        }
        with pytest.raises(SafetyPolicyValidationError):
            validate_safety_policy(data)

    def test_missing_policy_id_raises(self):
        data = {
            "schema_version": "0.1",
            "content_categories": {},
        }
        with pytest.raises(SafetyPolicyValidationError):
            validate_safety_policy(data)

    def test_invalid_action_value_raises(self):
        data = {
            "schema_version": "0.1",
            "policy_id": "test",
            "content_categories": {
                "nsfw_sexual_content": "allow",  # not a valid enum value
            },
        }
        with pytest.raises(SafetyPolicyValidationError):
            validate_safety_policy(data)

    def test_unknown_category_raises(self):
        data = {
            "schema_version": "0.1",
            "policy_id": "test",
            "content_categories": {
                "made_up_category": "block",  # additionalProperties: false
            },
        }
        with pytest.raises(SafetyPolicyValidationError):
            validate_safety_policy(data)

    def test_legacy_categories_pass_validation(self, legacy_category_yaml):
        data = load_safety_policy_yaml(legacy_category_yaml)
        # Legacy names are still in the schema for backward compat.
        validate_safety_policy(data)


# ---------------------------------------------------------------------------
# build_safety_policy_config
# ---------------------------------------------------------------------------


class TestBuildSafetyPolicyConfig:
    def test_policy_id_set(self, full_mvp_yaml):
        data = load_safety_policy_yaml(full_mvp_yaml)
        config = build_safety_policy_config(data)
        assert config.policy_id == "full_policy"

    def test_content_rating_set(self, full_mvp_yaml):
        data = load_safety_policy_yaml(full_mvp_yaml)
        config = build_safety_policy_config(data)
        assert config.content_rating == "PG"

    def test_categories_include_all_mvp(self, full_mvp_yaml):
        data = load_safety_policy_yaml(full_mvp_yaml)
        config = build_safety_policy_config(data)
        assert "nsfw_sexual_content" in config.categories
        assert "criminal_instruction" in config.categories
        assert "real_person_impersonation" in config.categories
        assert "voice_cloning_request" in config.categories
        assert "medical_or_therapy_claim" in config.categories
        assert "legal_claim" in config.categories
        assert "harassment_extreme" in config.categories

    def test_global_non_overridable_always_present(self, minimal_valid_yaml):
        # Minimal YAML omits minors and self_harm; they must still be present.
        data = load_safety_policy_yaml(minimal_valid_yaml)
        config = build_safety_policy_config(data)
        assert config.categories["minors_romantic_or_sexual"] == RouteAction.STOP
        assert config.categories["self_harm_crisis"] == RouteAction.STOP_WITH_RESOURCE

    def test_global_non_overridable_not_weakened(self, tmp_path):
        # Pass raw data with weaker actions directly to build_safety_policy_config,
        # bypassing schema validation. The service must override these to the correct
        # non-overridable actions regardless of what the pack specified.
        data = {
            "schema_version": "0.1",
            "policy_id": "weak_policy",
            "content_categories": {
                "minors_romantic_or_sexual": "redirect",  # weaker than stop; must be overridden
                "self_harm_crisis": "refuse",  # weaker than stop_with_resource_message; must be overridden
            },
            "content_rating_cap": "PG",
        }
        config = build_safety_policy_config(data)
        assert config.categories["minors_romantic_or_sexual"] == RouteAction.STOP
        assert config.categories["self_harm_crisis"] == RouteAction.STOP_WITH_RESOURCE

    def test_criminal_instruction_added_by_default(self, tmp_path):
        # Pack omits criminal_instruction; service adds it as refuse.
        data = {
            "schema_version": "0.1",
            "policy_id": "no_criminal",
            "content_categories": {},
        }
        config = build_safety_policy_config(data)
        assert config.categories["criminal_instruction"] == RouteAction.REFUSE

    def test_legacy_nsfw_sexual_alias_resolved(self, legacy_category_yaml):
        data = load_safety_policy_yaml(legacy_category_yaml)
        config = build_safety_policy_config(data)
        assert "nsfw_sexual_content" in config.categories
        assert config.categories["nsfw_sexual_content"] == RouteAction.STOP

    def test_legacy_instructional_criminal_alias_resolved(self, legacy_category_yaml):
        data = load_safety_policy_yaml(legacy_category_yaml)
        config = build_safety_policy_config(data)
        assert "criminal_instruction" in config.categories
        assert config.categories["criminal_instruction"] == RouteAction.STOP

    def test_legacy_medical_alias_resolved(self, legacy_category_yaml):
        data = load_safety_policy_yaml(legacy_category_yaml)
        config = build_safety_policy_config(data)
        assert "medical_or_therapy_claim" in config.categories
        assert config.categories["medical_or_therapy_claim"] == RouteAction.REDIRECT

    def test_legacy_crisis_alias_resolved(self, legacy_category_yaml):
        data = load_safety_policy_yaml(legacy_category_yaml)
        config = build_safety_policy_config(data)
        # Legacy crisis_content → redirect maps to self_harm_crisis,
        # then the global boundary overwrites to stop_with_resource_message.
        assert config.categories["self_harm_crisis"] == RouteAction.STOP_WITH_RESOURCE

    def test_global_redirect_message_from_yaml(self, full_mvp_yaml):
        data = load_safety_policy_yaml(full_mvp_yaml)
        config = build_safety_policy_config(data)
        assert "outside scope" in config.global_redirect_message

    def test_allow_profanity_false_by_default(self, minimal_valid_yaml):
        data = load_safety_policy_yaml(minimal_valid_yaml)
        config = build_safety_policy_config(data)
        assert config.allow_profanity is False


# ---------------------------------------------------------------------------
# load_safety_policy (round-trip integration)
# ---------------------------------------------------------------------------


class TestLoadSafetyPolicy:
    def test_round_trip_full_mvp_yaml(self, full_mvp_yaml):
        config = load_safety_policy(full_mvp_yaml)
        assert config.policy_id == "full_policy"
        assert "nsfw_sexual_content" in config.categories
        assert "self_harm_crisis" in config.categories

    def test_invalid_file_raises(self, tmp_path):
        with pytest.raises(SafetyPolicyValidationError):
            load_safety_policy(tmp_path / "missing.yaml")

    def test_interview_safety_yaml_loads_successfully(self, interview_safety_yaml):
        if not interview_safety_yaml.exists():
            pytest.skip("official pack not present in test environment")
        config = load_safety_policy(interview_safety_yaml)
        assert config.policy_id == "interview_safety"
        assert config.content_rating == "PG"
        assert config.categories["minors_romantic_or_sexual"] == RouteAction.STOP
        assert config.categories["self_harm_crisis"] == RouteAction.STOP_WITH_RESOURCE
        assert config.categories["criminal_instruction"] in (
            RouteAction.REFUSE, RouteAction.STOP
        )
