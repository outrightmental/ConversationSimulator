# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — the docs site's release notes are RELEASE_NOTES.md's.

The docs-site page ``project/release-notes.md`` is a hand-kept copy of
``RELEASE_NOTES.md``, and nothing copied new sections across. By v0.4.0, the
release the free Steam demo is built from, the page still ended at v0.2.1, and
its closing sections (the alpha's download and system-requirements notes,
which read as the page's own) still promised installers with checksum files
and Intel Mac support, after Steam had become the only channel that ships
binaries and the macOS build had become Apple Silicon only.

These tests hold the page to the file. Every ``# Conversation Simulator vX.Y.Z
— Release Notes`` section must appear on the page as a ``## vX.Y.Z`` section,
in the same order (newest first), with the same words. A copy may change only
two things: heading levels (each section's headings sit one level lower on
the page, under its version) and link targets (repository paths become
docs-site routes or GitHub URLs, and a code span may become a link). Text
before the first version heading, and ``##`` sections after the last release,
belong to the page and are not compared.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE = _REPO_ROOT / "RELEASE_NOTES.md"
_PAGE = _REPO_ROOT / "docs-site" / "src" / "content" / "docs" / "project" / "release-notes.md"

_SOURCE_HEADING = re.compile(r"^# Conversation Simulator (v\S+) — Release Notes\s*$")
_PAGE_HEADING = re.compile(r"^## (v\d\S*)\s*$")
# On the page, any other level-2 heading ends a release section.
_PAGE_BOUNDARY = re.compile(r"^## ")
_LINK = re.compile(r"\[([^\]]*)\]\([^)\s]*\)")
_HEADING_MARK = re.compile(r"^#{1,6}$")


def _sections(path: Path, heading: re.Pattern[str], boundary: re.Pattern[str] | None) -> dict[str, list[str]]:
    """Each version's lines, in file order. Fenced code never starts or ends one."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            match = heading.match(line)
            if match:
                current = match.group(1)
                assert current not in sections, f"{path.name} has two {current} sections"
                sections[current] = []
                continue
            if boundary is not None and boundary.match(line):
                current = None
                continue
        if current is not None:
            sections[current].append(line)
    return sections


def _words(lines: list[str]) -> list[str]:
    """The section's words, with link targets and heading levels dropped."""
    words = _LINK.sub(r"\1", "\n".join(lines)).split()
    words = ["#" if _HEADING_MARK.match(word) else word for word in words]
    while words and words[-1] == "---":
        words.pop()
    return words


def _source_sections() -> dict[str, list[str]]:
    return _sections(_SOURCE, _SOURCE_HEADING, None)


def _page_sections() -> dict[str, list[str]]:
    return _sections(_PAGE, _PAGE_HEADING, _PAGE_BOUNDARY)


def test_release_notes_have_version_sections() -> None:
    assert _source_sections(), (
        "RELEASE_NOTES.md has no '# Conversation Simulator vX.Y.Z — Release Notes' "
        "heading; update this test (and release.yml, which publishes a tag's notes "
        "from that heading) to match the new format."
    )


def test_page_lists_every_release_newest_first() -> None:
    source = list(_source_sections())
    page = list(_page_sections())
    missing = [version for version in source if version not in page]
    extra = [version for version in page if version not in source]
    assert not missing, (
        f"RELEASE_NOTES.md has {missing} but {_PAGE.relative_to(_REPO_ROOT)} does not. "
        "Copy each new section onto the page as '## <version>', one heading level "
        "lower throughout, with repository links pointed at docs-site routes."
    )
    assert not extra, (
        f"{_PAGE.relative_to(_REPO_ROOT)} has {extra}, which RELEASE_NOTES.md does not. "
        "The page copies the file; add the section there first."
    )
    assert page == source, (
        f"The page lists releases as {page}; RELEASE_NOTES.md lists them as {source}. "
        "Keep the same order, newest first."
    )


@pytest.mark.parametrize("version", list(_source_sections()))
def test_page_section_matches_release_notes(version: str) -> None:
    page = _page_sections()
    if version not in page:
        pytest.skip(f"{version} is missing from the page; see test_page_lists_every_release_newest_first")
    want = _words(_source_sections()[version])
    got = _words(page[version])
    if got == want:
        return
    at = next((i for i, (a, b) in enumerate(zip(want, got)) if a != b), min(len(want), len(got)))
    lo = max(at - 8, 0)
    pytest.fail(
        f"The page's {version} section differs from RELEASE_NOTES.md at word {at}:\n"
        f"  RELEASE_NOTES.md: ...{' '.join(want[lo:at + 12])}...\n"
        f"  docs-site page:   ...{' '.join(got[lo:at + 12])}...\n"
        "Copy the section again. Only heading levels and link targets may differ."
    )
