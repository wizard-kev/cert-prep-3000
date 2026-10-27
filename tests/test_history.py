"""v2 P6: progress over time, suggestions, and progress backups (plan 8.1, 8.3, V11)."""
import itertools
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from certprep import certs, generator, history, pool, prompts, security, tracker
from certprep.config import PROJECT_ROOT, settings

CERT = "ccst-cyber"
API = f"/api/certs/{CERT}"
AUTHORED = PROJECT_ROOT / "data" / "certs" / CERT / "imports"


@pytest.fixture(autouse=True)
def fresh_data(monkeypatch):
    """Two C01 questions per objective, no progress, no backups, and a clock that ticks a minute per call."""
    assert "certprep-test-" in str(settings.data_dir)
    for f in (certs.cert_dir(CERT) / "questions").glob("*.json"):
        f.unlink()
    tracker.reset(CERT)
    for name in ("ch01_claude.json", "ch01_v2_set1a.json"):
        items = json.loads((AUTHORED / name).read_text(encoding="utf-8"))["questions"]
        generator.import_items(CERT, "C01", items, "claude", "test", seed=1, strict=False)
    for f in settings.backups_dir.glob("*"):
        f.unlink()
    ticks = itertools.count()
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(tracker, "now_iso", lambda: (start + timedelta(minutes=next(ticks))).isoformat(timespec="seconds"))
    yield


