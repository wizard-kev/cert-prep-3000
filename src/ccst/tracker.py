"""Tracker (plan 8.4). Sessions and attempts live in SQLite; per-objective status is
always derived from the attempts, never stored, so it cannot drift."""

import json
import sqlite3
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .config import settings

CONFIDENCE = ("guess", "unsure", "sure")
ERROR_TYPES = ("concept-gap", "terminology-confusion", "misread-question", "scenario-application")
MODES = ("diagnostic", "drill", "exam", "review")
# Spaced revisits for Solid objectives (proposed in 8.4, tunable): 3, 7, then 14 days.
REVISIT_DAYS = (3, 7, 14)
# A question answered correctly and "sure" this many times in a row (one per session) is probably
# too easy to teach anything; it is listed for the user to keep or retire.
TOO_EASY_STREAK = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    chapters TEXT NOT NULL,
    question_ids TEXT NOT NULL,
    time_limit_s INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    objective TEXT NOT NULL,
    domain TEXT,
    angle TEXT NOT NULL,
    selected TEXT NOT NULL,
    correct INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    error_type TEXT,
    flagged INTEGER NOT NULL DEFAULT 0,
    answered_at TEXT NOT NULL,
    PRIMARY KEY (session_id, question_id)
);
CREATE INDEX IF NOT EXISTS attempts_objective ON attempts(objective);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    path = settings.data_dir / "tracker.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---- sessions -------------------------------------------------------------

def create_session(session_id: str, mode: str, chapters: list[int], question_ids: list[str],
                   time_limit_s: int | None) -> dict:
    with connect() as c:
        c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, NULL)",
                  (session_id, mode, json.dumps(chapters), json.dumps(question_ids), time_limit_s, now_iso()))
    return get_session(session_id)


