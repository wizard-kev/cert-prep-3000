"""progress.db: migration from the v1 tracker.db, backups, schema guard, per-certification reset."""
import json
import shutil
import sqlite3
from types import SimpleNamespace

import pytest

from certprep import certs, tracker
from certprep.config import settings

V1_SCHEMA = """
CREATE TABLE sessions (id TEXT PRIMARY KEY, mode TEXT NOT NULL, chapters TEXT NOT NULL, question_ids TEXT NOT NULL,
                       time_limit_s INTEGER, started_at TEXT NOT NULL, finished_at TEXT);
CREATE TABLE attempts (session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, question_id TEXT NOT NULL,
                       chapter INTEGER NOT NULL, objective TEXT NOT NULL, domain TEXT, angle TEXT NOT NULL,
                       selected TEXT NOT NULL, correct INTEGER NOT NULL, confidence TEXT NOT NULL, error_type TEXT,
                       flagged INTEGER NOT NULL DEFAULT 0, answered_at TEXT NOT NULL,
                       PRIMARY KEY (session_id, question_id));
"""


def _v1_db(path):
    db = sqlite3.connect(path)
    db.executescript(V1_SCHEMA)
    db.execute("INSERT INTO sessions VALUES ('s1', 'diagnostic', '[1, 9]', '[\"Q-C01-0195\", \"Q-C09-0078\"]', NULL, "
               "'2026-10-20T10:00:00+00:00', '2026-10-20T10:20:00+00:00')")
    db.execute("INSERT INTO sessions VALUES ('s2', 'drill', '[9]', '[\"Q-C09-0080\"]', NULL, "
               "'2026-10-21T10:00:00+00:00', NULL)")
    rows = [("s1", "Q-C01-0195", 1, "C01-01", "1.0", "symptom-to-attack", '["A"]', 1, "sure", None, 0, "2026-10-20T10:01:00+00:00"),
            ("s1", "Q-C09-0078", 9, "C09-01", "4.0", "classify-element", '["B"]', 0, "unsure", "concept-gap", 0, "2026-10-20T10:02:00+00:00"),
            ("s2", "Q-C09-0080", 9, "C09-03", "4.0", "choose-response", '["C"]', 1, "guess", None, 0, "2026-10-21T10:01:00+00:00")]
    db.executemany("INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    db.commit()
    db.close()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point the tracker at an empty folder (not the shared test data dir)."""
    fake = SimpleNamespace(progress_db=tmp_path / "progress.db", legacy_tracker_db=tmp_path / "tracker.db",
                           backups_dir=tmp_path / "backups")
    monkeypatch.setattr(tracker, "settings", fake)
    monkeypatch.setattr(tracker, "_prepared", set())
    return fake


def test_v1_progress_is_migrated_and_the_original_kept(isolated):
    _v1_db(isolated.legacy_tracker_db)
    s = tracker.get_session("s1")  # first use triggers the migration
    assert s["cert_id"] == "ccst-cyber" and s["sections"] == ["C01", "C09"] and s["finished_at"]
    rows = tracker.all_attempts("ccst-cyber")
    assert [(r["question_id"], r["section"], r["confidence"], r["error_type"]) for r in rows] == [
        ("Q-C01-0195", "C01", 5, None), ("Q-C09-0078", "C09", 2, "concept-gap"),  # sure -> 5, unsure -> 2
        ("Q-C09-0080", "C09", 1, None)]                                           # guess -> 1
    # The v1 file moved into backups unchanged; nothing is left at the old path.
    assert not isolated.legacy_tracker_db.exists()
    (original,) = isolated.backups_dir.glob("tracker-v1-*.db")
    old = sqlite3.connect(original)
    assert old.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 3
    old.close()
    with tracker.connect() as c:
        assert c.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == str(tracker.SCHEMA_VERSION)


def test_migrated_stats_match_the_v1_rules(isolated):
    _v1_db(isolated.legacy_tracker_db)
    stats = tracker.objective_stats(tracker.all_attempts("ccst-cyber"))
    assert stats["C01-01"].correct == 1
    assert stats["C09-01"].status == "Weak" and stats["C09-01"].errors["concept-gap"] == 1
    assert stats["C09-03"].guessed_correct == 1 and stats["C09-03"].correct == 0


def test_migration_runs_once(isolated):
    _v1_db(isolated.legacy_tracker_db)
    tracker.get_session("s1")
    _v1_db(isolated.legacy_tracker_db)  # a stray old file appears again
    monkey_prepared = tracker._prepared
    monkey_prepared.clear()
    tracker.get_session("s1")
    assert len(tracker.all_attempts("ccst-cyber")) == 3  # not doubled
    assert isolated.legacy_tracker_db.exists()  # left alone once progress.db exists


SCHEMA_1 = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sessions (id TEXT PRIMARY KEY, cert_id TEXT NOT NULL, mode TEXT NOT NULL, sections TEXT NOT NULL,
                       question_ids TEXT NOT NULL, time_limit_s INTEGER, started_at TEXT NOT NULL, finished_at TEXT);
CREATE TABLE attempts (session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, cert_id TEXT NOT NULL,
                       question_id TEXT NOT NULL, section TEXT NOT NULL, objective TEXT NOT NULL, domain TEXT,
                       angle TEXT NOT NULL, selected TEXT NOT NULL, correct INTEGER NOT NULL, confidence TEXT NOT NULL,
                       error_type TEXT, flagged INTEGER NOT NULL DEFAULT 0, answered_at TEXT NOT NULL,
                       PRIMARY KEY (session_id, question_id));
INSERT INTO meta VALUES ('schema_version', '1');
INSERT INTO sessions VALUES ('s1', 'ccst-cyber', 'drill', '["C01"]', '[]', NULL, '2026-10-20T10:00:00+00:00', NULL);
INSERT INTO attempts VALUES ('s1', 'ccst-cyber', 'Q-C01-0001', 'C01', 'C01-01', '1.0', 'a', '["A"]', 1, 'sure', NULL, 0, 't1');
INSERT INTO attempts VALUES ('s1', 'ccst-cyber', 'Q-C01-0002', 'C01', 'C01-02', '1.0', 'a', '["B"]', 0, 'unsure', 'concept-gap', 1, 't2');
INSERT INTO attempts VALUES ('s1', 'ccst-cyber', 'Q-C01-0003', 'C01', 'C01-03', '1.0', 'a', '["C"]', 1, 'guess', NULL, 0, 't3');
"""


def test_schema_1_upgrades_to_1_to_5_confidence_with_a_backup(isolated):
    db = sqlite3.connect(isolated.progress_db)
    db.executescript(SCHEMA_1)
    db.close()
    rows = tracker.all_attempts("ccst-cyber")
    assert [(r["question_id"], r["confidence"], r["error_type"], r["flagged"]) for r in rows] == [
        ("Q-C01-0001", 5, None, 0), ("Q-C01-0002", 2, "concept-gap", 1), ("Q-C01-0003", 1, None, 0)]
    (bak,) = isolated.backups_dir.glob("progress-upgrade-*.db")
    old = sqlite3.connect(bak)
    assert old.execute("SELECT confidence FROM attempts ORDER BY question_id").fetchall() == [("sure",), ("unsure",), ("guess",)]
    old.close()
    with tracker.connect() as c:
        assert c.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == "2"
        assert c.execute("SELECT COUNT(*) FROM held_disputes").fetchone()[0] == 0
    with pytest.raises(sqlite3.IntegrityError):  # the new column only takes 1-5
        with tracker.connect() as c:
            c.execute("UPDATE attempts SET confidence = 9 WHERE question_id = 'Q-C01-0001'")


def test_upgrade_preserves_objective_status(isolated):
    """Same answers, same mastery: guess stays uncredited, sure-but-wrong still forces Weak."""
    db = sqlite3.connect(isolated.progress_db)
    db.executescript(SCHEMA_1)
    db.close()
    stats = tracker.objective_stats(tracker.all_attempts("ccst-cyber"))
    assert stats["C01-01"].correct == 1 and stats["C01-02"].status == "Weak"
    assert stats["C01-03"].guessed_correct == 1 and stats["C01-03"].correct == 0


def test_newer_schema_is_refused(isolated):
    db = sqlite3.connect(isolated.progress_db)
    db.executescript(tracker._SCHEMA)
    db.execute("INSERT INTO meta VALUES ('schema_version', '99')")
    db.commit()
    db.close()
    with pytest.raises(tracker.ProgressError, match="newer version"):
        tracker.get_session("x")


def test_backups_are_pruned(isolated):
    tracker.get_session("x")  # create progress.db
    for _ in range(tracker.KEEP_BACKUPS + 3):
        tracker.backup("test")
    assert len(list(isolated.backups_dir.glob("progress-test-*.db"))) == tracker.KEEP_BACKUPS
    with pytest.raises(ValueError):
        tracker.backup("../evil")


def test_reset_touches_one_certification_and_backs_up_first(isolated):
    q = SimpleNamespace(id="Q-C01-0001", section="C01", objectives=["C01-01"], domain="1.0",
                        angle="symptom-to-attack", answer=["A"], type="single")
    for cert in ("ccst-cyber", "other-cert"):
        tracker.create_session(f"{cert[:4]}" + "0" * 12, cert, "practice", ["C01"], [q.id], None)
        tracker.record_attempt(f"{cert[:4]}" + "0" * 12, cert, q, ["A"], 5, False)
    tracker.reset("ccst-cyber")
    assert tracker.all_attempts("ccst-cyber") == [] and len(tracker.all_attempts("other-cert")) == 1
    assert list(isolated.backups_dir.glob("progress-reset-*.db"))


def test_registry_skips_an_invalid_certification():
    bad = settings.certs_dir / "broken-cert"
    bad.mkdir()
    try:
        (bad / "cert.json").write_text(json.dumps({"format_version": 1, "id": "not-the-folder"}), encoding="utf-8")
        certs.reload()
        assert "broken-cert" in certs.cert_ids()
        assert [c.id for c in certs.list_certs()] == ["ccst-cyber"]
        with pytest.raises(ValueError):
            certs.get_cert("broken-cert")
    finally:
        shutil.rmtree(bad)
        certs.reload()


def test_cert_manifest_rejects_unknown_fields_and_bad_sections():
    data = json.loads((settings.certs_dir / "ccst-cyber" / "cert.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        certs.Cert.model_validate({**data, "script": "<b>x</b>"})
    with pytest.raises(ValueError):
        certs.Cert.model_validate({**data, "sections": data["sections"] + [data["sections"][0]]})
    with pytest.raises(ValueError):
        certs.Cert.model_validate({**data, "sections": [{"code": "C01", "name": "x", "domain": "9.9"}]})
    with pytest.raises(ValueError):
        certs.Cert.model_validate({**data, "sources": [{"title": "x", "url": "javascript:alert(1)"}]})
