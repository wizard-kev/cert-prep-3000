"""Question selection per mode (v2 plan section 7), score reports, and the export summary (8.5).
Exam length, timer, domain weights, and pass mark come from the certification's cert.json."""

import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import certs, pool, tracker
from .objectives import objective_names
from .schema import STATUS_LABELS, Question

DEFAULT_EXAM_MINUTES = 60
DEFAULT_EXAM_QUESTIONS = 40
DEFERRED_FEEDBACK = {"exam", "diagnostic"}  # feedback withheld until the end (diagnostic: v1 sessions)
MODE_LABELS = {"practice": "Practice", "focus": "Focus", "exam": "Exam simulation",
               "diagnostic": "Diagnostic (retired mode)", "drill": "Targeted drill (now Practice)",
               "review": "Review misses (now part of Practice)"}
# Practice weights per objective status: weak objectives most, then improving and due solid ones.
PRACTICE_WEIGHTS = {"Weak": 8.0, "Improving": 3.0, "Solid-due": 3.0, "New": 2.0, "Solid": 0.2}
NEW_SHARE = 0.2      # at least this share of a practice session goes to objectives never practiced
MISSED_SHARE = 0.3   # up to this share re-serves questions missed earlier, once their wait is over
MISS_WAIT_DAYS = (1, 3, 7)  # wait after the 1st, 2nd, and 3rd-or-later miss in a row


def exam_defaults(cert: certs.Cert) -> dict:
    """Question count and minutes for an exam simulation: the certification's facts when known."""
    def number(fact: certs.Fact, default: int) -> int:
        return int(fact.value) if isinstance(fact.value, (int, float)) and fact.value > 0 else default
    return {"questions": number(cert.exam.question_count, DEFAULT_EXAM_QUESTIONS),
            "minutes": number(cert.exam.minutes, DEFAULT_EXAM_MINUTES)}


def pass_mark(cert: certs.Cert) -> float | None:
    """Pass mark as a percentage, if the certification publishes one as a percentage. Scaled scores
    (e.g. 750 of 900) can't be converted, so there is no pass/fail estimate for them."""
    v = cert.exam.passing_score.value
    return float(v) if isinstance(v, (int, float)) and 0 < v <= 100 else None


def current_stats(cert_id: str) -> dict[str, tracker.ObjectiveStats]:
    flawed = pool.flawed_ids(cert_id)  # answers to flawed or disputed questions don't count; superseded ones do
    return tracker.objective_stats(tracker.all_attempts(cert_id, exclude_questions=flawed))


def _by_objective(questions: list[Question]) -> dict[str, list[Question]]:
    out = defaultdict(list)
    for q in questions:
        out[q.objectives[0]].append(q)
    return out


def _pick_for_objective(candidates: list[Question], stats: tracker.ObjectiveStats | None,
                        rng: random.Random) -> Question:
    """Avoid the angle and the questions seen most recently for this objective (section 10.1), and
    prefer questions not yet answered, so practice also reviews new questions."""
    last_angle = stats.last_angle if stats else None
    recent = set(stats.recent_questions) if stats else set()

    def score(q: Question):
        return (q.angle == last_angle, q.id in recent, q.seen_at is not None, rng.random())

    return min(candidates, key=score)


def _due_misses(cert_id: str, served: dict[str, Question], now: datetime) -> list[Question]:
    """Questions whose latest answer was wrong, once their wait is over (longer after repeated
    misses), oldest first. This is what the v1 "Review misses" mode did, now inside Practice."""
    history: dict[str, list[dict]] = defaultdict(list)
    for a in tracker.all_attempts(cert_id, exclude_questions=pool.inactive_ids(cert_id)):
        history[a["question_id"]].append(a)
    due = []
    for qid, rows in history.items():
        if qid not in served or rows[-1]["correct"]:
            continue
        misses = 0
        for a in reversed(rows):
            if a["correct"]:
                break
            misses += 1
        wait = timedelta(days=MISS_WAIT_DAYS[min(misses, len(MISS_WAIT_DAYS)) - 1])
        last = datetime.fromisoformat(rows[-1]["answered_at"])
        if now - last >= wait:
            due.append((last, served[qid]))
    return [q for _, q in sorted(due, key=lambda x: x[0])]


FOCUS_ORDER = {"Weak": 0, "New": 1, "Improving": 2, "Solid": 3}


def select_focus(cert_id: str, objective_ids: list[str], count: int, rng: random.Random | None = None) -> list[Question]:
    """Questions on the chosen objectives only (plan 7.2): taken in turns across the objectives, weakest
    first and preferring questions not yet answered, so a short session still covers the weak ones.
    More than one question per objective when the count allows."""
    rng = rng or random.Random()
    wanted = set(objective_ids)
    left = _by_objective([q for q in pool.active(cert_id) if q.objectives[0] in wanted])
    stats = current_stats(cert_id)

    def rank(o: str):
        s = stats.get(o)
        return (FOCUS_ORDER[s.status if s else "New"], s.score if s and s.score is not None else 0, rng.random())

    order = sorted(left, key=rank)
    picked: list[Question] = []
    while len(picked) < count and any(left.values()):
        for o in order:
            if len(picked) < count and left[o]:
                q = _pick_for_objective(left[o], stats.get(o), rng)
                left[o].remove(q)
                picked.append(q)
    rng.shuffle(picked)
    return picked


