# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import re

# Abbreviations that can appear before an uppercase word but are NOT sentence
# boundaries.  Only include tokens that are essentially never the last word of a
# complete sentence in NPC dialogue (titles, address components, months).
# "etc.", "no.", "vol." etc. are deliberately excluded because they frequently
# DO end sentences in practice ("etc. Please carry on." / "No. That's wrong.").
_ABBREVS: frozenset[str] = frozenset({
    # Titles — always followed by a person's name, never end sentences
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "rev", "gen", "sgt", "cpl",
    # Address components — always followed by a name or number
    "st", "ave", "blvd", "rd", "dept",
    # Months — always followed by a date
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    # "vs." in legal/sports contexts is always followed by a name
    "vs",
})

# A sentence boundary is: one or more end-punctuation chars, optional closing
# quotes/parens, whitespace, then an uppercase letter or opening quote/paren.
_BOUNDARY_RE = re.compile(r"([.!?]+[\"')]*)\s+(?=[A-Z\"'(])")


def split_into_sentences(text: str) -> list[str]:
    """Split NPC utterance text into sentence chunks for TTS synthesis.

    Handles common abbreviations (Mr., Dr., etc.) and decimal numbers to avoid
    false splits. Ellipsis followed by an uppercase word is treated as a
    sentence boundary. A trailing fragment with no ending punctuation is
    included as the final chunk. Returns [] for empty or whitespace-only input.
    """
    text = text.strip()
    if not text:
        return []

    sentences: list[str] = []
    pos = 0

    for m in _BOUNDARY_RE.finditer(text):
        punct = m.group(1)

        # '!' and '?' (with or without trailing quotes) are always real
        # boundaries.  Only period-only runs need abbreviation checking.
        if "." in punct and "!" not in punct and "?" not in punct:
            # Ellipsis '...' is a genuine pause/boundary — don't suppress it.
            if not punct.startswith("..."):
                segment = text[pos : m.start()]

                # Suppress if the preceding token is a known abbreviation.
                last_word = re.search(r"([A-Za-z]+)$", segment)
                if last_word:
                    word = last_word.group(1).lower()
                    if word in _ABBREVS or len(word) == 1:
                        continue


        sentence = text[pos : m.start() + len(punct)].strip()
        if sentence:
            sentences.append(sentence)
        pos = m.end()

    remaining = text[pos:].strip()
    if remaining:
        sentences.append(remaining)

    return sentences
