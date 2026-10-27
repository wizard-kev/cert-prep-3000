"""Selection, sessions, statuses, disputes, and scores (v2 P5: plan sections 6, 7, 8.2)."""
import json
import random
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from certprep import certs, generator, pool, sessions, tracker
from certprep.config import PROJECT_ROOT, settings
from certprep.schema import Question

CERT = "ccst-cyber"
API = f"/api/certs/{CERT}"
AUTHORED = PROJECT_ROOT / "data" / "certs" / CERT / "imports"
WHEN = "2026-10-07T00:00:00+00:00"


@pytest.fixture(autouse=True)
def fresh_data():
    """Each test starts with the authored C01 and C03 pools and no progress."""
    assert "certprep-test-" in str(settings.data_dir)
    for f in (certs.cert_dir(CERT) / "questions").glob("*.json"):
        f.unlink()
    tracker.reset(CERT)
    for ch in (1, 3):
        items = json.loads((AUTHORED / f"ch{ch:02d}_claude.json").read_text(encoding="utf-8"))["questions"]
        generator.import_items(CERT, f"C{ch:02d}", items, "claude", "test", seed=1, strict=False)  # v1 pools predate the cue checks
    yield


@pytest.fixture
def client():
    """Behaves like the app's own page: right host, same origin, this launch's CSRF token."""
    from certprep import security
    from certprep.main import app
    return TestClient(app, base_url="http://127.0.0.1:8000",
                      headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": security.CSRF_TOKEN})


def _answer(client, sid, qid, correct=True, conf=3):
    q = pool.get(CERT, qid)
    sel = q.answer if correct else [next(o.key for o in q.options if o.key not in q.answer)]
    return client.post(f"/api/sessions/{sid}/answer", json={"question_id": qid, "selected": sel, "confidence": conf})


# ---- status rules (plan 8.4, 1-5 confidence) --------------------------------

def _a(obj="C01-01", ok=True, conf=3, session="s1", angle="symptom-to-attack", qid="Q-C01-0001", err=None):
    return {"objective": obj, "correct": int(ok), "confidence": conf, "session_id": session, "angle": angle,
            "question_id": qid, "error_type": err, "answered_at": "2026-10-01T00:00:00+00:00"}


def test_status_new_weak_improving_solid():
    assert tracker.ObjectiveStats("C01-01").status == "New"
    weak = tracker.objective_stats([_a(ok=False), _a(ok=False), _a()])["C01-01"]
    assert weak.status == "Weak"  # 1/3 < 60%
    improving = tracker.objective_stats([_a(), _a(), _a()])["C01-01"]
    assert improving.status == "Improving"  # 3 correct but one session, one angle
    solid = tracker.objective_stats([
        _a(session="s1", angle="symptom-to-attack"),
        _a(session="s2", angle="neighbor-discrimination"),
        _a(session="s2", angle="which-is-not"),
    ])["C01-01"]
    assert solid.status == "Solid"


@pytest.mark.parametrize("conf, weak", [(3, False), (4, True), (5, True)])
def test_wrong_while_confident_forces_weak(conf, weak):
    s = tracker.objective_stats([_a(), _a(), _a(), _a(), _a(ok=False, conf=conf)])["C01-01"]
    assert s.last5_accuracy == 0.8
    assert (s.status == "Weak") is weak


def test_correct_guess_is_not_mastery():
    guesses = [_a(session=f"s{i}", angle=f"a{i}", conf=1) for i in range(5)]
    s = tracker.objective_stats(guesses)["C01-01"]
    assert s.correct == 0 and s.guessed_correct == 5 and s.last5_marks == ["guess"] * 5
    assert s.status == "Weak"  # five lucky guesses prove nothing
    assert s.calibration[1] == [5, 5]  # calibration still records what actually happened
    unsure = tracker.objective_stats([_a(session=f"s{i}", angle=f"a{i}", conf=2) for i in range(3)])["C01-01"]
    assert unsure.status == "Solid"  # Unsure (2) is credited, like v1 "unsure"


def test_solid_revisit_schedule():
    s = tracker.objective_stats([
        _a(session="s1", angle="a"), _a(session="s2", angle="b"), _a(session="s2", angle="c")])["C01-01"]
    seen = datetime.fromisoformat(s.last_seen)
    assert not s.revisit_due(seen + timedelta(days=2))
    assert s.revisit_due(seen + timedelta(days=3))  # 2 sessions correct -> 3 days


def test_too_easy_needs_a_certain_correct_streak():
    rows = [_a(session=f"s{i}", conf=5) for i in range(3)]
    assert tracker.too_easy(rows) == {"Q-C01-0001": 3}
    assert tracker.too_easy(rows[:2]) == {}
    assert tracker.too_easy(rows[:2] + [_a(session="s9", conf=4)]) == {}
    assert tracker.too_easy([_a(session="s0", ok=False)] + rows) == {"Q-C01-0001": 4}  # only the latest streak counts


# ---- statuses (plan section 6) ---------------------------------------------

def test_v1_status_names_still_load():
    q = pool.load(CERT, "C01")[0].model_dump()
    assert Question.model_validate({**q, "status": "draft"}).status == "unreviewed"
    assert Question.model_validate({**q, "status": "verified"}).status == "validated"


def test_new_questions_are_unreviewed_and_answering_validates_passively(client):
    s = client.post(f"{API}/sessions", json={"mode": "practice", "sections": ["C03"], "count": 1}).json()
    qid = s["questions"][0]["id"]
    assert s["questions"][0]["status"] == "unreviewed"
    r = _answer(client, s["id"], qid, correct=False).json()
    assert r["question"]["status"] == "passive" and r["question"]["status_label"] == "Passively-Validated"
    q = pool.get(CERT, qid)
    assert q.status == "passive" and q.seen_at


def test_answering_in_an_exam_also_validates_passively(client):
    s = client.post(f"{API}/sessions", json={"mode": "exam", "sections": ["C01"], "count": 2}).json()
    qid = s["questions"][0]["id"]
    assert _answer(client, s["id"], qid).json() == {"recorded": True}
    assert pool.get(CERT, qid).status == "passive"


def test_looks_right_validates_once(client):
    qid = pool.load(CERT, "C01")[0].id
    assert client.post(f"{API}/questions/{qid}/validate").json()["status"] == "validated"
    assert pool.get(CERT, qid).verified_at
    assert client.post(f"{API}/questions/{qid}/validate").status_code == 409


def test_status_sync_after_a_restore():
    a, b = pool.load(CERT, "C01")[:2]
    assert pool.mark_seen_many(CERT, {a.id: WHEN, b.id: WHEN, "Q-C99-0001": WHEN}) == 2
    assert pool.get(CERT, a.id).status == "passive" and pool.get(CERT, a.id).seen_at == WHEN
    assert pool.mark_seen_many(CERT, {a.id: WHEN}) == 0  # nothing left to change


# ---- disputes ------------------------------------------------------------------

def test_report_takes_the_question_out_of_play_until_decided(client):
    q = pool.load(CERT, "C01")[0]
    r = client.post(f"{API}/questions/{q.id}/report", json={"reason": "ambiguous", "note": "two fit"})
    assert r.json()["status"] == "disputed"
    assert q.id not in {x.id for x in pool.active(CERT)}
    listed = client.get(f"{API}/disputes").json()
    assert [d["id"] for d in listed] == [q.id] and listed[0]["disputed_reason"] == "ambiguous: two fit"
    # Undo: back into play with its old status.
    assert client.post(f"{API}/questions/{q.id}/dispute", json={"decision": "undo"}).json()["status"] == "unreviewed"
    assert q.id in {x.id for x in pool.active(CERT)} and client.get(f"{API}/disputes").json() == []
    # Confirm: retired with the reason, answers to it stop counting.
    client.post(f"{API}/questions/{q.id}/report", json={"reason": "wrong-answer"})
    assert client.post(f"{API}/questions/{q.id}/dispute", json={"decision": "confirm"}).json()["status"] == "retired"
    assert pool.get(CERT, q.id).retired_reason.startswith("Reported by user") and "wrong-answer" in pool.get(CERT, q.id).retired_reason
    assert client.post(f"{API}/questions/{q.id}/dispute", json={"decision": "undo"}).status_code == 404  # retired: gone


def test_disputed_answers_dont_count_toward_objectives():
    q = pool.load(CERT, "C01")[0]
    tracker.create_session("b" * 16, CERT, "practice", ["C01"], [q.id], None)
    tracker.record_attempt("b" * 16, CERT, q, ["Z"], 5, False)
    assert sessions.current_stats(CERT)[q.objectives[0]].status == "Weak"
    pool.dispute(CERT, q.id, "ambiguous", WHEN)
    assert q.objectives[0] not in sessions.current_stats(CERT)


def test_practice_summary_lists_its_disputes_and_scores_without_them(client):
    s = client.post(f"{API}/sessions", json={"mode": "practice", "sections": ["C01"], "count": 3}).json()
    q1, q2 = s["questions"][0]["id"], s["questions"][1]["id"]
    _answer(client, s["id"], q1, correct=True)
    _answer(client, s["id"], q2, correct=False)
    client.post(f"{API}/questions/{q2}/report", json={"reason": "wrong-answer", "session_id": s["id"]})
    rep = client.post(f"/api/sessions/{s['id']}/finish").json()
    assert rep["scores"]["all"] == {"correct": 1, "total": 1, "percent": 100.0}  # the disputed miss is left out
    assert [d["question"]["id"] for d in rep["disputes"]] == [q2] and rep["excluded"] == [q2]


def test_exam_reports_are_held_until_the_results(client):
    s = client.post(f"{API}/sessions", json={"mode": "exam", "sections": ["C01"], "count": 4}).json()
    ids = [q["id"] for q in s["questions"]]
    for qid in ids:
        _answer(client, s["id"], qid, correct=True)
    # A direct report during the exam is refused; a held one doesn't touch the question.
    assert client.post(f"{API}/questions/{ids[0]}/report",
                       json={"reason": "ambiguous", "session_id": s["id"]}).status_code == 409
    assert client.post(f"/api/sessions/{s['id']}/held-reports", json={"question_id": ids[0], "reason": "ambiguous"}).status_code == 200
    assert client.post(f"/api/sessions/{s['id']}/held-reports", json={"question_id": ids[1], "reason": "typo-or-wording"}).status_code == 200
    assert pool.get(CERT, ids[0]).status == "passive"
    decide = f"/api/sessions/{s['id']}/held-reports/decide"
    assert client.post(decide, json={"question_id": ids[0], "decision": "confirm"}).status_code == 409  # not before the end
    assert client.post(decide, json={"question_id": ids[1], "decision": "withdraw"}).status_code == 200  # take it back
    rep = client.post(f"/api/sessions/{s['id']}/finish").json()
    assert [(d["question"]["id"], d["decision"]) for d in rep["disputes"]] == [(ids[0], None)]
    assert rep["scores"]["all"] == {"correct": 4, "total": 4, "percent": 100.0}  # held, not yet confirmed: still counted
    rep = client.post(decide, json={"question_id": ids[0], "decision": "confirm"}).json()
    assert rep["scores"]["all"] == {"correct": 3, "total": 3, "percent": 100.0} and rep["excluded"] == [ids[0]]
    assert pool.get(CERT, ids[0]).status == "retired" and rep["disputes"][0]["decision"] == "confirmed"
    assert client.post(decide, json={"question_id": ids[0], "decision": "withdraw"}).status_code == 404


# ---- selection ---------------------------------------------------------------

def test_practice_prefers_weak_objectives():
    tracker.create_session("a" * 16, CERT, "practice", ["C01"], [], None)
    target = pool.load(CERT, "C01")[0]
    for _ in range(3):
        tracker.record_attempt("a" * 16, CERT, target, ["Z"], 5, False)  # wrong, certain
    later = datetime.now(timezone.utc)  # the miss isn't due yet, so only the weight brings it back
    hits = sum(any(q.objectives[0] == target.objectives[0]
                   for q in sessions.select(CERT, "practice", ["C01"], 5, random.Random(i), later))
               for i in range(200))
    # 5 picks from 48 objectives: uniform chance ~10% (~21 of 200 runs). Weak (8) vs 47 New (2) gives ~35%.
    assert hits > 50


def test_practice_brings_back_due_misses_with_growing_waits():
    q = pool.load(CERT, "C01")[5]
    tracker.create_session("e" * 16, CERT, "practice", ["C01"], [q.id], None)
    tracker.record_attempt("e" * 16, CERT, q, ["Z"], 3, False)
    answered = datetime.fromisoformat(tracker.all_attempts(CERT)[-1]["answered_at"])

    def served(days):
        return q.id in {x.id for x in sessions.select(CERT, "practice", ["C01"], 10, random.Random(3),
                                                       answered + timedelta(days=days))}
    assert not served(0.5) and served(1.1)  # first miss: back after a day
    tracker.create_session("f" * 16, CERT, "practice", ["C01"], [q.id], None)
    tracker.record_attempt("f" * 16, CERT, q, ["Z"], 3, False)  # missed twice in a row: wait 3 days
    answered = datetime.fromisoformat(tracker.all_attempts(CERT)[-1]["answered_at"])
    assert not served(2) and served(3.1)


def test_practice_reserves_room_for_new_objectives():
    # Make every C01 objective but the untouched ones Weak; new ones must still appear.
    qs = pool.load(CERT, "C01")
    tracker.create_session("g" * 16, CERT, "practice", ["C01"], [], None)
    for q in qs[:40]:
        tracker.record_attempt("g" * 16, CERT, q, ["Z"], 3, False)
    practiced = {q.objectives[0] for q in qs[:40]}
    soon = datetime.fromisoformat(tracker.all_attempts(CERT)[-1]["answered_at"])  # no misses due yet
    for seed in range(20):
        picked = sessions.select(CERT, "practice", ["C01"], 10, random.Random(seed), soon)
        assert sum(q.objectives[0] not in practiced for q in picked) >= 2  # 20% of 10


def test_exam_draws_from_every_served_question_preferring_unseen():
    seen = pool.load(CERT, "C01")[:40]
    pool.mark_seen_many(CERT, {q.id: WHEN for q in seen})
    picked = sessions.select(CERT, "exam", ["C01"], 8, random.Random(1))
    assert len(picked) == 8 and all(q.seen_at is None for q in picked)  # 8 unseen exist, so no repeats
    pool.dispute(CERT, pool.load(CERT, "C01")[45].id, "x", WHEN)
    assert pool.load(CERT, "C01")[45].id not in {q.id for q in sessions.select(CERT, "exam", ["C01"], 200, random.Random(1))}


def test_exam_allocation_follows_domain_weights():
    picked = sessions.select(CERT, "exam", ["C01", "C03"], 18, random.Random(1))
    by_domain = {d: sum(q.domain == d for q in picked) for d in ("1.0", "2.0")}
    assert by_domain == {"1.0": 8, "2.0": 10}  # cert.json weights 4:5


# ---- scores (plan 7.3) -----------------------------------------------------------

def test_exam_scores_all_and_validated_only(client):
    qs = pool.load(CERT, "C01")
    # Seen before the exam: two Passively-Validated questions, plus one marked Looks right.
    pool.mark_seen_many(CERT, {qs[0].id: WHEN, qs[1].id: WHEN})
    pool.validate(CERT, qs[2].id, WHEN)
    s = tracker.create_session("c" * 16, CERT, "exam", ["C01"], [q.id for q in qs[:6]], 3000)
    for q, ok in zip(qs[:6], (True, False, True, True, False)):  # qs[5] left unanswered
        _answer(client, s["id"], q.id, correct=ok)
    rep = client.post(f"/api/sessions/{s['id']}/finish").json()
    assert rep["scores"]["all"] == {"correct": 3, "total": 6, "percent": 50.0}       # unanswered counts as wrong
    assert rep["scores"]["validated"] == {"correct": 2, "total": 3, "percent": 66.7}  # qs[0..2] only
    assert rep["scores"]["repeat"]["total"] == 2 and rep["scores"]["new"]["total"] == 4
    assert rep["pass_mark"] is None and rep["passed"] is None and rep["pass_note"].startswith("No pass/fail estimate")


def test_pass_mark_only_for_percentages():
    cert = certs.get_cert(CERT)
    exam = cert.exam

    def with_score(v):
        return cert.model_copy(update={"exam": exam.model_copy(update={"passing_score": certs.Fact(value=v, confidence="official")})})
    assert sessions.pass_mark(with_score(70)) == 70.0
    assert sessions.pass_mark(with_score(750)) is None   # scaled: can't convert
    assert sessions.pass_mark(with_score(None)) is None


# ---- API flow -----------------------------------------------------------------------

def test_certs_and_sections_endpoints(client):
    listed = client.get("/api/certs").json()
    assert [c["id"] for c in listed] == [CERT] and listed[0]["short_name"] == "CCST Cybersecurity"
    assert client.get(API).json()["exam_defaults"] == {"questions": 40, "minutes": 50}
    c01 = client.get(f"{API}/sections").json()[0]
    assert c01["name"] == "Chapter 1: Security Concepts" and c01["objectives"] == 48
    assert c01["unreviewed"] == c01["served"] > 0 and c01["passive"] == c01["validated"] == 0


def test_exam_flow_withholds_feedback_until_finish(client):
    s = client.post(f"{API}/sessions", json={"mode": "exam", "sections": ["C01"], "count": 5}).json()
    assert s["time_limit_s"] == 50 * 60 and len(s["questions"]) == 5 and s["cert_id"] == CERT
    assert "answer" not in s["questions"][0]
    qid = s["questions"][0]["id"]
    assert _answer(client, s["id"], qid, conf=5).json() == {"recorded": True}
    assert client.get(f"/api/sessions/{s['id']}/report").status_code == 409
    assert "correct" not in client.get(f"/api/sessions/{s['id']}").json()["answers"][qid]
    rep = client.post(f"/api/sessions/{s['id']}/finish").json()
    assert rep["answered"] == 1 and rep["total"] == 5 and "1.0" in rep["by_domain"]
    assert rep["weights_note"].startswith("Cisco does not publish domain weights")
    assert _answer(client, s["id"], qid).status_code == 409


def test_practice_gives_feedback_and_error_type(client):
    s = client.post(f"{API}/sessions", json={"mode": "practice", "sections": ["C03"], "count": 3}).json()
    qid = s["questions"][0]["id"]
    r = _answer(client, s["id"], qid, correct=False, conf=1).json()
    assert r["correct"] is False and r["question"]["answer"]
    ok = client.post(f"/api/sessions/{s['id']}/error-type", json={"question_id": qid, "error_type": "concept-gap"})
    assert ok.status_code == 200
    assert client.get(f"/api/sessions/{s['id']}").json()["answers"][qid]["confidence"] == 1


def test_superseded_question_attempts_still_count():
    q, r = pool.load(CERT, "C01")[0], pool.load(CERT, "C01")[1]
    tracker.create_session("c" * 16, CERT, "practice", ["C01"], [q.id, r.id], None)
    tracker.record_attempt("c" * 16, CERT, q, ["Z"], 5, False)
    tracker.record_attempt("c" * 16, CERT, r, ["Z"], 5, False)
    pool.retire_many(CERT, "C01", {q.id}, f"{pool.SUPERSEDED_PREFIX} by the v2 pool")  # rewrite: history kept
    pool.retire(CERT, r.id, "Reported by user: wrong-answer")                         # flawed: history dropped
    stats = sessions.current_stats(CERT)
    assert stats[q.objectives[0]].attempts == 1
    assert r.objectives[0] == q.objectives[0] or r.objectives[0] not in stats


def test_retired_question_does_not_block_its_replacement():
    items = json.loads((AUTHORED / "ch01_claude.json").read_text(encoding="utf-8"))["questions"][:1]
    assert generator.import_items(CERT, "C01", items, "claude", "test", strict=False).rejected  # live duplicate
    original = next(q for q in pool.load(CERT, "C01") if q.objectives[0] == items[0]["objectives"][0])
    pool.retire(CERT, original.id, "test: replaced by a corrected version")
    result = generator.import_items(CERT, "C01", items, "claude", "test", strict=False)
    assert len(result.accepted) == 1 and not result.rejected


def test_imported_questions_get_section_ids_and_source():
    q = pool.load(CERT, "C03")[0]
    assert q.id.startswith("Q-C03-") and q.section == "C03" and q.domain == "2.0" and q.status == "unreviewed"
    assert q.source_ref == f"objectives/C03.md#{q.objectives[0]}"


def test_too_easy_endpoint_and_report_reason(client):
    q = pool.load(CERT, "C01")[0]
    for i in range(3):
        sid = f"{i:016x}"
        tracker.create_session(sid, CERT, "practice", ["C01"], [q.id], None)
        tracker.record_attempt(sid, CERT, q, q.answer, 5, False)
    flagged = client.get(f"{API}/too-easy?section=C01").json()
    assert [x["id"] for x in flagged] == [q.id] and flagged[0]["attempts"] == 3
    r = client.post(f"{API}/questions/{q.id}/report", json={"reason": "too-easy"})
    assert r.json()["status"] == "disputed" and pool.get(CERT, q.id).disputed_reason == "too-easy"
    assert client.get(f"{API}/too-easy?section=C01").json() == []


def test_exhibit_is_public_and_roles_are_not():
    item = json.loads((AUTHORED / "ch01_claude.json").read_text(encoding="utf-8"))["questions"][0]
    q = generator.GeneratedQuestion.model_validate({**item, "exhibit": "Oct 21 10:02:11 sshd: Failed password for root",
                                                    "options": [{**o, "role": "related"} for o in item["options"]]})
    full = Question(**q.model_dump(), id="Q-C01-0999", section="C01", domain="1.0", source_ref="x",
                    provider="claude", model="test", created_at="2026-10-21T00:00:00+00:00")
    public = sessions.question_public(full)
    assert public["exhibit"].startswith("Oct 21") and "role" not in public["options"][0]
    assert sessions.question_full(full)["options"][0]["role"] == "related"


def test_retire_many_retires_only_unretired():
    ids = {q.id for q in pool.load(CERT, "C01")[:3]}
    pool.retire(CERT, sorted(ids)[0], "already gone")
    done = pool.retire_many(CERT, "C01", ids | {"Q-C01-9999"}, "superseded")
    assert len(done) == 2 and all(pool.get(CERT, i).status == "retired" for i in ids)


def test_export_summary(client):
    s = client.post(f"{API}/sessions", json={"mode": "practice", "sections": ["C01"], "count": 2}).json()
    for item in s["questions"]:
        _answer(client, s["id"], item["id"], conf=5)
    client.post(f"/api/sessions/{s['id']}/finish")
    text = client.get(f"{API}/export").json()["text"]
    assert text.startswith("CCST Cybersecurity export") and "Last session: practice (C01), 2/2 correct" in text
    assert "Next focus:" in text


def test_input_validation(client):
    assert client.post(f"{API}/sessions", json={"mode": "exam", "sections": [1]}).status_code == 422
    assert client.post(f"{API}/sessions", json={"mode": "exam", "sections": ["c01"]}).status_code == 422
    assert client.post(f"{API}/sessions", json={"mode": "exam", "sections": ["C99"]}).status_code == 404
    for retired_mode in ("drill", "diagnostic", "review", "hack"):
        assert client.post(f"{API}/sessions", json={"mode": retired_mode, "sections": ["C01"]}).status_code == 422
    s = client.post(f"{API}/sessions", json={"mode": "practice", "sections": ["C01"], "count": 1}).json()
    qid = s["questions"][0]["id"]
    for conf in ("sure", 0, 6, 2.5, True):
        r = client.post(f"/api/sessions/{s['id']}/answer", json={"question_id": qid, "selected": ["A"], "confidence": conf})
        assert r.status_code == 422, conf
    assert client.get("/api/sessions/../../etc").status_code == 404
    assert client.get(f"{API}/tracker?section=C99").status_code == 404
    assert client.get(f"{API}/tracker?section=../x").status_code == 422
    assert client.post(f"{API}/progress/reset", json={"confirm": "yes"}).status_code == 422
    assert client.post(f"{API}/questions/Q-C02-0001/validate").status_code == 404
    assert client.post(f"{API}/questions/{qid}/dispute", json={"decision": "maybe"}).status_code == 422


@pytest.mark.parametrize("cert_id", ["nope", "..%2F..%2Fetc", "CCST", "ccst-cyber%00", "a"])
def test_unknown_or_malformed_cert_is_rejected(client, cert_id):
    assert client.get(f"/api/certs/{cert_id}/sections").status_code in (404, 422)