def select(cert_id: str, mode: str, sections: list[str], count: int,
           rng: random.Random | None = None, now: datetime | None = None) -> list[Question]:
    rng = rng or random.Random()
    now = now or datetime.now(timezone.utc)
    questions = pool.active(cert_id, sections)
    if mode == "exam":
        return _select_exam(certs.get_cert(cert_id), questions, count, rng)
    return _select_practice(cert_id, questions, count, rng, now)


def _select_practice(cert_id: str, questions: list[Question], count: int, rng: random.Random,
                     now: datetime) -> list[Question]:
    """Missed questions that are due, a share of never-practiced objectives, then the rest weighted
    toward weak objectives. One question per objective per session."""
    stats = current_stats(cert_id)
    groups = _by_objective(questions)
    picked: list[Question] = []
    used: set[str] = set()

    def take(q: Question):
        picked.append(q)
        used.add(q.objectives[0])

    for q in _due_misses(cert_id, {q.id: q for q in questions}, now):
        if len(picked) >= max(1, int(count * MISSED_SHARE)):
            break
        if q.objectives[0] not in used:
            take(q)

    new = [o for o in groups if o not in stats and o not in used]
    rng.shuffle(new)
    for obj in new[:max(1, round(count * NEW_SHARE))]:
        if len(picked) < count:
            take(_pick_for_objective(groups[obj], None, rng))

    def weight(obj: str) -> float:
        s = stats.get(obj)
        if s is None:
            return PRACTICE_WEIGHTS["New"]
        if s.status == "Solid":
            return PRACTICE_WEIGHTS["Solid-due"] if s.revisit_due(now) else PRACTICE_WEIGHTS["Solid"]
        return PRACTICE_WEIGHTS[s.status]

    remaining = {obj: weight(obj) for obj in groups if obj not in used}
    while remaining and len(picked) < count:
        objs = list(remaining)
        obj = rng.choices(objs, weights=[remaining[o] for o in objs])[0]
        del remaining[obj]
        take(_pick_for_objective(groups[obj], stats.get(obj), rng))
    rng.shuffle(picked)
    return picked


def _select_exam(cert: certs.Cert, served: list[Question], count: int, rng: random.Random) -> list[Question]:
    """Selection across the domains that have questions, weighted by cert.json, preferring
    questions the learner hasn't answered before (repeats inflate the score)."""
    buckets = defaultdict(list)
    for q in served:
        buckets[q.domain].append(q)
    for qs in buckets.values():
        rng.shuffle(qs)
        qs.sort(key=lambda q: q.seen_at is not None)  # stable: unseen first, otherwise random
    count = min(count, len(served))
    weights = {d: cert.domain_weight(d) for d in buckets}
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


def _score(correct: int, total: int) -> dict:
    return {"correct": correct, "total": total, "percent": _pct(correct, total)}


def _confirmed_dispute(q: Question) -> bool:
    return q.status == "retired" and (q.retired_reason or "").startswith(pool.REPORTED_PREFIX)


def _validated_before(q: Question, when: str) -> bool:
    """Passively-Validated or Validated when the session started."""
    return bool((q.seen_at and q.seen_at < when) or (q.verified_at and q.verified_at < when))


def session_report(session: dict) -> dict:
    """Scores leave out questions whose dispute was confirmed, and questions still disputed. In an
    exam, unanswered questions count as wrong; in practice, scores are out of the answered ones."""
    cert = certs.get_cert(session["cert_id"])
    exam = session["mode"] == "exam"
    started = session["started_at"]
    attempts = {a["question_id"]: a for a in tracker.session_attempts(session["id"])}
    held = tracker.held_disputes(session["id"])
    ids = set(session["question_ids"])
    questions = {q.id: q for q in pool.all_questions(cert.id, session["sections"]) if q.id in ids}
    by_domain = defaultdict(lambda: [0, 0])
    by_objective = defaultdict(lambda: [0, 0])
    tallies = {k: [0, 0] for k in ("all", "validated", "new", "repeat")}  # [correct, counted]
    items, disputes, excluded = [], [], []
    for qid in session["question_ids"]:
        q = questions.get(qid)
        if q is None:
            continue
        a = attempts.get(qid)
        ok = bool(a and a["correct"])
        out_of_score = _confirmed_dispute(q) or q.status == "disputed"
        if out_of_score:
            excluded.append(qid)
        elif a or exam:
            seen_before = bool(q.seen_at and q.seen_at < started)
            keys = ["all", "repeat" if seen_before else "new"] + (["validated"] if _validated_before(q, started) else [])
            for k in keys:
                tallies[k][0] += ok
                tallies[k][1] += 1
            if a:
                by_domain[q.domain or "untagged"][0] += 1
                by_domain[q.domain or "untagged"][1] += ok
                by_objective[q.objectives[0]][0] += 1
                by_objective[q.objectives[0]][1] += ok
        if qid in held:
            disputes.append({"question": question_full(q), "reason": held[qid]["reason"],
                             "decision": held[qid]["decision"], "held": True})
        elif q.status == "disputed" and q.disputed_session == session["id"]:
            disputes.append({"question": question_full(q), "reason": q.disputed_reason, "decision": None, "held": False})
        items.append({"question": question_full(q), "attempt": a, "correct": ok, "excluded": out_of_score})
    scores = {k: _score(c, n) for k, (c, n) in tallies.items()}
    mark = pass_mark(cert) if exam else None
    weights_note = None
    if exam and cert.weights.confidence != "official":
        weights_note = cert.weights.note or "Domain weights are estimates."
    return {
        "session": session,
        "mode_label": MODE_LABELS.get(session["mode"], session["mode"]),
        "answered": sum(1 for qid in session["question_ids"] if qid in attempts),
        "total": len(session["question_ids"]),
        "correct": scores["all"]["correct"],
        "percent": scores["all"]["percent"],
        "scores": scores,
        "excluded": excluded,
        "pass_mark": mark,
        "passed": (scores["all"]["percent"] >= mark) if mark is not None and scores["all"]["percent"] is not None else None,
        "pass_note": None if not exam or mark is not None else (
            "No pass/fail estimate: " + (cert.exam.passing_score.note or "the passing score isn't published as a percentage.")),
        "disputes": disputes,
        "by_domain": {d: {"answered": n, "correct": c, "percent": _pct(c, n)} for d, (n, c) in sorted(by_domain.items())},
        "by_objective": {o: {"answered": n, "correct": c} for o, (n, c) in sorted(by_objective.items())},
        "items": items,
        "weights_note": weights_note,
    }


