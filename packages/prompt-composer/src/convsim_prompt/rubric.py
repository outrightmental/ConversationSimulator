# SPDX-License-Identifier: Apache-2.0
"""Matching model-written rubric ids onto a scenario rubric's dimensions (issue #578).

The turn schema makes ``rubric_id`` an enum of the rubric's ids, so a runtime
that enforces the schema can only write those. A runtime that does not (a
plain-text reply, a repair call, which is sent with no schema) can still
write ``Self-Awareness`` for ``self_awareness``, or an id the rubric does not
have. These helpers fold the first onto the declared id and drop the second.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, Optional

from .types import ScenarioRubric

_DIMENSION_ID_SEPARATORS = re.compile(r"[^a-z0-9]+")


def normalize_dimension_id(rubric_id: str) -> str:
    """Fold a model-written rubric id onto one spelling.

    One session scored ``self-awareness`` and ``self_awareness`` as two
    dimensions, and the debrief listed both as "Self-Awareness" and "Self
    Awareness". Lowercase, with every run of other characters as one
    underscore, matches the ids rubric files declare (``self_awareness``,
    ``learning_velocity``).
    """
    return _DIMENSION_ID_SEPARATORS.sub("_", rubric_id.strip().lower()).strip("_")


class RubricIdMatcher:
    """Maps a model-written id onto one of a rubric's declared dimension ids.

    A written id matches a dimension when it normalises to the dimension's id
    or to its name ("Vocabulary Use" is ``vocabulary_use``). Anything else
    matches nothing.
    """

    def __init__(self, ids: Iterable[str], names: Optional[Dict[str, str]] = None) -> None:
        self._lookup: Dict[str, str] = {}
        declared = [i for i in ids if isinstance(i, str) and i]
        # Ids first, so a name can never shadow another dimension's id.
        for dimension_id in declared:
            self._lookup.setdefault(normalize_dimension_id(dimension_id), dimension_id)
        for dimension_id, name in (names or {}).items():
            if dimension_id in declared and isinstance(name, str) and name.strip():
                self._lookup.setdefault(normalize_dimension_id(name), dimension_id)

    @classmethod
    def for_rubric(cls, rubric: ScenarioRubric) -> "RubricIdMatcher":
        return cls(rubric.dimension_ids, {d.id: d.name for d in rubric.dimensions})

    def match(self, written: object) -> Optional[str]:
        """The declared id ``written`` stands for, or None."""
        if not isinstance(written, str) or not written.strip():
            return None
        return self._lookup.get(normalize_dimension_id(written))