@pytest.fixture
def client():
    from certprep.main import app
    return TestClient(app, base_url="http://127.0.0.1:8000",
                      headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": security.CSRF_TOKEN})


def _qids(objective):
    return [q.id for q in pool.active(CERT) if q.objectives[0] == objective]


def _session(sid, answers, mark_seen=True):
    """answers: [(question_id, correct, confidence)], recorded in order."""
    tracker.create_session(sid, CERT, "practice", ["C01"], [a[0] for a in answers], None)
    for qid, ok, conf in answers:
        q = pool.get(CERT, qid)
        sel = q.answer if ok else [next(o.key for o in q.options if o.key not in q.answer)]
        tracker.record_attempt(sid, CERT, q, sel, conf, False)
    tracker.finish_session(sid)
    if mark_seen:
        pool.mark_seen_many(CERT, tracker.first_answered(CERT))


def _rows():
    return [(a["session_id"], a["question_id"], a["correct"], a["confidence"]) for a in tracker.all_attempts(CERT)]


# ---- objective score (plan 8.3) ---------------------------------------------

def test_answer_score_rewards_sure_right_and_penalises_sure_wrong():
    right = [tracker.answer_score(True, c) for c in tracker.CONFIDENCE]
    wrong = [tracker.answer_score(False, c) for c in tracker.CONFIDENCE]
    assert right == [50, 62.5, 75, 87.5, 100] and wrong == [25, 18.75, 12.5, 6.25, 0]
    assert min(right) > max(wrong)  # any right answer beats any wrong one


def _a(ok, conf, n=0):
    return {"objective": "C01-01", "correct": int(ok), "confidence": conf, "session_id": f"s{n}", "angle": "a",
            "question_id": "Q-C01-0001", "error_type": None, "answered_at": f"2026-10-01T00:00:{n:02d}+00:00"}


def test_objective_score_leans_on_recent_answers():
    assert tracker.objective_stats([_a(True, 3)])["C01-01"].score == 75
    recovered = tracker.objective_stats([_a(False, 5, 0), _a(True, 5, 1)])["C01-01"].score
    slipped = tracker.objective_stats([_a(True, 5, 0), _a(False, 5, 1)])["C01-01"].score
    assert (recovered, slipped) == (57, 43)  # (0*.75 + 100) / 1.75 and (100*.75 + 0) / 1.75
    assert tracker.ObjectiveStats("C01-01").score is None


def test_folding_answers_one_at_a_time_matches_the_batch():
    rows = [_a(i % 3 != 0, 1 + i % 5, i) for i in range(12)]
    s = tracker.ObjectiveStats("C01-01")
    for r in rows:
        s.add(r)
    assert s.as_dict() == tracker.objective_stats(rows)["C01-01"].as_dict()
    assert s.sure_wrong_recent == sum(1 for r in rows[-5:] if r["confidence"] >= 4 and not r["correct"])


# ---- overview and history ----------------------------------------------------

def test_overview_takes_a_snapshot_after_each_session(client):
    a, b = _qids("C01-01")[0], _qids("C01-02")[0]
    _session("s1", [(a, False, 5), (b, True, 2)])
    _session("s2", [(a, True, 4)])
    o = client.get(f"{API}/progress/overview").json()
    total = sum(r["objectives"] for r in o["by_section"])
    assert [(p["session_id"], p["Weak"], p["Improving"], p["Solid"], p["New"]) for p in o["timeline"]] == [
        ("s1", 1, 1, 0, total - 2), ("s2", 1, 1, 0, total - 2)]  # C01-01 stays Weak: wrong at Certain is recent
    assert o["timeline"][0]["mode"] == "practice"
    assert o["totals"]["answers"] == 3 and o["totals"]["practised"] == 2
    cal = {c["confidence"]: (c["answered"], c["correct"]) for c in o["calibration"]}
    assert cal == {1: (0, 0), 2: (1, 1), 3: (0, 0), 4: (1, 1), 5: (1, 0)}
    c01 = next(s for s in o["by_section"] if s["code"] == "C01")
    assert (c01["practised"], c01["Weak"], c01["Improving"]) == (2, 1, 1)
    assert o["by_domain"][0]["id"] == certs.get_cert(CERT).domains[0].id
    assert all(s["score"] is None for s in o["by_section"] if s["code"] != "C01")


def test_answers_to_reported_questions_are_left_out(client):
    a, b = _qids("C01-01")
    _session("s1", [(a, False, 5), (b, True, 5)])
    pool.dispute(CERT, a, "ambiguous", tracker.now_iso())
    o = client.get(f"{API}/progress/overview").json()
    assert o["totals"]["answers"] == 1
    points = client.get(f"{API}/progress/objectives/C01-01").json()["points"]
    assert [p["question_id"] for p in points] == [b]


def test_objective_history_api(client):
    a, b = _qids("C01-03")
    _session("s1", [(a, True, 3)])
    _session("s2", [(b, False, 2)])
    h = client.get(f"{API}/progress/objectives/C01-03").json()
    assert h["objective"] == "C01-03" and h["section"] == "C01" and h["name"]
    assert [(p["correct"], p["confidence"], p["score"]) for p in h["points"]] == [(True, 3, 75), (False, 2, 43)]
    assert client.get(f"{API}/progress/objectives/C01-04").json()["points"] == []
    assert client.get(f"{API}/progress/objectives/C01-99").status_code == 404
    assert client.get(f"{API}/progress/objectives/C99-01").status_code == 404
    assert client.get(f"{API}/progress/objectives/..%2FC01-01").status_code in (404, 422)
    assert client.get(f"{API}/progress/objectives/C1-1").status_code == 422


# ---- suggestions (V11) --------------------------------------------------------

def test_recommendations_find_weak_too_easy_and_seen_through_objectives(client):
    weak, easy, seen, quiet = (_qids(f"C01-{n:02d}") for n in (5, 6, 7, 8))
    _session("s1", [(weak[0], False, 2), (easy[0], True, 5), (seen[0], True, 3), (quiet[0], False, 2)])
    _session("s2", [(weak[1], False, 2), (easy[1], True, 5), (seen[1], True, 3)])
    _session("s3", [(weak[0], True, 3), (easy[0], True, 5)])
    recs = client.get(f"{API}/recommendations").json()
    by_id = {r["objective"]: r for r in recs}
    assert by_id["C01-05"]["reasons"] == ["weak", "no-unseen"] and by_id["C01-05"]["attempts"] == 3
    assert by_id["C01-06"]["reasons"] == ["too-easy", "no-unseen"]
    assert by_id["C01-07"]["reasons"] == ["no-unseen"] and by_id["C01-07"]["unseen"] == 0
    assert "C01-08" not in by_id  # weak, but only one answer and a question still unseen
    assert [r["objective"] for r in recs] == ["C01-05", "C01-06", "C01-07"]  # weak, then too easy, then the rest


def test_harder_prompt_asks_for_difficulty_3(client):
    plain = prompts.question_prompt(CERT, ["C01-01"])["prompt"]
    hard = client.get(f"{API}/prompts/questions?objective=C01-01&harder=true").json()["prompt"]
    assert "| difficulty: 3" in hard and '"difficulty": 3' in hard and "two steps of reasoning" in hard
    assert "| difficulty: 3" not in plain and '"difficulty": 2' in plain


# ---- backups and restore (plan 8.1) --------------------------------------------

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
INSERT INTO sessions VALUES ('old1', 'ccst-cyber', 'drill', '["C01"]', '[]', NULL, '2026-09-20T10:00:00+00:00', NULL);
INSERT INTO attempts VALUES ('old1', 'ccst-cyber', 'Q-C01-0001', 'C01', 'C01-01', '1.0', 'a', '["A"]', 1, 'sure', NULL, 0, '2026-09-20T10:01:00+00:00');
"""


def _named(kind, n=0):
    return settings.backups_dir / f"progress-{kind}-202609{n + 1:02d}T000000-000000Z.db"


def _db(path, script):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(script)
    db.commit()
    db.close()


def test_back_up_now_and_the_list(client):
    _session("s1", [(_qids("C01-01")[0], True, 3)])
    name = client.post("/api/progress/backups", json={}).json()["name"]
    _db(_named("upgrade", 1), SCHEMA_1)
    _named("manual", 2).write_bytes(b"not a database at all")
    (settings.backups_dir / "progress-notes.db").write_bytes(b"x")         # doesn't match the naming scheme
    (settings.backups_dir / "notes.txt").write_text("x")
    listed = {b["name"]: b for b in client.get("/api/progress/backups").json()}
    assert set(listed) == {name, _named("upgrade", 1).name, _named("manual", 2).name}
    mine = listed[name]
    assert (mine["kind"], mine["sessions"], mine["answers"], mine["schema"], mine["restorable"]) == ("manual", 1, 1, 2, True)
    assert listed[_named("upgrade", 1).name]["restorable"] is True          # an older schema can be restored
    assert listed[_named("manual", 2).name]["restorable"] is False and listed[_named("manual", 2).name]["problem"]
    assert list(listed)[0] == name                                          # newest first


def test_restore_round_trip_and_undo(client):
    _session("s1", [(_qids("C01-01")[0], True, 3), (_qids("C01-02")[0], False, 5)])
    before = _rows()
    name = client.post("/api/progress/backups", json={}).json()["name"]
    _session("s2", [(_qids("C01-03")[0], True, 4)])
    after = _rows()
    r = client.post("/api/progress/restore", json={"name": name, "confirm": "RESTORE"})
    assert r.status_code == 200, r.text
    assert _rows() == before and r.json()["answers"] == 2
    assert tracker.get_session("s2") is None
    # The progress replaced by the restore was saved first, so the restore can be undone.
    safety = r.json()["safety_backup"]
    assert safety.startswith("progress-before-restore-")
    assert client.post("/api/progress/restore", json={"name": safety, "confirm": "RESTORE"}).status_code == 200
    assert _rows() == after


def test_restore_upgrades_a_backup_from_an_older_version(client):
    _db(_named("upgrade", 1), SCHEMA_1)
    assert client.post("/api/progress/restore", json={"name": _named("upgrade", 1).name, "confirm": "RESTORE"}).status_code == 200
    assert [(a["session_id"], a["confidence"]) for a in tracker.all_attempts(CERT)] == [("old1", 5)]  # sure -> 5
    with tracker.connect() as c:
        assert c.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == str(tracker.SCHEMA_VERSION)
    assert len(list(settings.backups_dir.glob("progress-upgrade-*.db"))) == 2  # the source, and one made before upgrading


def test_restore_refuses_newer_damaged_and_unlisted_backups(client):
    _session("s1", [(_qids("C01-01")[0], True, 3)])
    before = _rows()
    newer = _named("manual", 3)
    _db(newer, tracker._SCHEMA + "INSERT INTO meta VALUES ('schema_version', '99');")
    damaged = _named("manual", 4)
    damaged.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    for name in (newer.name, damaged.name):
        r = client.post("/api/progress/restore", json={"name": name, "confirm": "RESTORE"})
        assert r.status_code == 422, r.text
    for bad in ("../progress.db", "progress.db", "progress-manual-..-20261001T000000-000000Z.db", "C:\\x.db"):
        assert client.post("/api/progress/restore", json={"name": bad, "confirm": "RESTORE"}).status_code == 422, bad
    missing = "progress-manual-20261001T000000-000000Z.db"
    assert client.post("/api/progress/restore", json={"name": missing, "confirm": "RESTORE"}).status_code == 404
    name = client.post("/api/progress/backups", json={}).json()["name"]
    assert client.post("/api/progress/restore", json={"name": name}).status_code == 422          # no confirmation
    assert client.post("/api/progress/restore", json={"name": name, "confirm": "yes"}).status_code == 422
    assert _rows() == before
    assert not list(settings.backups_dir.glob("progress-before-restore-*.db"))  # nothing was attempted


def test_restore_survives_its_own_safety_backup_pruning_the_source(client, monkeypatch):
    monkeypatch.setattr(tracker, "KEEP_BACKUPS", 2)
    _session("s1", [(_qids("C01-01")[0], True, 3)])
    oldest = tracker.backup("before-restore").name
    tracker.backup("before-restore")
    _session("s2", [(_qids("C01-02")[0], True, 3)])
    assert client.post("/api/progress/restore", json={"name": oldest, "confirm": "RESTORE"}).status_code == 200
    assert [r[0] for r in _rows()] == ["s1"]
    assert not (settings.backups_dir / oldest).exists()  # pruned by the safety backup, but restored from memory


def test_download_returns_the_backup(client):
    _session("s1", [(_qids("C01-01")[0], True, 3)])
    name = client.post("/api/progress/backups", json={}).json()["name"]
    r = client.get(f"/api/progress/backups/{name}")
    assert r.status_code == 200 and r.content == (settings.backups_dir / name).read_bytes()
    assert "attachment" in r.headers["content-disposition"] and name in r.headers["content-disposition"]
    assert client.get("/api/progress/backups/progress-manual-20261001T000000-000000Z.db").status_code == 404
    assert client.get("/api/progress/backups/progress.db").status_code == 422
    assert client.get("/api/progress/backups/..%2F..%2Fprogress.db").status_code in (404, 422)


def test_restored_answers_mark_their_questions_passive(client):
    qid = _qids("C01-01")[0]
    _session("s1", [(qid, True, 3)], mark_seen=False)
    assert pool.get(CERT, qid).status == "unreviewed"
    name = client.post("/api/progress/backups", json={}).json()["name"]
    tracker.reset(CERT)
    assert client.post("/api/progress/restore", json={"name": name, "confirm": "RESTORE"}).status_code == 200
    assert pool.get(CERT, qid).status == "passive"


def test_backup_routes_need_the_page_token():
    from certprep.main import app
    bare = TestClient(app, base_url="http://127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"})
    assert bare.post("/api/progress/backups", json={}).status_code == 403
    assert bare.post("/api/progress/restore", json={"name": "x", "confirm": "RESTORE"}).status_code == 403
