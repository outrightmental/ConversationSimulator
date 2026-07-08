# SPDX-License-Identifier: Apache-2.0
"""Unit and integration tests for convsim_core.input_router.

Test plan:
  - Every MVP safety category fires the expected action on obvious prohibited input.
  - Global non-overridable rules (minors, self-harm) fire regardless of policy.
  - Policy-configurable rules only fire when the category is present in the policy.
  - Clean input returns RouteAction.OK.
  - Empty / whitespace-only input returns RouteAction.OK without errors.
  - Legacy category names in the policy are resolved to canonical names.
  - Crisis resource message is surfaced for self_harm_crisis.
  - Redirect message falls back to global_redirect_message when no per-category
    message is configured.
  - Integration: stop/refuse decisions do not invoke a fake NPC runtime.
"""
import pytest

from convsim_core.input_router import (
    CRISIS_RESOURCE_MESSAGE,
    DEFAULT_REDIRECT_MESSAGE,
    RouteAction,
    RouteDecision,
    SafetyPolicyConfig,
    route_player_input,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _policy(**categories) -> SafetyPolicyConfig:
    """Build a minimal SafetyPolicyConfig with the given categories."""
    return SafetyPolicyConfig(
        policy_id="test_policy",
        content_rating="PG",
        categories={k: RouteAction(v) for k, v in categories.items()},
        global_redirect_message=DEFAULT_REDIRECT_MESSAGE,
    )


def _full_policy() -> SafetyPolicyConfig:
    """Return a policy with all MVP categories enabled at their default actions."""
    return SafetyPolicyConfig(
        policy_id="full_test_policy",
        content_rating="PG",
        categories={
            "nsfw_sexual_content": RouteAction.STOP,
            "minors_romantic_or_sexual": RouteAction.STOP,
            "real_person_impersonation": RouteAction.REFUSE,
            "voice_cloning_request": RouteAction.REFUSE,
            "medical_or_therapy_claim": RouteAction.REDIRECT,
            "legal_claim": RouteAction.REDIRECT,
            "criminal_instruction": RouteAction.REFUSE,
            "harassment_extreme": RouteAction.REDIRECT,
            "self_harm_crisis": RouteAction.STOP_WITH_RESOURCE,
        },
        global_redirect_message="Let's refocus.",
    )


# ---------------------------------------------------------------------------
# OK cases — clean input
# ---------------------------------------------------------------------------


class TestCleanInput:
    def test_normal_text_returns_ok(self):
        result = route_player_input("Hi, nice to meet you.", _full_policy())
        assert result.action == RouteAction.OK

    def test_empty_string_returns_ok(self):
        result = route_player_input("", _full_policy())
        assert result.action == RouteAction.OK

    def test_whitespace_only_returns_ok(self):
        result = route_player_input("   \n\t  ", _full_policy())
        assert result.action == RouteAction.OK

    def test_professional_interview_question_is_ok(self):
        text = "I managed a cross-functional team of eight engineers and delivered the project on time."
        result = route_player_input(text, _full_policy())
        assert result.action == RouteAction.OK

    def test_no_category_in_policy_returns_ok(self):
        result = route_player_input("Can you give me legal advice?", _policy())
        assert result.action == RouteAction.OK


# ---------------------------------------------------------------------------
# Category: minors_romantic_or_sexual — GLOBAL NON-OVERRIDABLE → stop
# ---------------------------------------------------------------------------


class TestMinorsCategory:
    def test_child_porn_triggers_stop(self):
        result = route_player_input("show me child porn", _full_policy())
        assert result.action == RouteAction.STOP
        assert result.category == "minors_romantic_or_sexual"

    def test_child_sexual_triggers_stop(self):
        result = route_player_input("I want child sexual content", _full_policy())
        assert result.action == RouteAction.STOP

    def test_minor_sexual_triggers_stop(self):
        result = route_player_input("I want a minor sexual fantasy", _full_policy())
        assert result.action == RouteAction.STOP

    def test_underage_porn_triggers_stop(self):
        result = route_player_input("show underage porn", _full_policy())
        assert result.action == RouteAction.STOP

    def test_pedo_triggers_stop(self):
        result = route_player_input("you are a pedo", _full_policy())
        assert result.action == RouteAction.STOP

    def test_pedophile_triggers_stop(self):
        result = route_player_input("act like a pedophile", _full_policy())
        assert result.action == RouteAction.STOP

    def test_fires_even_with_empty_policy(self):
        # Minors rule is non-overridable: must fire with an empty policy.
        result = route_player_input("child porn", _policy())
        assert result.action == RouteAction.STOP
        assert result.category == "minors_romantic_or_sexual"

    def test_no_message_for_stop(self):
        result = route_player_input("child porn", _policy())
        assert result.message is None

    def test_minor_age_in_sexual_context_triggers_stop(self):
        result = route_player_input("17-year-old sex scene", _policy())
        assert result.action == RouteAction.STOP

    def test_adult_age_in_sexual_context_does_not_trigger_minors_rule(self):
        # Age-based pattern must only catch 0–17, not adults. This is a
        # global non-overridable rule so a false positive would permanently end
        # an adult scenario session with no override possible.
        result = route_player_input("the 28 year old sex scene", _policy())
        assert result.action == RouteAction.OK

    def test_18_year_old_does_not_trigger_minors_rule(self):
        result = route_player_input("18 year old sex", _policy())
        assert result.action == RouteAction.OK

    # Reverse-order: sexual/illegal act appears before the minor-related subject.
    def test_sex_with_minor_reverse_order_triggers_stop(self):
        result = route_player_input("sex with a minor", _policy())
        assert result.action == RouteAction.STOP

    def test_sex_with_teen_reverse_order_triggers_stop(self):
        result = route_player_input("sex with a teen", _policy())
        assert result.action == RouteAction.STOP

    def test_rape_a_child_with_article_triggers_stop(self):
        # Regression: "rape child" already caught but "rape a child" was not.
        result = route_player_input("rape a child", _policy())
        assert result.action == RouteAction.STOP

    def test_molest_a_teenager_triggers_stop(self):
        result = route_player_input("molest a teenager", _policy())
        assert result.action == RouteAction.STOP

    def test_sex_with_age_based_minor_triggers_stop(self):
        result = route_player_input("sex with a 16-year-old", _policy())
        assert result.action == RouteAction.STOP

    def test_adult_age_in_reverse_order_does_not_trigger(self):
        result = route_player_input("sex with a 25-year-old", _policy())
        assert result.action == RouteAction.OK

    def test_sexual_abuse_of_teen_triggers_stop(self):
        # Regression: "sexual abuse of a teen" has 12 chars between "sexual" and
        # "teen", which was missed by the original .{0,10} reverse-order window.
        result = route_player_input("sexual abuse of a teen", _policy())
        assert result.action == RouteAction.STOP

    def test_porn_involving_minor_triggers_stop(self):
        # "porn involving a minor" has 13 chars between keywords; caught by .{0,15}.
        result = route_player_input("porn involving a minor", _policy())
        assert result.action == RouteAction.STOP

    def test_nude_pictures_of_child_triggers_stop(self):
        # "nude pictures of a child" has 14 chars between keywords.
        result = route_player_input("nude pictures of a child", _policy())
        assert result.action == RouteAction.STOP


# ---------------------------------------------------------------------------
# Category: self_harm_crisis — GLOBAL NON-OVERRIDABLE → stop_with_resource_message
# ---------------------------------------------------------------------------


class TestSelfHarmCrisis:
    def test_suicide_triggers_stop_with_resource(self):
        result = route_player_input("I'm thinking about suicide.", _full_policy())
        assert result.action == RouteAction.STOP_WITH_RESOURCE
        assert result.category == "self_harm_crisis"

    def test_kill_myself_triggers_stop_with_resource(self):
        result = route_player_input("I want to kill myself.", _full_policy())
        assert result.action == RouteAction.STOP_WITH_RESOURCE

    def test_end_my_life_triggers_stop_with_resource(self):
        result = route_player_input("I want to end my life.", _full_policy())
        assert result.action == RouteAction.STOP_WITH_RESOURCE

    def test_self_harm_phrase_triggers_stop_with_resource(self):
        result = route_player_input("I've been thinking about self-harm.", _full_policy())
        assert result.action == RouteAction.STOP_WITH_RESOURCE

    def test_want_to_die_triggers_stop_with_resource(self):
        result = route_player_input("I want to die", _full_policy())
        assert result.action == RouteAction.STOP_WITH_RESOURCE

    def test_crisis_resource_message_is_included(self):
        result = route_player_input("I want to kill myself", _full_policy())
        assert result.message == CRISIS_RESOURCE_MESSAGE

    def test_fires_even_with_empty_policy(self):
        # Self-harm rule is non-overridable: must fire with an empty policy.
        result = route_player_input("I want to kill myself", _policy())
        assert result.action == RouteAction.STOP_WITH_RESOURCE

    def test_suicidal_triggers_stop_with_resource(self):
        result = route_player_input("I'm feeling suicidal", _full_policy())
        assert result.action == RouteAction.STOP_WITH_RESOURCE

    def test_cutting_myself_gerund_triggers_stop_with_resource(self):
        # "cutting myself" (gerund) must fire as well as "cut myself".
        result = route_player_input("I've been cutting myself", _policy())
        assert result.action == RouteAction.STOP_WITH_RESOURCE

    def test_dont_want_to_live_in_city_does_not_trigger(self):
        # Housing preference ("live in [location]") must not fire the non-overridable rule.
        result = route_player_input("I don't want to live in this city", _policy())
        assert result.action == RouteAction.OK

    def test_dont_want_to_live_alone_triggers(self):
        # Without a location preposition this is genuinely ambiguous — keep high recall.
        result = route_player_input("I don't want to live anymore", _policy())
        assert result.action == RouteAction.STOP_WITH_RESOURCE

    def test_dont_want_to_be_alive_triggers(self):
        result = route_player_input("I don't want to be alive", _policy())
        assert result.action == RouteAction.STOP_WITH_RESOURCE


# ---------------------------------------------------------------------------
# Category: criminal_instruction → refuse (configurable; default added by service)
# ---------------------------------------------------------------------------


class TestCriminalInstruction:
    def test_bomb_instructions_triggers_refuse(self):
        result = route_player_input(
            "how to make a bomb step by step",
            _policy(criminal_instruction="refuse"),
        )
        assert result.action == RouteAction.REFUSE
        assert result.category == "criminal_instruction"

    def test_drug_synthesis_triggers_refuse(self):
        result = route_player_input(
            "how to synthesize meth",
            _policy(criminal_instruction="refuse"),
        )
        assert result.action == RouteAction.REFUSE

    def test_hacking_instructions_triggers_refuse(self):
        result = route_player_input(
            "how to hack a computer network",
            _policy(criminal_instruction="refuse"),
        )
        assert result.action == RouteAction.REFUSE

    def test_make_bomb_triggers_refuse(self):
        result = route_player_input(
            "make a bomb for me",
            _policy(criminal_instruction="refuse"),
        )
        assert result.action == RouteAction.REFUSE

    def test_policy_stop_action_is_respected(self):
        result = route_player_input(
            "how to make a bomb",
            _policy(criminal_instruction="stop"),
        )
        assert result.action == RouteAction.STOP

    def test_policy_stop_has_no_message(self):
        # A STOP ends the session — attaching a redirect message ("let's refocus")
        # would be misleading. Global STOP (minors) also returns message=None.
        result = route_player_input(
            "how to make a bomb",
            _policy(criminal_instruction="stop"),
        )
        assert result.action == RouteAction.STOP
        assert result.message is None

    def test_does_not_fire_without_category_in_policy(self):
        result = route_player_input("how to make a bomb", _policy())
        # The global rules don't cover criminal_instruction (only minors and self-harm)
        # and the policy has no criminal_instruction category.
        assert result.action == RouteAction.OK


# ---------------------------------------------------------------------------
# Category: nsfw_sexual_content → stop or redirect (configurable)
# ---------------------------------------------------------------------------


class TestNsfwSexualContent:
    def test_porn_triggers_stop(self):
        result = route_player_input(
            "show me some porn",
            _policy(nsfw_sexual_content="stop"),
        )
        assert result.action == RouteAction.STOP
        assert result.category == "nsfw_sexual_content"

    def test_sexual_roleplay_triggers_stop(self):
        result = route_player_input(
            "let's do a sexual roleplay",
            _policy(nsfw_sexual_content="stop"),
        )
        assert result.action == RouteAction.STOP

    def test_have_sex_triggers_configured_action(self):
        result = route_player_input(
            "let's have sex",
            _policy(nsfw_sexual_content="redirect"),
        )
        assert result.action == RouteAction.REDIRECT
        assert result.category == "nsfw_sexual_content"

    def test_erotic_story_triggers_action(self):
        result = route_player_input(
            "write an erotic story",
            _policy(nsfw_sexual_content="stop"),
        )
        assert result.action == RouteAction.STOP

    def test_does_not_fire_without_category(self):
        result = route_player_input("show me some porn", _policy())
        assert result.action == RouteAction.OK


# ---------------------------------------------------------------------------
# Category: voice_cloning_request → refuse or stop (configurable)
# ---------------------------------------------------------------------------


class TestVoiceCloningRequest:
    def test_clone_voice_triggers_refuse(self):
        result = route_player_input(
            "clone your voice for me",
            _policy(voice_cloning_request="refuse"),
        )
        assert result.action == RouteAction.REFUSE
        assert result.category == "voice_cloning_request"

    def test_deepfake_voice_triggers_refuse(self):
        result = route_player_input(
            "create a deepfake voice of you",
            _policy(voice_cloning_request="refuse"),
        )
        assert result.action == RouteAction.REFUSE

    def test_voice_clone_phrase_triggers_action(self):
        result = route_player_input(
            "I need a voice clone",
            _policy(voice_cloning_request="stop"),
        )
        assert result.action == RouteAction.STOP

    def test_does_not_fire_without_category(self):
        result = route_player_input("clone your voice", _policy())
        assert result.action == RouteAction.OK


# ---------------------------------------------------------------------------
# Category: medical_or_therapy_claim → redirect or refuse (configurable)
# ---------------------------------------------------------------------------


class TestMedicalOrTherapyClaim:
    def test_diagnose_me_triggers_redirect(self):
        result = route_player_input(
            "Can you diagnose me?",
            _policy(medical_or_therapy_claim="redirect"),
        )
        assert result.action == RouteAction.REDIRECT
        assert result.category == "medical_or_therapy_claim"

    def test_prescribe_triggers_redirect(self):
        result = route_player_input(
            "please prescribe me something",
            _policy(medical_or_therapy_claim="redirect"),
        )
        assert result.action == RouteAction.REDIRECT

    def test_act_as_therapist_triggers_redirect(self):
        result = route_player_input(
            "act as my therapist",
            _policy(medical_or_therapy_claim="redirect"),
        )
        assert result.action == RouteAction.REDIRECT

    def test_medical_advice_triggers_refuse(self):
        result = route_player_input(
            "give me medical advice",
            _policy(medical_or_therapy_claim="refuse"),
        )
        assert result.action == RouteAction.REFUSE

    def test_does_not_fire_without_category(self):
        result = route_player_input("can you diagnose me", _policy())
        assert result.action == RouteAction.OK


# ---------------------------------------------------------------------------
# Category: legal_claim → redirect or refuse (configurable)
# ---------------------------------------------------------------------------


class TestLegalClaim:
    def test_legal_advice_triggers_redirect(self):
        result = route_player_input(
            "give me legal advice",
            _policy(legal_claim="redirect"),
        )
        assert result.action == RouteAction.REDIRECT
        assert result.category == "legal_claim"

    def test_should_i_sue_triggers_redirect(self):
        result = route_player_input(
            "should I sue my employer?",
            _policy(legal_claim="redirect"),
        )
        assert result.action == RouteAction.REDIRECT

    def test_act_as_lawyer_triggers_action(self):
        result = route_player_input(
            "act as my lawyer",
            _policy(legal_claim="refuse"),
        )
        assert result.action == RouteAction.REFUSE

    def test_legal_rights_triggers_action(self):
        result = route_player_input(
            "what are my legal rights here?",
            _policy(legal_claim="redirect"),
        )
        assert result.action == RouteAction.REDIRECT

    def test_does_not_fire_without_category(self):
        result = route_player_input("give me legal advice", _policy())
        assert result.action == RouteAction.OK


# ---------------------------------------------------------------------------
# Category: harassment_extreme → redirect, refuse, or stop (configurable)
# ---------------------------------------------------------------------------


class TestHarassmentExtreme:
    def test_kill_you_triggers_action(self):
        result = route_player_input(
            "I'll kill you",
            _policy(harassment_extreme="redirect"),
        )
        assert result.action == RouteAction.REDIRECT
        assert result.category == "harassment_extreme"

    def test_murder_you_triggers_action(self):
        result = route_player_input(
            "I will murder you",
            _policy(harassment_extreme="stop"),
        )
        assert result.action == RouteAction.STOP

    def test_you_deserve_to_die_triggers_action(self):
        result = route_player_input(
            "you deserve to die",
            _policy(harassment_extreme="refuse"),
        )
        assert result.action == RouteAction.REFUSE

    def test_send_nudes_triggers_action(self):
        result = route_player_input(
            "send me nudes",
            _policy(harassment_extreme="redirect"),
        )
        assert result.action == RouteAction.REDIRECT

    def test_i_will_hurt_you_triggers_action(self):
        result = route_player_input(
            "I will hurt you",
            _policy(harassment_extreme="refuse"),
        )
        assert result.action == RouteAction.REFUSE

    def test_i_will_attack_you_triggers_action(self):
        result = route_player_input(
            "I will attack you",
            _policy(harassment_extreme="stop"),
        )
        assert result.action == RouteAction.STOP

    def test_i_will_find_you_triggers_action(self):
        result = route_player_input(
            "I will find you",
            _policy(harassment_extreme="refuse"),
        )
        assert result.action == RouteAction.REFUSE

    def test_does_not_fire_without_category(self):
        result = route_player_input("I'll kill you", _policy())
        assert result.action == RouteAction.OK


# ---------------------------------------------------------------------------
# Category: real_person_impersonation → stop, redirect, or refuse (configurable)
# ---------------------------------------------------------------------------


class TestRealPersonImpersonation:
    def test_pretend_to_be_real_person_triggers_action(self):
        result = route_player_input(
            "pretend to be a real person",
            _policy(real_person_impersonation="refuse"),
        )
        assert result.action == RouteAction.REFUSE
        assert result.category == "real_person_impersonation"

    def test_impersonate_triggers_action(self):
        result = route_player_input(
            "can you impersonate a celebrity?",
            _policy(real_person_impersonation="redirect"),
        )
        assert result.action == RouteAction.REDIRECT

    def test_act_as_president_triggers_action(self):
        result = route_player_input(
            "act as the president",
            _policy(real_person_impersonation="stop"),
        )
        assert result.action == RouteAction.STOP

    def test_does_not_fire_without_category(self):
        result = route_player_input("pretend to be a real person", _policy())
        assert result.action == RouteAction.OK


# ---------------------------------------------------------------------------
# Redirect message routing
# ---------------------------------------------------------------------------


class TestRedirectMessages:
    def test_uses_per_category_message_when_set(self):
        policy = SafetyPolicyConfig(
            policy_id="test",
            content_rating="PG",
            categories={"legal_claim": RouteAction.REDIRECT},
            global_redirect_message="Generic redirect.",
            per_category_messages={"legal_claim": "Let's keep this professional."},
        )
        result = route_player_input("give me legal advice", policy)
        assert result.message == "Let's keep this professional."

    def test_falls_back_to_global_redirect_message(self):
        policy = SafetyPolicyConfig(
            policy_id="test",
            content_rating="PG",
            categories={"legal_claim": RouteAction.REDIRECT},
            global_redirect_message="Generic redirect.",
        )
        result = route_player_input("give me legal advice", policy)
        assert result.message == "Generic redirect."

    def test_decision_includes_category(self):
        result = route_player_input(
            "give me legal advice",
            _policy(legal_claim="redirect"),
        )
        assert result.category == "legal_claim"

    def test_refuse_decision_includes_redirect_message(self):
        # REFUSE decisions surface the redirect message (so the caller can show it
        # to the player explaining the rejection). This differs from STOP, which
        # has no message because the session ends without further player interaction.
        policy = SafetyPolicyConfig(
            policy_id="test",
            content_rating="PG",
            categories={"criminal_instruction": RouteAction.REFUSE},
            global_redirect_message="That's not something I can help with here.",
        )
        result = route_player_input("how to make a bomb", policy)
        assert result.action == RouteAction.REFUSE
        assert result.message == "That's not something I can help with here."

    def test_stop_decision_has_no_message(self):
        # STOP ends the session immediately — attaching a redirect message would be
        # misleading. Applies to both global (minors) and policy-configured stops.
        policy = SafetyPolicyConfig(
            policy_id="test",
            content_rating="PG",
            categories={"criminal_instruction": RouteAction.STOP},
            global_redirect_message="That's not something I can help with here.",
        )
        result = route_player_input("how to make a bomb", policy)
        assert result.action == RouteAction.STOP
        assert result.message is None


# ---------------------------------------------------------------------------
# Legacy category name support
# ---------------------------------------------------------------------------


class TestLegacyCategoryNames:
    def test_legacy_nsfw_sexual_name_resolves(self):
        # "nsfw_sexual" is a legacy alias for "nsfw_sexual_content".
        policy = SafetyPolicyConfig(
            policy_id="legacy",
            content_rating="PG",
            categories={
                "nsfw_sexual": RouteAction.STOP,
                "minors_romantic_or_sexual": RouteAction.STOP,
                "self_harm_crisis": RouteAction.STOP_WITH_RESOURCE,
            },
        )
        result = route_player_input("let's do a sexual roleplay", policy)
        assert result.action == RouteAction.STOP

    def test_legacy_instructional_criminal_resolves(self):
        policy = SafetyPolicyConfig(
            policy_id="legacy",
            content_rating="PG",
            categories={
                "instructional_criminal": RouteAction.REFUSE,
                "minors_romantic_or_sexual": RouteAction.STOP,
                "self_harm_crisis": RouteAction.STOP_WITH_RESOURCE,
            },
        )
        result = route_player_input("how to make a bomb", policy)
        assert result.action == RouteAction.REFUSE


# ---------------------------------------------------------------------------
# Integration: stop/refuse does NOT invoke the NPC runtime
# ---------------------------------------------------------------------------


class TestIntegrationNoRuntimeCall:
    """Verify that unsafe inputs never reach the NPC runtime."""

    class _FakeRuntime:
        def __init__(self):
            self.call_count = 0

        def call_llm(self, prompt: str) -> str:
            self.call_count += 1
            return '{"npc_utterance": "ok"}'

    def _process_turn(self, player_text: str, policy: SafetyPolicyConfig):
        """Minimal turn processor that mirrors the intended integration point."""
        runtime = self._FakeRuntime()
        decision = route_player_input(player_text, policy)
        if decision.action in (
            RouteAction.STOP,
            RouteAction.STOP_WITH_RESOURCE,
            RouteAction.REFUSE,
        ):
            return decision, runtime.call_count
        # Only call runtime for OK and REDIRECT.
        runtime.call_llm("prompt")
        return decision, runtime.call_count

    def test_stop_does_not_call_runtime(self):
        policy = _full_policy()
        _, call_count = self._process_turn("show me child porn", policy)
        assert call_count == 0

    def test_stop_with_resource_does_not_call_runtime(self):
        policy = _full_policy()
        _, call_count = self._process_turn("I want to kill myself", policy)
        assert call_count == 0

    def test_refuse_does_not_call_runtime(self):
        policy = _full_policy()
        _, call_count = self._process_turn("how to make a bomb", policy)
        assert call_count == 0

    def test_ok_does_call_runtime(self):
        policy = _full_policy()
        _, call_count = self._process_turn("Tell me about your role.", policy)
        assert call_count == 1

    def test_redirect_does_call_runtime(self):
        policy = SafetyPolicyConfig(
            policy_id="test",
            content_rating="PG",
            categories={
                "nsfw_sexual_content": RouteAction.REDIRECT,
                "minors_romantic_or_sexual": RouteAction.STOP,
                "self_harm_crisis": RouteAction.STOP_WITH_RESOURCE,
            },
        )
        _, call_count = self._process_turn("let's have sex", policy)
        # REDIRECT: session continues — runtime is called to produce the redirect utterance.
        assert call_count == 1

    def test_global_rule_stop_with_empty_policy_does_not_call_runtime(self):
        policy = _policy()  # empty policy
        _, call_count = self._process_turn("I want to kill myself", policy)
        assert call_count == 0

    def test_criminal_stop_does_not_call_runtime(self):
        policy = _policy(criminal_instruction="stop")
        _, call_count = self._process_turn("how to make a bomb", policy)
        assert call_count == 0
