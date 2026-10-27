"""v2 security baseline: Host allowlist, Origin and CSRF checks, body limits, headers, text cleaning."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from certprep import security
from certprep.main import app

BASE = "http://127.0.0.1:8000"
GOOD = {"Origin": BASE, "X-CSRF-Token": security.CSRF_TOKEN}
NEW_SESSION = "/api/certs/ccst-cyber/sessions"
BODY = {"mode": "drill", "sections": ["C01"], "count": 1}
STATIC = Path(security.__file__).parent / "static"


@pytest.fixture
def client():
    return TestClient(app, base_url=BASE)


# ---- SR-1: Host (DNS rebinding) ---------------------------------------------

@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.1:8000", "localhost", "localhost:8002", "LOCALHOST:8000"])
def test_local_host_names_are_served(client, host):
    assert client.get("/api/certs", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8000", "127.0.0.1.evil.example", "localhost.evil.example",
                                  "192.168.1.20:8000", "[::1]:8000", "localhost:abc", "localhost:99999", ""])
def test_other_host_names_are_refused(client, host):
    r = client.get("/api/certs", headers={"Host": host})
    assert r.status_code == 403 and "127.0.0.1 or localhost" in r.json()["detail"]


def test_the_page_is_refused_to_a_rebinding_domain(client):
    assert client.get("/", headers={"Host": "attacker.example:8000"}).status_code == 403


# ---- SR-1: Origin and CSRF token on changes --------------------------------

def test_change_with_origin_and_token_is_allowed(client):
    assert client.post(NEW_SESSION, json=BODY, headers=GOOD).status_code in (201, 409)  # 409 = no questions yet


@pytest.mark.parametrize("headers", [
    {},                                                              # nothing: a plain cross-site form post
    {"Origin": BASE},                                                # no token
    {"Origin": BASE, "X-CSRF-Token": "guess"},                       # wrong token
    {"X-CSRF-Token": security.CSRF_TOKEN},                           # no Origin
    {"Origin": "http://evil.example", "X-CSRF-Token": security.CSRF_TOKEN},
    {"Origin": "null", "X-CSRF-Token": security.CSRF_TOKEN},
    {"Origin": "http://localhost:8000", "X-CSRF-Token": security.CSRF_TOKEN},   # not the same origin as the Host
    {"Origin": "https://127.0.0.1:8000", "X-CSRF-Token": security.CSRF_TOKEN},  # different scheme
    {**GOOD, "Sec-Fetch-Site": "cross-site"},
    {**GOOD, "Sec-Fetch-Site": "same-site"},
])
def test_change_without_proof_of_origin_is_refused(client, headers):
    r = client.post(NEW_SESSION, json=BODY, headers=headers)
    assert r.status_code == 403


def test_stale_token_message_tells_the_user_to_reload(client):
    r = client.post(NEW_SESSION, json=BODY, headers={"Origin": BASE, "X-CSRF-Token": "from-an-old-launch"})
    assert r.json()["detail"] == security.STALE_PAGE


def test_every_change_route_is_protected(client):
    """No POST route may skip the check (a new route added later is covered automatically)."""
    posts = [r.path for r in app.routes if "POST" in getattr(r, "methods", set())]
    assert len(posts) >= 8
    for path in posts:
        concrete = re.sub(r"\{cert_id\}", "ccst-cyber", path)
        concrete = re.sub(r"\{question_id\}", "Q-C01-0001", concrete)
        concrete = re.sub(r"\{session_id\}", "0" * 16, concrete)
        assert client.post(concrete, json={}, headers={"Origin": BASE}).status_code == 403, path


def test_reads_need_no_token(client):
    assert client.get("/api/certs").status_code == 200


# ---- SR-2: body limits ------------------------------------------------------

def test_non_json_body_is_refused(client):
    r = client.post(NEW_SESSION, content=b"mode=drill", headers={**GOOD, "Content-Type": "text/plain"})
    assert r.status_code == 415
    r = client.post(NEW_SESSION, content=b"mode=drill", headers={**GOOD, "Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415


def test_oversized_body_is_refused(client):
    big = b'{"note": "' + b"x" * (security.MAX_BODY_BYTES + 10) + b'"}'
    r = client.post(NEW_SESSION, content=big, headers={**GOOD, "Content-Type": "application/json"})
    assert r.status_code == 413


def test_chunked_body_is_refused(client):
    def chunks():
        yield b'{"mode": "drill", "sections": ["C01"]}'
    r = client.post(NEW_SESSION, content=chunks(), headers={**GOOD, "Content-Type": "application/json"})
    assert r.status_code == 411


# ---- SR-4: headers and the page --------------------------------------------

@pytest.mark.parametrize("path", ["/", "/api/certs", "/static/app.js", "/static/style.css", "/api/nope"])
def test_security_headers_on_every_response(client, path):
    r = client.get(path)
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"


def test_headers_also_on_refused_requests(client):
    r = client.get("/api/certs", headers={"Host": "evil.example"})
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_page_carries_the_token_and_is_not_cached(client):
    r = client.get("/")
    assert f'<meta name="csrf-token" content="{security.CSRF_TOKEN}">' in r.text
    assert "__CSRF_TOKEN__" not in r.text and r.headers["cache-control"] == "no-store"
    assert client.get("/api/certs").headers["cache-control"] == "no-store"


def test_static_files_are_revalidated_so_updates_are_never_mixed(client):
    r = client.get("/static/app.js")
    assert r.headers["cache-control"] == "no-cache" and r.headers.get("etag")
    assert client.get("/static/app.js", headers={"If-None-Match": r.headers["etag"]}).status_code == 304


def test_api_schema_and_docs_are_not_served(client):
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 404


def test_ui_never_builds_html_from_strings():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "setTimeout(\"",
                "setTimeout('"):
        assert bad not in js.replace("never innerHTML", ""), bad


def test_page_has_no_inline_script_style_or_handlers():
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    assert re.findall(r"<script\b[^>]*>", page) == ['<script src="/static/app.js">']
    assert not re.search(r"\sstyle\s*=", page) and not re.search(r"<style\b", page)
    assert not re.search(r"\son[a-z]+\s*=", page)


# ---- SR-2: text cleaning ----------------------------------------------------

def test_clean_text_normalizes_and_strips_invisible_characters():
    assert security.clean_text("  ＡＢＣ　ｘ  ", 50) == "ABC x"                     # fullwidth -> ASCII (NFKC)
    assert security.clean_text("pay‮evil​", 50) == "payevil"             # bidi override, zero-width
    assert security.clean_text("a\x00b\x07c\x1b[31m", 50) == "abc[31m"             # control characters
    assert security.clean_text("line one\r\nline two", 50) == "line one line two"   # single line
    assert security.clean_text("one\r\ntwo  \n\tthree", 50, multiline=True) == "one\ntwo\n\tthree"


def test_clean_text_enforces_the_length_after_normalizing():
    assert security.clean_text("x" * 10, 10) == "x" * 10
    with pytest.raises(ValueError):
        security.clean_text("x" * 11, 10)
    with pytest.raises(ValueError):
        security.clean_text("ﷺ", 5)  # one character that NFKC expands to 18
    with pytest.raises(ValueError):
        security.clean_text(None, 5)


def test_report_note_is_cleaned_before_it_is_stored():
    from certprep.main import ReportRequest
    assert ReportRequest(reason="other", note="  wrong‮ port\x00 ").note == "wrong port"
    with pytest.raises(ValueError):
        ReportRequest(reason="other", note="x" * 301)