def get_session(session_id: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        return None
    s = dict(row)
    s["chapters"] = json.loads(s["chapters"])
    s["question_ids"] = json.loads(s["question_ids"])
    return s


def finish_session(session_id: str) -> None:
    with connect() as c:
        c.execute("UPDATE sessions SET finished_at = ? WHERE id = ? AND finished_at IS NULL", (now_iso(), session_id))


def last_finished_session() -> dict | None:
    with connect() as c:
        row = c.execute("SELECT id FROM sessions WHERE finished_at IS NOT NULL "
                        "ORDER BY finished_at DESC LIMIT 1").fetchone()
    return get_session(row["id"]) if row else None


# ---- attempts -------------------------------------------------------------

def record_attempt(session_id: str, question, selected: list[str], confidence: str, flagged: bool) -> bool:
    """Upsert: in exam mode the user may change an answer before finishing."""
    correct = sorted(set(selected)) == sorted(question.answer)
    with connect() as c:
        c.execute(
            """INSERT INTO attempts (session_id, question_id, chapter, objective, domain, angle, selected,
                                     correct, confidence, flagged, answered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, question_id) DO UPDATE SET
                 selected = excluded.selected, correct = excluded.correct, confidence = excluded.confidence,
                 flagged = excluded.flagged, answered_at = excluded.answered_at, error_type = NULL""",
            (session_id, question.id, question.chapter, question.objectives[0], question.domain, question.angle,
             json.dumps(sorted(set(selected))), int(correct), confidence, int(flagged), now_iso()))
    return correct


def set_flag(session_id: str, question_id: str, flagged: bool) -> None:
    with connect() as c:
        c.execute("UPDATE attempts SET flagged = ? WHERE session_id = ? AND question_id = ?",
                  (int(flagged), session_id, question_id))


def set_error_type(session_id: str, question_id: str, error_type: str | None) -> bool:
    with connect() as c:
        cur = c.execute("UPDATE attempts SET error_type = ? WHERE session_id = ? AND question_id = ? AND correct = 0",
                        (error_type, session_id, question_id))
    return cur.rowcount == 1


def session_attempts(session_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM attempts WHERE session_id = ? ORDER BY answered_at", (session_id,)).fetchall()
    return [{**dict(r), "selected": json.loads(r["selected"])} for r in rows]


def all_attempts(exclude_questions: set[str] = frozenset(), exclude_session: str | None = None) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM attempts ORDER BY answered_at").fetchall()
    return [dict(r) for r in rows
            if r["question_id"] not in exclude_questions and r["session_id"] != exclude_session]


def reset() -> None:
    with connect() as c:
        c.execute("DELETE FROM attempts")
        c.execute("DELETE FROM sessions")


# ---- derived per-objective status ----------------------------------------

@dataclass
class ObjectiveStats:
    """`correct`, `last5`, and the Solid evidence count only credited answers: correct and not
    marked "guess". A lucky guess is recorded (and scored in the session) but proves nothing."""
    objective: str
    attempts: int = 0
    correct: int = 0
    guessed_correct: int = 0
    last5: list[bool] = field(default_factory=list)
    last5_marks: list[str] = field(default_factory=list)  # "right", "guess" (right but guessed), "wrong"
    sure_wrong_recent: int = 0
    calibration: dict = field(default_factory=lambda: {c: [0, 0] for c in CONFIDENCE})  # [answered, correct]
    errors: Counter = field(default_factory=Counter)
    last_seen: str | None = None
    sessions_correct: set = field(default_factory=set)
    angles_seen: set = field(default_factory=set)
    angles_correct: set = field(default_factory=set)
    last_angle: str | None = None
    recent_questions: list[str] = field(default_factory=list)

    @property
    def last5_accuracy(self) -> float | None:
        return sum(self.last5) / len(self.last5) if self.last5 else None

    @property
    def status(self) -> str:
        """New / Weak / Improving / Solid, per plan 8.4 (thresholds are the proposed defaults)."""
        if not self.attempts:
            return "New"
        acc = self.last5_accuracy
        if acc < 0.6 or self.sure_wrong_recent:
            return "Weak"
        if self.correct >= 3 and len(self.sessions_correct) >= 2 and len(self.angles_correct) >= 2 and acc >= 0.8:
            return "Solid"
        return "Improving"

    def revisit_due(self, now: datetime | None = None) -> bool:
        if self.status != "Solid" or not self.last_seen:
            return False
        step = min(len(self.sessions_correct) - 2, len(REVISIT_DAYS) - 1)
        due_at = datetime.fromisoformat(self.last_seen) + timedelta(days=REVISIT_DAYS[max(step, 0)])
        return (now or datetime.now(timezone.utc)) >= due_at

    def as_dict(self) -> dict:
        return {
            "objective": self.objective, "status": self.status, "attempts": self.attempts, "correct": self.correct,
            "guessed_correct": self.guessed_correct,
            "last5": [int(x) for x in self.last5], "last5_marks": self.last5_marks, "last5_accuracy": self.last5_accuracy,
            "sure_wrong_recent": self.sure_wrong_recent, "calibration": self.calibration,
            "errors": dict(self.errors), "dominant_error": self.errors.most_common(1)[0][0] if self.errors else None,
            "last_seen": self.last_seen, "sessions_correct": len(self.sessions_correct),
            "angles_seen": sorted(self.angles_seen), "revisit_due": self.revisit_due(),
        }


def objective_stats(attempts: list[dict]) -> dict[str, ObjectiveStats]:
    """`attempts` must be in answer order (oldest first)."""
    out: dict[str, ObjectiveStats] = {}
    for a in attempts:
        s = out.setdefault(a["objective"], ObjectiveStats(a["objective"]))
        right = bool(a["correct"])
        ok = right and a["confidence"] != "guess"  # credited toward mastery
        s.attempts += 1
        s.correct += ok
        s.guessed_correct += right and not ok
        s.last5 = (s.last5 + [ok])[-5:]
        s.last5_marks = (s.last5_marks + ["right" if ok else "guess" if right else "wrong"])[-5:]
        s.calibration[a["confidence"]][0] += 1
        s.calibration[a["confidence"]][1] += right
        if a["error_type"]:
            s.errors[a["error_type"]] += 1
        s.last_seen = a["answered_at"]
        s.angles_seen.add(a["angle"])
        s.last_angle = a["angle"]
        s.recent_questions = (s.recent_questions + [a["question_id"]])[-3:]
        if ok:
            s.sessions_correct.add(a["session_id"])
            s.angles_correct.add(a["angle"])
    # "Sure but wrong" within the last five answers keeps an objective Weak.
    recent: dict[str, list[dict]] = {}
    for a in attempts:
        recent.setdefault(a["objective"], []).append(a)
    for obj, rows in recent.items():
        out[obj].sure_wrong_recent = sum(1 for a in rows[-5:] if a["confidence"] == "sure" and not a["correct"])
    return out


def too_easy(attempts: list[dict]) -> dict[str, int]:
    """Question ID -> attempts, for questions whose last TOO_EASY_STREAK answers (one per session)
    were all correct and marked "sure". `attempts` must be in answer order (oldest first)."""
    by_q: dict[str, list[dict]] = {}
    for a in attempts:
        by_q.setdefault(a["question_id"], []).append(a)
    return {qid: len(rows) for qid, rows in by_q.items()
            if len(rows) >= TOO_EASY_STREAK
            and all(a["correct"] and a["confidence"] == "sure" for a in rows[-TOO_EASY_STREAK:])}
