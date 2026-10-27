import json
import random

import pytest
from fastapi.testclient import TestClient

from certprep import certs, generator, pool, sessions, tracker
from certprep.config import PROJECT_ROOT, settings
from certprep.schema import Question

CERT = "ccst-cyber"
API = f"/api/certs/{CERT}"
AUTHORED = PROJECT_ROOT / "data" / "certs" / CERT / "imports"


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


# ---- status rules (plan 8.4) ------------------------------------------

def _a(obj="C01-01", ok=True, conf="unsure", session="s1", angle="symptom-to-attack", qid="Q-C01-0001", err=None):
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


def test_sure_but_wrong_forces_weak():
    s = tracker.objective_stats([_a(), _a(), _a(), _a(), _a(ok=False, conf="sure")])["C01-01"]
    assert s.last5_accuracy == 0.8
    assert s.status == "Weak"


def test_solid_revisit_schedule():
    from datetime import datetime, timedelta
    s = tracker.objective_stats([
        _a(session="s1", angle="a"), _a(session="s2", angle="b"), _a(session="s2", angle="c")])["C01-01"]
    seen = datetime.fromisoformat(s.last_seen)
    assert not s.revisit_due(seen + timedelta(days=2))
    assert s.revisit_due(seen + timedelta(days=3))  # 2 sessions correct -> 3 days


# ---- selection --------------------------------------------------------

def test_diagnostic_one_question_per_objective():
    picked = sessions.select(CERT, "diagnostic", ["C01", "C03"], 500, random.Random(1))
    assert len(picked) == 48 + 39
    assert len({q.objectives[0] for q in picked}) == len(picked)


def test_exam_uses_verified_only():
    assert sessions.select(CERT, "exam", ["C01", "C03"], 40, random.Random(1)) == []
    for q in pool.load(CERT, "C01")[:10]:
        pool.verify(CERT, q.id, "2026-10-07T00:00:00+00:00")
    picked = sessions.select(CERT, "exam", ["C01", "C03"], 40, random.Random(1))
    assert len(picked) == 10 and all(q.status == "verified" for q in picked)


def test_exam_allocation_follows_domain_weights():
    for code in ("C01", "C03"):
        for q in pool.load(CERT, code):
            pool.verify(CERT, q.id, "2026-10-07T00:00:00+00:00")
    picked = sessions.select(CERT, "exam", ["C01", "C03"], 18, random.Random(1))
    by_domain = {d: sum(q.domain == d for q in picked) for d in ("1.0", "2.0")}
    assert by_domain == {"1.0": 8, "2.0": 10}  # cert.json weights 4:5


def test_drill_prefers_weak_objectives():
    tracker.create_session("a" * 16, CERT, "drill", ["C01"], [], None)
    target = pool.load(CERT, "C01")[0]
    for _ in range(3):
        tracker.record_attempt("a" * 16, CERT, target, ["Z"], "sure", False)  # wrong, sure
    hits = sum(any(q.objectives[0] == target.objectives[0]
                   for q in sessions.select(CERT, "drill", ["C01"], 5, random.Random(i)))
               for i in range(200))
    # 5 picks from 48 objectives: uniform chance ~10% (~21 of 200 runs). Weak (8) vs 47 New (2) gives ~35%.
    assert hits > 50


# ---- API flow ---------------------------------------------------------

def test_certs_and_sections_endpoints(client):
    listed = client.get("/api/certs").json()
    assert [c["id"] for c in listed] == [CERT] and listed[0]["short_name"] == "CCST Cybersecurity"
    detail = client.get(API).json()
    assert detail["exam_defaults"] == {"questions": 40, "minutes": 50}
    secs = client.get(f"{API}/sections").json()
    assert [s["code"] for s in secs][:3] == ["C01", "C02", "C03"]
    c01 = secs[0]
    assert c01["name"] == "Chapter 1: Security Concepts" and c01["objectives"] == 48 and c01["draft"] > 0


