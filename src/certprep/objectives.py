"""Objective files: one per section, `<cert folder>/objectives/<CODE>.md`, holding a Markdown
table of objectives (ID | objective | core idea | discriminator). Objective IDs are `<CODE>-NN`
and frozen within a certification: retire, never rename."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import certs

_HEADING = re.compile(r"^##\s+(.+?)\s*$")


@dataclass(frozen=True)
class Objective:
    id: str
    group: str  # the "## ..." heading the row sits under
    objective: str
    core_idea: str
    discriminator: str
    ref: str = ""  # official reference number (e.g. 4.2), from an optional fifth column


@dataclass(frozen=True)
class Section:
    cert_id: str
    code: str
    name: str
    domain: str | None
    text: str
    objectives: dict[str, Objective]


def objectives_path(cert_id: str, code: str) -> Path:
    cert = certs.get_cert(cert_id)
    # The filename is built only from a section code listed in cert.json, never from user text.
    return certs.cert_dir(cert_id) / "objectives" / f"{cert.section(code).code}.md"


@lru_cache(maxsize=None)
def load_section(cert_id: str, code: str) -> Section:
    info = certs.get_cert(cert_id).section(code)
    path = objectives_path(cert_id, code)
    text = path.read_text(encoding="utf-8")
    row = re.compile(rf"^\|\s*({re.escape(info.code)}-\d{{2}})\s*\|(.+)\|\s*$")
    objectives: dict[str, Objective] = {}
    group = ""
    for line in text.splitlines():
        if m := _HEADING.match(line):
            group = m.group(1)
            continue
        m = row.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        cells += [""] * (4 - len(cells))
        objectives[m.group(1)] = Objective(m.group(1), group, cells[0], cells[1], cells[2], cells[3])
    if not objectives:
        raise ValueError(f"no objectives parsed from {path.name}")
    return Section(cert_id, info.code, info.name, info.domain, text, objectives)


def load_sections(cert_id: str) -> list[Section]:
    """Every section of a certification whose objective file loads, in cert.json order."""
    out = []
    for code in certs.get_cert(cert_id).section_codes:
        try:
            out.append(load_section(cert_id, code))
        except (OSError, ValueError):
            continue
    return out


def objective_names(cert_id: str) -> dict[str, str]:
    return {o.id: o.objective for s in load_sections(cert_id) for o in s.objectives.values()}


class UnknownObjective(ValueError):
    pass


def find_objective(cert_id: str, objective_id: object) -> tuple[Section, Objective]:
    """The section and row for an objective ID such as C09-23 (its section is the part before the dash)."""
    if not isinstance(objective_id, str) or not re.match(certs.OBJECTIVE_ID, objective_id):
        raise UnknownObjective(f"not an objective id: {objective_id!r}")
    try:
        section = load_section(cert_id, objective_id.split("-")[0])
    except (certs.UnknownSection, OSError, ValueError):
        raise UnknownObjective(f"unknown objective: {objective_id}") from None
    if objective_id not in section.objectives:
        raise UnknownObjective(f"unknown objective: {objective_id}")
    return section, section.objectives[objective_id]