def question_public(q: Question) -> dict:
    """What the browser sees before answering: no answer, rationales, or objective IDs."""
    return {"id": q.id, "type": q.type, "status": q.status, "status_label": STATUS_LABELS[q.status],
            "stem": q.stem, "exhibit": q.exhibit, "choose": len(q.answer) if q.type == "multi" else 1,
            "options": [{"key": o.key, "text": o.text} for o in q.options],
            **({"match_targets": q.match_targets} if q.type == "matching" else {})}


def answer_problem(q: Question, selected: list[str]) -> str | None:
    """Why an answer doesn't fit its question's format (None if it does). Wrong answers are fine;
    malformed ones are refused."""
    keys = [o.key for o in q.options]
    if q.type == "matching":
        pairs = {s[0]: s[1:] for s in selected}
        if len(selected) != len(keys) or sorted(pairs) != sorted(keys) or \
                any(not n.isdigit() or not 1 <= int(n) <= len(q.match_targets or []) for n in pairs.values()):
            return "match every item with one of the descriptions"
        return None
    if any(len(s) != 1 or s not in keys for s in selected) or len(set(selected)) != len(selected):
        return "the answer uses options this question doesn't have"
    if q.type == "ordering" and len(selected) != len(keys):
        return "put every step in order"
    if q.type == "single" and len(selected) != 1:
        return "choose one option"
    return None


def question_full(q: Question) -> dict:
    return {**question_public(q), "answer": q.answer, "options": [o.model_dump() for o in q.options],
            "explanation": q.explanation, "discriminator_tested": q.discriminator_tested,
            "objectives": q.objectives, "angle": q.angle, "difficulty": q.difficulty, "domain": q.domain,
            "provider": q.provider, "model": q.model, "retired_reason": q.retired_reason,
            "disputed_reason": q.disputed_reason}


# ---- export summary (8.5) -----------------------------------------------

def export_summary(cert_id: str) -> str:
    cert = certs.get_cert(cert_id)
    session = tracker.last_finished_session(cert_id)
    retired = pool.flawed_ids(cert_id)
    after = tracker.objective_stats(tracker.all_attempts(cert_id, exclude_questions=retired))
    names = objective_names(cert_id)
    date = datetime.now(timezone.utc).date().isoformat()
    lines = [f"{cert.short_name} export {date}"]
    if session:
        rep = session_report(session)
        secs = ", ".join(session["sections"])
        all_ = rep["scores"]["all"]
        lines.append(f"Last session: {session['mode']} ({secs}), {all_['correct']}/{all_['total']} correct"
                     + (f" ({all_['percent']}%)" if all_["percent"] is not None else "")
                     + (f", {rep['answered']} of {rep['total']} answered" if session["mode"] == "exam" else ""))
        before = tracker.objective_stats(tracker.all_attempts(cert_id, exclude_questions=retired,
                                                              exclude_session=session["id"]))
        newly_solid = sorted(o for o, s in after.items()
                             if s.status == "Solid" and (o not in before or before[o].status != "Solid"))
    else:
        lines.append("Last session: none finished yet")
        newly_solid = []

    # Per-domain accuracy over the last five answers of each objective.
    dom = defaultdict(lambda: [0, 0])
    domain_of = {q.objectives[0]: q.domain for q in pool.active(cert_id)}
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
    lines.append("Next focus: " + (("practice on " + ", ".join(focus)) if focus
                                   else "practice on an unstarted section, or an exam simulation"))
    return "\n".join(lines)
