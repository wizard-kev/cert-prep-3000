"""Surface-cue audit of a pool: how far can a test-wise reader get without knowing the material?
Run after each import: python -m certprep.cli audit --sections C01"""

from collections import Counter
from statistics import mean

from . import pool
from .generator import _ABSOLUTE, _echo_words, objective_terms
from .objectives import load_section


def audit(cert_id: str, sections: list[str]) -> dict:
    singles = longest = shortest = abs_only = echo_top = 0
    ratios = []
    multi = multi_longest = 0
    which_not = exhibits = names_term = 0
    roles, difficulty = Counter(), Counter()
    total = 0
    for code in sections:
        names = {o.id: o.objective for o in load_section(cert_id, code).objectives.values()}
        for q in pool.active(cert_id, [code]):
            total += 1
            difficulty[q.difficulty] += 1
            which_not += q.angle == "which-is-not"
            exhibits += bool(q.exhibit)
            roles.update(o.role or "untagged" for o in q.options)
            # The stem names the primary objective, so the learner never has to recognise it.
            terms = objective_terms(names.get(q.objectives[0], ""))
            names_term += bool(terms & _echo_words(q.stem))
            lens = {o.key: len(o.text.strip()) for o in q.options}
            others = [v for k, v in lens.items() if k not in q.answer]
            if q.type == "single":
                singles += 1
                a = lens[q.answer[0]]
                longest += a > max(others)
                shortest += a < min(others)
                ratios.append(a / mean(others))
                texts = {o.key: o.text for o in q.options}
                if not _ABSOLUTE.search(texts[q.answer[0]]) and any(
                        _ABSOLUTE.search(t) for k, t in texts.items() if k != q.answer[0]):
                    abs_only += 1
                stem = _echo_words(q.stem)
                echo = {k: len(stem & _echo_words(t)) for k, t in texts.items()}
                echo_top += echo[q.answer[0]] > max(v for k, v in echo.items() if k != q.answer[0])
            else:
                multi += 1
                ranked = sorted(lens, key=lens.get, reverse=True)
                multi_longest += set(q.answer) == set(ranked[:len(q.answer)])
    return {
        "questions": total, "single": singles, "multi": multi,
        "answer_longest": longest, "answer_shortest": shortest,
        "length_ratio": round(mean(ratios), 2) if ratios else None,
        "absolute_only_in_distractors": abs_only, "answer_echoes_stem_most": echo_top,
        "multi_answers_are_longest": multi_longest, "which_is_not": which_not, "exhibits": exhibits,
        "stem_names_objective": names_term, "roles": dict(roles), "difficulty": dict(sorted(difficulty.items())),
    }


def _pct(n: int, d: int) -> str:
    return f"{n} ({n / d:.0%})" if d else "0"


# Pool-level bands. Per-question checks keep the answer from standing out; these keep the pool from
# teaching a habit (e.g. "the answer is never the shortest", which a skewed fix would create).
BANDS = {
    "answer_longest": (0.15, 0.35),      # of single-answer questions; uniform is 25%
    "answer_shortest": (0.15, 0.35),
    "multi_answers_are_longest": (0.0, 0.20),  # of multi-select; uniform for 2 of 5 is 10%
    "absolute_only_in_distractors": (0.0, 0.05),
    "answer_echoes_stem_most": (0.0, 0.15),
}


def cue_failures(r: dict) -> list[str]:
    out = []
    for key, (lo, hi) in BANDS.items():
        denom = r["multi"] if key.startswith("multi") else r["single"]
        if not denom:
            continue
        share = r[key] / denom
        if not lo <= share <= hi:
            out.append(f"{key} {share:.0%} outside {lo:.0%}-{hi:.0%}")
    return out


def print_audit(cert_id: str, sections: list[str]) -> bool:
    r = audit(cert_id, sections)
    s = r["single"]
    print(f"{cert_id} {', '.join(sections)}: {r['questions']} active ({s} single, {r['multi']} multi)")
    print(f"  answer is the longest option:   {_pct(r['answer_longest'], s)}  (no cue: about 25%)")
    print(f"  answer is the shortest option:  {_pct(r['answer_shortest'], s)}  (no cue: about 25%)")
    print(f"  answer length / distractor mean: {r['length_ratio']}x  (no cue: about 1.0x)")
    print(f"  absolutes only in distractors:  {_pct(r['absolute_only_in_distractors'], s)}")
    print(f"  answer echoes the stem most:    {_pct(r['answer_echoes_stem_most'], s)}")
    print(f"  multi answers = longest options: {_pct(r['multi_answers_are_longest'], r['multi'])}  (no cue: 10%)")
    print(f"  stem names its objective:       {_pct(r['stem_names_objective'], r['questions'])}")
    print(f"  which-is-NOT questions:         {r['which_is_not']} | exhibits: {r['exhibits']}")
    print(f"  option roles: {r['roles']} | difficulty: {r['difficulty']}")
    failures = cue_failures(r)
    print("  cue bands: " + ("PASS" if not failures else "FAIL: " + "; ".join(failures)))
    return not failures
