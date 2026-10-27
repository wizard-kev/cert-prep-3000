"""Progress over time (v2 plan 8.3) and recommendations to generate more questions (V11). Everything
here is derived from the recorded answers, like objective status. Answers to flawed or disputed
questions are left out, as everywhere else."""

from collections import Counter, defaultdict
from statistics import mean

from . import certs, pool, tracker
from .objectives import find_objective, load_sections

STATUSES = ("Weak", "Improving", "Solid", "New")
WEAK_AFTER = 3  # answers before a Weak objective is suggested for new questions
REASONS = ("weak", "too-easy", "no-unseen")


def _answers(cert_id: str) -> list[dict]:
    return tracker.all_attempts(cert_id, exclude_questions=pool.flawed_ids(cert_id))


def _average(stats: list[tracker.ObjectiveStats]) -> int | None:
    return round(mean(s.score for s in stats)) if stats else None


def _totals(objective_ids: list[str], stats: dict[str, tracker.ObjectiveStats]) -> dict:
    practised = [stats[o] for o in objective_ids if o in stats]
    counts = Counter(s.status for s in practised)
    return {"objectives": len(objective_ids), "practised": len(practised), "score": _average(practised),
            **{k: counts.get(k, 0) for k in STATUSES[:3]}, "New": len(objective_ids) - len(practised)}


def overview(cert_id: str) -> dict:
    """Where the learner stands now and how they got there: totals, scores by section and domain,
    calibration, and objective status counts after each session."""
    cert = certs.get_cert(cert_id)
    sections = load_sections(cert_id)
    known = {o.id for s in sections for o in s.objectives.values()}
    answers = [a for a in _answers(cert_id) if a["objective"] in known]
    modes = tracker.session_modes(cert_id)
    last_of = {a["session_id"]: i for i, a in enumerate(answers)}

    stats: dict[str, tracker.ObjectiveStats] = {}
    timeline = []
    for i, a in enumerate(answers):
        stats.setdefault(a["objective"], tracker.ObjectiveStats(a["objective"])).add(a)
        if last_of[a["session_id"]] == i:  # the session's last answer: take a snapshot
            counts = Counter(s.status for s in stats.values())
            timeline.append({"at": a["answered_at"], "session_id": a["session_id"],
                             "mode": modes.get(a["session_id"], ""),
                             **{k: counts.get(k, 0) for k in STATUSES[:3]}, "New": len(known) - len(stats),
                             "score": _average(list(stats.values()))})

    calibration = []
    for c in tracker.CONFIDENCE:
        rows = [a for a in answers if a["confidence"] == c]
        right = sum(bool(a["correct"]) for a in rows)
        calibration.append({"confidence": c, "label": tracker.CONFIDENCE_LABELS[c], "answered": len(rows),
                            "correct": right, "percent": round(100 * right / len(rows), 1) if rows else None})

    by_section = [{"code": s.code, "name": s.name, "domain": s.domain, **_totals(list(s.objectives), stats)}
                  for s in sections]
    domain_ids: dict[str, list[str]] = defaultdict(list)
    for s in sections:
        domain_ids[s.domain or "untagged"] += list(s.objectives)
    order = [d.id for d in cert.domains] + ["untagged"]
    domain_names = {d.id: d.name for d in cert.domains}
    by_domain = [{"id": d, "name": domain_names.get(d, "No domain"), **_totals(domain_ids[d], stats)}
                 for d in order if d in domain_ids]

    return {"totals": {**_totals(sorted(known), stats), "answers": len(answers)},
            "timeline": timeline, "calibration": calibration, "by_section": by_section, "by_domain": by_domain}


def objective_history(cert_id: str, objective_id: str) -> dict:
    """One objective's score and status after each answer, oldest first."""
    section, objective = find_objective(cert_id, objective_id)
    s = tracker.ObjectiveStats(objective.id)
    points = []
    for a in _answers(cert_id):
        if a["objective"] != objective.id:
            continue
        s.add(a)
        points.append({"at": a["answered_at"], "question_id": a["question_id"], "correct": bool(a["correct"]),
                       "confidence": a["confidence"], "answer_score": tracker.answer_score(bool(a["correct"]), a["confidence"]),
                       "score": s.score, "status": s.status})
    return {"objective": objective.id, "name": objective.objective, "section": section.code, "points": points}


def recommendations(cert_id: str) -> list[dict]:
    """Practised objectives that would gain from new questions (V11), most urgent first:
    - weak: still Weak after WEAK_AFTER or more answers;
    - too-easy: the latest TOO_EASY_STREAK answers were all correct at Certain;
    - no-unseen: every question on it has been answered at least once."""
    stats = tracker.objective_stats(_answers(cert_id))
    served = defaultdict(list)
    for q in pool.active(cert_id):
        served[q.objectives[0]].append(q)
    out = []
    for section in load_sections(cert_id):
        for o in section.objectives.values():
            st = stats.get(o.id)
            if st is None:
                continue
            unseen = sum(1 for q in served[o.id] if not q.seen_at)
            reasons = [r for r, hit in (("weak", st.status == "Weak" and st.attempts >= WEAK_AFTER),
                                        ("too-easy", st.certain_streak >= tracker.TOO_EASY_STREAK),
                                        ("no-unseen", unseen == 0)) if hit]
            if reasons:
                out.append({"objective": o.id, "name": o.objective, "section": section.code, "status": st.status,
                            "score": st.score, "attempts": st.attempts, "questions": len(served[o.id]),
                            "unseen": unseen, "reasons": reasons,
                            "dominant_error": st.errors.most_common(1)[0][0] if st.errors else None})
    # Weak first, then too easy, then the rest; within each, a Solid objective last and the lowest score first.
    return sorted(out, key=lambda r: (REASONS.index(r["reasons"][0]), r["status"] == "Solid", r["score"]))
