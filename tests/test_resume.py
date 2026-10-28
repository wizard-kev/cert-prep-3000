"""v2 P11: picking up an unfinished session (plan 8.1)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from certprep import certs, generator, pool, security, tracker
from certprep.config import PROJECT_ROOT, settings

CERT = "ccst-cyber"
AUTHORED = PROJECT_ROOT / "data" / "certs" / CERT / "imports"


@pytest.fixture(autouse=True)
def fresh():
    assert "certprep-test-" in str(settings.data_dir)
    for f in (certs.cert_dir(CERT) / "questions").glob("*.json"):
        f.unlink()
    tracker.reset(CERT)
    items = json.loads((AUTHORED / "ch01_v2_set1a.json").read_text(encoding="utf-8"))["questions"]
    generator.import_items(CERT, "C01", items, "claude", "test", seed=1, strict=False)
    yield


@pytest.fixture
def client():
    from certprep.main import app
    return TestClient(app, base_url="http://127.0.0.1:8000",
                      headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": security.CSRF_TOKEN})


def _start(client, mode, count=4, **extra):
    r = client.post(f"/api/certs/{CERT}/sessions", json={"mode": mode, "sections": ["C01"], "count": count, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _answer(client, s, n, held=False):
    for q in s["questions"][:n]:
        full = pool.get(CERT, q["id"])
        client.post(f"/api/sessions/{s['id']}/answer", json={"question_id": q["id"], "selected": full.answer, "confidence": 3})


def test_open_sessions_lists_current_modes_newest_first(client):
    done = _start(client, "practice")
    client.post(f"/api/sessions/{done['id']}/finish", json={})
    tracker.create_session("a" * 16, CERT, "drill", ["C01"], [done["questions"][0]["id"]], None)  # a v1 mode: history only
    first = _start(client, "practice")
    _answer(client, first, 2)
    second = _start(client, "exam", minutes=30)
    rows = client.get(f"/api/certs/{CERT}/sessions/open").json()
    assert [r["id"] for r in rows] == [second["id"], first["id"]]
    assert rows[1]["answered"] == 2 and rows[1]["questions"] == 4 and rows[1]["sections"] == ["C01"]
    assert rows[0]["mode"] == "exam" and rows[0]["time_up"] is False


def test_open_sessions_shows_at_most_five(client):
    for _ in range(7):
        _start(client, "practice", count=1)
    assert len(client.get(f"/api/certs/{CERT}/sessions/open").json()) == 5


def test_a_resumed_practice_session_keeps_its_feedback(client):
    s = _start(client, "practice")
    _answer(client, s, 2)
    view = client.get(f"/api/sessions/{s['id']}").json()
    answered = [q["id"] for q in s["questions"][:2]]
    assert set(view["answers"]) == set(answered) and set(view["revealed"]) == set(answered)
    q0 = view["revealed"][answered[0]]
    assert q0["correct"] is True and q0["question"]["answer"] == pool.get(CERT, answered[0]).answer
    assert view["held"] == {}


def test_a_resumed_exam_stays_secret_and_keeps_held_reports(client):
    s = _start(client, "exam", minutes=30)
    _answer(client, s, 1)
    qid = s["questions"][1]["id"]
    assert client.post(f"/api/sessions/{s['id']}/held-reports", json={"question_id": qid, "reason": "ambiguous"}).status_code == 200
    view = client.get(f"/api/sessions/{s['id']}").json()
    assert view["revealed"] == {} and "correct" not in view["answers"][s["questions"][0]["id"]]
    assert all("answer" not in q for q in view["questions"])
    assert view["held"] == {qid: True}


def test_an_exam_whose_time_ran_out_is_marked(client):
    s = _start(client, "exam", minutes=5)
    long_ago = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds")
    with tracker.connect() as c:
        c.execute("UPDATE sessions SET started_at = ? WHERE id = ?", (long_ago, s["id"]))
    (row,) = [r for r in client.get(f"/api/certs/{CERT}/sessions/open").json() if r["id"] == s["id"]]
    assert row["time_up"] is True


def test_open_sessions_needs_a_known_certification(client):
    assert client.get("/api/certs/nope/sessions/open").status_code == 404
    assert client.get("/api/certs/..%2Fx/sessions/open").status_code in (404, 422)
