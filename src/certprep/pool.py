"""Question pool (D6): one JSON file per section, `<cert folder>/questions/<CODE>.json`.

Statuses (v2 plan section 6): unreviewed -> passive (first answered) -> validated ("Looks right");
any served status -> disputed (reported) -> retired (dispute confirmed) or back (dispute undone)."""

import json
import os
import threading
from collections import Counter, defaultdict
from pathlib import Path

from . import certs
from .schema import SERVED_STATUSES, Question

_lock = threading.Lock()
REPORTED_PREFIX = "Reported by user"


def _pool_path(cert_id: str, section: str) -> Path:
    code = certs.get_cert(cert_id).section(section).code
    return certs.cert_dir(cert_id) / "questions" / f"{code}.json"


def load(cert_id: str, section: str) -> list[Question]:
    path = _pool_path(cert_id, section)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Question.model_validate(q) for q in data.get("questions", [])]


def _save(cert_id: str, section: str, questions: list[Question]) -> None:
    path = _pool_path(cert_id, section)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = {"section": section, "questions": [q.stored() for q in questions]}
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)  # atomic on the same volume


def next_ids(section: str, existing: list[Question], n: int) -> list[str]:
    prefix = f"Q-{section}-"
    used = [int(q.id.removeprefix(prefix)) for q in existing if q.id.startswith(prefix)]
    start = max(used, default=0) + 1
    return [f"{prefix}{i:04d}" for i in range(start, start + n)]


def add(cert_id: str, section: str, build) -> list[Question]:
    """`build(existing)` returns the new questions; runs under the pool lock so IDs stay unique."""
    with _lock:
        existing = load(cert_id, section)
        new = build(existing)
        if new:
            _save(cert_id, section, existing + new)
        return new


def _update(cert_id: str, question_id: str, change) -> Question | None:
    """Apply `change(q) -> updated or None` to one question under the lock; save only if it changed."""
    section = certs.section_of(question_id)
    with _lock:
        questions = load(cert_id, section)
        for i, q in enumerate(questions):
            if q.id == question_id:
                new = change(q)
                if new is None or new == q:
                    return None
                questions[i] = new
                _save(cert_id, section, questions)
                return new
        return None


def retire(cert_id: str, question_id: str, reason: str) -> bool:
    """Questions are retired with a reason, never edited in place (section 10.2)."""
    return _update(cert_id, question_id, lambda q: q.model_copy(update={"status": "retired", "retired_reason": reason})
                   if q.status != "retired" else None) is not None


def retire_many(cert_id: str, section: str, question_ids: set[str], reason: str) -> list[str]:
    """Retire several questions in one write (e.g. a whole pool superseded by a rewrite)."""
    with _lock:
        questions = load(cert_id, section)
        done = []
        for i, q in enumerate(questions):
            if q.id in question_ids and q.status != "retired":
                questions[i] = q.model_copy(update={"status": "retired", "retired_reason": reason})
                done.append(q.id)
        if done:
            _save(cert_id, section, questions)
        return done


def validate(cert_id: str, question_id: str, when: str) -> bool:
    """The learner marked the question "Looks right" (Validated)."""
    return _update(cert_id, question_id, lambda q: q.model_copy(update={"status": "validated", "verified_at": when})
                   if q.status in ("unreviewed", "passive") else None) is not None


def _seen(q: Question, when: str) -> Question | None:
    update = {}
    if q.seen_at is None or when < q.seen_at:
        update["seen_at"] = when
    if q.status == "unreviewed":
        update["status"] = "passive"
    return q.model_copy(update=update) if update else None


def mark_seen(cert_id: str, question_id: str, when: str) -> bool:
    """Answered (in any mode): an unreviewed question becomes Passively-Validated."""
    return _update(cert_id, question_id, lambda q: _seen(q, when)) is not None


