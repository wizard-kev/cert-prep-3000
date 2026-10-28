"""FastAPI app. The browser sends only certification ids, section codes, question and session IDs,
option keys, fixed choices, and short notes (FR1, SR6); every id is pattern-checked and must exist
in the registry before it touches a file (v2 SR-3). `security.SecurityMiddleware` checks every
request first (v2 SR-1, SR-2, SR-4). No AI model runs here and the app makes no network calls
(v2 decision V2)."""

import html
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator

from . import audit, certs, focus, history, importer, packs, pool, prompts, security, sessions, tracker, wizard
from .config import APP_NAME
from .objectives import UnknownObjective, load_section, load_sections, objective_names
from .schema import SERVED_STATUSES, STATUSES

STATIC = Path(__file__).parent / "static"
QuestionId = Annotated[str, Field(pattern=certs.QUESTION_ID)]
ObjectiveId = Annotated[str, Field(pattern=certs.OBJECTIVE_ID)]
ObjectiveIdPath = Annotated[str, PathParam(pattern=certs.OBJECTIVE_ID)]
BackupName = Annotated[str, Field(pattern=tracker.BACKUP_NAME, max_length=120)]
BackupNamePath = Annotated[str, PathParam(pattern=tracker.BACKUP_NAME, max_length=120)]
QuestionIdPath = Annotated[str, PathParam(pattern=certs.QUESTION_ID)]
CertIdPath = Annotated[str, PathParam(pattern=certs.CERT_ID)]
SectionCode = Annotated[str, Field(pattern=certs.SECTION_CODE)]
SessionIdPath = Annotated[str, PathParam(pattern=r"^[0-9a-f]{16}$")]
OptionKey = Annotated[str, Field(pattern=r"^[A-F]$")]
REPORT_REASONS = ("wrong-answer", "ambiguous", "factual-error", "off-objective", "typo-or-wording", "duplicate",
                  "too-easy", "other")
EXAM_GRACE_S = 30


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """On start: make question statuses agree with recorded answers (after a migration or a
    progress restore, an answered question may still read Unreviewed)."""
    _sync_statuses()
    yield


def _sync_statuses() -> None:
    for cert in certs.list_certs():
        pool.mark_seen_many(cert.id, tracker.first_answered(cert.id))


app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
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


def _reason_text(reason: str, note: str) -> str:
    return reason + (f": {note}" if note else "")


@app.get("/")
def index():
    """The page, carrying this launch's CSRF token (the page sends it back on every change)."""
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(page.replace(CSRF_PLACEHOLDER, html.escape(security.CSRF_TOKEN, quote=True)))


# ---- certifications and sections -----------------------------------------

@app.get("/api/certs")
def list_certs():
    answers = tracker.answer_counts()
    return [{"id": c.id, "name": c.name, "short_name": c.short_name, "vendor": c.vendor,
             "exam_code": c.exam_code, "sections": len(c.sections), "answers": answers.get(c.id, 0)}
            for c in certs.list_certs()]


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
        counts = {status: sum(q.status == status for q in qs) for status in STATUSES}
        out.append({"code": s.code, "name": s.name, "objectives": len(s.objectives), "domain": s.domain,
                    "served": sum(counts[st] for st in SERVED_STATUSES), **counts})
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
                    per_objective: Annotated[int, Query(ge=1, le=3)] = 1, harder: bool = False):
    cert = _cert_or_404(cert_id)
    return _prompt_or_422(lambda: prompts.question_prompt(cert.id, objective, per_objective, harder=harder))


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


# ---- Focus: match a pasted objective list (v2 plan 7.2, SR-2, SR-3, SR-7) ----

class FocusRequest(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=focus.MAX_CHARS)]


@app.post("/api/certs/{cert_id}/focus/match")
def focus_match(cert_id: CertIdPath, req: FocusRequest):
    """Sent as a POST so the pasted list never appears in a URL or a log line."""
    cert = _cert_or_404(cert_id)
    try:
        return focus.match(cert.id, req.text)
    except ValueError as e:  # FocusError, or clean_text's length check after normalizing
        raise HTTPException(422, str(e) if isinstance(e, focus.FocusError)
                            else f"That's too long: paste at most {focus.MAX_CHARS} characters.") from None


