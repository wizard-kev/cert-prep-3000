"""Tracker (plan 8.4). Sessions and attempts live in SQLite (`data/progress.db`), keyed by
certification; per-objective status is always derived from the attempts, never stored, so it
cannot drift.

The v1 app kept CCST-only progress in `data/tracker.db`. On first start it is migrated into
progress.db, and the original file is moved into `data/backups/` untouched (v2 section 8.1)."""

import json
import os
import sqlite3
import threading
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import settings

CONFIDENCE = ("guess", "unsure", "sure")
ERROR_TYPES = ("concept-gap", "terminology-confusion", "misread-question", "scenario-application")
MODES = ("diagnostic", "drill", "exam", "review")
# Spaced revisits for Solid objectives (proposed in 8.4, tunable): 3, 7, then 14 days.
REVISIT_DAYS = (3, 7, 14)
# A question answered correctly and "sure" this many times in a row (one per session) is probably
# too easy to teach anything; it is listed for the user to keep or retire.
TOO_EASY_STREAK = 3

SCHEMA_VERSION = 1
# The v1 app was CCST-only, so its sessions and answers belong to this certification.
LEGACY_CERT = "ccst-cyber"
KEEP_BACKUPS = 10  # automatic progress backups kept per kind

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    cert_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    sections TEXT NOT NULL,
    question_ids TEXT NOT NULL,
    time_limit_s INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    cert_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    section TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS sessions_cert ON sessions(cert_id);
CREATE INDEX IF NOT EXISTS attempts_cert_objective ON attempts(cert_id, objective);
"""


class ProgressError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp() -> str:
    # Microseconds keep two backups in the same second apart; the format sorts by time.
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ")


# ---- database file: preparation, migration, backups ----------------------

def _sqlite_copy(src: Path, dst: Path) -> None:
    """Consistent copy of a live SQLite database (safe while the app is using it)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def _prune(prefix: str) -> None:
    olds = sorted(settings.backups_dir.glob(f"{prefix}-*.db"))
    for old in olds[:-KEEP_BACKUPS]:
        old.unlink()


def backup(reason: str) -> Path:
    """Copy progress.db into data/backups (keeping the newest KEEP_BACKUPS per reason)."""
    if not reason.replace("-", "").isalnum():
        raise ValueError("backup reason must be letters, digits, and dashes")
    dst = settings.backups_dir / f"progress-{reason}-{_stamp()}.db"
    _sqlite_copy(settings.progress_db, dst)
    _prune(f"progress-{reason}")
    return dst


def _counts(conn: sqlite3.Connection) -> tuple[int, int]:
    return (conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0])


def _section_code(chapter) -> str:
    return f"C{int(chapter):02d}"


