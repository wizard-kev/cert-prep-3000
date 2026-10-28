"""v2 P7: Focus mode (plan 7.2), with fuzz tests for SR-2 (pasted text), SR-3 (files reached only through
the certification's index) and SR-7 (results reveal only IDs, names and question counts)."""
import json
import pathlib
import random
import shutil
import string
import time

import pytest
from fastapi.testclient import TestClient

from certprep import certs, focus, generator, objectives, pool, security, sessions, tracker
from certprep.config import PROJECT_ROOT, settings

CERT = "ccst-cyber"
API = f"/api/certs/{CERT}"
AUTHORED = PROJECT_ROOT / "data" / "certs" / CERT / "imports"
NAME = certs.get_cert(CERT).name


@pytest.fixture(autouse=True)
def fresh_data():
    """C01 has two questions per objective; every other section is empty. No progress."""
    assert "certprep-test-" in str(settings.data_dir)
    for f in (certs.cert_dir(CERT) / "questions").glob("*.json"):
        f.unlink()
    tracker.reset(CERT)
    for name in ("ch01_claude.json", "ch01_v2_set1a.json"):
        items = json.loads((AUTHORED / name).read_text(encoding="utf-8"))["questions"]
        generator.import_items(CERT, "C01", items, "claude", "test", seed=1, strict=False)
    yield