# ---- question statuses: Looks right, report, disputes (v2 section 6) -------

@app.post("/api/certs/{cert_id}/questions/{question_id}/validate")
def validate(cert_id: CertIdPath, question_id: QuestionIdPath):
    """The learner marks a question "Looks right" (Validated)."""
    cert = _cert_or_404(cert_id)
    q = _question_or_404(cert.id, question_id)
    if not pool.validate(cert.id, q.id, tracker.now_iso()):
        raise HTTPException(409, f"this question is already {q.status}")
    return {"id": q.id, "status": "validated"}


class ReportRequest(BaseModel):
    reason: Literal[REPORT_REASONS]  # type: ignore[valid-type]
    note: Annotated[str, Field(max_length=300)] = ""
    session_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")] | None = None

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str) -> str:
        return security.clean_text(v, 300)


@app.post("/api/certs/{cert_id}/questions/{question_id}/report")
def report(cert_id: CertIdPath, question_id: QuestionIdPath, req: ReportRequest):
    """Dispute a question: it leaves play at once and waits for the learner to confirm (retire) or
    undo. During an unfinished exam, use the session's held reports instead."""
    cert = _cert_or_404(cert_id)
    q = _question_or_404(cert.id, question_id)
    if req.session_id:
        s = _session_or_404(req.session_id)
        if s["mode"] == "exam" and not s["finished_at"]:
            raise HTTPException(409, "during an exam, reports are held until the results page")
    # The note (already cleaned) is stored for the user's own records only.
    if not pool.dispute(cert.id, q.id, _reason_text(req.reason, req.note), tracker.now_iso(), req.session_id):
        raise HTTPException(409, f"this question is {q.status}")
    return {"id": q.id, "status": "disputed"}


@app.get("/api/certs/{cert_id}/disputes")
def disputes(cert_id: CertIdPath):
    cert = _cert_or_404(cert_id)
    names = objective_names(cert.id)
    return [{**sessions.question_full(q), "disputed_at": q.disputed_at,
             "objective_names": [names.get(o, "") for o in q.objectives]} for q in pool.disputed(cert.id)]


class DisputeDecision(BaseModel):
    decision: Literal["confirm", "undo"]


@app.post("/api/certs/{cert_id}/questions/{question_id}/dispute")
def decide_dispute(cert_id: CertIdPath, question_id: QuestionIdPath, req: DisputeDecision):
    """Confirm (the question is retired) or undo (it goes back into play) a pending dispute."""
    cert = _cert_or_404(cert_id)
    q = _question_or_404(cert.id, question_id)
    done = (pool.confirm_dispute(cert.id, q.id, tracker.now_iso()) if req.decision == "confirm"
            else pool.undo_dispute(cert.id, q.id))
    if not done:
        raise HTTPException(409, "this question has no pending dispute")
    return {"id": q.id, "status": pool.get(cert.id, q.id).status}


# ---- sessions (Practice, Exam; Focus arrives in P7) ------------------------

class SessionRequest(BaseModel):
    mode: Literal["practice", "exam", "focus"]
    sections: Annotated[list[SectionCode], Field(min_length=1, max_length=200)] | None = None
    objectives: Annotated[list[ObjectiveId], Field(min_length=1, max_length=focus.MAX_OBJECTIVES)] | None = None
    count: Annotated[StrictInt, Field(ge=1, le=200)] | None = None
    minutes: Annotated[StrictInt, Field(ge=5, le=300)] | None = None


PRACTICE_COUNT = 10


