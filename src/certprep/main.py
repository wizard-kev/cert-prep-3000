"""FastAPI app. The browser sends only certification ids, section codes, question and session IDs,
option keys, fixed choices, and short notes (FR1, SR6); every id is pattern-checked and must exist
in the registry before it touches a file (v2 SR-3). `security.SecurityMiddleware` checks every
request first (v2 SR-1, SR-2, SR-4). No AI model runs here and the app makes no network calls
(v2 decision V2)."""

import html
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path as PathParam, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator

from . import certs, importer, pool, prompts, security, sessions, tracker
from .config import APP_NAME
from .objectives import UnknownObjective, load_section, load_sections, objective_names

STATIC = Path(__file__).parent / "static"
QuestionId = Annotated[str, Field(pattern=certs.QUESTION_ID)]
ObjectiveId = Annotated[str, Field(pattern=certs.OBJECTIVE_ID)]
QuestionIdPath = Annotated[str, PathParam(pattern=certs.QUESTION_ID)]
CertIdPath = Annotated[str, PathParam(pattern=certs.CERT_ID)]
SectionCode = Annotated[str, Field(pattern=certs.SECTION_CODE)]
SessionIdPath = Annotated[str, PathParam(pattern=r"^[0-9a-f]{16}$")]
OptionKey = Annotated[str, Field(pattern=r"^[A-F]$")]
REPORT_REASONS = ("wrong-answer", "ambiguous", "factual-error", "off-objective", "typo-or-wording", "duplicate",
                  "too-easy", "other")
EXAM_GRACE_S = 30

app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(security.SecurityMiddleware)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
CSRF_PLACEHOLDER = "__CSRF_TOKEN__"


def _cert_or_404(cert_id: str) -> certs.Cert:
    try:
        return certs.get_cert(cert_id)
    except (certs.UnknownCert, OSError, ValueError):
        raise HTTPException(404, "unknown certification") from None


def _sections_or_404(cert: certs.Cert, codes: list[str]) -> list[str]:
    try:
        return sorted({cert.section(c).code for c in codes}, key=cert.section_codes.index)
    except certs.UnknownSection:
        raise HTTPException(404, f"unknown section for {cert.short_name}") from None


def _question_or_404(cert_id: str, question_id: str, allow_retired: bool = False):
    q = pool.get(cert_id, question_id)
    if q is None or (q.status == "retired" and not allow_retired):
        raise HTTPException(404, "unknown question")
    return q


@app.get("/")
def index():
    """The page, carrying this launch's CSRF token (the page sends it back on every change)."""
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(page.replace(CSRF_PLACEHOLDER, html.escape(security.CSRF_TOKEN, quote=True)))


# ---- certifications and sections -----------------------------------------

@app.get("/api/certs")
def list_certs():
    return [{"id": c.id, "name": c.name, "short_name": c.short_name, "vendor": c.vendor,
             "exam_code": c.exam_code, "sections": len(c.sections)} for c in certs.list_certs()]


@app.get("/api/certs/{cert_id}")
def get_cert(cert_id: CertIdPath):
    cert = _cert_or_404(cert_id)
    return {**cert.model_dump(), "exam_defaults": sessions.exam_defaults(cert)}


@app.get("/api/certs/{cert_id}/sections")
def sections_view(cert_id: CertIdPath):
    cert = _cert_or_404(cert_id)
    out = []
    for s in load_sections(cert.id):
        qs = pool.load(cert.id, s.code)
        out.append({
            "code": s.code, "name": s.name, "objectives": len(s.objectives), "domain": s.domain,
            "draft": sum(q.status == "draft" for q in qs),
            "verified": sum(q.status == "verified" for q in qs),
            "retired": sum(q.status == "retired" for q in qs),
        })
    return out