@pytest.fixture
def client():
    from certprep.main import app
    return TestClient(app, base_url="http://127.0.0.1:8000",
                      headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": security.CSRF_TOKEN})


def _match(client, text):
    r = client.post(f"{API}/focus/match", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()["lines"]


def _ids(line):
    return [m["objective"] for m in line["matches"]]


# ---- splitting the pasted text (SR-2) ----------------------------------------

def test_lines_lose_their_list_markers():
    text = "- Smurf\n* SYN flood\n1. Botnet\n2) Ransomware\na. Tailgating\n• Phishing • Vishing\n[ ] Smishing\n\n   \n## C01-02"
    assert focus.split_lines(text) == ["Smurf", "SYN flood", "Botnet", "Ransomware", "Tailgating", "Phishing",
                                       "Vishing", "Smishing", "C01-02"]
    assert focus.split_lines("1.2 Explain common threats") == ["1.2 Explain common threats"]  # a reference, not a list number


def test_pasted_text_is_cleaned_and_capped():
    assert focus.split_lines("Smu\u200brf\x00\n\u202eSYN flood") == ["Smurf", "SYN flood"]
    assert focus.split_lines("Ｓｍｕｒｆ") == ["Smurf"]  # fullwidth -> ASCII (NFKC)
    with pytest.raises(focus.FocusError, match="at most 60"):
        focus.split_lines("\n".join(f"line {i}" for i in range(61)))
    with pytest.raises(focus.FocusError, match="at least one"):
        focus.split_lines(" \n - \n * ")
    with pytest.raises(ValueError):
        focus.split_lines("x" * (focus.MAX_CHARS + 1))
    with pytest.raises(ValueError):
        focus.split_lines("ﷺ" * 500)  # 500 characters that NFKC expands past the cap


# ---- matching and its messages (plan 7.2) ---------------------------------

def test_objective_ids_names_and_messages(client):
    lines = _match(client, "C01-09\nC01-99 not real\nSmurf attack\nBake a chocolate cake\nDHCP snooping")
    assert _ids(lines[0]) == ["C01-09"] and lines[0]["matches"][0]["confidence"] == "exact"
    assert lines[1]["status"] == "not-known" and lines[1]["unknown_ids"] == ["C01-99"]
    assert lines[1]["message"] == f"This objective is not in the objective list for {NAME}."
    assert _ids(lines[2]) == ["C01-09"] and lines[2]["matches"][0]["confidence"] == "high"
    assert lines[3]["status"] == "not-known" and lines[3]["matches"] == []
    assert lines[3]["message"] == f"This objective is not in the objective list for {NAME}."
    dhcp = lines[4]["matches"][0]
    assert dhcp["objective"] == "C01-34" and dhcp["questions"] >= 1 and "note" not in dhcp


def test_an_objective_without_questions_says_so(client):
    (line,) = _match(client, "Windows Defender Firewall")  # C06: no questions in this test pool
    m = line["matches"][0]
    assert m["objective"] == "C06-01" and m["questions"] == 0
    assert m["note"] == "No questions exist for this objective yet."
    prompt = client.get(f"{API}/prompts/questions?objective=C06-01&per_objective=2").json()
    assert len(prompt["targets"]) == 2 and "C06-01" in prompt["prompt"]


def test_a_topic_list_is_matched_topic_by_topic(client):
    (line,) = _match(client, "1.2 Explain common threats: ransomware, DoS, botnets, social engineering "
                             "(tailgating, spear phishing, made-up-thing)")
    ids = _ids(line)
    assert {"C01-20", "C01-01", "C01-02", "C01-39", "C01-46", "C01-44"} <= set(ids)
    assert len(ids) == len(set(ids))
    vias = {m["objective"]: m["via"] for m in line["matches"]}
    assert vias["C01-46"] == "tailgating"


def test_values_in_parentheses_need_a_strong_match(client):
    (line,) = _match(client, "4.3 Explain risk management: risk levels (low, medium, high)")
    assert "C08-08" in _ids(line)
    names = [m["name"].lower() for m in line["matches"]]
    assert not any(n.startswith("low-level") for n in names)


def test_acronyms_work_both_ways(client):
    lines = _match(client, "man in the middle\nMulti-factor authentication\nMFA")
    assert _ids(lines[0]) == ["C01-12"]  # On-path attack (formerly MitM)
    assert _ids(lines[1]) == ["C04-04"] and _ids(lines[2]) == ["C04-04"]


def test_domain_headings_and_long_lines(client):
    lines = _match(client, "1.0 Essential Security Principles\n" + "word " * 70)
    assert lines[0]["status"] == "heading" and "skipped" in lines[0]["message"]
    assert lines[1]["status"] == "too-long" and lines[1]["matches"] == []


def test_weak_matches_come_with_alternatives(client):
    (line,) = _match(client, "RAID levels")
    assert all(m["confidence"] == "low" for m in line["matches"])  # the preview leaves weak ones unticked


@pytest.fixture
def ref_cert():
    """A second certification whose objective file carries official reference numbers (fifth column)."""
    folder = settings.certs_dir / "ref-cert"
    (folder / "objectives").mkdir(parents=True)
    (folder / "questions").mkdir()
    (folder / "cert.json").write_text(json.dumps({
        "format_version": 1, "id": "ref-cert", "name": "Reference Test Cert", "short_name": "Ref",
        "exam": {"minutes": {}, "question_count": {}, "passing_score": {}},
        "domains": [{"id": "4.0", "name": "Risk", "weight": 1}],
        "sections": [{"code": "R01", "name": "Risk", "domain": "4.0"}]}), encoding="utf-8")
    (folder / "objectives" / "R01.md").write_text(
        "# Ref | Risk\n\n## A. Threat intelligence\n\n| ID | Objective | Core idea | Discriminator | Ref |\n|---|---|---|---|---|\n"
        "| R01-01 | Vulnerability databases | Public lists of known flaws | Lists, not scanners | 4.2 |\n"
        "| R01-02 | Threat feeds | Automated indicator sharing | Machine-readable | 4.2.1 |\n"
        "| R01-03 | Risk ranking | Ordering risks | Likelihood x impact | 4.3 |\n", encoding="utf-8")
    certs.reload()
    yield "ref-cert"
    shutil.rmtree(folder)
    certs.reload()


def test_reference_numbers_select_every_objective_under_them(client, ref_cert):
    r = client.post(f"/api/certs/{ref_cert}/focus/match", json={"text": "4.2 Threat intelligence techniques\n4.3\n4.9 Nothing"})
    lines = r.json()["lines"]
    assert _ids(lines[0]) == ["R01-01", "R01-02"] and lines[0]["matches"][0]["how"] == "reference"
    assert _ids(lines[1]) == ["R01-03"]
    assert lines[2]["status"] == "not-known" and "Reference Test Cert" in lines[2]["message"]
    assert objectives.load_section(ref_cert, "R01").objectives["R01-02"].ref == "4.2.1"


# ---- focus sessions ---------------------------------------------------------

def test_focus_session_serves_only_the_chosen_objectives(client):
    r = client.post(f"{API}/sessions", json={"mode": "focus", "objectives": ["C01-09", "C01-10", "C01-11"], "count": 4})
    assert r.status_code == 201, r.text
    s = r.json()
    objs = [pool.get(CERT, q["id"]).objectives[0] for q in s["questions"]]
    assert s["mode"] == "focus" and len(objs) == 4 and set(objs) <= {"C01-09", "C01-10", "C01-11"}
    assert len(set(objs)) == 3  # spread across every objective before doubling up
    assert not s["deferred"]


def test_focus_takes_weak_objectives_first():
    weak = [q for q in pool.active(CERT) if q.objectives[0] == "C01-05"][0]
    tracker.create_session("f" * 16, CERT, "practice", ["C01"], [weak.id], None)
    tracker.record_attempt("f" * 16, CERT, weak, [next(o.key for o in weak.options if o.key not in weak.answer)], 5, False)
    for seed in range(10):
        (q,) = sessions.select_focus(CERT, ["C01-04", "C01-05", "C01-06"], 1, random.Random(seed))
        assert q.objectives[0] == "C01-05"


@pytest.mark.parametrize("body, status", [
    ({"mode": "focus"}, 422),
    ({"mode": "focus", "objectives": []}, 422),
    ({"mode": "focus", "objectives": ["C01-99"]}, 422),
    ({"mode": "focus", "objectives": ["../C01-01"]}, 422),
    ({"mode": "focus", "objectives": ["C06-01"]}, 409),  # matched, but no questions
    ({"mode": "practice"}, 422),
    ({"mode": "focus", "objectives": ["C01-01"] * 301}, 422),
], ids=["no-objectives", "empty", "unknown", "traversal", "no-questions", "practice-no-sections", "too-many"])
def test_focus_session_rejects_bad_requests(client, body, status):
    assert client.post(f"{API}/sessions", json=body).status_code == status


def test_focus_match_needs_the_token_and_limits_input():
    from certprep.main import app
    bare = TestClient(app, base_url="http://127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"})
    assert bare.post(f"{API}/focus/match", json={"text": "Smurf"}).status_code == 403
    c = TestClient(app, base_url="http://127.0.0.1:8000",
                   headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": security.CSRF_TOKEN})
    assert c.post(f"{API}/focus/match", json={"text": "x" * (focus.MAX_CHARS + 1)}).status_code == 422
    r = c.post(f"{API}/focus/match", json={"text": "\n".join("Smurf" for _ in range(61))})
    assert r.status_code == 422 and "at most 60" in r.json()["detail"]
    assert c.post(f"{API}/focus/match", json={"text": "   "}).status_code == 422
    assert c.post(f"{API}/focus/match", json={"text": 5}).status_code == 422


# ---- fuzzing (SR-2, SR-3, SR-7) -------------------------------------------

LINE_KEYS = {"line", "text", "status", "message", "matches", "candidates", "unknown_ids"}
MATCH_KEYS = {"objective", "name", "section", "questions", "how", "confidence", "via", "note"}
CANDIDATE_KEYS = {"objective", "name", "section", "questions"}
NASTY = ["../../../../etc/passwd", "..\\..\\Windows\\win.ini", "C:\\Windows\\System32\\drivers\\etc\\hosts",
         "objectives/C01.md", "questions/C01.json", "%2e%2e%2fcert.json", "file:///etc/shadow", "\\\\server\\share\\x",
         "(((((a*)*)*)*)*$", "(a|aa)+$" + "a" * 40, "'; DROP TABLE attempts; --", "<script>alert(1)</script>",
         "{{7*7}}", "${jndi:ldap://x}", "\x00\x01\x1b[31m", "\u202e\u200b\u2066", "ﷺ" * 3, "C01-01" * 40,
         "1.2.3.4.5.6", "C01-01, C01-02; C99-99", "a" * 299, "🙂" * 50]


def _random_text(rng: random.Random) -> str:
    pools = [string.printable, "".join(chr(c) for c in range(0x20, 0x2FF)), "\u200b\u202e\u2066\ufeff\x00\x07\x1b",
             "-*•·1.2)a( ):;,", "".join(chr(c) for c in range(0x4E00, 0x4E40))]
    lines = []
    for _ in range(rng.randint(1, 70)):
        if rng.random() < 0.3:
            lines.append(rng.choice(NASTY))
        else:
            src = rng.choice(pools)
            lines.append("".join(rng.choice(src) for _ in range(rng.randint(0, 120))))
    return rng.choice(["\n", "\r\n", "\n\n"]).join(lines)


def _check_shape(body: dict):
    assert set(body) == {"cert", "cert_name", "lines"}
    for line in body["lines"]:
        assert set(line) <= LINE_KEYS
        for m in line["matches"]:
            assert set(m) <= MATCH_KEYS
        for c in line["candidates"]:
            assert set(c) == CANDIDATE_KEYS


def test_fuzzed_text_never_breaks_the_matcher(client):
    """SR-2: any pasted text gives a result or a clear refusal, quickly, and never a server error."""
    rng = random.Random(7)
    for i in range(200):
        text = _random_text(rng)
        started = time.perf_counter()
        r = client.post(f"{API}/focus/match", json={"text": text[:focus.MAX_CHARS]})
        assert time.perf_counter() - started < 3, i
        assert r.status_code in (200, 422), (i, r.status_code, r.text[:200])
        if r.status_code == 200:
            _check_shape(r.json())
            for line in r.json()["lines"]:
                assert all(ord(ch) >= 0x20 and ch not in "\u200b\u202e\u2066\ufeff" for ch in line["text"])


def test_matching_reads_only_this_certifications_objective_and_question_files(client, monkeypatch):
    """SR-3: whatever the text says, only files inside the certification's objectives/ and questions/
    folders (and its cert.json) are read."""
    read = []
    real_read_text = pathlib.Path.read_text

    def spy(self, *a, **k):
        read.append(self.resolve())
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", spy)
    certs.reload()  # make the objective files load again, through the spy
    folder = certs.cert_dir(CERT).resolve()
    allowed = (folder / "objectives", folder / "questions")
    for text in NASTY + ["\n".join(NASTY)]:
        assert client.post(f"{API}/focus/match", json={"text": text}).status_code in (200, 422)
    assert read, "the spy saw no reads"
    for p in read:
        assert p == folder / "cert.json" or any(p.is_relative_to(a) for a in allowed), p


def test_results_reveal_only_ids_names_and_counts(client):
    """SR-7: no objective file text beyond the names, no file names or paths."""
    text = "\n".join(["Smurf", "DHCP snooping", "C01-12", "1.2 threats: ransomware, botnets, tailgating", "RAID levels"] + NASTY)
    body = client.post(f"{API}/focus/match", json={"text": text}).json()
    _check_shape(body)
    raw = json.dumps(body)
    section = objectives.load_section(CERT, "C01")
    pasted = text.lower()
    for o in section.objectives.values():
        for hidden in (o.core_idea, o.discriminator):
            if len(hidden) > 25 and hidden.lower() not in pasted:
                assert hidden not in raw, hidden
    for leak in (str(settings.data_dir), "objectives/", "objectives\\\\", ".md", "| ID |", "Core idea"):
        assert leak not in raw.replace("objectives/C01.md", ""), leak  # (the pasted text itself may say it)
