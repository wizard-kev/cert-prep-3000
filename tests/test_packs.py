"""v2 P9: certification packs (plan section 9, SR-5) and the question-bank health page (plan 5.2)."""
import hashlib
import io
import json
import random
import shutil
import stat
import zipfile

import pytest
from fastapi.testclient import TestClient

from certprep import certs, generator, objectives, packs, pool, security, tracker
from certprep.config import PROJECT_ROOT, settings

CERT = "ccst-cyber"
AUTHORED = PROJECT_ROOT / "data" / "certs" / CERT / "imports"
ZIP = {"Content-Type": "application/zip"}


@pytest.fixture(autouse=True)
def fresh():
    assert "certprep-test-" in str(settings.data_dir)
    for f in (certs.cert_dir(CERT) / "questions").glob("*.json"):
        f.unlink()
    tracker.reset(CERT)
    for name in ("ch01_claude.json", "ch01_v2_set1a.json"):
        items = json.loads((AUTHORED / name).read_text(encoding="utf-8"))["questions"]
        generator.import_items(CERT, "C01", items, "claude", "test", seed=1, strict=False)
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


def _upload(client, body: bytes, **params):
    return client.post("/api/packs/import", params=params, content=body, headers=ZIP)


# ---- round trip --------------------------------------------------------------

def test_a_ccst_pack_round_trips(client):
    qs = pool.active(CERT, ["C01"])
    pool.mark_seen(CERT, qs[0].id, "2026-10-01T00:00:00+00:00")       # answered: travels as Unreviewed
    pool.validate(CERT, qs[1].id, "2026-10-01T00:00:00+00:00")        # validated: travels as Validated
    pool.retire(CERT, qs[2].id, "Reported by user: ambiguous")          # retired: left out by default
    pool.dispute(CERT, qs[3].id, "ambiguous", "2026-10-01T00:00:00+00:00")  # disputed: never travels
    r = client.get(f"/api/certs/{CERT}/pack")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"] and "ccst-cyber-pack-" in r.headers["content-disposition"]
    check = _upload(client, r.content).json()
    assert check["suggested_id"] == "ccst-cyber-2" and check["suggested_short_name"] == "CCST Cybersecurity (copy)"
    assert check["pack"]["sections"] == 13 and check["pack"]["questions"] == len(qs) - 2 and check["pack"]["retired"] == 0
    assert certs.cert_ids() == [CERT]  # checking wrote nothing

    done = _upload(client, r.content, check="false", id="ccst-copy", short_name="CCST copy")
    assert done.status_code == 200 and done.json() == {"cert": "ccst-copy"}
    a, b = certs.get_cert(CERT).model_dump(), certs.get_cert("ccst-copy").model_dump()
    assert b.pop("id") == "ccst-copy" and b.pop("short_name") == "CCST copy"
    a.pop("id"), a.pop("short_name")
    assert a == b
    for s in objectives.load_sections(CERT):
        assert objectives.load_section("ccst-copy", s.code).text == s.text
    old = {q.id: q for q in pool.load(CERT, "C01")}
    new = {q.id: q for q in pool.load("ccst-copy", "C01")}
    assert set(new) == {q.id for q in qs} - {qs[2].id, qs[3].id}
    for qid, q in new.items():
        expected = old[qid].model_dump()
        expected["seen_at"] = None
        if expected["status"] == "passive":
            expected["status"] = "unreviewed"
        assert q.model_dump() == expected, qid
    assert new[qs[0].id].status == "unreviewed" and new[qs[1].id].status == "validated"
    # The copy is a working certification with no progress.
    s = client.post("/api/certs/ccst-copy/sessions", json={"mode": "practice", "sections": ["C01"], "count": 3})
    assert s.status_code == 201 and tracker.all_attempts("ccst-copy") == []


def test_retired_questions_can_travel_too(client):
    q = pool.active(CERT, ["C01"])[0]
    pool.retire(CERT, q.id, "Superseded by a rewrite")
    pack = packs.check_pack(packs.export_pack(CERT, include_retired=True))
    assert pack.summary()["retired"] == 1
    assert client.get(f"/api/certs/{CERT}/pack?retired=true").status_code == 200


def test_import_never_overwrites(client):
    body = client.get(f"/api/certs/{CERT}/pack").content
    for taken in (CERT, "ccst-cyber"):
        r = _upload(client, body, check="false", id=taken)
        assert r.status_code == 422 and "already exists" in r.json()["detail"]
    assert _upload(client, body, check="false").status_code == 422                  # no id chosen
    assert _upload(client, body, check="false", id="../evil").status_code == 422     # pattern-checked
    assert _upload(client, body, check="false", id="ok-id", short_name="x" * 61).status_code == 422
    assert certs.cert_ids() == [CERT]


# ---- the upload route (SR-1, SR-5) ---------------------------------------------

