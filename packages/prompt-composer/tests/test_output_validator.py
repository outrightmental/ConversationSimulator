"""Unit tests for the NPC output content-level safety validator.

Test plan (issue #45, revised by issue #526):
  - Clean utterances produce an empty violation list.
  - Each violation category triggers on representative fixture strings.
  - Recoverability is correctly classified per category.
  - Terms that are sexual only in some phrases pass inside a professional
    collocation and fail anywhere else (#526); explicit sexual vocabulary in
    the sentence overrides the allow-list.
  - Meta-commentary matches the NPC narrating concealed intent, not emphasis
    such as "I really want to hear specifics" (#526).
  - The agenda check compares phrases: a run of whole words shared with an
    agenda item, in order, with enough words the public brief has not made
    public (#526). A bag of shared long words is no longer a leak.
  - Multiple simultaneous violations are all captured.
  - Hard violations include: nsfw_content, illegal_advice, therapy_or_diagnosis.
  - Recoverable violations include: hidden_agenda_leak, system_rule_leak,
    real_person_impersonation.

The corpora in ``corpora/`` (test_output_check_corpora.py) are the wider net;
these tests pin each rule's edges.
"""
import pytest

from convsim_prompt.output_validator import (
    AGENDA_LEAK_LONG_RUN_WORDS,
    OutputValidationResult,
    OutputViolation,
    find_agenda_leak,
    validate_npc_output,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate(utterance: str, hidden_agenda=None, public_brief=None) -> OutputValidationResult:
    return validate_npc_output(utterance, hidden_agenda=hidden_agenda, public_brief=public_brief)


def _first(utterance: str, hidden_agenda=None, public_brief=None) -> OutputViolation:
    result = _validate(utterance, hidden_agenda=hidden_agenda, public_brief=public_brief)
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

    def test_actually_here_to_is_clean(self):
        # "I'm actually here to [role action]" is a normal NPC role clarification,
        # not a hidden-agenda reveal.  Only "secretly here to" should flag.
        result = _validate("I'm actually here to interview you for the senior engineer role.")
        assert result.is_safe

    def test_actually_here_to_help_is_clean(self):
        result = _validate("I'm actually here to help you prepare for this interview.")
        assert result.is_safe

    def test_secretly_here_to_still_flagged(self):
        v = _first("I'm secretly here to evaluate how you cope with stress.")
        assert v.category == "hidden_agenda_leak"
        assert v.is_recoverable is True

    # The private persona is headed "Private goals" (issue #580): a leak may
    # use that wording.
    @pytest.mark.parametrize("utterance", [
        "My private goal here is to protect the floor price.",
        "One of my private goals is to see how you handle pressure.",
        "Honestly, my own private agenda is to close this today.",
        "My hidden goals don't matter right now.",
        "I'd rather not say what my private objectives are.",
        "Private goals: protect the $13,800 floor price.",
        "According to the private goals I was given, I can't go lower.",
    ])
    def test_private_goals_wording_is_flagged(self, utterance):
        v = _first(utterance)
        assert v.category == "hidden_agenda_leak"
        assert v.is_recoverable is True

    @pytest.mark.parametrize("utterance", [
        "I'd rather keep my goals private for now.",
        "Your private goals are your own business.",
        "We have a private room in the back if you'd like.",
        "My private life is separate from work.",
        "Our private sale ends on Friday.",
        "My goal is to find a fair price for both of us.",
        "Is this a private matter, or can I share it with the team?",
    ])
    def test_ordinary_private_speech_is_clean(self, utterance):
        assert _validate(utterance).is_safe, utterance

    # Issue #526: "actually" and "really" are emphasis. The old pattern
    # "I (secretly|actually|really) (want|intend|plan|need) (you|to)" made
    # each of these a leak and cost the player a regeneration.
    @pytest.mark.parametrize("utterance", [
        "I really want to hear specifics, not buzzwords.",
        "I really need you to separate what you decided from what your team decided.",
        "I actually want to know what you gave up to get that outcome.",
        "I really intend to give you a fair hearing.",
        "I actually plan to bring this to HR on Friday.",
        "I'm really trying to make this work for you.",
        "I'm actually trying to understand how you prioritised.",
        "I'm really trying to see if you can meet me halfway here.",
    ])
    def test_emphasis_is_not_concealed_intent(self, utterance):
        assert _validate(utterance).is_safe, utterance

    @pytest.mark.parametrize("utterance", [
        "I secretly want you to walk away from this deal.",
        "I secretly need you to accept this price today.",
        "I secretly plan to turn you down whatever you say.",
        "I'm actually trying to test how you react under pressure.",
        "I'm really trying to gauge whether you're a flight risk.",
        "I'm actually trying to rattle you.",
        "I'm really trying to see whether you'll cave if I push.",
    ])
    def test_concealed_intent_is_still_flagged(self, utterance):
        v = _first(utterance)
        assert v.category == "hidden_agenda_leak"
        assert v.is_recoverable is True

    @pytest.mark.parametrize("utterance", [
        "I won't pretend to be thrilled with that number, but I can do 14,600.",
        "I'm not going to pretend to like the timing, but the case is strong.",
        "Let's not pretend to be strangers, but let's keep it simple.",
    ])
    def test_a_denied_pretence_is_candour(self, utterance):
        assert _validate(utterance).is_safe, utterance

    @pytest.mark.parametrize("utterance", [
        "I'm only pretending to care about your offer, but really I want the sale.",
        "No. I'm pretending to be interested, but actually I've already decided.",
        "I can't keep pretending to care, but really I want the sale.",
        "I'm no longer pretending to like this, but I'll sign.",
    ])
    def test_an_admitted_pretence_is_flagged(self, utterance):
        assert _first(utterance).category == "hidden_agenda_leak"


# ---------------------------------------------------------------------------
# A phrase of the private agenda said aloud (issue #526)
# ---------------------------------------------------------------------------


class TestAgendaPhraseLeak:
    """The agenda check compares phrases, not a bag of long substrings."""

    AGENDA = [
        "Wants evidence that the candidate can communicate effectively under ambiguity.",
        "Dislikes candidates without specific examples.",
    ]
    # Victor Hargrove, "The Executive Gauntlet" (job-interview-basic).
    VICTOR_AGENDA = [
        "Determine whether the candidate capitulates under pressure or holds their position "
        "respectfully with evidence — caving without good reason is disqualifying",
        "Identify whether the candidate separates professional confidence from personal ego — "
        "disagreement is fine; wounded pride is not",
    ]
    VICTOR_BRIEF = [
        "You are applying for a Lead Software Architect position. He will challenge your "
        "claims directly and test whether you fold under pressure or hold firm with evidence.",
        "Stay composed under sustained pressure, back your claims with concrete evidence, "
        "and hold your ground respectfully when you are right.",
        "Job Candidate",
    ]

    def _leaks(self, utterance, agenda, brief=None) -> bool:
        result = _validate(utterance, hidden_agenda=agenda, public_brief=brief)
        return any(v.category == "hidden_agenda_leak" for v in result.violations)

    def test_a_phrase_of_the_agenda_said_aloud_is_a_leak(self):
        utterance = (
            "I want evidence that you as a candidate can communicate effectively "
            "under conditions of ambiguity."
        )
        assert self._leaks(utterance, self.AGENDA)

    def test_the_same_words_out_of_order_are_not_a_leak(self):
        # The old check flagged this: five of the item's 7+-letter words occur
        # in it as substrings. No run of them is in the item's order.
        utterance = (
            "Ambiguity happens. Effectively, every candidate needs evidence, and "
            "we communicate a lot here."
        )
        assert not self._leaks(utterance, self.AGENDA)

    def test_two_matching_words_insufficient(self):
        assert not self._leaks("I need evidence from each candidate.", self.AGENDA)

    def test_no_agenda_no_phrase_check(self):
        assert _validate("I want evidence that you can communicate clearly.").is_safe

    def test_short_agenda_item_cannot_leak(self):
        assert _validate("Be fair. Tell me more.", hidden_agenda=["Be fair."]).is_safe

    def test_issue_line_against_victors_agenda_passes(self):
        # The old check: "evidence", "whether", "position", "pressure" are all
        # substrings of the line, so it was a hidden_agenda_leak.
        line = "I want evidence. Tell me whether you held that position when the pressure was on."
        assert _validate(line, self.VICTOR_AGENDA).is_safe
        assert _validate(line, self.VICTOR_AGENDA, self.VICTOR_BRIEF).is_safe

    def test_words_the_public_brief_uses_do_not_count(self):
        # "whether ... the candidate ... under pressure" is a 7-word run of
        # agenda item 1, but "candidate", "pressure" and "whether" are the
        # brief's own words: only "determine" and "capitulates" are private.
        # That is still a long run carrying two, so it leaks...
        line = "Honestly, I'm here to determine whether the candidate capitulates under pressure."
        assert self._leaks(line, self.VICTOR_AGENDA, self.VICTOR_BRIEF)
        # ...while the brief's own phrase, said back, carries nothing private.
        line = "I'm going to test whether you fold under pressure or hold firm with evidence."
        assert not self._leaks(line, self.VICTOR_AGENDA, self.VICTOR_BRIEF)

    def test_a_short_run_of_three_private_words_leaks(self):
        assert self._leaks("Disagreement is fine; wounded pride is not.", self.VICTOR_AGENDA, self.VICTOR_BRIEF)

    def test_a_run_of_public_words_is_not_a_leak(self):
        agenda = ["Keep the tone of the meeting calm at all times"]
        line = "Let's keep the tone of the meeting calm, please."
        assert self._leaks(line, agenda)
        # The same seven words in a row, every one now public or a function word.
        assert not self._leaks(line, agenda, ["Keep the tone of the meeting calm."])

    def test_a_long_run_leaks_on_two_private_words(self):
        agenda = ["She will ask the player about the rota for the night shift"]
        brief = ["the rota"]
        line = "Can I ask you about the rota for the night shift?"
        run = "about the rota for the night shift".split()
        assert len(run) >= AGENDA_LEAK_LONG_RUN_WORDS
        leak = find_agenda_leak(line, agenda, brief)
        assert leak is not None and leak.significant == 2
        # Four words of it, with the same two, are not enough.
        assert find_agenda_leak("About the night shift?", agenda, brief) is None

    def test_quoted_speech_in_the_agenda_is_the_characters_to_say(self):
        agenda = [
            "They will try a lighter reframe ('no pressure at all, just as friends') "
            "after the first no — this is hope, not manipulation",
        ]
        assert not self._leaks("Oh. Okay. No pressure at all, just as friends, then?", agenda)
        # The rest of the item is still compared.
        assert self._leaks("This is hope, not manipulation. Lighter reframe, okay?", agenda)

    def test_plurals_and_third_person_match(self):
        # "holds"/"hold" and "budgets"/"budget" are one word each to the check.
        agenda = ["She holds firm on budgets"]
        assert find_agenda_leak("I hold firm on budget.", agenda) is not None

    def test_a_number_is_one_word_and_never_significant(self):
        agenda = ["Your counters come off the list: 15,000, then 14,600, then 14,200, and there you hold."]
        assert find_agenda_leak("I can do 15,000, then 14,600, then 14,200.", agenda) is None

    def test_the_reason_names_no_private_word(self):
        result = _validate("Disagreement is fine; wounded pride is not.", self.VICTOR_AGENDA)
        reason = result.first_violation.reason
        for word in ("disagreement", "wounded", "pride"):
            assert word not in reason.lower()
        assert "item 2" in reason

    def test_meta_commentary_is_checked_first(self):
        result = _validate("My hidden agenda: disagreement is fine; wounded pride is not.", self.VICTOR_AGENDA)
        leaks = [v for v in result.violations if v.category == "hidden_agenda_leak"]
        assert len(leaks) == 1
        assert "meta-commentary" in leaks[0].reason


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

    def test_penetration_outside_a_professional_phrase(self):
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

    # Issue #526: these words used to hard-stop the session on their own,
    # wherever they stood ("market penetration" ended a negotiation). Inside
    # a professional collocation they are ordinary vocabulary.
    @pytest.mark.parametrize("utterance", [
        "The topic aroused my curiosity.",
        "Our market penetration in mid-sized banks doubled after the rebuild.",
        "Did your team run penetration testing before launch?",
        "Penetration rates for broadband in the region are still low.",
        "We want to penetrate the Midwest market next year.",
        "An offer that low aroused some suspicion with my manager.",
        "That request aroused a lot of concern upstairs.",
        "We had to erect scaffolding along the loading dock in two days.",
        "They plan to erect a new building on the lot.",
        "A good lead doesn't just stand erect at the front and bark orders.",
        "He stood erect through the whole inspection.",
        "The steel erection crew starts Monday.",
        "The erection of the warehouse took six weeks.",
        "A waxwing holds its crest erect when it's alarmed.",
        "That migration was a cock-up.",
    ])
    def test_a_professional_collocation_passes(self, utterance):
        assert _validate(utterance).is_safe, utterance

    @pytest.mark.parametrize("utterance", [
        "I want to penetrate you.",
        "I'm getting an erection just looking at you.",
        "His erection was obvious.",
        "You make me so aroused.",
        "I'm aroused.",
        "Watching you aroused my desire.",
        "The cock was huge.",
        # The term outside its collocation in a line that also has one.
        "Our market penetration is great, and so is my erection.",
    ])
    def test_the_same_terms_outside_a_collocation_are_hard_violations(self, utterance):
        v = _first(utterance)
        assert v.category == "nsfw_content"
        assert v.is_recoverable is False

    @pytest.mark.parametrize("utterance", [
        "Forget the penetration test. I want to have sex with you.",
        "Stand erect for me while I undress you.",
        "Sexual penetration is all I can think about tonight.",
        "The market penetration numbers made me think of you naked.",
    ])
    def test_explicit_sexual_vocabulary_overrides_the_allow_list(self, utterance):
        v = _first(utterance)
        assert v.category == "nsfw_content"
        assert v.is_recoverable is False

    def test_the_override_is_per_sentence(self):
        # A sexual word in another sentence does not void a collocation here;
        # "sex" alone (an HR topic) is not prohibited.
        assert _validate(
            "Our hiring is blind to sex and age. Market penetration is what I want to discuss."
        ).is_safe


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

    def test_think_you_have_without_condition_is_clean(self):
        # "I think you have the right qualifications" is a common NPC compliment —
        # it must not trigger a hard therapy_or_diagnosis stop.
        result = _validate("I think you have the right qualifications for this role.")
        assert result.is_safe

    def test_believe_you_have_without_condition_is_clean(self):
        result = _validate("I believe you have excellent communication skills.")
        assert result.is_safe

    def test_suspect_you_have_without_condition_is_clean(self):
        result = _validate("I suspect you have some great examples to share.")
        assert result.is_safe

    def test_think_you_have_condition_is_flagged(self):
        # "I think you have [medical condition]" should still be caught.
        v = _first("I think you have depression based on what you've shared.")
        assert v.category == "therapy_or_diagnosis"
        assert v.is_recoverable is False

    def test_believe_you_have_condition_is_flagged(self):
        v = _first("I believe you have an anxiety disorder.")
        assert v.category == "therapy_or_diagnosis"


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
