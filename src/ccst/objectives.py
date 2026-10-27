"""Loads per-chapter objective files. Chapter IDs are allowlisted (FR2, SR6)."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import settings

CHAPTERS = range(1, 14)

# Provisional chapter-level domain tags, taken from each file's header. None = the
# chapter spans several domains; resolved per objective by the Phase 7 crosswalk.
PROVISIONAL_DOMAIN = {
    1: "1.0", 3: "2.0", 6: "3.0", 7: "3.0", 8: "4.0", 9: "4.0",
    11: "5.0", 12: "5.0", 13: "5.0",
}

_ROW = re.compile(r"^\|\s*(C(\d{2})-\d{2})\s*\|(.+)\|\s*$")
_SECTION = re.compile(r"^##\s+(.+?)\s*$")


class InvalidChapter(ValueError):
    pass


@dataclass(frozen=True)
class Objective:
    id: str
    section: str
    objective: str
    core_idea: str
    discriminator: str


@dataclass(frozen=True)
class Chapter:
    number: int
    title: str
    text: str
    objectives: dict[str, Objective]

    @property
    def domain(self) -> str | None:
        return PROVISIONAL_DOMAIN.get(self.number)


def validate_chapter(chapter: object) -> int:
    """Accepts only an int 1..13 (bool excluded). Anything else is rejected."""
    if isinstance(chapter, bool) or not isinstance(chapter, int) or chapter not in CHAPTERS:
        raise InvalidChapter(f"chapter must be an integer from 1 to 13, got {chapter!r}")
    return chapter


def chapter_path(chapter: int) -> Path:
    n = validate_chapter(chapter)
    # The filename is built only from the validated integer, never from user text.
    return settings.objectives_dir / f"CCST_Ch{n:02d}.md"


@lru_cache(maxsize=None)
def load_chapter(chapter: int) -> Chapter:
    n = validate_chapter(chapter)
    text = chapter_path(n).read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ").strip() if text else f"Chapter {n}"
    objectives: dict[str, Objective] = {}
    section = ""
    for line in text.splitlines():
        if m := _SECTION.match(line):
            section = m.group(1)
            continue
        m = _ROW.match(line)
        if not m or int(m.group(2)) != n:
            continue
        cells = [c.strip() for c in m.group(3).split("|")]
        cells += [""] * (3 - len(cells))
        objectives[m.group(1)] = Objective(m.group(1), section, cells[0], cells[1], cells[2])
    if not objectives:
        raise ValueError(f"no objectives parsed from {chapter_path(n).name}")
    return Chapter(n, title, text, objectives)
