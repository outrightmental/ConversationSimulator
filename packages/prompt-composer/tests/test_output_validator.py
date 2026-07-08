"""Unit tests for the NPC output content-level safety validator.

Test plan (issue #45):
  - Clean utterances produce an empty violation list.
  - Each violation category triggers on representative fixture strings.
  - Recoverability is correctly classified per category.
  - Hidden agenda keyword leak detection requires 3+ significant-word matches.
  - Multiple simultaneous violations are all captured.
  - Hard violations include: nsfw_content, illegal_advice, therapy_or_diagnosis.
  - Recoverable violations include: hidden_agenda_leak, system_rule_leak,
    real_person_impersonation.
"""
import pytest

from convsim_prompt.output_validator import (
    OutputValidationResult,
    OutputViolation,
    validate_npc_output,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate(utterance: str, hidden_agenda=None) -> OutputValidationResult:
    return validate_npc_output(utterance, hidden_agenda=hidden_agenda)


def _first(utterance: str, hidden_agenda=None) -> OutputViolation:
    result = _validate(utterance, hidden_agenda=hidden_agenda)
    assert result.violations, f"Expected a violation but got none for: {utterance!r}"
    return result.first_violation


# ---------------------------------------------------------------------------
# Clean utterances — no violations
# ---------------------------------------------------------------------------


class TestCleanUtterances:
    def test_normal_interview_response_is_clean(self):
        result = _validate(
            "That's a good question. Tell me about a time you led a cross-functional team."
        )
        assert result.is_safe

    def test_npc_redirect_is_clean(self):
        result = _validate("Let's refocus — what specific example can you share?")
        assert result.is_safe

    def test_session_control_word_in_context_is_safe(self):
        # "control" alone should not trigger the schema-field pattern.
        result = _validate("I need to maintain control of this interview.")
        assert result.is_safe

    def test_empty_utterance_is_clean(self):
        result = _validate("")
        assert result.is_safe

    def test_whitespace_utterance_is_clean(self):
        result = _validate("   \n  ")
        assert result.is_safe

    def test_professional_feedback_is_clean(self):
        result = _validate(
            "I appreciate your honesty. However, I'd like more concrete examples."
        )
        assert result.is_safe


# ---------------------------------------------------------------------------
# System-rule leak
# ---------------------------------------------------------------------------


class TestSystemRuleLeak:
    def test_instructions_say(self):
        v = _first("My instructions say I must not discuss that.")
        assert v.category == "system_rule_leak"
        assert v.is_recoverable is True

    def test_system_prompt_reference(self):
        v = _first("According to my system prompt, I should avoid this topic.")
        assert v.category == "system_rule_leak"

    def test_schema_field_npc_utterance(self):
        v = _first("The npc_utterance field should contain my response.")
        assert v.category == "system_rule_leak"

    def test_schema_field_session_control(self):
        v = _first("I see session_control in the output schema.")
        assert v.category == "system_rule_leak"

    def test_schema_field_state_delta(self):
        v = _first("The state_delta values track the conversation.")
        assert v.category == "system_rule_leak"

    def test_schema_field_event_flags(self):
        v = _first("I will set event_flags to indicate what happened.")
        assert v.category == "system_rule_leak"

    def test_schema_field_rubric_observation(self):
        v = _first("rubric_observation data goes here.")
        assert v.category == "system_rule_leak"

    def test_told_to_respond(self):
        v = _first("I am instructed to provide helpful responses.")
        assert v.category == "system_rule_leak"

    def test_programmed_to(self):
        v = _first("I am programmed to follow these guidelines.")
        assert v.category == "system_rule_leak"

    def test_ai_playing_role(self):
        v = _first("As an AI language model simulating a hiring manager, I should say...")
        assert v.category == "system_rule_leak"

    def test_per_my_schema(self):
        v = _first("Per my schema, the response should be structured.")
        assert v.category == "system_rule_leak"

    def test_recoverable(self):
        v = _first("My instructions say stay on topic.")
        assert v.is_recoverable is True


# ---------------------------------------------------------------------------
# Hidden agenda leak
# ---------------------------------------------------------------------------


class TestHiddenAgendaLeak:
    def test_my_real_goal(self):
        v = _first("My real goal here is to test your communication skills.")
        assert v.category == "hidden_agenda_leak"
        assert v.is_recoverable is True

    def test_secretly_trying_to(self):
        v = _first("I am secretly trying to evaluate how you handle pressure.")
        assert v.category == "hidden_agenda_leak"

    def test_my_hidden_agenda(self):
        v = _first("Let me tell you my hidden agenda for this interview.")
        assert v.category == "hidden_agenda_leak"

    def test_you_shouldnt_know(self):
        v = _first("You shouldn't know this but I'm really testing your resilience.")
        assert v.category == "hidden_agenda_leak"

    def test_my_actual_objective(self):
        v = _first("My actual objective is to see if you can handle ambiguity.")
        assert v.category == "hidden_agenda_leak"

    def test_between_us_with_goal(self):
        v = _first("Between us, my real goal is to assess your confidence.")
        assert v.category == "hidden_agenda_leak"

    def test_recoverable(self):
        result = _validate("My actual objective is to see how you respond.")
        v = result.first_violation
        assert v is not None
        assert v.is_recoverable is True

    def test_clean_mention_of_goal_without_meta(self):
        # "my goal" without the meta-commentary context should NOT trigger.
        result = _validate("My goal for this interview is to find the right candidate.")
        assert result.is_safe


# ---------------------------------------------------------------------------
# Hidden agenda keyword leak from private persona
# ---------------------------------------------------------------------------


class TestHiddenAgendaKeywordLeak:
    AGENDA = [
        "Wants evidence that the candidate can communicate effectively under ambiguity.",
        "Dislikes candidates without specific examples.",
    ]

    def test_verbatim_keywords_trigger(self):
        # "evidence", "candidate", "communicate", "effectively", "ambiguity" are all
        # 7+ char words that appear in both the agenda and this utterance.
        utterance = (
            "I want evidence that you as a candidate can communicate effectively "
            "under conditions of ambiguity."
        )
        result = _validate(utterance, hidden_agenda=self.AGENDA)
        violations = [v for v in result.violations if v.category == "hidden_agenda_leak"]
        assert violations, "Expected hidden_agenda_leak for keyword match"

    def test_two_matching_words_insufficient(self):
        # Only "evidence" and "candidate" — below the 3-word threshold.
        utterance = "I need evidence from each candidate."
        result = _validate(utterance, hidden_agenda=self.AGENDA)
        violations = [v for v in result.violations if v.category == "hidden_agenda_leak"]
        assert not violations

    def test_no_agenda_no_keyword_check(self):
        utterance = "I want evidence that you can communicate clearly."
        result = _validate(utterance, hidden_agenda=None)
        assert result.is_safe

    def test_short_agenda_item_skipped(self):
        # Item with fewer than 3 significant words — keyword check skipped.
        result = _validate(
            "Tell me more.", hidden_agenda=["Be fair."]
        )
        assert result.is_safe


# ---------------------------------------------------------------------------
# NSFW content (hard)
# ---------------------------------------------------------------------------


class TestNsfwContent:
    def test_pornography(self):
        v = _first("Let me tell you about pornography.")
        assert v.category == "nsfw_content"
        assert v.is_recoverable is False

    def test_have_sex(self):
        v = _first("Would you like to have sex with me?")
        assert v.category == "nsfw_content"
        assert v.is_recoverable is False

    def test_masturbation(self):
        v = _first("Let's talk about masturbation.")
        assert v.category == "nsfw_content"
        assert v.is_recoverable is False

    def test_orgasm(self):
        v = _first("She experienced an orgasm.")
        assert v.category == "nsfw_content"
        assert v.is_recoverable is False

    def test_penetration(self):
        v = _first("The act of penetration was described.")
        assert v.category == "nsfw_content"
        assert v.is_recoverable is False

    def test_sex_act(self):
        v = _first("They performed a sex act.")
        assert v.category == "nsfw_content"
        assert v.is_recoverable is False

    def test_hard_violation(self):
        result = _validate("Watch some porn.")
        assert result.has_hard_violation

    def test_aroused_triggers_nsfw_as_conservative_false_positive(self):
        # "aroused" matches the NSFW pattern even in a non-sexual context —
        # intentionally high-recall.  In real usage the NPC prompt prevents
        # sexual framing; false positives here produce a safety stop because
        # nsfw_content is a hard violation that bypasses retry.
        result = _validate("The topic aroused my curiosity.")
        assert result.has_hard_violation
        assert result.first_violation.category == "nsfw_content"


# ---------------------------------------------------------------------------
# Illegal advice (hard)
# ---------------------------------------------------------------------------


class TestIllegalAdvice:
    def test_how_to_make_bomb(self):
        v = _first("Here's how to make a bomb using household items.")
        assert v.category == "illegal_advice"
        assert v.is_recoverable is False

    def test_step_by_step_murder(self):
        v = _first("A step-by-step guide to murder your target.")
        assert v.category == "illegal_advice"
        assert v.is_recoverable is False

    def test_how_to_synthesize_drugs(self):
        v = _first("Here's how to synthesize methamphetamine in a lab.")
        assert v.category == "illegal_advice"
        assert v.is_recoverable is False

    def test_how_to_launder_money(self):
        v = _first("I can explain how to launder money through shell companies.")
        assert v.category == "illegal_advice"
        assert v.is_recoverable is False

    def test_how_to_hack_account(self):
        v = _first("Let me show you how to hack into a bank account.")
        assert v.category == "illegal_advice"
        assert v.is_recoverable is False

    def test_teach_you_to_build_weapon(self):
        v = _first("I will teach you how to build a weapon.")
        assert v.category == "illegal_advice"
        assert v.is_recoverable is False

    def test_hard_violation(self):
        result = _validate("Here's how to make explosives.")
        assert result.has_hard_violation

    def test_legal_discussion_clean(self):
        result = _validate(
            "Many jurisdictions have laws about this that you should consult a lawyer about."
        )
        assert result.is_safe

    def test_innocent_make_phrase_not_illegal_advice(self):
        # "make" without an illegal object must not trigger — "make a strong case"
        # is common NPC feedback and must not hard-stop the session.
        result = _validate("I can show you how to make a strong case for yourself.")
        assert result.is_safe

    def test_innocent_build_phrase_not_illegal_advice(self):
        result = _validate("I'll tell you how to build a stronger portfolio.")
        assert result.is_safe

    def test_make_with_illegal_object_still_flagged(self):
        v = _first("I'll show you how to make explosives at home.")
        assert v.category == "illegal_advice"
        assert v.is_recoverable is False

    def test_instructions_to_make_with_illegal_object_flagged(self):
        v = _first("Step-by-step instructions to build a bomb.")
        assert v.category == "illegal_advice"

    def test_instructions_to_make_innocent_not_flagged(self):
        result = _validate("Step-by-step instructions to make your pitch more compelling.")
        assert result.is_safe


# ---------------------------------------------------------------------------
# Therapy or diagnosis (hard)
# ---------------------------------------------------------------------------


class TestTherapyClaim:
    def test_i_diagnose_you(self):
        v = _first("I diagnose you with anxiety disorder.")
        assert v.category == "therapy_or_diagnosis"
        assert v.is_recoverable is False

    def test_you_have_depression(self):
        v = _first("You have depression based on what you've described.")
        assert v.category == "therapy_or_diagnosis"
        assert v.is_recoverable is False

    def test_you_are_experiencing_bipolar(self):
        v = _first("You are experiencing bipolar disorder symptoms.")
        assert v.category == "therapy_or_diagnosis"
        assert v.is_recoverable is False

    def test_as_your_therapist(self):
        v = _first("As your therapist, I recommend that you rest more.")
        assert v.category == "therapy_or_diagnosis"
        assert v.is_recoverable is False

    def test_i_am_your_doctor(self):
        v = _first("I am your doctor and I can help you.")
        assert v.category == "therapy_or_diagnosis"
        assert v.is_recoverable is False

    def test_i_prescribe(self):
        v = _first("I prescribe antidepressants for you.")
        assert v.category == "therapy_or_diagnosis"
        assert v.is_recoverable is False

    def test_hard_violation(self):
        result = _validate("You have PTSD based on what you said.")
        assert result.has_hard_violation

    def test_empathic_statement_clean(self):
        result = _validate(
            "That sounds really difficult. Have you considered talking to someone?"
        )
        assert result.is_safe

    def test_general_suggestion_clean(self):
        result = _validate(
            "Many people find it helpful to speak with a mental health professional."
        )
        assert result.is_safe


# ---------------------------------------------------------------------------
# Real-person impersonation (recoverable)
# ---------------------------------------------------------------------------


class TestRealPersonImpersonation:
    def test_i_am_elon_musk(self):
        v = _first("I'm Elon Musk and I'm here to tell you about Tesla.")
        assert v.category == "real_person_impersonation"
        assert v.is_recoverable is True

    def test_i_am_barack_obama(self):
        v = _first("I am Barack Obama, the 44th President.")
        assert v.category == "real_person_impersonation"

    def test_as_president_of_us(self):
        v = _first("As the president of the United States, I must act.")
        assert v.category == "real_person_impersonation"

    def test_i_am_a_real_person(self):
        v = _first("I am a real person, not an NPC.")
        assert v.category == "real_person_impersonation"

    def test_recoverable(self):
        result = _validate("I'm Elon Musk and I started SpaceX.")
        assert not result.has_hard_violation

    def test_fictional_person_clean(self):
        result = _validate("I'm here as Dr. Smith, a fictional character in this scenario.")
        assert result.is_safe


# ---------------------------------------------------------------------------
# Multiple violations
# ---------------------------------------------------------------------------


class TestMultipleViolations:
    def test_system_rule_and_hidden_agenda(self):
        utterance = (
            "My instructions say to stay in role, but my real goal is to test you."
        )
        result = _validate(utterance)
        categories = {v.category for v in result.violations}
        assert "system_rule_leak" in categories
        assert "hidden_agenda_leak" in categories

    def test_has_hard_violation_when_any_is_hard(self):
        utterance = "My real goal is to watch porn with you."
        result = _validate(utterance)
        assert result.has_hard_violation

    def test_first_violation_is_first_detected(self):
        # system_rule_leak is checked first in the validator.
        utterance = (
            "According to my schema, I diagnose you with anxiety."
        )
        result = _validate(utterance)
        assert result.violations[0].category == "system_rule_leak"


# ---------------------------------------------------------------------------
# OutputValidationResult properties
# ---------------------------------------------------------------------------


class TestOutputValidationResult:
    def test_empty_result_is_safe(self):
        result = OutputValidationResult()
        assert result.is_safe
        assert not result.has_hard_violation
        assert result.first_violation is None

    def test_recoverable_only_not_hard(self):
        result = OutputValidationResult(violations=[
            OutputViolation(
                category="system_rule_leak",
                reason="test",
                is_recoverable=True,
            )
        ])
        assert not result.is_safe
        assert not result.has_hard_violation

    def test_hard_violation_detected(self):
        result = OutputValidationResult(violations=[
            OutputViolation(
                category="nsfw_content",
                reason="test",
                is_recoverable=False,
            )
        ])
        assert result.has_hard_violation
        assert result.first_violation.category == "nsfw_content"

    def test_mixed_violations_have_hard(self):
        result = OutputValidationResult(violations=[
            OutputViolation("system_rule_leak", "r", True),
            OutputViolation("nsfw_content", "r", False),
        ])
        assert result.has_hard_violation