@app.post("/api/certs/{cert_id}/sessions", status_code=201)
def create_session(cert_id: CertIdPath, req: SessionRequest):
    cert = _cert_or_404(cert_id)
    defaults = sessions.exam_defaults(cert)
    count = req.count or (defaults["questions"] if req.mode == "exam" else PRACTICE_COUNT)
    if req.mode == "focus":
        if not req.objectives:
            raise HTTPException(422, "choose at least one objective for a focus session")
        try:
            codes = focus.objective_sections(cert.id, req.objectives)
        except KeyError as e:
            raise HTTPException(422, f"{e.args[0]} isn't an objective of {cert.short_name}") from None
        picked = sessions.select_focus(cert.id, list(dict.fromkeys(req.objectives)), count)
        if not picked:
            raise HTTPException(409, "None of these objectives has questions yet. Get a prompt to generate some.")
    else:
        if not req.sections:
            raise HTTPException(422, "choose at least one section")
        codes = _sections_or_404(cert, req.sections)
        picked = sessions.select(cert.id, req.mode, codes, count)
        if not picked:
            raise HTTPException(409, "There are no questions in these sections yet. Add some in the Claude workspace.")
    limit = (req.minutes or defaults["minutes"]) * 60 if req.mode == "exam" else None
    s = tracker.create_session(uuid.uuid4().hex[:16], cert.id, req.mode, codes, [q.id for q in picked], limit)
    return _session_view(s)


def _session_view(s: dict) -> dict:
    ids = set(s["question_ids"])
    qs = {q.id: q for q in pool.all_questions(s["cert_id"], s["sections"]) if q.id in ids}
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
    confidence: Annotated[StrictInt, Field(ge=1, le=5)]  # 1 Guessing ... 5 Certain
    flagged: StrictBool = False  # "Mark for review" in an exam


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
    pool.mark_seen(s["cert_id"], q.id, tracker.now_iso())  # answered: passively validated
    if s["mode"] in sessions.DEFERRED_FEEDBACK:
        return {"recorded": True}
    return {"recorded": True, "correct": correct, "question": sessions.question_full(pool.get(s["cert_id"], q.id))}


class HeldReportRequest(BaseModel):
    question_id: QuestionId
    reason: Literal[REPORT_REASONS]  # type: ignore[valid-type]
    note: Annotated[str, Field(max_length=300)] = ""

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str) -> str:
        return security.clean_text(v, 300)


@app.post("/api/sessions/{session_id}/held-reports")
def hold_report(session_id: SessionIdPath, req: HeldReportRequest):
    """Report a question during an exam: held until the results page, where the learner sees the
    answer and confirms or withdraws it (v2 decision V8). The exam is not interrupted."""
    s = _session_or_404(session_id)
    if s["mode"] != "exam" or s["finished_at"]:
        raise HTTPException(409, "held reports are for exams in progress; report the question directly")
    if req.question_id not in s["question_ids"]:
        raise HTTPException(404, "question is not part of this session")
    tracker.hold_dispute(s["id"], req.question_id, _reason_text(req.reason, req.note))
    return {"ok": True}


class HeldDecision(BaseModel):
    question_id: QuestionId
    decision: Literal["confirm", "withdraw"]


@app.post("/api/sessions/{session_id}/held-reports/decide")
def decide_held_report(session_id: SessionIdPath, req: HeldDecision):
    """Before the exam ends: withdraw takes the report back. After it ends: confirm retires the
    question (it leaves the score); withdraw keeps it counted."""
    s = _session_or_404(session_id)
    held = tracker.held_disputes(s["id"]).get(req.question_id)
    if held is None or held["decision"] is not None:
        raise HTTPException(404, "no undecided report for that question in this session")
    if not s["finished_at"]:
        if req.decision != "withdraw":
            raise HTTPException(409, "finish the exam first; you'll see the answer before confirming")
        tracker.drop_held_dispute(s["id"], req.question_id)
        return {"ok": True}
    if req.decision == "confirm":
        pool.retire(s["cert_id"], req.question_id,
                    f"{pool.REPORTED_PREFIX} ({held['created_at']}): {held['reason']}")
    tracker.decide_held_dispute(s["id"], req.question_id, "confirmed" if req.decision == "confirm" else "withdrawn")
    return sessions.session_report(tracker.get_session(s["id"]))


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
    """Questions answered correctly at Certain every recent time: candidates to keep or retire."""
    cert = _cert_or_404(cert_id)
    codes = _sections_or_404(cert, section)
    flagged = tracker.too_easy(tracker.all_attempts(cert.id, exclude_questions=pool.inactive_ids(cert.id)))
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


# ---- question-bank health (v2 plan 5.2) and certification packs (section 9, SR-5) ----

