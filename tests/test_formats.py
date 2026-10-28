"""v2 P10: ordering and matching questions (plan 7.4): import checks and shuffling, answering and scoring,
prompts for the certifications whose exam uses them, storage, and the audit."""
import copy
import json
import random
import shutil

import pytest
from fastapi.testclient import TestClient

from certprep import audit, certs, generator, pool, prompts, security, sessions, tracker
from certprep.config import settings

CERT = "ccst-cyber"

ORDERING = {
    "objectives": ["C01-10"], "type": "ordering", "angle": "cause-and-effect-ordering", "difficulty": 2,
    "stem": "A web server stops accepting new connections during a SYN flood. Put the events in the order they happen.",
    "options": [
        {"key": "A", "text": "The attacker sends many SYN packets from spoofed source addresses", "rationale": "The flood starts the attack."},
        {"key": "B", "text": "The server answers each one with a SYN-ACK and waits for the reply", "rationale": "The handshake's second step."},
        {"key": "C", "text": "Each half-open connection holds a slot until its timer expires", "rationale": "No final ACK ever arrives."},
        {"key": "D", "text": "The half-open table fills and genuine clients are turned away", "rationale": "The resource is exhausted last."},
    ],
    "answer": ["A", "B", "C", "D"],
    "explanation": "A SYN flood never completes the TCP handshake, so half-open connections pile up until the table is full.",
    "discriminator_tested": "The resource exhausted is the half-open connection table, not bandwidth.",
}
MATCHING = {
    "objectives": ["C01-09", "C01-10", "C01-02"], "type": "matching", "angle": "classify-element", "difficulty": 2,
    "stem": "Match each attack term with the description that fits it.",
    "options": [
        {"key": "A", "text": "Smurf", "rationale": "Broadcast echo requests with the victim's spoofed address."},
        {"key": "B", "text": "SYN flood", "rationale": "Handshakes that are never completed."},
        {"key": "C", "text": "Botnet", "rationale": "The compromised devices themselves, not an attack."},
    ],
    "match_targets": ["Half-open TCP connections fill a server's table", "ICMP replies from many hosts flood one victim",
                      "A network of compromised devices under one controller", "A single source floods a link with UDP"],
    "answer": ["A2", "B1", "C3"],
    "explanation": "Smurf abuses broadcast ICMP replies, a SYN flood exhausts half-open connections, and a botnet is the army.",
    "discriminator_tested": "Smurf uses broadcast echo replies; SYN floods use unfinished handshakes.",
}


@pytest.fixture(autouse=True)
def fresh():
    assert "certprep-test-" in str(settings.data_dir)
    for f in (certs.cert_dir(CERT) / "questions").glob("*.json"):
        f.unlink()
    tracker.reset(CERT)
    yield
    for extra in settings.certs_dir.iterdir():
        if extra.name != CERT:
            shutil.rmtree(extra)
    certs.reload()


