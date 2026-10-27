"""Question selection per mode (plan 8.2), score reports, and the export summary (8.5)."""

import random
from collections import defaultdict
from datetime import datetime, timezone

from . import pool, tracker
from .objectives import CHAPTERS, load_chapter
from .schema import Question

# Phase 0 decision: Cisco publishes no weights, so the default is proportional to the number
# of official sub-objectives per domain (4, 5, 6, 4, 4 of 23). Labelled as an estimate in the UI.
DOMAIN_WEIGHTS = {"1.0": 4, "2.0": 5, "3.0": 6, "4.0": 4, "5.0": 4}
UNTAGGED_WEIGHT = 4  # chapters whose domain is not yet tagged (until the Phase 7 crosswalk)
EXAM_MINUTES = 50
DEFERRED_FEEDBACK = {"exam", "diagnostic"}  # withhold feedback until the end
# Drill weights per objective status. New objectives are mainly introduced by the diagnostic,
# so a drill leans hard on Weak ones, then reinforces Improving and due Solid ones.
DRILL_WEIGHTS = {"Weak": 8.0, "Improving": 3.0, "Solid-due": 3.0, "New": 2.0, "Solid": 0.2}


def current_stats(chapters) -> dict[str, tracker.ObjectiveStats]:
    flawed = pool.flawed_ids(CHAPTERS)  # answers to flawed questions don't count; superseded ones do
    return tracker.objective_stats(tracker.all_attempts(exclude_questions=flawed))


def _by_objective(questions: list[Question]) -> dict[str, list[Question]]:
    out = defaultdict(list)
    for q in questions:
        out[q.objectives[0]].append(q)
    return out


def _pick_for_objective(candidates: list[Question], stats: tracker.ObjectiveStats | None,
                        rng: random.Random) -> Question:
    """Avoid the angle and the questions seen most recently for this objective (section 10.1)."""
    last_angle = stats.last_angle if stats else None
    recent = set(stats.recent_questions) if stats else set()

    def score(q: Question):
        return (q.angle == last_angle, q.id in recent, q.status != "verified", rng.random())

    return min(candidates, key=score)


def select(mode: str, chapters: list[int], count: int, rng: random.Random | None = None) -> list[Question]:
    rng = rng or random.Random()
    questions = pool.active(chapters)
    stats = current_stats(chapters)

    if mode == "exam":
        return _select_exam([q for q in questions if q.status == "verified"], count, rng)

    if mode == "review":
        latest: dict[str, dict] = {}
        for a in tracker.all_attempts(exclude_questions=pool.retired_ids(CHAPTERS)):
            latest[a["question_id"]] = a
        by_id = {q.id: q for q in questions}
        missed = [a for a in latest.values() if not a["correct"] and a["question_id"] in by_id]
        missed.sort(key=lambda a: a["answered_at"], reverse=True)
        return [by_id[a["question_id"]] for a in missed[:count]]

    groups = _by_objective(questions)
    if mode == "diagnostic":
        # One question per objective, preferring ones never attempted.
        picked = [_pick_for_objective(qs, stats.get(obj), rng) for obj, qs in groups.items()]
        rng.shuffle(picked)
        return picked[:count]

    # Targeted drill: weighted toward Weak objectives, with spaced revisits of Solid ones.
    def weight(obj: str) -> float:
        s = stats.get(obj)
        if s is None:
            return DRILL_WEIGHTS["New"]
        if s.status == "Solid":
            return DRILL_WEIGHTS["Solid-due"] if s.revisit_due() else DRILL_WEIGHTS["Solid"]
        return DRILL_WEIGHTS[s.status]

    remaining = {obj: weight(obj) for obj in groups}
    picked: list[Question] = []
    while remaining and len(picked) < count:
        objs = list(remaining)
        obj = rng.choices(objs, weights=[remaining[o] for o in objs])[0]
        del remaining[obj]
        picked.append(_pick_for_objective(groups[obj], stats.get(obj), rng))
    return picked


def _select_exam(verified: list[Question], count: int, rng: random.Random) -> list[Question]:
    """Blueprint-weighted (estimated) selection across the domains that have verified questions."""
    buckets = defaultdict(list)
    for q in verified:
        buckets[q.domain].append(q)
    for qs in buckets.values():
        rng.shuffle(qs)
    count = min(count, len(verified))
    weights = {d: DOMAIN_WEIGHTS.get(d, UNTAGGED_WEIGHT) for d in buckets}
    alloc = {d: 0 for d in buckets}
    # Largest-remainder allocation, re-run while any bucket runs out of questions.
    left = count
    open_buckets = set(buckets)
    while left and open_buckets:
        total = sum(weights[d] for d in open_buckets)
        shares = {d: left * weights[d] / total for d in open_buckets}
        give = {d: int(shares[d]) for d in open_buckets}
        for d in sorted(open_buckets, key=lambda d: shares[d] - give[d], reverse=True)[: left - sum(give.values())]:
            give[d] += 1
        for d in list(open_buckets):
            take = min(give[d], len(buckets[d]) - alloc[d])
            alloc[d] += take
            left -= take
            if alloc[d] >= len(buckets[d]):
                open_buckets.discard(d)
    picked = [q for d, n in alloc.items() for q in buckets[d][:n]]
    rng.shuffle(picked)
    return picked


# ---- reports --------------------------------------------------------------

def _pct(c: int, n: int) -> float | None:
    return round(100 * c / n, 1) if n else None