@app.get("/api/certs/{cert_id}/objectives")
def objectives_view(cert_id: CertIdPath):
    """Every objective with its active question count, angles, and the learner's status (for choosing
    what to generate or study)."""
    cert = _cert_or_404(cert_id)
    stats = sessions.current_stats(cert.id)
    out = []
    for s in load_sections(cert.id):
        active = pool.active(cert.id, [s.code])
        for o in s.objectives.values():
            mine = [q for q in active if q.objectives[0] == o.id]
            st = stats.get(o.id)
            out.append({"id": o.id, "section": s.code, "name": o.objective, "questions": len(mine),
                        "angles": sorted({q.angle for q in mine}), "status": st.status if st else "New",
                        "attempts": st.attempts if st else 0})
    return out


# ---- prompts for a Claude chat, and importing the reply (v2 section 5) ----

ObjectiveQuery = Annotated[list[ObjectiveId], Query(min_length=1, max_length=prompts.MAX_OBJECTIVES)]


def _prompt_or_422(build):
    try:
        return build()
    except (prompts.PromptError, UnknownObjective) as e:
        raise HTTPException(422, str(e)) from None


@app.get("/api/certs/{cert_id}/prompts/questions")
def question_prompt(cert_id: CertIdPath, objective: ObjectiveQuery,
                    per_objective: Annotated[int, Query(ge=1, le=3)] = 1):
    cert = _cert_or_404(cert_id)
    return _prompt_or_422(lambda: prompts.question_prompt(cert.id, objective, per_objective))


@app.get("/api/certs/{cert_id}/prompts/study")
def study_prompt(cert_id: CertIdPath, objective: ObjectiveQuery):
    cert = _cert_or_404(cert_id)
    return {"prompt": _prompt_or_422(lambda: prompts.study_prompt(cert.id, objective))}


@app.get("/api/certs/{cert_id}/prompts/ask/{question_id}")
def ask_prompt(cert_id: CertIdPath, question_id: QuestionIdPath,
               selected: Annotated[list[Annotated[str, Field(pattern=r"^[A-F]$")]], Query(max_length=6)] = []):
    cert = _cert_or_404(cert_id)
    _question_or_404(cert.id, question_id, allow_retired=True)
    return {"prompt": _prompt_or_422(lambda: prompts.ask_prompt(cert.id, question_id, selected))}


class ImportRequest(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=importer.MAX_TEXT_CHARS)]


@app.post("/api/certs/{cert_id}/imports")
def import_questions(cert_id: CertIdPath, req: ImportRequest):
    cert = _cert_or_404(cert_id)
    try:
        return importer.import_reply(cert.id, req.text).as_dict()
    except importer.ImportProblem as e:
        raise HTTPException(422, str(e)) from None


# ---- question review: verify / report (D7, FR6) -------------------------

@app.get("/api/certs/{cert_id}/review-queue")
def review_queue(cert_id: CertIdPath, section: Annotated[str, Query(pattern=certs.SECTION_CODE)]):
    cert = _cert_or_404(cert_id)
    (code,) = _sections_or_404(cert, [section])
    names = objective_names(cert.id)
    drafts = [q for q in pool.load(cert.id, code) if q.status == "draft"]
    return [{**sessions.question_full(q), "objective_names": [names.get(o, "") for o in q.objectives]}
            for q in drafts]


@app.post("/api/certs/{cert_id}/questions/{question_id}/verify")
def verify(cert_id: CertIdPath, question_id: QuestionIdPath):
    cert = _cert_or_404(cert_id)
    q = _question_or_404(cert.id, question_id)
    if not pool.verify(cert.id, q.id, tracker.now_iso()):
        raise HTTPException(409, f"question is {q.status}, not draft")
    return {"id": q.id, "status": "verified"}


class ReportRequest(BaseModel):
    reason: Literal[REPORT_REASONS]  # type: ignore[valid-type]
    note: Annotated[str, Field(max_length=300)] = ""

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str) -> str:
        return security.clean_text(v, 300)