@pytest.fixture
def client():
    from certprep.main import app
    return TestClient(app, base_url="http://127.0.0.1:8000",
                      headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": security.CSRF_TOKEN})


def _import(*items, seed=1):
    r = generator.import_items(CERT, "C01", list(items), "claude", "test", seed=seed)
    assert not r.rejected, r.rejected
    return r.accepted


def _problems(item):
    r = generator.import_items(CERT, "C01", [item], "claude", "test", seed=1)
    return r.rejected[0]["problems"] if r.rejected else []


# ---- import: checks and shuffling -------------------------------------------------

def test_ordering_imports_shuffled_but_keeps_its_sequence():
    for seed in range(15):
        for f in (certs.cert_dir(CERT) / "questions").glob("*.json"):
            f.unlink()
        (q,) = _import(ORDERING, seed=seed)
        text = {o.key: o.text for o in q.options}
        assert [text[k] for k in q.answer] == [o["text"] for o in ORDERING["options"]]  # same sequence
        assert q.answer != sorted(q.answer)  # never displayed already in order


def test_matching_imports_with_items_and_descriptions_shuffled():
    seen_orders = set()
    for seed in range(10):
        for f in (certs.cert_dir(CERT) / "questions").glob("*.json"):
            f.unlink()
        (q,) = _import(MATCHING, seed=seed)
        text = {o.key: o.text for o in q.options}
        pairs = {text[a[0]]: q.match_targets[int(a[1:]) - 1] for a in q.answer}
        assert pairs == {"Smurf": MATCHING["match_targets"][1], "SYN flood": MATCHING["match_targets"][0],
                         "Botnet": MATCHING["match_targets"][2]}
        seen_orders.add(tuple(q.match_targets))
    assert len(seen_orders) > 1


@pytest.mark.parametrize("change, phrase", [
    (lambda q: q.update(answer=["A", "B", "C"]), "every option key exactly once"),
    (lambda q: q.update(answer=["A", "B", "C", "C"]), "every option key exactly once"),
    (lambda q: q.update(stem="A web server stops accepting connections during a SYN flood. What happened?"), "ask for the order"),
    (lambda q: q["options"][0].update(role="partial"), "take no roles"),
    (lambda q: q.update(match_targets=["a", "b", "c"]), "match_targets belongs to matching questions only"),
], ids=["missing-step", "repeated-step", "no-order-wording", "roles", "stray-targets"])
def test_bad_ordering_questions_are_rejected(change, phrase):
    item = copy.deepcopy(ORDERING)
    change(item)
    assert any(phrase in p for p in _problems(item)), _problems(item)


@pytest.mark.parametrize("change, phrase", [
    (lambda q: q.update(answer=["A2", "B2", "C3"]), "different target number"),
    (lambda q: q.update(answer=["A2", "B5", "C3"]), "different target number"),  # only 4 descriptions
    (lambda q: q.update(answer=["A2", "B9", "C3"]), "should match pattern"),      # 9 is never a description number
    (lambda q: q.update(answer=["A2", "B1"]), "pairs every option key once"),
    (lambda q: q.update(answer=["A", "B", "C"]), "pairs every option key once"),
    (lambda q: q.update(match_targets=["one", "two"]), "match_targets"),
    (lambda q: q.update(match_targets=["Same", "same", "Other"]), "duplicate match_targets"),
    (lambda q: q.update(stem="Which description fits each attack term listed below?"), "ask to match"),
], ids=["target-twice", "target-out-of-range", "target-beyond-8", "item-missing", "keys-only", "too-few-targets", "duplicate-targets", "no-match-wording"])
def test_bad_matching_questions_are_rejected(change, phrase):
    item = copy.deepcopy(MATCHING)
    change(item)
    assert any(phrase in p for p in _problems(item)), _problems(item)


def test_single_and_multi_rules_are_unchanged():
    item = copy.deepcopy(ORDERING)
    item.update(type="single", answer=["A"])
    assert any("single and multi-select questions need at least 4 options" in p or "role" in p for p in _problems(
        {**item, "options": item["options"][:3]}))
    assert any("not a subset" in p for p in _problems({**item, "answer": ["A2"]}))


def test_pool_files_keep_their_shape():
    """match_targets is written only on matching questions."""
    _import(ORDERING, MATCHING)
    stored = json.loads((certs.cert_dir(CERT) / "questions" / "C01.json").read_text(encoding="utf-8"))["questions"]
    by_type = {q["type"]: q for q in stored}
    assert "match_targets" not in by_type["ordering"] and len(by_type["matching"]["match_targets"]) == 4
    r = audit.audit(CERT, ["C01"])
    assert (r["questions"], r["ordering"], r["matching"], r["single"], r["multi"]) == (2, 1, 1, 0, 0)


# ---- answering and scoring ------------------------------------------------------------

def _session(client, qid):
    tracker.create_session("e" * 16, CERT, "practice", ["C01"], [qid], None)
    return "e" * 16


def test_ordering_answers(client):
    (q,) = _import(ORDERING)
    sid = _session(client, q.id)
    pub = sessions.question_public(q)
    assert "answer" not in pub and "match_targets" not in pub
    wrong = list(reversed(q.answer))
    r = client.post(f"/api/sessions/{sid}/answer", json={"question_id": q.id, "selected": wrong, "confidence": 3})
    assert r.status_code == 200 and r.json()["correct"] is False
    assert tracker.session_attempts(sid)[0]["selected"] == wrong  # stored in the learner's order
    r = client.post(f"/api/sessions/{sid}/answer", json={"question_id": q.id, "selected": q.answer, "confidence": 4})
    assert r.json()["correct"] is True and r.json()["question"]["answer"] == q.answer
    for bad in (q.answer[:3], q.answer[:3] + q.answer[:1], ["A2", "B", "C", "D"], q.answer + ["E"]):
        assert client.post(f"/api/sessions/{sid}/answer", json={"question_id": q.id, "selected": bad, "confidence": 3}).status_code == 422


def test_matching_answers(client):
    (q,) = _import(MATCHING)
    sid = _session(client, q.id)
    assert sessions.question_public(q)["match_targets"] == q.match_targets
    swapped = [f"{a[0]}{b[1:]}" for a, b in zip(q.answer, q.answer[1:] + q.answer[:1])]
    r = client.post(f"/api/sessions/{sid}/answer", json={"question_id": q.id, "selected": swapped, "confidence": 2})
    assert r.json()["correct"] is False
    r = client.post(f"/api/sessions/{sid}/answer", json={"question_id": q.id, "selected": list(reversed(q.answer)), "confidence": 5})
    assert r.json()["correct"] is True  # pairs, in any order
    for bad in (q.answer[:2], ["A1", "A2", "B3"], ["A9", "B1", "C2"], ["A", "B", "C"]):
        assert client.post(f"/api/sessions/{sid}/answer", json={"question_id": q.id, "selected": bad, "confidence": 3}).status_code == 422


def test_ask_prompt_explains_the_new_formats(client):
    o, m = _import(ORDERING, MATCHING)
    p = client.get(f"/api/certs/{CERT}/prompts/ask/{o.id}?" + "&".join(f"selected={k}" for k in o.answer)).json()["prompt"]
    assert f"Correct order: {', '.join(o.answer)}" in p and "(correct)" in p
    p = client.get(f"/api/certs/{CERT}/prompts/ask/{m.id}?selected=A1&selected=B2&selected=C3").json()["prompt"]
    assert "Descriptions:" in p and "Correct pairs" in p and "My answer: A1, B2, C3" in p


def test_report_and_focus_work_with_the_new_formats(client):
    o, m = _import(ORDERING, MATCHING)
    s = client.post(f"/api/certs/{CERT}/sessions", json={"mode": "focus", "objectives": ["C01-09", "C01-10"], "count": 5}).json()
    assert {q["type"] for q in s["questions"]} == {"ordering", "matching"}
    for q in s["questions"]:
        full = pool.get(CERT, q["id"])
        client.post(f"/api/sessions/{s['id']}/answer", json={"question_id": q["id"], "selected": full.answer, "confidence": 4})
    client.post(f"/api/sessions/{s['id']}/finish", json={})
    rep = client.get(f"/api/sessions/{s['id']}/report").json()
    assert rep["scores"]["all"]["correct"] == 2


# ---- prompts ----------------------------------------------------------------------------

def _cert_with_formats(formats):
    data = json.loads((certs.cert_dir(CERT) / "cert.json").read_text(encoding="utf-8"))
    data["id"] = "fmt-cert"
    data["exam"]["question_formats"] = [{"format": f, "served": True, "note": ""} for f in formats]
    files = {"cert.json": json.dumps(data), "objectives/C01.md": (certs.cert_dir(CERT) / "objectives" / "C01.md").read_text(encoding="utf-8")}
    data["sections"] = [s for s in data["sections"] if s["code"] == "C01"]
    files["cert.json"] = json.dumps(data)
    certs.install("fmt-cert", files)
    return "fmt-cert"


def test_prompts_ask_for_the_formats_the_exam_uses():
    cid = _cert_with_formats(["single", "multi", "ordering", "drag-and-drop"])
    ids = [f"C01-{n:02d}" for n in range(1, 16)]
    types, rules = set(), ""
    for seed in range(12):
        r = prompts.question_prompt(cid, ids, 2, random.Random(seed))
        types |= {t["type"] for t in r["targets"]}
        if "ordering" in {t["type"] for t in r["targets"]}:
            rules = r["prompt"]
            assert all(t["angle"] == "cause-and-effect-ordering" for t in r["targets"] if t["type"] == "ordering")
    assert types == {"single", "multi", "ordering", "matching"}
    assert 'type "ordering"' in rules
    template = json.loads(rules.split("```json\n", 1)[1].split("\n```", 1)[0])
    shapes = {q["type"]: q for q in template["questions"]}
    assert shapes["ordering"]["answer"] == ["C", "A", "D", "B"] and "role" not in shapes["ordering"]["options"][0]
    # CCST's exam lists neither, so its prompts never ask for them.
    for seed in range(12):
        r = prompts.question_prompt(CERT, ids, 2, random.Random(seed))
        assert {t["type"] for t in r["targets"]} <= {"single", "multi"}
        assert 'type "ordering"' not in r["prompt"] and "match_targets" not in r["prompt"]


def test_imported_formats_travel_in_packs():
    from certprep import packs
    _import(ORDERING, MATCHING)
    pack = packs.check_pack(packs.export_pack(CERT))
    assert {q.type for q in pack.questions["C01"]} == {"ordering", "matching"}