@app.get("/api/certs/{cert_id}/health")
def pool_health(cert_id: CertIdPath):
    """Coverage per section and the surface-cue bands: the CLI's coverage and audit, in the app."""
    cert = _cert_or_404(cert_id)
    codes = [s.code for s in load_sections(cert.id)]
    r = audit.audit(cert.id, codes)
    return {"minimum": 2, "sections": audit.coverage(cert.id, codes, 2), "audit": r, "bands": audit.bands(r)}


@app.get("/api/certs/{cert_id}/pack")
def export_pack(cert_id: CertIdPath, retired: bool = False):
    cert = _cert_or_404(cert_id)
    body = packs.export_pack(cert.id, include_retired=retired)
    name = f"{cert.id}-pack-{datetime.now(timezone.utc).date().isoformat()}.zip"
    return Response(body, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post(security.PACK_UPLOAD_PATH)
async def import_pack(request: Request, check: bool = True,
                      id: Annotated[str | None, Query(pattern=certs.CERT_ID)] = None,
                      short_name: Annotated[str | None, Query(max_length=60)] = None):
    """The body is the pack itself (application/zip, at most 20 MB: the middleware checks both). With
    check=true nothing is written: the pack is validated and summarised. Then the learner chooses the id."""
    data = await request.body()
    try:
        pack = packs.check_pack(data)
        if check:
            taken = {c.short_name for c in certs.list_certs()}
            short = pack.cert.short_name
            return {"pack": pack.summary(), "suggested_id": packs.suggest_id(pack.cert.id),
                    "suggested_short_name": short if short not in taken else f"{short[:53]} (copy)"}
        if id is None:
            raise HTTPException(422, "choose an id for the new certification")
        name = security.clean_text(short_name, 60) if short_name else None
        return {"cert": packs.install_pack(pack, id, name)}
    except packs.PackError as e:
        raise HTTPException(422, str(e)) from None
    except ValueError:
        raise HTTPException(422, "That short name isn't valid.") from None


# ---- certification wizard (v2 plan 3.3) --------------------------------------

DraftIdPath = Annotated[str, PathParam(pattern=certs.CERT_ID)]


def _draft_or_404(draft_id: str) -> dict:
    try:
        return wizard.get(draft_id)
    except KeyError:
        raise HTTPException(404, "no certification set-up by that id") from None


def _wizard_call(fn):
    try:
        return fn()
    except wizard.WizardError as e:
        raise HTTPException(422, str(e)) from None


class DraftRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    short_name: Annotated[str, Field(max_length=60)] = ""
    vendor: Annotated[str, Field(max_length=100)] = ""
    exam_code: Annotated[str, Field(max_length=40)] = ""


class ReplyRequest(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=importer.MAX_TEXT_CHARS)]


class OfficialListRequest(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=wizard.MAX_OFFICIAL_LIST)]


class FactEdit(BaseModel):
    value: StrictInt | float | Annotated[str, Field(max_length=40)] | None = None
    confidence: Literal[wizard.CONFIDENCES]  # type: ignore[valid-type]


class FactsEditRequest(BaseModel):
    minutes: FactEdit | None = None
    question_count: FactEdit | None = None
    passing_score: FactEdit | None = None
    weights: dict[Annotated[str, Field(pattern=r"^[A-Za-z0-9.]{1,10}$")], Annotated[float, Field(gt=0, le=1000)]] | None = None


class DiscardRequest(BaseModel):
    confirm: Literal["DISCARD"]


@app.get("/api/wizard")
def list_drafts():
    return [{k: d.get(k) for k in ("id", "name", "short_name", "step", "installed", "updated")} for d in wizard.list_drafts()]


@app.post("/api/wizard", status_code=201)
def create_draft(req: DraftRequest):
    return _wizard_call(lambda: wizard.create(req.name, req.short_name, req.vendor, req.exam_code))


@app.get("/api/wizard/{draft_id}")
def get_draft(draft_id: DraftIdPath):
    return _draft_or_404(draft_id)


@app.get("/api/wizard/{draft_id}/prompts/facts")
def facts_prompt(draft_id: DraftIdPath):
    _draft_or_404(draft_id)
    return {"prompt": wizard.facts_prompt(draft_id)}


