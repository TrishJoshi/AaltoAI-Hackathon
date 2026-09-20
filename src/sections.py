"""Split policy Markdown into reviewable sections."""

from __future__ import annotations

import re

from src.review_models import PolicySection

ATX_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_ITEM = re.compile(r"^(\d+)\.\s+(.+?)\s*$")
RECITAL_ITEM = re.compile(r"^\((\d+)\)\s+(\S.*)$")
NON_ID = re.compile(r"[^a-z0-9]+")


def slugify(text: str, fallback: str = "section") -> str:
    slug = NON_ID.sub("_", text.lower()).strip("_")
    return slug or fallback


def unique_id(base: str, taken: set[str]) -> str:
    candidate = base or "item"
    if candidate not in taken:
        return candidate
    index = 2
    while f"{candidate}_{index}" in taken:
        index += 1
    return f"{candidate}_{index}"


def split_markdown(text: str) -> list[PolicySection]:
    """Prefer sequential (1)(2) recitals, then ATX headings, then 1. numbered items."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    recitals = _split_recitals(lines)
    if _body_count(recitals) >= 2:
        return recitals
    atx = _split_atx(lines)
    if _body_count(atx) >= 2:
        return atx
    numbered = _split_numbered(lines)
    if _body_count(numbered) >= 2:
        return numbered
    if recitals:
        return recitals
    if atx:
        return atx
    if numbered:
        return numbered
    stripped = text.strip()
    title = _first_line_title(stripped) or "Document"
    return [PolicySection(id="sec_1", title=title, markdown=stripped, order=0)]


def _body_count(sections: list[PolicySection]) -> int:
    return sum(1 for section in sections if section.markdown.strip())


def _first_line_title(text: str) -> str:
    for line in text.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:80]
    return ""


def _split_atx(lines: list[str]) -> list[PolicySection]:
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = ATX_HEADING.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    if not headings:
        return []
    levels: dict[int, int] = {}
    for _, level, _ in headings:
        levels[level] = levels.get(level, 0) + 1
    split_levels = [level for level, count in levels.items() if count >= 2]
    if not split_levels:
        return []
    split_level = min(split_levels)
    starts = [(index, title) for index, level, title in headings if level == split_level]
    return _sections_from_starts(lines, starts, preamble_title="Preamble")


def _split_numbered(lines: list[str]) -> list[PolicySection]:
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = NUMBERED_ITEM.match(line)
        if match:
            starts.append((index, match.group(2).strip()))
    if len(starts) < 2:
        return []
    return _sections_from_starts(lines, starts, preamble_title="Preamble")


def _split_recitals(lines: list[str]) -> list[PolicySection]:
    """Split sequential '(1)', '(2)' recitals; skip footnote markers that restart at (1)."""
    starts: list[tuple[int, str]] = []
    expected = 1
    for index, line in enumerate(lines):
        match = RECITAL_ITEM.match(line.strip())
        if not match:
            continue
        number = int(match.group(1))
        if number != expected:
            continue
        rest = match.group(2).strip()
        snippet = rest[:72].rsplit(" ", 1)[0] if len(rest) > 72 else rest
        title = f"({number}) {snippet}"
        starts.append((index, title))
        expected = number + 1
    if len(starts) < 2:
        return []
    return _sections_from_starts(lines, starts, preamble_title="Preamble")


def _sections_from_starts(
    lines: list[str],
    starts: list[tuple[int, str]],
    preamble_title: str,
) -> list[PolicySection]:
    sections: list[PolicySection] = []
    taken: set[str] = set()
    first_start = starts[0][0]
    if first_start > 0:
        preamble = "\n".join(lines[:first_start]).strip()
        if preamble:
            section_id = unique_id("sec_preamble", taken)
            taken.add(section_id)
            sections.append(
                PolicySection(
                    id=section_id,
                    title=preamble_title,
                    markdown=preamble,
                    order=len(sections),
                )
            )
    for position, (start, title) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        section_id = unique_id(f"sec_{slugify(title, fallback=str(position + 1))}", taken)
        taken.add(section_id)
        sections.append(
            PolicySection(id=section_id, title=title, markdown=body, order=len(sections))
        )
    return sections