def session_report(session: dict) -> dict:
    attempts = {a["question_id"]: a for a in tracker.session_attempts(session["id"])}
    questions = {q.id: q for q in pool.active(session["chapters"]) + _retired_in(session)}
    by_domain = defaultdict(lambda: [0, 0])
    by_objective = defaultdict(lambda: [0, 0])
    items = []
    for qid in session["question_ids"]:
        q = questions.get(qid)
        a = attempts.get(qid)
        if q is None:
            continue
        ok = bool(a and a["correct"])
        if a:
            by_domain[q.domain or "untagged"][0] += 1
            by_domain[q.domain or "untagged"][1] += ok
            by_objective[q.objectives[0]][0] += 1
            by_objective[q.objectives[0]][1] += ok
        items.append({"question": question_full(q), "attempt": a, "correct": ok})
    answered = sum(1 for qid in session["question_ids"] if qid in attempts)
    correct = sum(1 for a in attempts.values() if a["correct"])
    return {
        "session": session,
        "answered": answered,
        "total": len(session["question_ids"]),
        "correct": correct,
        "percent": _pct(correct, len(session["question_ids"]) if session["mode"] == "exam" else answered),
        "by_domain": {d: {"answered": n, "correct": c, "percent": _pct(c, n)} for d, (n, c) in sorted(by_domain.items())},
        "by_objective": {o: {"answered": n, "correct": c} for o, (n, c) in sorted(by_objective.items())},
        "items": items,
        "weights_note": "Exam domain weights are estimates; Cisco does not publish them." if session["mode"] == "exam" else None,
    }


def _retired_in(session: dict) -> list[Question]:
    return [q for ch in session["chapters"] for q in pool.load(ch)
            if q.status == "retired" and q.id in session["question_ids"]]


def question_public(q: Question) -> dict:
    """What the browser sees before answering: no answer, rationales, or objective IDs."""
    return {"id": q.id, "type": q.type, "status": q.status, "stem": q.stem, "exhibit": q.exhibit,
            "choose": len(q.answer) if q.type == "multi" else 1,
            "options": [{"key": o.key, "text": o.text} for o in q.options]}


def question_full(q: Question) -> dict:
    return {**question_public(q), "answer": q.answer, "options": [o.model_dump() for o in q.options],
            "explanation": q.explanation, "discriminator_tested": q.discriminator_tested,
            "objectives": q.objectives, "angle": q.angle, "difficulty": q.difficulty, "domain": q.domain,
            "provider": q.provider, "model": q.model, "retired_reason": q.retired_reason}


# ---- export summary (8.5) -----------------------------------------------

def objective_names() -> dict[str, str]:
    names = {}
    for n in CHAPTERS:
        try:
            names.update({o.id: o.objective for o in load_chapter(n).objectives.values()})
        except (OSError, ValueError):
            continue
    return names


def export_summary() -> str:
    session = tracker.last_finished_session()
    retired = pool.flawed_ids(CHAPTERS)
    after = tracker.objective_stats(tracker.all_attempts(exclude_questions=retired))
    names = objective_names()
    date = datetime.now(timezone.utc).date().isoformat()
    lines = [f"CCST export {date}"]
    if session:
        rep = session_report(session)
        chs = ", ".join(f"Ch{c}" for c in session["chapters"])
        denom = rep["total"] if session["mode"] == "exam" else rep["answered"]
        lines.append(f"Last session: {session['mode']} ({chs}), {rep['correct']}/{denom} correct"
                     + (f" ({rep['percent']}%)" if rep["percent"] is not None else "")
                     + (f", {rep['answered']} of {rep['total']} answered" if session["mode"] == "exam" else ""))
        before = tracker.objective_stats(tracker.all_attempts(exclude_questions=retired, exclude_session=session["id"]))
        newly_solid = sorted(o for o, s in after.items()
                             if s.status == "Solid" and (o not in before or before[o].status != "Solid"))
    else:
        lines.append("Last session: none finished yet")
        newly_solid = []

    # Per-domain accuracy over the last five answers of each objective.
    dom = defaultdict(lambda: [0, 0])
    domain_of = {q.objectives[0]: q.domain for q in pool.active(CHAPTERS)}
    for o, s in after.items():
        d = domain_of.get(o) or "untagged"
        dom[d][0] += len(s.last5)
        dom[d][1] += sum(s.last5)
    if dom:
        lines.append("Domains (recent): " + " | ".join(f"{d} {_pct(c, n)}% ({n})" for d, (n, c) in sorted(dom.items())))

    weak = sorted((s for s in after.values() if s.status == "Weak"),
                  key=lambda s: (-s.sure_wrong_recent, s.last5_accuracy or 0))
    if weak:
        lines.append("Weak: " + "; ".join(
            f"{s.objective} {names.get(s.objective, '')}".strip()
            + (f" [{s.errors.most_common(1)[0][0]}]" if s.errors else "")
            + (" [sure-but-wrong]" if s.sure_wrong_recent else "")
            for s in weak[:8]))
    else:
        lines.append("Weak: none")
    lines.append("Newly Solid: " + (", ".join(newly_solid) if newly_solid else "none"))
    due = [o for o, s in after.items() if s.revisit_due()]
    focus = [s.objective for s in weak[:5]] + due[: max(0, 5 - len(weak))]
    lines.append("Next focus: " + (("targeted drill on " + ", ".join(focus)) if focus
                                   else "diagnostic on an unstarted chapter, or an exam simulation"))
    return "\n".join(lines)