@app.post("/api/certs/{cert_id}/questions/{question_id}/report")
def report(cert_id: CertIdPath, question_id: QuestionIdPath, req: ReportRequest):
    cert = _cert_or_404(cert_id)
    q = _question_or_404(cert.id, question_id)
    # The note (already cleaned) is stored for the user's own records only.
    reason = req.reason + (f": {req.note}" if req.note else "")
    pool.retire(cert.id, q.id, f"Reported by user ({tracker.now_iso()}): {reason}")
    return {"id": q.id, "status": "retired"}


# ---- sessions (four modes) ----------------------------------------------

class SessionRequest(BaseModel):
    mode: Literal[tracker.MODES]  # type: ignore[valid-type]
    sections: Annotated[list[SectionCode], Field(min_length=1, max_length=200)]
    count: Annotated[StrictInt, Field(ge=1, le=200)] | None = None
    minutes: Annotated[StrictInt, Field(ge=5, le=300)] | None = None


DEFAULT_COUNTS = {"drill": 10, "review": 20}


@app.post("/api/certs/{cert_id}/sessions", status_code=201)
def create_session(cert_id: CertIdPath, req: SessionRequest):
    cert = _cert_or_404(cert_id)
    codes = _sections_or_404(cert, req.sections)
    defaults = sessions.exam_defaults(cert)
    count = req.count or (defaults["questions"] if req.mode == "exam" else DEFAULT_COUNTS.get(req.mode, 200))
    picked = sessions.select(cert.id, req.mode, codes, count)
    if not picked:
        msg = {"exam": "no verified questions in these sections yet; verify drafts first",
               "review": "no missed questions to review yet"}.get(req.mode, "no questions in these sections yet")
        raise HTTPException(409, msg)
    limit = (req.minutes or defaults["minutes"]) * 60 if req.mode == "exam" else None
    s = tracker.create_session(uuid.uuid4().hex[:16], cert.id, req.mode, codes, [q.id for q in picked], limit)
    return _session_view(s)


def _session_view(s: dict) -> dict:
    qs = {q.id: q for q in pool.active(s["cert_id"], s["sections"])}
    attempts = {a["question_id"]: a for a in tracker.session_attempts(s["id"])}
    deferred = s["mode"] in sessions.DEFERRED_FEEDBACK and not s["finished_at"]
    answers = {}
    for qid, a in attempts.items():
        answers[qid] = {"selected": a["selected"], "confidence": a["confidence"], "flagged": bool(a["flagged"]),
                        **({} if deferred else {"correct": bool(a["correct"])})}
    return {
        "id": s["id"], "cert_id": s["cert_id"], "mode": s["mode"], "sections": s["sections"],
        "started_at": s["started_at"], "finished_at": s["finished_at"], "time_limit_s": s["time_limit_s"],
        "deferred": s["mode"] in sessions.DEFERRED_FEEDBACK,
        "questions": [sessions.question_public(qs[qid]) for qid in s["question_ids"] if qid in qs],
        "answers": answers,
    }


def _session_or_404(session_id: str) -> dict:
    s = tracker.get_session(session_id)
    if s is None:
        raise HTTPException(404, "unknown session")
    return s


def _time_left(s: dict) -> float | None:
    if not s["time_limit_s"]:
        return None
    started = datetime.fromisoformat(s["started_at"])
    return s["time_limit_s"] - (datetime.now(timezone.utc) - started).total_seconds()


@app.get("/api/sessions/{session_id}")
def get_session(session_id: SessionIdPath):
    return _session_view(_session_or_404(session_id))


class AnswerRequest(BaseModel):
    question_id: QuestionId
    selected: Annotated[list[OptionKey], Field(min_length=1, max_length=6)]
    confidence: Literal[tracker.CONFIDENCE]  # type: ignore[valid-type]
    flagged: StrictBool = False