def test_upload_route_rules(client):
    from certprep.main import app
    body = client.get(f"/api/certs/{CERT}/pack").content
    bare = TestClient(app, base_url="http://127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"})
    assert bare.post("/api/packs/import", content=body, headers=ZIP).status_code == 403          # token still required
    assert client.post("/api/packs/import", content=body, headers={"Content-Type": "application/json"}).status_code == 415
    assert client.post("/api/certs/ccst-cyber/imports", content=body, headers=ZIP).status_code == 415  # zip only here
    big = b"x" * (security.MAX_PACK_BYTES + 1)
    assert client.post("/api/packs/import", content=big, headers=ZIP).status_code == 413
    assert client.post("/api/certs/ccst-cyber/imports", content=b'{"text": "' + b"x" * 1_000_001 + b'"}',
                       headers={"Content-Type": "application/json"}).status_code == 413  # JSON limit unchanged


# ---- crafted packs (SR-5) ------------------------------------------------------------

def _files() -> dict[str, bytes]:
    """The files of a valid pack (without its manifest)."""
    with zipfile.ZipFile(io.BytesIO(packs.export_pack(CERT))) as z:
        return {n: z.read(n) for n in z.namelist() if n != "manifest.json"}


def _manifest(files: dict[str, bytes], **override) -> bytes:
    m = {"format": "certprep-pack", "format_version": 1, "cert": CERT, "name": "x", "short_name": "x",
         "created": "2026-10-27T00:00:00+00:00", "app": "test", "includes_retired": False,
         "files": [{"path": p, "sha256": hashlib.sha256(b).hexdigest(), "size": len(b)} for p, b in files.items()]}
    m.update(override)
    return json.dumps(m).encode()


def _zip(entries: list[tuple], method=zipfile.ZIP_DEFLATED) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", method) as z:
        for entry in entries:
            name, body = entry[0], entry[1]
            info = name if isinstance(name, zipfile.ZipInfo) else zipfile.ZipInfo(name)
            info.compress_type = method
            z.writestr(info, body)
    return out.getvalue()


def _encrypted(data: bytes, name: bytes) -> bytes:
    """Set the "encrypted" bit on one entry's central-directory record (zipfile won't write it)."""
    out = bytearray(data)
    at = out.find(b"PK\x01\x02")
    while at != -1:
        name_len = int.from_bytes(out[at + 28:at + 30], "little")
        if bytes(out[at + 46:at + 46 + name_len]) == name:
            flags = int.from_bytes(out[at + 8:at + 10], "little") | 0x1
            out[at + 8:at + 10] = flags.to_bytes(2, "little")
        at = out.find(b"PK\x01\x02", at + 4)
    return bytes(out)


def _pack(files: dict[str, bytes], extra: list[tuple] = (), manifest: bytes | None = None) -> bytes:
    return _zip([("manifest.json", manifest or _manifest(files)), *files.items(), *extra])


def _refused(client, body: bytes, phrase: str):
    r = _upload(client, body)
    assert r.status_code == 422, r.text
    assert phrase in r.json()["detail"], r.json()["detail"]
    assert certs.cert_ids() == [CERT] and not list(settings.certs_dir.glob(".installing-*"))


def test_a_valid_handmade_pack_passes(client):
    assert _upload(client, _pack(_files())).status_code == 200


@pytest.mark.parametrize("name", ["evil.txt", "../cert.json", "/etc/cert.json", "C:/x/cert.json", "objectives/../../x.md",
                                  "objectives/c01.md", "questions/C01.json.exe", "objectives/sub/C01.md", "Objectives/C01.md",
                                  "objectives/C01.md/", "imports/claude.json"])
def test_unexpected_names_are_refused(client, name):
    _refused(client, _pack(_files(), [(name, b"{}")]), "Unexpected file")


def test_links_encryption_and_duplicates_are_refused(client):
    files = _files()
    link = zipfile.ZipInfo("objectives/C99.md")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    _refused(client, _pack(files, [(link, b"/etc/passwd")]), "is a link")
    _refused(client, _encrypted(_pack(files, [("objectives/C98.md", b"x")]), b"objectives/C98.md"), "encrypted")
    with pytest.warns(UserWarning):  # zipfile itself warns about the duplicate
        dup = _pack(files, [("cert.json", files["cert.json"])])
    _refused(client, dup, "appears twice")


def test_zip_bombs_and_oversized_files_are_refused(client):
    files = _files()
    bomb = dict(files)
    bomb["questions/C02.json"] = b" " * 15_000_000  # compresses about 1000:1
    _refused(client, _pack(bomb), "compressed suspiciously well")
    big = dict(files)
    big["cert.json"] = random.Random(1).randbytes(packs.LIMITS["cert.json"] + 1)
    _refused(client, _pack(big), "larger than")
    many = [(f"objectives/{a}{b}{n:02d}.md", b"x") for a in "ABCDEFGHIJ" for b in "ABCDEFGHIJ" for n in range(21)]
    _refused(client, _zip(many), "more than 2000 files")
    _refused(client, b"PK\x03\x04 not really a zip", "isn't a zip file")
    _refused(client, b"", "isn't a zip file")


