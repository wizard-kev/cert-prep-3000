"""FastAPI app. The browser sends only chapter numbers, IDs, option keys, and fixed choices
(FR1, SR6); nothing it sends is ever placed in a model prompt."""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path as PathParam, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool, StrictInt

from . import pool, sessions, tracker
from .config import settings
from .generator import generate_batch
from .objectives import CHAPTERS, load_chapter
from .providers import ProviderError, get_provider

STATIC = Path(__file__).parent / "static"
QID_PATTERN = r"^Q-C(0[1-9]|1[0-3])-\d{4}$"
QuestionId = Annotated[str, Field(pattern=QID_PATTERN)]
QuestionIdPath = Annotated[str, PathParam(pattern=QID_PATTERN)]
SessionIdPath = Annotated[str, PathParam(pattern=r"^[0-9a-f]{16}$")]
OptionKey = Annotated[str, Field(pattern=r"^[A-F]$")]
ChapterNo = Annotated[StrictInt, Field(ge=1, le=13)]
REPORT_REASONS = ("wrong-answer", "ambiguous", "factual-error", "off-objective", "typo-or-wording", "duplicate",
                  "too-easy", "other")
EXAM_GRACE_S = 30

app = FastAPI(title="CCST Cybersecurity Prep", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
provider = get_provider()

# Model calls are serialized and rate-limited (SR5): one job at a time, plus a cooldown for generation.
_jobs: dict[str, dict] = {}
_model_lock = asyncio.Lock()
_last_generate = 0.0


def _chapter_of(question_id: str) -> int:
    return int(question_id[3:5])


def _question_or_404(question_id: str, allow_retired: bool = False):
    q = pool.get(_chapter_of(question_id), question_id)
    if q is None or (q.status == "retired" and not allow_retired):
        raise HTTPException(404, "unknown question")
    return q


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


# ---- status, chapters ---------------------------------------------------

@app.get("/api/status")
async def status():
    return {"provider": provider.name, "model": provider.model,
            "health": await provider.health(), "busy": _model_lock.locked()}


@app.get("/api/chapters")
def chapters():
    out = []
    for n in CHAPTERS:
        try:
            ch = load_chapter(n)
        except (OSError, ValueError):
            continue
        qs = pool.load(n)
        out.append({
            "chapter": n, "title": ch.title, "objectives": len(ch.objectives), "domain": ch.domain,
            "draft": sum(q.status == "draft" for q in qs),
            "verified": sum(q.status == "verified" for q in qs),
            "retired": sum(q.status == "retired" for q in qs),
        })
    return out


# ---- model jobs (generation, explanations) ------------------------------

async def _run_job(job_id: str, work):
    global _last_generate
    job = _jobs[job_id]
    async with _model_lock:
        job.update(status="running", started=time.time())
        try:
            job.update(status="done", result=await work())
        except ProviderError as e:
            job.update(status="failed", error=str(e))
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            job.update(status="failed", error=f"{type(e).__name__}: {e}")
        finally:
            if job["kind"] == "generate":
                _last_generate = time.monotonic()


def _start_job(kind: str, work, **meta) -> dict:
    if _model_lock.locked() or any(j["status"] in ("queued", "running") for j in _jobs.values()):
        raise HTTPException(409, "the model is busy with another job")
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {"id": job_id, "kind": kind, "status": "queued", **meta}
    asyncio.create_task(_run_job(job_id, work))
    return _jobs[job_id]


class GenerateRequest(BaseModel):
    chapter: ChapterNo
    count: Annotated[StrictInt, Field(ge=1, le=settings.max_batch_size)] = settings.batch_size


@app.post("/api/generate", status_code=202)
async def generate(req: GenerateRequest):
    wait = settings.generate_cooldown_s - (time.monotonic() - _last_generate)
    if _last_generate and wait > 0:
        raise HTTPException(429, f"try again in {wait:.0f} s")

    async def work():
        return (await generate_batch(provider, req.chapter, req.count)).summary()

    return _start_job("generate", work, chapter=req.chapter, count=req.count)


EXPLAIN_SYSTEM = """You are a tutor for the Cisco CCST Cybersecurity exam. Explain the practice question below to a learner who got it wrong.
Use only the objective rows provided as your source of truth. Name the discriminator: the one fact that separates the correct answer from the most tempting wrong option.
Plain text only, no markdown, at most 150 words. Do not invent facts beyond the objective rows."""


@app.post("/api/questions/{question_id}/explain", status_code=202)
async def explain(question_id: QuestionIdPath):
    q = _question_or_404(question_id)
    chapter = load_chapter(q.chapter)
    rows = [chapter.objectives[o] for o in q.objectives if o in chapter.objectives]
    # The prompt is built only from stored question data and the objective file (SR6).
    user = json.dumps({
        "objectives": [{"id": r.id, "objective": r.objective, "core_idea": r.core_idea,
                        "discriminator": r.discriminator} for r in rows],
        "question": {"stem": q.stem, "exhibit": q.exhibit, "options": [o.model_dump() for o in q.options],
                     "answer": q.answer, "discriminator_tested": q.discriminator_tested},
    }, ensure_ascii=False)
    schema = {"type": "object", "properties": {"explanation": {"type": "string"}}, "required": ["explanation"]}

    async def work():
        completion = await provider.complete_json(EXPLAIN_SYSTEM, user, schema, max_tokens=500)
        text = str(json.loads(completion.text).get("explanation", "")).strip()
        return {"question_id": q.id, "explanation": text[:2000], "provider": provider.name,
                "model": completion.model, "seconds": completion.seconds}

    return _start_job("explain", work, question_id=q.id)


@app.get("/api/jobs/{job_id}")
def job(job_id: Annotated[str, PathParam(pattern=r"^[0-9a-f]{12}$")]):
    if job_id not in _jobs:
        raise HTTPException(404, "unknown job")
    return _jobs[job_id]


# ---- question review: verify / report (D7, FR6) -------------------------

@app.get("/api/review-queue")
def review_queue(chapter: Annotated[int, Query(ge=1, le=13)]):
    names = sessions.objective_names()
    drafts = [q for q in pool.load(chapter) if q.status == "draft"]
    return [{**sessions.question_full(q), "objective_names": [names.get(o, "") for o in q.objectives]}
            for q in drafts]


@app.post("/api/questions/{question_id}/verify")
def verify(question_id: QuestionIdPath):
    q = _question_or_404(question_id)
    if not pool.verify(q.chapter, q.id, tracker.now_iso()):
        raise HTTPException(409, f"question is {q.status}, not draft")
    return {"id": q.id, "status": "verified"}


class ReportRequest(BaseModel):
    reason: Literal[REPORT_REASONS]  # type: ignore[valid-type]
    note: Annotated[str, Field(max_length=300)] = ""


@app.post("/api/questions/{question_id}/report")
def report(question_id: QuestionIdPath, req: ReportRequest):
    q = _question_or_404(question_id)
    # The note is stored for the user's own records only; it never reaches a model prompt (SR6).
    reason = req.reason + (f": {req.note.strip()}" if req.note.strip() else "")
    pool.retire(q.chapter, q.id, f"Reported by user ({tracker.now_iso()}): {reason}")
    return {"id": q.id, "status": "retired"}


# ---- sessions (four modes) ----------------------------------------------

class SessionRequest(BaseModel):
    mode: Literal[tracker.MODES]  # type: ignore[valid-type]
    chapters: Annotated[list[ChapterNo], Field(min_length=1, max_length=13)]
    count: Annotated[StrictInt, Field(ge=1, le=200)] | None = None
    minutes: Annotated[StrictInt, Field(ge=5, le=180)] | None = None


DEFAULT_COUNTS = {"drill": 10, "review": 20, "exam": 40}


@app.post("/api/sessions", status_code=201)
def create_session(req: SessionRequest):
    chapters = sorted(set(req.chapters))
    count = req.count or DEFAULT_COUNTS.get(req.mode, 200)
    picked = sessions.select(req.mode, chapters, count)
    if not picked:
        msg = {"exam": "no verified questions in these chapters yet; verify drafts first",
               "review": "no missed questions to review yet"}.get(req.mode, "no questions in these chapters yet")
        raise HTTPException(409, msg)
    limit = (req.minutes or sessions.EXAM_MINUTES) * 60 if req.mode == "exam" else None
    s = tracker.create_session(uuid.uuid4().hex[:16], req.mode, chapters, [q.id for q in picked], limit)
    return _session_view(s)


def _session_view(s: dict) -> dict:
    qs = {q.id: q for q in pool.active(s["chapters"])}
    attempts = {a["question_id"]: a for a in tracker.session_attempts(s["id"])}
    deferred = s["mode"] in sessions.DEFERRED_FEEDBACK and not s["finished_at"]
    answers = {}
    for qid, a in attempts.items():
        answers[qid] = {"selected": a["selected"], "confidence": a["confidence"], "flagged": bool(a["flagged"]),
                        **({} if deferred else {"correct": bool(a["correct"])})}
    return {
        "id": s["id"], "mode": s["mode"], "chapters": s["chapters"], "started_at": s["started_at"],
        "finished_at": s["finished_at"], "time_limit_s": s["time_limit_s"], "deferred": s["mode"] in sessions.DEFERRED_FEEDBACK,
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
    q = _question_or_404(req.question_id)
    correct = tracker.record_attempt(s["id"], q, req.selected, req.confidence, req.flagged)
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

@app.get("/api/tracker")
def tracker_view(chapter: Annotated[list[int], Query()]):
    chs = sorted({c for c in chapter if c in CHAPTERS})
    if not chs:
        raise HTTPException(422, "give at least one chapter from 1 to 13")
    stats = sessions.current_stats(chs)
    out = []
    for n in chs:
        for o in load_chapter(n).objectives.values():
            s = stats.get(o.id)
            row = s.as_dict() if s else tracker.ObjectiveStats(o.id).as_dict()
            out.append({**row, "name": o.objective, "chapter": n})
    return out


@app.get("/api/too-easy")
def too_easy(chapter: Annotated[list[int], Query()]):
    """Questions answered correctly and "sure" every recent time: candidates to keep or retire."""
    chs = sorted({c for c in chapter if c in CHAPTERS})
    if not chs:
        raise HTTPException(422, "give at least one chapter from 1 to 13")
    flagged = tracker.too_easy(tracker.all_attempts(exclude_questions=pool.retired_ids(CHAPTERS)))
    names = sessions.objective_names()
    return [{**sessions.question_full(q), "attempts": flagged[q.id],
             "objective_names": [names.get(o, "") for o in q.objectives]}
            for q in pool.active(chs) if q.id in flagged]


@app.get("/api/export")
def export():
    return {"text": sessions.export_summary()}


class ResetRequest(BaseModel):
    confirm: Literal["RESET"]


@app.post("/api/tracker/reset")
def reset(req: ResetRequest):
    tracker.reset()
    return {"ok": True}
