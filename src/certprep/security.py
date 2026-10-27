"""Request guards, response headers, and text cleaning (v2 plan section 10).

SR-1  Only requests addressed to this machine by name (Host 127.0.0.1 or localhost) are served,
      which defeats DNS rebinding. Every state-changing request must come from this app's own
      page: a same-origin Origin header plus the per-launch CSRF token that only the page knows.
SR-2  Request bodies are JSON, size-capped; free text from the user goes through `clean_text`.
SR-4  Every response carries a strict Content-Security-Policy and related headers.
"""

import re
import secrets
import unicodedata

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost"}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_BODY_BYTES = 1_000_000
CSRF_HEADER = "x-csrf-token"
# New on every start of the app: a page from an earlier run must be reloaded to get it.
CSRF_TOKEN = secrets.token_urlsafe(32)

STALE_PAGE = "This page is out of date because the app was restarted. Reload the page and try again."

SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                "connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; "
                                "frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}

_HOST = re.compile(r"^(?P<name>[A-Za-z0-9.\-]+)(?::(?P<port>\d{1,5}))?$")


def host_allowed(host: str | None) -> bool:
    """`127.0.0.1` or `localhost`, with an optional port. Anything else (another domain that
    happens to resolve to this machine) is refused."""
    m = _HOST.match(host or "")
    return bool(m) and m.group("name").lower() in ALLOWED_HOSTNAMES and int(m.group("port") or 80) <= 65535


def request_problem(method: str, headers: Headers) -> tuple[int, str] | None:
    """Why a request must be refused, as (status, message), or None if it may proceed."""
    host = headers.get("host")
    if not host_allowed(host):
        return 403, "This app only answers requests addressed to 127.0.0.1 or localhost."
    if method in UNSAFE_METHODS:
        if headers.get("transfer-encoding"):
            return 411, "Send the request with a Content-Length."
        length = headers.get("content-length", "0")
        if not length.isdigit():
            return 400, "Invalid Content-Length."
        if int(length) > MAX_BODY_BYTES:
            return 413, f"The request is too large (limit {MAX_BODY_BYTES // 1000} KB)."
        if int(length) > 0 and headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return 415, "Requests must be sent as JSON."
        origin = headers.get("origin")
        if origin is None or origin.lower() != f"http://{host}".lower():
            return 403, "Requests that change data must come from this app's own page."
        if headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
            return 403, "Requests that change data must come from this app's own page."
        if not secrets.compare_digest(headers.get(CSRF_HEADER, ""), CSRF_TOKEN):
            return 403, STALE_PAGE
    return None


class SecurityMiddleware:
    """Pure ASGI middleware: refuses bad requests before any route runs, and adds the security
    headers to every response, including errors and static files."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        problem = request_problem(scope["method"], Headers(scope=scope))
        if problem:
            status, message = problem
            await JSONResponse({"detail": message}, status_code=status,
                               headers={**SECURITY_HEADERS, "Cache-Control": "no-store"})(scope, receive, send)
            return
        no_store = scope["path"] == "/" or scope["path"].startswith("/api/")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                for key, value in SECURITY_HEADERS.items():
                    h[key] = value
                if no_store:
                    h["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)


# ---- text from the user (SR-2) --------------------------------------------

_KEEP_IN_MULTILINE = {"\n", "\t"}


def clean_text(value: str, max_len: int, multiline: bool = False) -> str:
    """Normalize user text before it is stored or matched: Unicode NFKC, line endings to \\n,
    and no control or invisible formatting characters (zero-width, bidirectional overrides).
    Raises ValueError if the result is longer than `max_len`."""
    if not isinstance(value, str):
        raise ValueError("text expected")
    text = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch in _KEEP_IN_MULTILINE:
            out.append(ch if multiline else " ")
        elif cat in ("Cc", "Cf", "Cs", "Co", "Cn"):
            continue
        else:
            out.append(ch)
    text = "".join(out)
    if multiline:
        text = "\n".join(line.rstrip() for line in text.split("\n"))
    else:
        text = re.sub(r"\s+", " ", text)
    text = text.strip()
    if len(text) > max_len:
        raise ValueError(f"text longer than {max_len} characters")
    return text