@app.post("/api/wizard/{draft_id}/facts")
def import_facts(draft_id: DraftIdPath, req: ReplyRequest):
    _draft_or_404(draft_id)
    return _wizard_call(lambda: wizard.import_facts(draft_id, req.text))


@app.post("/api/wizard/{draft_id}/facts/edit")
def edit_facts(draft_id: DraftIdPath, req: FactsEditRequest):
    _draft_or_404(draft_id)
    return _wizard_call(lambda: wizard.edit_facts(draft_id, req.model_dump(exclude_none=True)))


@app.post("/api/wizard/{draft_id}/prompts/objectives")
def objectives_prompt(draft_id: DraftIdPath, req: OfficialListRequest):
    """A POST: the pasted official list goes into the prompt (on purpose, v2 plan 5.1) and is kept in the draft."""
    _draft_or_404(draft_id)
    return {"prompt": _wizard_call(lambda: wizard.objectives_prompt(draft_id, req.text))}


@app.post("/api/wizard/{draft_id}/objectives")
def import_objectives(draft_id: DraftIdPath, req: ReplyRequest):
    _draft_or_404(draft_id)
    return _wizard_call(lambda: wizard.import_objectives(draft_id, req.text))


@app.post("/api/wizard/{draft_id}/install")
def install_cert(draft_id: DraftIdPath):
    _draft_or_404(draft_id)
    return {"cert": _wizard_call(lambda: wizard.install(draft_id))}


@app.post("/api/wizard/{draft_id}/finish")
def finish_draft(draft_id: DraftIdPath):
    """Done with the wizard: the draft goes; an installed certification stays."""
    d = _draft_or_404(draft_id)
    if not d.get("installed"):
        raise HTTPException(409, "install the certification first, or discard this set-up")
    wizard.finish(draft_id)
    return {"cert": draft_id}


@app.post("/api/wizard/{draft_id}/discard")
def discard_draft(draft_id: DraftIdPath, req: DiscardRequest):
    _draft_or_404(draft_id)
    wizard.finish(draft_id)
    return {"ok": True}


# ---- progress over time and suggestions (v2 plan 8.3, V11) ------------------

@app.get("/api/certs/{cert_id}/progress/overview")
def progress_overview(cert_id: CertIdPath):
    cert = _cert_or_404(cert_id)
    return history.overview(cert.id)


@app.get("/api/certs/{cert_id}/progress/objectives/{objective_id}")
def objective_history(cert_id: CertIdPath, objective_id: ObjectiveIdPath):
    cert = _cert_or_404(cert_id)
    try:
        return history.objective_history(cert.id, objective_id)
    except UnknownObjective:
        raise HTTPException(404, f"{objective_id} isn't an objective of {cert.short_name}") from None


@app.get("/api/certs/{cert_id}/recommendations")
def recommendations(cert_id: CertIdPath):
    cert = _cert_or_404(cert_id)
    return history.recommendations(cert.id)


# ---- progress backups (every certification at once; v2 plan 8.1) ---------------

def _backup_or_404(name: str):
    try:
        return tracker.backup_file(name)
    except FileNotFoundError:
        raise HTTPException(404, "no backup by that name") from None


@app.get("/api/progress/backups")
def list_backups():
    return tracker.list_backups()


@app.post("/api/progress/backups")
def make_backup():
    if not tracker.settings.progress_db.exists():
        raise HTTPException(409, "there's no progress to back up yet")
    return {"name": tracker.backup("manual").name}


@app.get("/api/progress/backups/{name}")
def download_backup(name: BackupNamePath):
    path = _backup_or_404(name)
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=path.name)


class RestoreRequest(BaseModel):
    name: BackupName
    confirm: Literal["RESTORE"]


@app.post("/api/progress/restore")
def restore_backup(req: RestoreRequest):
    """Replace all progress with a backup; the current progress is backed up first."""
    _backup_or_404(req.name)
    try:
        result = tracker.restore(req.name)
    except tracker.ProgressError as e:
        raise HTTPException(422, str(e)) from None
    _sync_statuses()
    return result
