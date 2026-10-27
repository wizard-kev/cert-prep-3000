"""Question pool (D6): one JSON file per chapter in data/questions/."""

import json
import os
import threading
from collections import Counter
from pathlib import Path

from .config import settings
from .objectives import validate_chapter
from .schema import Question

_lock = threading.Lock()


def _pool_path(chapter: int) -> Path:
    return settings.questions_dir / f"ch{validate_chapter(chapter):02d}.json"


def load(chapter: int) -> list[Question]:
    path = _pool_path(chapter)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Question.model_validate(q) for q in data.get("questions", [])]


def _save(chapter: int, questions: list[Question]) -> None:
    path = _pool_path(chapter)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = {"chapter": chapter, "questions": [q.model_dump() for q in questions]}
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)  # atomic on the same volume


def next_ids(chapter: int, existing: list[Question], n: int) -> list[str]:
    prefix = f"Q-C{chapter:02d}-"
    used = [int(q.id.removeprefix(prefix)) for q in existing if q.id.startswith(prefix)]
    start = max(used, default=0) + 1
    return [f"{prefix}{i:04d}" for i in range(start, start + n)]


def add(chapter: int, build) -> list[Question]:
    """`build(existing)` returns the new questions; runs under the pool lock so IDs stay unique."""
    with _lock:
        existing = load(chapter)
        new = build(existing)
        if new:
            _save(chapter, existing + new)
        return new


def _set_status(chapter: int, question_id: str, allowed_from: tuple[str, ...], **update) -> bool:
    with _lock:
        questions = load(chapter)
        for i, q in enumerate(questions):
            if q.id == question_id and q.status in allowed_from:
                questions[i] = q.model_copy(update=update)
                _save(chapter, questions)
                return True
        return False


def retire(chapter: int, question_id: str, reason: str) -> bool:
    """Questions are retired with a reason, never edited in place (section 10.2)."""
    return _set_status(chapter, question_id, ("draft", "verified"), status="retired", retired_reason=reason)


def retire_many(chapter: int, question_ids: set[str], reason: str) -> list[str]:
    """Retire several active questions in one write (e.g. a whole pool superseded by a rewrite)."""
    with _lock:
        questions = load(chapter)
        done = []
        for i, q in enumerate(questions):
            if q.id in question_ids and q.status in ("draft", "verified"):
                questions[i] = q.model_copy(update={"status": "retired", "retired_reason": reason})
                done.append(q.id)
        if done:
            _save(chapter, questions)
        return done


def verify(chapter: int, question_id: str, when: str) -> bool:
    """Promote draft -> verified after the user's spot-check (D7)."""
    return _set_status(chapter, question_id, ("draft",), status="verified", verified_at=when)


def active(chapters) -> list[Question]:
    return [q for ch in chapters for q in load(ch) if q.status != "retired"]


def retired_ids(chapters) -> set[str]:
    return {q.id for ch in chapters for q in load(ch) if q.status == "retired"}


# Retired only because a rewritten pool replaced it: nothing was wrong with the question, so the
# learner's answers to it still count toward objective status.
SUPERSEDED_PREFIX = "Superseded"


def flawed_ids(chapters) -> set[str]:
    """Retired because something was wrong (reported, factual error, mislabelled): answers don't count."""
    return {q.id for ch in chapters for q in load(ch)
            if q.status == "retired" and not (q.retired_reason or "").startswith(SUPERSEDED_PREFIX)}


def get(chapter: int, question_id: str) -> Question | None:
    return next((q for q in load(chapter) if q.id == question_id), None)


def coverage(questions: list[Question]) -> Counter:
    """Active questions per primary objective."""
    return Counter(q.objectives[0] for q in questions if q.status != "retired")


def last_angle(questions: list[Question]) -> dict[str, str]:
    """Most recent angle used per primary objective (pool order = creation order)."""
    out: dict[str, str] = {}
    for q in questions:
        out[q.objectives[0]] = q.angle
    return out