def test_manifest_and_checksums_are_enforced(client):
    files = _files()
    _refused(client, _pack(files, manifest=_manifest(files, format="something")), "isn't a certification pack")
    _refused(client, _pack(files, manifest=_manifest(files, format_version=2)), "version 2")
    _refused(client, _pack(files, manifest=_manifest(files, script="x")), "Unexpected fields")
    tampered = dict(files)
    tampered["objectives/C01.md"] = files["objectives/C01.md"] + b"\n| C01-99 | Planted | x | y |\n"
    _refused(client, _pack(tampered, manifest=_manifest(files)), "checksum")
    missing = dict(files)
    del missing["objectives/C02.md"]
    _refused(client, _pack(missing, manifest=_manifest(files)), "don't match its manifest")
    _refused(client, _pack(missing), "missing objectives/C02.md")
    _refused(client, _zip([("cert.json", files["cert.json"])]), "needs manifest.json")


@pytest.mark.parametrize("change, phrase", [
    (lambda f: f.update({"cert.json": b"\xff\xfe not utf-8"}), "isn't valid UTF-8"),
    (lambda f: f.update({"cert.json": json.dumps({**json.loads(f["cert.json"]), "hook": "x"}).encode()}), "cert.json isn't valid"),
    (lambda f: f.update({"cert.json": json.dumps({**json.loads(f["cert.json"]), "id": "other"}).encode()}), "different certifications"),
    (lambda f: f.update({"objectives/C01.md": f["objectives/C01.md"].replace(b"| DoS / DDoS |", "| DoS\u202e / DDoS |".encode())}),
     "control or invisible"),
    (lambda f: f.update({"objectives/C01.md": b"# nothing here\n"}), "no objective rows"),
    (lambda f: f.update({"questions/C01.json": b"[1, 2]"}), "isn't a question file"),
    (lambda f: f.update({"questions/C01.json": json.dumps({"section": "C02", "questions": []}).encode()}), "isn't a question file"),
    (lambda f: f.update({"questions/C01.json": f["questions/C01.json"].replace(b'"C01-01"', b'"C01-77"', 1)}), "doesn't define"),
    (lambda f: f.update({"questions/C02.json": f["questions/C01.json"].replace(b'"section": "C01"', b'"section": "C02"', 1)}),
     "wrong file"),
    (lambda f: f.update({"questions/C01.json": f["questions/C01.json"].replace(b'"status": "unreviewed"', b'"status": "disputed"', 1)}),
     "disputed"),
    (lambda f: f.update({"objectives/Z99.md": f["objectives/C01.md"]}), "sections cert.json doesn't list"),
], ids=["bad-utf8", "cert-extra-field", "cert-other-id", "bidi-in-objective", "empty-objectives", "questions-not-object",
        "questions-wrong-section", "unknown-objective", "question-wrong-file", "disputed-question", "stray-section"])
def test_every_file_is_validated(client, change, phrase):
    files = _files()
    change(files)
    _refused(client, _pack(files), phrase)


def test_mutated_packs_never_break_the_import(client):
    """Random byte flips in a valid pack: always a summary or a clear refusal, never a server error."""
    good = bytearray(_pack(_files()))
    rng = random.Random(3)
    for _ in range(60):
        body = bytearray(good)
        for _ in range(rng.randint(1, 20)):
            body[rng.randrange(len(body))] = rng.randrange(256)
        r = _upload(client, bytes(body))
        assert r.status_code in (200, 422), r.text[:200]
    assert certs.cert_ids() == [CERT]


# ---- question-bank health -------------------------------------------------------------

def test_health_reports_coverage_and_cue_bands(client):
    h = client.get(f"/api/certs/{CERT}/health").json()
    c01 = next(s for s in h["sections"] if s["code"] == "C01")
    assert c01["active"] == len(pool.active(CERT, ["C01"])) and c01["objectives"] == 48
    c02 = next(s for s in h["sections"] if s["code"] == "C02")
    assert c02["active"] == 0 and c02["ok"] is False and len(c02["below_minimum"]) == c02["objectives"]
    keys = {b["key"] for b in h["bands"]}
    assert keys == {"answer_longest", "answer_shortest", "multi_answers_are_longest", "absolute_only_in_distractors",
                    "answer_echoes_stem_most"}
    assert h["audit"]["questions"] == c01["active"] and h["minimum"] == 2
    assert client.get("/api/certs/nope/health").status_code == 404
