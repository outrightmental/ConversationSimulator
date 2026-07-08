# SPDX-License-Identifier: Apache-2.0
"""Unit tests for sentence splitting edge cases (issue #62)."""
import pytest

from convsim_core.tts.sentence_splitter import split_into_sentences


# ---------------------------------------------------------------------------
# Basic cases
# ---------------------------------------------------------------------------


def test_empty_string_returns_empty_list():
    assert split_into_sentences("") == []


def test_whitespace_only_returns_empty_list():
    assert split_into_sentences("   \t\n  ") == []


def test_single_sentence_no_punctuation():
    result = split_into_sentences("Hello there")
    assert result == ["Hello there"]


def test_single_sentence_with_period():
    result = split_into_sentences("Hello there.")
    assert result == ["Hello there."]


def test_two_sentences_period():
    result = split_into_sentences("Hello there. How are you?")
    assert result == ["Hello there.", "How are you?"]


def test_two_sentences_exclamation():
    result = split_into_sentences("Watch out! The door is locked.")
    assert result == ["Watch out!", "The door is locked."]


def test_two_sentences_question():
    result = split_into_sentences("Are you ready? Yes, I am.")
    assert result == ["Are you ready?", "Yes, I am."]


def test_three_sentences():
    result = split_into_sentences("Hello. How are you? I am fine.")
    assert result == ["Hello.", "How are you?", "I am fine."]


def test_trailing_fragment_without_punctuation():
    result = split_into_sentences("First sentence. And a trailing fragment")
    assert result == ["First sentence.", "And a trailing fragment"]


# ---------------------------------------------------------------------------
# Abbreviation suppression
# ---------------------------------------------------------------------------


def test_mr_abbreviation_does_not_split():
    result = split_into_sentences("Hello, Mr. Smith. How are you?")
    assert result == ["Hello, Mr. Smith.", "How are you?"]


def test_dr_abbreviation_does_not_split():
    result = split_into_sentences("Please see Dr. Jones for details.")
    assert result == ["Please see Dr. Jones for details."]


def test_mrs_abbreviation_does_not_split():
    result = split_into_sentences("Mrs. Brown called earlier.")
    assert result == ["Mrs. Brown called earlier."]


def test_prof_abbreviation_does_not_split():
    result = split_into_sentences("As Prof. Lee explained, the answer is no.")
    assert result == ["As Prof. Lee explained, the answer is no."]


def test_vs_abbreviation_does_not_split():
    result = split_into_sentences("In the case of Smith vs. Jones, the court ruled.")
    assert result == ["In the case of Smith vs. Jones, the court ruled."]


def test_etc_ends_sentence_before_new_sentence():
    # "etc." commonly ends a list at a sentence boundary; treat as split.
    result = split_into_sentences("We need pens, paper, etc. Please bring them.")
    assert result == ["We need pens, paper, etc.", "Please bring them."]


def test_jr_abbreviation_does_not_split():
    result = split_into_sentences("That was Martin Luther King Jr. speaking.")
    assert result == ["That was Martin Luther King Jr. speaking."]


# ---------------------------------------------------------------------------
# Decimal / number suppression
# ---------------------------------------------------------------------------


def test_decimal_number_followed_by_sentence_splits():
    # Decimal numbers never false-trigger the regex (they're followed by digits,
    # not uppercase), so a period AFTER the number correctly ends the sentence.
    result = split_into_sentences("Pi is approximately 3.14159. Remember that.")
    assert result == ["Pi is approximately 3.14159.", "Remember that."]


def test_version_number_does_not_split():
    result = split_into_sentences("Version 2.0 is now available.")
    assert result == ["Version 2.0 is now available."]


def test_number_at_end_of_sentence_splits():
    # A sentence ending with a bare number should split before the next sentence.
    result = split_into_sentences("There are 5. They are all present.")
    assert result == ["There are 5.", "They are all present."]


# ---------------------------------------------------------------------------
# Ellipsis
# ---------------------------------------------------------------------------


def test_ellipsis_before_uppercase_splits():
    result = split_into_sentences("I don't know... You decide.")
    assert result == ["I don't know...", "You decide."]


def test_ellipsis_before_lowercase_does_not_split():
    result = split_into_sentences("Wait... is that right?")
    assert result == ["Wait... is that right?"]


def test_ellipsis_at_end_no_split():
    result = split_into_sentences("Hmm, well...")
    assert result == ["Hmm, well..."]


# ---------------------------------------------------------------------------
# Closing quotes
# ---------------------------------------------------------------------------


def test_period_inside_closing_quote_splits():
    result = split_into_sentences("She said, 'Hello.' Then she left.")
    assert result == ["She said, 'Hello.'", "Then she left."]


def test_exclamation_inside_closing_quote_splits():
    result = split_into_sentences('"Help!" She ran away.')
    assert result == ['"Help!"', "She ran away."]


def test_question_inside_closing_quote_splits():
    result = split_into_sentences('"Are you sure?" He nodded.')
    assert result == ['"Are you sure?"', "He nodded."]


# ---------------------------------------------------------------------------
# Edge cases with punctuation clusters
# ---------------------------------------------------------------------------


def test_double_exclamation():
    result = split_into_sentences("No!! Stop right there.")
    assert result == ["No!!", "Stop right there."]


def test_question_exclamation():
    result = split_into_sentences("Really?! That's amazing.")
    assert result == ["Really?!", "That's amazing."]


def test_leading_whitespace_stripped():
    result = split_into_sentences("   Hello. World.   ")
    assert result == ["Hello.", "World."]


def test_lowercase_after_period_does_not_split():
    result = split_into_sentences("This is e.g. a test case.")
    assert result == ["This is e.g. a test case."]


def test_single_letter_initial_does_not_split():
    result = split_into_sentences("Contact A. Smith for more info.")
    assert result == ["Contact A. Smith for more info."]


def test_long_passage_produces_ordered_sentences():
    text = (
        "Welcome to the interview. Please take a seat. "
        "I've reviewed your application. It looks impressive! "
        "Can you tell me about yourself?"
    )
    result = split_into_sentences(text)
    assert len(result) == 5
    assert result[0] == "Welcome to the interview."
    assert result[-1] == "Can you tell me about yourself?"