def mark_seen_many(cert_id: str, first_answered: dict[str, str]) -> int:
    """Bring statuses in line with recorded answers (after a migration or a progress restore).
    `first_answered` maps question ID -> earliest answer time. Returns how many changed."""
    by_section = defaultdict(dict)
    for qid, when in first_answered.items():
        try:
            by_section[certs.section_of(qid)][qid] = when
        except ValueError:
            continue
    changed = 0
    with _lock:
        for section, whens in by_section.items():
            try:
                questions = load(cert_id, section)
            except certs.UnknownSection:
                continue
            dirty = False
            for i, q in enumerate(questions):
                if q.id in whens and (new := _seen(q, whens[q.id])) is not None:
                    questions[i] = new
                    dirty = True
                    changed += 1
            if dirty:
                _save(cert_id, section, questions)
    return changed


def dispute(cert_id: str, question_id: str, reason: str, when: str, session_id: str | None = None) -> bool:
    """Reported by the learner: out of play until the dispute is confirmed (retired) or undone."""
    def change(q: Question):
        if not q.served:
            return None
        return q.model_copy(update={"status": "disputed", "disputed_reason": reason, "disputed_at": when,
                                    "disputed_session": session_id, "status_before_dispute": q.status})
    return _update(cert_id, question_id, change) is not None


def confirm_dispute(cert_id: str, question_id: str, when: str) -> bool:
    def change(q: Question):
        if q.status != "disputed":
            return None
        return q.model_copy(update={"status": "retired",
                                    "retired_reason": f"{REPORTED_PREFIX} ({q.disputed_at or when}): {q.disputed_reason}"})
    return _update(cert_id, question_id, change) is not None


def undo_dispute(cert_id: str, question_id: str) -> bool:
    def change(q: Question):
        if q.status != "disputed":
            return None
        return q.model_copy(update={"status": q.status_before_dispute or "unreviewed", "disputed_reason": None,
                                    "disputed_at": None, "disputed_session": None, "status_before_dispute": None})
    return _update(cert_id, question_id, change) is not None


def _all_sections(cert_id: str, sections) -> list[str]:
    return list(sections) if sections is not None else certs.get_cert(cert_id).section_codes


def all_questions(cert_id: str, sections=None) -> list[Question]:
    return [q for s in _all_sections(cert_id, sections) for q in load(cert_id, s)]


def active(cert_id: str, sections=None) -> list[Question]:
    """Questions that can be served: unreviewed, Passively-Validated, or Validated."""
    return [q for q in all_questions(cert_id, sections) if q.status in SERVED_STATUSES]


def inactive_ids(cert_id: str, sections=None) -> set[str]:
    """Disputed or retired: never served."""
    return {q.id for q in all_questions(cert_id, sections) if q.status not in SERVED_STATUSES}


def disputed(cert_id: str) -> list[Question]:
    return [q for q in all_questions(cert_id) if q.status == "disputed"]


# Retired only because a rewritten pool replaced it: nothing was wrong with the question, so the
# learner's answers to it still count toward objective status.
SUPERSEDED_PREFIX = "Superseded"


def flawed_ids(cert_id: str, sections=None) -> set[str]:
    """Disputed, or retired because something was wrong (reported, factual error...): answers to
    these don't count toward objective status."""
    return {q.id for q in all_questions(cert_id, sections)
            if q.status == "disputed"
            or (q.status == "retired" and not (q.retired_reason or "").startswith(SUPERSEDED_PREFIX))}


def get(cert_id: str, question_id: str) -> Question | None:
    try:
        section = certs.section_of(question_id)
        return next((q for q in load(cert_id, section) if q.id == question_id), None)
    except (ValueError, certs.UnknownSection):
        return None


def coverage(questions: list[Question]) -> Counter:
    """Served questions per primary objective."""
    return Counter(q.objectives[0] for q in questions if q.status in SERVED_STATUSES)


def last_angle(questions: list[Question]) -> dict[str, str]:
    """Most recent angle used per primary objective (pool order = creation order)."""
    out: dict[str, str] = {}
    for q in questions:
        out[q.objectives[0]] = q.angle
    return out