def test_exam_flow_withholds_feedback_until_finish(client):
    for q in pool.load(CERT, "C01")[:5]:
        pool.verify(CERT, q.id, "2026-10-07T00:00:00+00:00")
    s = client.post(f"{API}/sessions", json={"mode": "exam", "sections": ["C01"], "count": 5}).json()
    assert s["time_limit_s"] == 50 * 60 and len(s["questions"]) == 5 and s["cert_id"] == CERT
    assert "answer" not in s["questions"][0]
    qid = s["questions"][0]["id"]
    r = client.post(f"/api/sessions/{s['id']}/answer", json={"question_id": qid, "selected": ["A"], "confidence": "sure"})
    assert r.json() == {"recorded": True}
    assert client.get(f"/api/sessions/{s['id']}/report").status_code == 409
    assert "correct" not in client.get(f"/api/sessions/{s['id']}").json()["answers"][qid]
    rep = client.post(f"/api/sessions/{s['id']}/finish").json()
    assert rep["answered"] == 1 and rep["total"] == 5 and "1.0" in rep["by_domain"]
    assert rep["weights_note"].startswith("Cisco does not publish domain weights")
    assert client.post(f"/api/sessions/{s['id']}/answer",
                       json={"question_id": qid, "selected": ["A"], "confidence": "sure"}).status_code == 409


def test_drill_gives_feedback_and_error_type(client):
    s = client.post(f"{API}/sessions", json={"mode": "drill", "sections": ["C03"], "count": 3}).json()
    qid = s["questions"][0]["id"]
    wrong = next(o["key"] for o in client.get(f"/api/sessions/{s['id']}").json()["questions"][0]["options"]
                 if o["key"] not in pool.get(CERT, qid).answer)
    r = client.post(f"/api/sessions/{s['id']}/answer", json={"question_id": qid, "selected": [wrong], "confidence": "guess"}).json()
    assert r["correct"] is False and r["question"]["answer"]
    ok = client.post(f"/api/sessions/{s['id']}/error-type", json={"question_id": qid, "error_type": "concept-gap"})
    assert ok.status_code == 200
    review = client.post(f"{API}/sessions", json={"mode": "review", "sections": ["C03"]}).json()
    assert [q["id"] for q in review["questions"]] == [qid]


def test_verify_and_report(client):
    qid = pool.load(CERT, "C01")[0].id
    assert client.post(f"{API}/questions/{qid}/verify").json()["status"] == "verified"
    assert client.post(f"{API}/questions/{qid}/verify").status_code == 409
    r = client.post(f"{API}/questions/{qid}/report", json={"reason": "factual-error", "note": "port is 162"})
    assert r.json()["status"] == "retired"
    assert "factual-error: port is 162" in pool.get(CERT, qid).retired_reason
    assert client.post(f"{API}/questions/{qid}/report", json={"reason": "made-up"}).status_code in (404, 422)


def test_retired_question_attempts_do_not_count(client):
    q = pool.load(CERT, "C01")[0]
    tracker.create_session("b" * 16, CERT, "drill", ["C01"], [q.id], None)
    tracker.record_attempt("b" * 16, CERT, q, ["Z"], "sure", False)
    assert sessions.current_stats(CERT)[q.objectives[0]].status == "Weak"
    pool.retire(CERT, q.id, "test")
    assert q.objectives[0] not in sessions.current_stats(CERT)


def test_superseded_question_attempts_still_count():
    q, r = pool.load(CERT, "C01")[0], pool.load(CERT, "C01")[1]
    tracker.create_session("c" * 16, CERT, "drill", ["C01"], [q.id, r.id], None)
    tracker.record_attempt("c" * 16, CERT, q, ["Z"], "sure", False)
    tracker.record_attempt("c" * 16, CERT, r, ["Z"], "sure", False)
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
    assert q.id.startswith("Q-C03-") and q.section == "C03" and q.domain == "2.0"
    assert q.source_ref == f"objectives/C03.md#{q.objectives[0]}"


# ---- v2: guesses, too-easy flags, exhibits ------------------------------