def migrate_legacy(legacy: Path, target: Path) -> Path:
    """Build progress.db from the v1 tracker.db, then move tracker.db into backups untouched.
    Returns where the original now lives."""
    tmp = target.with_name(target.name + ".migrating")
    if tmp.exists():
        tmp.unlink()
    old = sqlite3.connect(f"file:{legacy.as_posix()}?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    new = sqlite3.connect(tmp)
    try:
        new.executescript(_SCHEMA)
        for s in old.execute("SELECT * FROM sessions"):
            sections = [_section_code(c) for c in json.loads(s["chapters"])]
            new.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (s["id"], LEGACY_CERT, s["mode"], json.dumps(sections), s["question_ids"],
                         s["time_limit_s"], s["started_at"], s["finished_at"]))
        for a in old.execute("SELECT * FROM attempts"):
            new.execute(
                """INSERT INTO attempts (session_id, cert_id, question_id, section, objective, domain, angle,
                                         selected, correct, confidence, error_type, flagged, answered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (a["session_id"], LEGACY_CERT, a["question_id"], _section_code(a["chapter"]), a["objective"],
                 a["domain"], a["angle"], a["selected"], a["correct"], a["confidence"], a["error_type"],
                 a["flagged"], a["answered_at"]))
        if _counts(new) != _counts(old):
            raise ProgressError(f"migration lost rows: {_counts(old)} -> {_counts(new)}")
        new.executemany("INSERT INTO meta VALUES (?, ?)", [
            ("schema_version", str(SCHEMA_VERSION)),
            ("migrated_from", f"v1 tracker.db, {now_iso()}"),
        ])
        new.commit()
    finally:
        new.close()
        old.close()
    os.replace(tmp, target)
    original = settings.backups_dir / f"tracker-v1-{_stamp()}.db"
    original.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(legacy, original)
    except OSError:
        # Another program has the old file open: keep it where it is, and back up a copy.
        _sqlite_copy(legacy, original)
    return original


_prepared: set[Path] = set()
_prepare_lock = threading.Lock()


def _prepare() -> None:
    """Once per process: migrate v1 progress if needed, create the schema, check the version."""
    path = settings.progress_db
    with _prepare_lock:
        if path in _prepared:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() and settings.legacy_tracker_db.exists():
            migrate_legacy(settings.legacy_tracker_db, path)
        conn = sqlite3.connect(path)
        try:
            conn.executescript(_SCHEMA)
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            if row is None:
                conn.execute("INSERT INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            elif int(row[0]) > SCHEMA_VERSION:
                raise ProgressError(f"{path.name} was written by a newer version of the app "
                                    f"(schema {row[0]}, this app reads {SCHEMA_VERSION}); update the app")
            elif int(row[0]) < SCHEMA_VERSION:
                conn.close()
                backup("upgrade")  # always before changing the schema
                conn = sqlite3.connect(path)
                # Upgrade steps for later schema versions go here.
                conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION),))
            conn.commit()
        finally:
            conn.close()
        _prepared.add(path)


@contextmanager
def connect():
    _prepare()
    conn = sqlite3.connect(settings.progress_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---- sessions -------------------------------------------------------------

def create_session(session_id: str, cert_id: str, mode: str, sections: list[str], question_ids: list[str],
                   time_limit_s: int | None) -> dict:
    with connect() as c:
        c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                  (session_id, cert_id, mode, json.dumps(sections), json.dumps(question_ids), time_limit_s, now_iso()))
    return get_session(session_id)


def get_session(session_id: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        return None
    s = dict(row)
    s["sections"] = json.loads(s["sections"])
    s["question_ids"] = json.loads(s["question_ids"])
    return s


def finish_session(session_id: str) -> None:
    with connect() as c:
        c.execute("UPDATE sessions SET finished_at = ? WHERE id = ? AND finished_at IS NULL", (now_iso(), session_id))


def last_finished_session(cert_id: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT id FROM sessions WHERE cert_id = ? AND finished_at IS NOT NULL "
                        "ORDER BY finished_at DESC LIMIT 1", (cert_id,)).fetchone()
    return get_session(row["id"]) if row else None


# ---- attempts -------------------------------------------------------------

def record_attempt(session_id: str, cert_id: str, question, selected: list[str], confidence: str,
                   flagged: bool) -> bool:
    """Upsert: in exam mode the user may change an answer before finishing."""
    correct = sorted(set(selected)) == sorted(question.answer)
    with connect() as c:
        c.execute(
            """INSERT INTO attempts (session_id, cert_id, question_id, section, objective, domain, angle, selected,
                                     correct, confidence, flagged, answered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, question_id) DO UPDATE SET
                 selected = excluded.selected, correct = excluded.correct, confidence = excluded.confidence,
                 flagged = excluded.flagged, answered_at = excluded.answered_at, error_type = NULL""",
            (session_id, cert_id, question.id, question.section, question.objectives[0], question.domain,
             question.angle, json.dumps(sorted(set(selected))), int(correct), confidence, int(flagged), now_iso()))
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


def all_attempts(cert_id: str, exclude_questions: set[str] = frozenset(),
                 exclude_session: str | None = None) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM attempts WHERE cert_id = ? ORDER BY answered_at", (cert_id,)).fetchall()
    return [dict(r) for r in rows
            if r["question_id"] not in exclude_questions and r["session_id"] != exclude_session]


def reset(cert_id: str) -> None:
    """Delete one certification's sessions and answers (a backup is taken first)."""
    if settings.progress_db.exists():
        backup("reset")
    with connect() as c:
        c.execute("DELETE FROM attempts WHERE cert_id = ?", (cert_id,))
        c.execute("DELETE FROM sessions WHERE cert_id = ?", (cert_id,))


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
