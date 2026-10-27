"""v2 P4: prompts for a Claude chat, and importing Claude's reply."""
import copy
import json
import random
import re

import pytest
from fastapi.testclient import TestClient

from certprep import certs, generator, importer, pool, prompts, security, tracker
from certprep.config import PROJECT_ROOT, settings

CERT = "ccst-cyber"
API = f"/api/certs/{CERT}"
IMPORTS = PROJECT_ROOT / "data" / "certs" / CERT / "imports"


def _v2(name: str, i: int = 0) -> dict:
    return json.loads((IMPORTS / name).read_text(encoding="utf-8"))["questions"][i]


def _reply(*questions, **envelope) -> str:
    data = {"format": "certprep-questions", "format_version": 1, "cert": CERT, "questions": list(questions)}
    data.update(envelope)
    return json.dumps(data)


@pytest.fixture(autouse=True)
def fresh():
    assert "certprep-test-" in str(settings.data_dir)
    folder = certs.cert_dir(CERT)
    for f in (folder / "questions").glob("*.json"):
        f.unlink()
    for f in (folder / "imports").glob("claude-*.json") if (folder / "imports").exists() else []:
        f.unlink()
    tracker.reset(CERT)
    yield


@pytest.fixture
def client():
    from certprep.main import app
    return TestClient(app, base_url="http://127.0.0.1:8000",
                      headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": security.CSRF_TOKEN})


# ---- prompts ------------------------------------------------------------

def test_question_prompt_lists_targets_rows_rules_and_format(client):
    r = client.get(f"{API}/prompts/questions?objective=C01-46&objective=C03-01&per_objective=2")
    assert r.status_code == 200
    body = r.json()
    assert [t["objective"] for t in body["targets"]] == ["C01-46", "C01-46", "C03-01", "C03-01"]
    p = body["prompt"]
    assert "Cisco Certified Support Technician (CCST) Cybersecurity (Cisco 100-160)" in p
    assert re.search(r"^- C01-46 \| .+ \| core idea: .+ \| discriminator: .+$", p, re.M)
    assert '"format": "certprep-questions"' in p and '"cert": "ccst-cyber"' in p and "```json" in p
    assert "The import rejects" in p and "(Choose two.)" in p and "CVE" in p
    assert "C01-45" in p  # neighbouring objectives are offered as look-alikes
    # Two questions on one objective use two different angles.
    angles = [t["angle"] for t in body["targets"]]
    assert angles[0] != angles[1] and angles[2] != angles[3]
    assert set(angles) <= set(prompts.PROMPT_ANGLES)


def test_new_questions_avoid_angles_already_used():
    item = _v2("ch01_v2_set1a.json")  # C01-01 on symptom-to-attack
    assert generator.import_items(CERT, "C01", [item], "claude", "test").accepted
    for seed in range(20):
        (t,) = prompts.question_prompt(CERT, ["C01-01"], 1, random.Random(seed))["targets"]
        assert t["angle"] != "symptom-to-attack"


def test_retired_questions_angles_count_as_used():
    q = generator.import_items(CERT, "C01", [_v2("ch01_v2_set1a.json")], "claude", "test").accepted[0]
    pool.retire(CERT, q.id, "Reported by user: ambiguous")
    angles = {prompts.question_prompt(CERT, ["C01-01"], 1, random.Random(s))["targets"][0]["angle"] for s in range(30)}
    assert "symptom-to-attack" not in angles


@pytest.mark.parametrize("query", ["objective=C01-99", "objective=C99-01", "objective=x", "objective=../C01-01",
                                   "objective=C01-01&per_objective=4", "per_objective=1",
                                   "&".join(f"objective=C01-{n:02d}" for n in range(1, 32))],
                         ids=["unknown-id", "unknown-section", "malformed", "traversal", "too-many-each", "none", "31-objectives"])
def test_question_prompt_rejects_bad_choices(client, query):
    assert client.get(f"{API}/prompts/questions?{query}").status_code == 422


def test_too_many_questions_for_one_prompt_is_refused(client):
    q = "&".join(f"objective=C01-{n:02d}" for n in range(1, 12)) + "&per_objective=3"  # 33 questions
    r = client.get(f"{API}/prompts/questions?{q}")
    assert r.status_code == 422 and "choose fewer objectives" in r.json()["detail"]


def test_study_prompt_includes_the_learners_mistakes(client):
    q = generator.import_items(CERT, "C01", [_v2("ch01_v2_set1a.json")], "claude", "test").accepted[0]
    wrong = next(o for o in q.options if o.key not in q.answer)
    tracker.create_session("d" * 16, CERT, "practice", ["C01"], [q.id], None)
    tracker.record_attempt("d" * 16, CERT, q, [wrong.key], 5, False)
    p = client.get(f"{API}/prompts/study?objective=C01-01&objective=C01-02").json()["prompt"]
    assert "tutor" in p and "- C01-01: Weak, 1 answered, last five 0%, recently wrong while sure" in p
    assert f'chose "{wrong.text}"' in p and "- C01-02: not practiced yet" in p


def test_ask_prompt_explains_one_question(client):
    q = generator.import_items(CERT, "C01", [_v2("ch01_v2_set1a.json")], "claude", "test").accepted[0]
    wrong = next(o for o in q.options if o.key not in q.answer)
    p = client.get(f"{API}/prompts/ask/{q.id}?selected={wrong.key}").json()["prompt"]
    assert q.stem in p and "<- keyed answer" in p and f"My answer: {wrong.key} (wrong)" in p
    assert "report the question" in p
    assert client.get(f"{API}/prompts/ask/Q-C01-0999").status_code == 404
    assert client.get(f"{API}/prompts/ask/{q.id}?selected=Z").status_code == 422


# ---- import ---------------------------------------------------------------

def test_valid_reply_is_imported_as_draft_and_archived(client):
    text = "Here are your questions:\n```json\n" + _reply(_v2("ch01_v2_set1a.json")) + "\n```"
    r = client.post(f"{API}/imports", json={"text": text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [a["id"] for a in body["accepted"]] == ["Q-C01-0001"] and body["rejected"] == []
    assert body["repair_prompt"] is None
    q = pool.get(CERT, "Q-C01-0001")
    assert q.status == "unreviewed" and q.provider == "claude" and q.model == "claude-chat"
    assert re.fullmatch(r"claude-\d{8}T\d{6}Z-[0-9a-f]{8}\.json", body["archive"])
    archived = json.loads((certs.cert_dir(CERT) / "imports" / body["archive"]).read_text(encoding="utf-8"))
    assert archived["questions"][0]["objectives"] == ["C01-01"]


def test_questions_for_two_sections_land_in_their_own_pools(client):
    body = client.post(f"{API}/imports", json={"text": _reply(_v2("ch01_v2_set1a.json"), _v2("ch03_v2_set1a.json"))}).json()
    assert {a["id"] for a in body["accepted"]} == {"Q-C01-0001", "Q-C03-0001"}
    assert pool.get(CERT, "Q-C03-0001").domain == "2.0"


def test_text_is_cleaned_before_it_is_stored(client):
    item = _v2("ch01_v2_set1a.json")
    item["stem"] = item["stem"].replace("online store", "online‮ store​")
    client.post(f"{API}/imports", json={"text": _reply(item)})
    assert "‮" not in pool.get(CERT, "Q-C01-0001").stem and "online store" in pool.get(CERT, "Q-C01-0001").stem


@pytest.mark.parametrize("text, message", [
    ("not json at all", "isn't valid JSON"),
    ("[1, 2]", "must be a JSON object"),
    (_reply(_v2("ch01_v2_set1a.json"), format="something-else"), "isn't a question file"),
    (_reply(_v2("ch01_v2_set1a.json"), format_version=2), "isn't a question file"),
    (_reply(_v2("ch01_v2_set1a.json"), cert="other-cert"), "not the certification you're studying"),
    (_reply(_v2("ch01_v2_set1a.json"), notes="hi"), "Unexpected fields"),
    (_reply(), "no questions"),
    (_reply(*[_v2("ch01_v2_set1a.json")] * 51), "at most 50"),
], ids=["not-json", "array", "wrong-format", "wrong-version", "other-cert", "extra-field", "empty", "too-many"])
def test_unusable_replies_are_refused_with_a_reason(client, text, message):
    r = client.post(f"{API}/imports", json={"text": text})
    assert r.status_code == 422 and message in r.json()["detail"]
    assert pool.load(CERT, "C01") == []


def test_bad_questions_are_rejected_with_reasons_and_a_repair_prompt(client):
    good = _v2("ch01_v2_set1a.json")
    long_answer = copy.deepcopy(_v2("ch01_v2_set1a.json", 1))
    for o in long_answer["options"]:
        if o["key"] in long_answer["answer"]:
            o["text"] += " that sends traffic from a very large number of separate devices at the same time"
    extra_field = copy.deepcopy(_v2("ch01_v2_set1a.json", 2))
    extra_field["source"] = "an exam dump"
    extra_field["options"][0]["hint"] = "pick me"
    other_cert = copy.deepcopy(_v2("ch01_v2_set1a.json", 3))
    other_cert["objectives"] = ["C99-01"]
    body = client.post(f"{API}/imports", json={"text": _reply(good, long_answer, extra_field, other_cert)}).json()
    assert [a["index"] for a in body["accepted"]] == [0]
    rejected = {r["index"]: r for r in body["rejected"]}
    assert set(rejected) == {1, 2, 3}
    assert any("longer than the distractors" in p or "longest" in p for p in rejected[1]["problems"])
    assert 'unknown field "source"' in rejected[2]["problems"] and 'unknown field "hint" in options[0]' in rejected[2]["problems"]
    assert any("isn't in CCST Cybersecurity" in p for p in rejected[3]["problems"])
    repair = body["repair_prompt"]
    assert "rejected 3 of them" in repair and '"format": "certprep-questions"' in repair
    assert "unknown field \"source\"" in repair and long_answer["stem"] in repair
    assert len(pool.load(CERT, "C01")) == 1


def test_a_question_rejected_early_still_gets_every_problem_listed(client):
    item = copy.deepcopy(_v2("ch01_v2_set1a.json"))
    item["hint"] = "x"                                            # unknown field: rejected before the checks
    item["explanation"] = "Option A is right because it is distributed."  # also refers to a letter
    body = client.post(f"{API}/imports", json={"text": _reply(item)}).json()
    (r,) = body["rejected"]
    assert 'unknown field "hint"' in r["problems"]
    assert any("option letter" in p for p in r["problems"])      # found by the dry-run checks, in the same round
    assert pool.load(CERT, "C01") == []


def test_import_needs_the_page_token():
    from certprep.main import app
    bare = TestClient(app, base_url="http://127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"})
    assert bare.post(f"{API}/imports", json={"text": _reply(_v2("ch01_v2_set1a.json"))}).status_code == 403
    assert pool.load(CERT, "C01") == []


def test_objectives_endpoint_reports_counts_and_status(client):
    client.post(f"{API}/imports", json={"text": _reply(_v2("ch01_v2_set1a.json"))})
    rows = {r["id"]: r for r in client.get(f"{API}/objectives").json()}
    assert rows["C01-01"]["questions"] == 1 and rows["C01-01"]["angles"] == ["symptom-to-attack"]
    assert rows["C01-02"]["questions"] == 0 and rows["C01-02"]["status"] == "New"
    from certprep.objectives import load_sections
    assert len(rows) == sum(len(s.objectives) for s in load_sections(CERT))  # one row per objective