def test_correct_guess_is_not_mastery():
    guesses = [_a(session=f"s{i}", angle=f"a{i}", conf="guess") for i in range(5)]
    s = tracker.objective_stats(guesses)["C01-01"]
    assert s.correct == 0 and s.guessed_correct == 5 and s.last5_marks == ["guess"] * 5
    assert s.status == "Weak"  # five lucky guesses prove nothing
    assert s.calibration["guess"] == [5, 5]  # calibration still records what actually happened
    sure = tracker.objective_stats([_a(session=f"s{i}", angle=f"a{i}") for i in range(3)])["C01-01"]
    assert sure.status == "Solid"


def test_too_easy_needs_a_sure_correct_streak():
    rows = [_a(session=f"s{i}", conf="sure") for i in range(3)]
    assert tracker.too_easy(rows) == {"Q-C01-0001": 3}
    assert tracker.too_easy(rows[:2]) == {}
    assert tracker.too_easy(rows[:2] + [_a(session="s9", conf="unsure")]) == {}
    assert tracker.too_easy([_a(session="s0", ok=False)] + rows) == {"Q-C01-0001": 4}  # only the latest streak counts


def test_too_easy_endpoint_and_report_reason(client):
    q = pool.load(CERT, "C01")[0]
    for i in range(3):
        sid = f"{i:016x}"
        tracker.create_session(sid, CERT, "drill", ["C01"], [q.id], None)
        tracker.record_attempt(sid, CERT, q, q.answer, "sure", False)
    flagged = client.get(f"{API}/too-easy?section=C01").json()
    assert [x["id"] for x in flagged] == [q.id] and flagged[0]["attempts"] == 3
    r = client.post(f"{API}/questions/{q.id}/report", json={"reason": "too-easy"})
    assert r.json()["status"] == "retired" and pool.get(CERT, q.id).retired_reason.endswith("too-easy")
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


def test_retire_many_retires_only_active():
    ids = {q.id for q in pool.load(CERT, "C01")[:3]}
    pool.retire(CERT, sorted(ids)[0], "already gone")
    done = pool.retire_many(CERT, "C01", ids | {"Q-C01-9999"}, "superseded")
    assert len(done) == 2 and all(pool.get(CERT, i).status == "retired" for i in ids)


def test_export_summary(client):
    s = client.post(f"{API}/sessions", json={"mode": "drill", "sections": ["C01"], "count": 2}).json()
    for item in s["questions"]:
        client.post(f"/api/sessions/{s['id']}/answer",
                    json={"question_id": item["id"], "selected": ["A"], "confidence": "sure"})
    client.post(f"/api/sessions/{s['id']}/finish")
    text = client.get(f"{API}/export").json()["text"]
    assert text.startswith("CCST Cybersecurity export") and "Last session: drill (C01)" in text and "Next focus:" in text


def test_input_validation(client):
    assert client.post(f"{API}/sessions", json={"mode": "exam", "sections": [1]}).status_code == 422
    assert client.post(f"{API}/sessions", json={"mode": "exam", "sections": ["c01"]}).status_code == 422
    assert client.post(f"{API}/sessions", json={"mode": "exam", "sections": ["C99"]}).status_code == 404
    assert client.post(f"{API}/sessions", json={"mode": "hack", "sections": ["C01"]}).status_code == 422
    assert client.get("/api/sessions/../../etc").status_code == 404
    assert client.get(f"{API}/tracker?section=C99").status_code == 404
    assert client.get(f"{API}/tracker?section=../x").status_code == 422
    assert client.post(f"{API}/progress/reset", json={"confirm": "yes"}).status_code == 422
    assert client.post(f"{API}/questions/Q-C02-0001/verify").status_code == 404


@pytest.mark.parametrize("cert_id", ["nope", "..%2F..%2Fetc", "CCST", "ccst-cyber%00", "a"])
def test_unknown_or_malformed_cert_is_rejected(client, cert_id):
    assert client.get(f"/api/certs/{cert_id}/sections").status_code in (404, 422)