@app.post("/api/sessions/{session_id}/answer")
def answer(session_id: SessionIdPath, req: AnswerRequest):
    s = _session_or_404(session_id)
    if s["finished_at"]:
        raise HTTPException(409, "session is finished")
    if req.question_id not in s["question_ids"]:
        raise HTTPException(404, "question is not part of this session")
    left = _time_left(s)
    if left is not None and left < -EXAM_GRACE_S:
        raise HTTPException(409, "time is up")
    q = _question_or_404(s["cert_id"], req.question_id)
    correct = tracker.record_attempt(s["id"], s["cert_id"], q, req.selected, req.confidence, req.flagged)
    if s["mode"] in sessions.DEFERRED_FEEDBACK:
        return {"recorded": True}
    return {"recorded": True, "correct": correct, "question": sessions.question_full(q)}


class FlagRequest(BaseModel):
    question_id: QuestionId
    flagged: StrictBool


@app.post("/api/sessions/{session_id}/flag")
def flag(session_id: SessionIdPath, req: FlagRequest):
    s = _session_or_404(session_id)
    if req.question_id not in s["question_ids"]:
        raise HTTPException(404, "question is not part of this session")
    tracker.set_flag(s["id"], req.question_id, req.flagged)
    return {"ok": True}


class ErrorTypeRequest(BaseModel):
    question_id: QuestionId
    error_type: Literal[tracker.ERROR_TYPES] | None  # type: ignore[valid-type]


@app.post("/api/sessions/{session_id}/error-type")
def error_type(session_id: SessionIdPath, req: ErrorTypeRequest):
    s = _session_or_404(session_id)
    if s["mode"] in sessions.DEFERRED_FEEDBACK and not s["finished_at"]:
        raise HTTPException(409, "finish the session first")
    if not tracker.set_error_type(s["id"], req.question_id, req.error_type):
        raise HTTPException(404, "no incorrect answer for that question in this session")
    return {"ok": True}


@app.post("/api/sessions/{session_id}/finish")
def finish(session_id: SessionIdPath):
    s = _session_or_404(session_id)
    tracker.finish_session(s["id"])
    return sessions.session_report(tracker.get_session(s["id"]))


@app.get("/api/sessions/{session_id}/report")
def session_report(session_id: SessionIdPath):
    s = _session_or_404(session_id)
    if s["mode"] in sessions.DEFERRED_FEEDBACK and not s["finished_at"]:
        raise HTTPException(409, "finish the session first")
    return sessions.session_report(s)


# ---- tracker, export, reset ---------------------------------------------

SectionQuery = Annotated[list[SectionCode], Query(min_length=1, max_length=200)]


@app.get("/api/certs/{cert_id}/tracker")
def tracker_view(cert_id: CertIdPath, section: SectionQuery):
    cert = _cert_or_404(cert_id)
    codes = _sections_or_404(cert, section)
    stats = sessions.current_stats(cert.id)
    out = []
    for code in codes:
        for o in load_section(cert.id, code).objectives.values():
            s = stats.get(o.id)
            row = s.as_dict() if s else tracker.ObjectiveStats(o.id).as_dict()
            out.append({**row, "name": o.objective, "section": code})
    return out


@app.get("/api/certs/{cert_id}/too-easy")
def too_easy(cert_id: CertIdPath, section: SectionQuery):
    """Questions answered correctly and "sure" every recent time: candidates to keep or retire."""
    cert = _cert_or_404(cert_id)
    codes = _sections_or_404(cert, section)
    flagged = tracker.too_easy(tracker.all_attempts(cert.id, exclude_questions=pool.retired_ids(cert.id)))
    names = objective_names(cert.id)
    return [{**sessions.question_full(q), "attempts": flagged[q.id],
             "objective_names": [names.get(o, "") for o in q.objectives]}
            for q in pool.active(cert.id, codes) if q.id in flagged]


@app.get("/api/certs/{cert_id}/export")
def export(cert_id: CertIdPath):
    cert = _cert_or_404(cert_id)
    return {"text": sessions.export_summary(cert.id)}


class ResetRequest(BaseModel):
    confirm: Literal["RESET"]


@app.post("/api/certs/{cert_id}/progress/reset")
def reset(cert_id: CertIdPath, req: ResetRequest):
    cert = _cert_or_404(cert_id)
    tracker.reset(cert.id)
    return {"ok": True}
