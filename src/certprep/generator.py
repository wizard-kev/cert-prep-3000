"""Question import: validate authored questions, check them for surface cues, shuffle the
options, and store them as draft. `plan_targets` picks the objectives and angles a new batch
should cover."""

import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean

from pydantic import ValidationError

from . import pool
from .objectives import Section, load_section
from .schema import EXHIBIT_MAX_LINES, GENERIC_ANGLES, GeneratedQuestion, Question

MULTI_SHARE = 0.25
NEAR_DUPLICATE = 0.8


@dataclass
class Target:
    objective: str
    angle: str
    type: str


@dataclass
class BatchResult:
    requested: int
    accepted: list[Question] = field(default_factory=list)
    accepted_index: list[int] = field(default_factory=list)  # position of each accepted question in the input
    rejected: list[dict] = field(default_factory=list)       # each has "index", "target", "problems"
    model: str = ""

    def summary(self) -> dict:
        return {
            "requested": self.requested,
            "accepted": [q.id for q in self.accepted],
            "rejected": self.rejected,
            "model": self.model,
        }


def plan_targets(section: Section, existing: list[Question], n: int, rng: random.Random) -> list[Target]:
    """Least-covered objectives first; never repeat an objective's previous angle (section 10.1)."""
    cover = pool.coverage(existing)
    last = pool.last_angle(existing)
    angles_used: dict[str, Counter] = {}
    for q in existing:
        angles_used.setdefault(q.objectives[0], Counter())[q.angle] += 1

    ids = list(section.objectives)
    rng.shuffle(ids)
    ids.sort(key=lambda i: cover[i])
    targets = []
    for obj_id in ids[:n]:
        choices = [a for a in GENERIC_ANGLES if a != last.get(obj_id)]
        used = angles_used.get(obj_id, Counter())
        fewest = min(used[a] for a in choices)
        angle = rng.choice([a for a in choices if used[a] == fewest])
        qtype = "multi" if rng.random() < MULTI_SHARE else "single"
        targets.append(Target(obj_id, angle, qtype))
    return targets


EXTRA_TYPE_ANGLES = {"ordering": "cause-and-effect-ordering", "matching": "classify-element"}


def _pick_type(rng: random.Random, extra_types: dict[str, float]) -> str:
    """single or multi; ordering and matching only for certifications whose exam uses them."""
    if extra_types:
        r, total = rng.random(), 0.0
        for qtype, share in extra_types.items():
            total += share
            if r < total:
                return qtype
    return "multi" if rng.random() < MULTI_SHARE else "single"


def targets_for(objective_ids: list[str], existing: list[Question], per_objective: int, angles: list[str],
                rng: random.Random, extra_types: dict[str, float] | None = None) -> list[Target]:
    """Targets for chosen objectives: `per_objective` each, every one on the angle the objective's
    questions have used least (never the newest active one), so new questions add variety. Retired
    questions count as used too: a replacement for a reported question takes a different approach.
    An ordering or matching target takes the angle that suits its format."""
    active = [q for q in existing if q.served]
    last = pool.last_angle(active)
    used: dict[str, Counter] = {}
    for q in existing:
        used.setdefault(q.objectives[0], Counter())[q.angle] += 1
    targets = []
    for obj_id in objective_ids:
        counts = Counter(used.get(obj_id, Counter()))
        for _ in range(per_objective):
            choices = [a for a in angles if a != last.get(obj_id)] or list(angles)
            fewest = min(counts[a] for a in choices)
            angle = rng.choice([a for a in choices if counts[a] == fewest])
            qtype = _pick_type(rng, extra_types or {})
            if qtype in EXTRA_TYPE_ANGLES and EXTRA_TYPE_ANGLES[qtype] in angles:
                angle = EXTRA_TYPE_ANGLES[qtype]
            counts[angle] += 1
            targets.append(Target(obj_id, angle, qtype))
    return targets


_WORD = re.compile(r"[a-z0-9]+")
# The keyword is case-insensitive but the letter must be a capital, so "answers a SYN" is not a hit.
_LETTER_REF = re.compile(r"\b(?i:option|answer|choice)s?\s+\(?[A-F]\)?(?![A-Za-z])|\([A-F]\)")
_BOOK_REF = re.compile(r"\b(?:according to|per) the (?:book|text|study guide|chapter)\b", re.I)
_CHOOSE = re.compile(r"\((?:choose|select) (two|three|2|3)\.?\)", re.I)
_COUNTS = {"two": 2, "2": 2, "three": 3, "3": 3}
# Surface cues (v2 pools): words a test-wise reader uses to eliminate options without knowing the topic.
_ABSOLUTE = re.compile(r"\b(?:always|never|only|all|every|none|cannot|can't|impossible|guarantee[sd]?|completely|entirely)\b", re.I)
# A "partial" (technically correct) option is fair only if the stem asks for the best one.
_QUALIFIER = re.compile(r"\b(?:best|most|first|primary|primarily|least|main|mainly|greatest|strongest|"
                        r"recommended|preferred|next|minimum)\b|\baccording to\b", re.I)
_ECHO_STOP = {"the", "and", "for", "with", "that", "this", "from", "which", "what", "when", "why", "how",
              "does", "not", "are", "was", "its", "has", "have", "into", "than", "then", "they", "their", "but"}
LENGTH_RATIO = 1.25   # answer vs mean distractor length
LONGEST_RATIO = 1.15  # single answer vs the longest distractor
LENGTH_SLACK = 6      # characters, so short option texts aren't held to a strict ratio
ECHO_MARGIN = 2       # stem words the answer may share beyond the best-echoing distractor


def _words(s: str) -> set[str]:
    return set(_WORD.findall(s.lower()))


def _similar(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def content_words(q) -> set[str]:
    """Stem plus option texts: short templated stems ("Which statement about X is NOT true?")
    differ only in their options, so duplicates are judged on both."""
    return _words(" ".join([q.stem] + [o.text for o in q.options] + list(q.match_targets or [])))


def _echo_words(s: str) -> set[str]:
    return {w for w in _words(s) if len(w) > 2 and w not in _ECHO_STOP}


def cue_problems(q: GeneratedQuestion) -> list[str]:
    """Surface cues that give the answer away without knowing the material (v2 pools)."""
    right = [o for o in q.options if o.key in q.answer]
    others = [o for o in q.options if o.key not in q.answer]
    if not right or not others:
        return []
    problems = []
    lens = {o.key: len(o.text.strip()) for o in q.options}
    right_len, other_len = mean(lens[o.key] for o in right), mean(lens[o.key] for o in others)
    if right_len > other_len * LENGTH_RATIO + LENGTH_SLACK:
        problems.append(f"answer is noticeably longer than the distractors ({right_len:.0f} vs {other_len:.0f} chars)")
    elif q.type == "single" and right_len > max(lens[o.key] for o in others) * LONGEST_RATIO + LENGTH_SLACK:
        problems.append("answer is clearly the longest option")
    if right_len < other_len / LENGTH_RATIO - LENGTH_SLACK:
        problems.append(f"answer is noticeably shorter than the distractors ({right_len:.0f} vs {other_len:.0f} chars)")
    if max(lens.values()) > 2.5 * min(lens.values()) + 10:
        problems.append("option lengths vary so much that the odd one out stands out")
    if any(_ABSOLUTE.search(o.text) for o in others) and not any(_ABSOLUTE.search(o.text) for o in right):
        problems.append("absolute wording (always, never, only, all...) appears only in wrong options")
    stem = _echo_words(q.stem)
    echo_right = max(len(stem & _echo_words(o.text)) for o in right)
    echo_other = max(len(stem & _echo_words(o.text)) for o in others)
    if echo_right - echo_other >= ECHO_MARGIN:
        problems.append("answer repeats the stem's wording more than any distractor")
    if any(o.role is None for o in q.options):
        problems.append("every option needs a role (best, partial, related, wrong)")
    else:
        if {o.key for o in q.options if o.role == "best"} != set(q.answer):
            problems.append("keyed answers must be exactly the options with role 'best'")
        if any(o.role == "partial" for o in q.options) and not _QUALIFIER.search(q.stem):
            problems.append("a 'partial' (technically correct) option needs a stem that asks for the best, first, or most")
    return problems


def check(q: GeneratedQuestion, target: Target, section: Section, seen_stems: list[set[str]],
          strict: bool = True) -> list[str]:
    """Automated checks from section 10.2, plus the surface-cue checks for v2 pools when `strict`.
    Returns a list of problems (empty = pass)."""
    problems = []
    if q.exhibit is not None and len(q.exhibit.strip().splitlines()) > EXHIBIT_MAX_LINES:
        problems.append(f"exhibit longer than {EXHIBIT_MAX_LINES} lines")
    if q.exhibit is not None and not q.exhibit.strip():
        problems.append("empty exhibit")
    unknown = [o for o in q.objectives if o not in section.objectives]
    if unknown:
        problems.append(f"unknown objective IDs {unknown}")
    if q.objectives[0] != target.objective:
        problems.append(f"primary objective {q.objectives[0]} != assigned {target.objective}")
    keys = [o.key for o in q.options]
    if keys != [chr(ord("A") + i) for i in range(len(keys))]:
        problems.append(f"option keys not sequential from A: {keys}")
    texts = [o.text.strip().lower() for o in q.options]
    if len(set(texts)) != len(texts):
        problems.append("duplicate option text")
    if any(t in ("all of the above", "none of the above") for t in texts):
        problems.append("all/none of the above")
    if any(not o.rationale.strip() for o in q.options):
        problems.append("missing rationale")
    if q.type != "matching" and q.match_targets is not None:
        problems.append("match_targets belongs to matching questions only")
    if q.type in ("single", "multi"):
        if len(set(q.answer)) != len(q.answer) or not set(q.answer) <= set(keys):
            problems.append(f"answer keys {q.answer} not a subset of options {keys}")
        if len(q.options) < 4:
            problems.append("single and multi-select questions need at least 4 options")
    if q.type == "single" and len(q.answer) != 1:
        problems.append("single-answer question must have exactly 1 answer")
    if q.type == "multi":
        m = _CHOOSE.search(q.stem)
        if not m:
            problems.append("multi-select stem does not say how many to choose")
        elif _COUNTS[m.group(1).lower()] != len(q.answer):
            problems.append("multi-select count in stem does not match answer count")
        if len(q.answer) < 2:
            problems.append("multi-select needs at least 2 answers")
    if q.type == "ordering":
        problems += _ordering_problems(q, keys)
    if q.type == "matching":
        problems += _matching_problems(q, keys)
    prose = " ".join([q.explanation] + [o.rationale for o in q.options])
    if _LETTER_REF.search(prose):
        problems.append("rationale/explanation refers to an option letter")
    if _BOOK_REF.search(q.stem + " " + prose):
        problems.append("'per the book' wording")
    if _similar(_words(q.discriminator_tested), _words(q.explanation)) >= NEAR_DUPLICATE:
        problems.append("discriminator_tested just repeats the explanation")
    if q.objectives[0] in section.objectives:
        terms = objective_terms(section.objectives[q.objectives[0]].objective)
        body = _words(" ".join([q.stem, q.explanation, q.discriminator_tested] + [o.text for o in q.options]
                               + list(q.match_targets or [])))
        if terms and not terms & body:
            problems.append(f"never mentions its objective ({', '.join(sorted(terms))}); likely tests a different concept")
    words = content_words(q)
    if any(_similar(words, s) >= NEAR_DUPLICATE for s in seen_stems):
        problems.append("near-duplicate question")
    if strict and q.type in ("single", "multi"):  # ordering and matching have no distractors to compare
        problems += cue_problems(q)
    return problems


_ORDER_WORDS = re.compile(r"\b(?:order|sequence|arrange|chronolog\w*|first to last|earliest|steps?)\b", re.I)
_MATCH_WORDS = re.compile(r"\bmatch(?:es|ing)?\b|\bpair\b", re.I)


def _ordering_problems(q: GeneratedQuestion, keys: list[str]) -> list[str]:
    """Every option is a step; the answer lists every key once, first step first."""
    problems = []
    if len(q.options) > 6:
        problems.append("an ordering question has 3 to 6 steps")
    if sorted(q.answer) != sorted(keys) or len(q.answer) != len(keys):
        problems.append("an ordering answer must list every option key exactly once, in the correct order")
    if not _ORDER_WORDS.search(q.stem):
        problems.append("an ordering stem must ask for the order or sequence")
    if any(o.role not in (None, "best") for o in q.options):
        problems.append("ordering steps take no roles (every step is part of the answer)")
    return problems


def _matching_problems(q: GeneratedQuestion, keys: list[str]) -> list[str]:
    """Each option is paired with exactly one of match_targets; a target is used at most once."""
    problems = []
    targets = q.match_targets or []
    if len(targets) < len(keys):
        problems.append("a matching question needs at least as many match_targets as options")
    if len({t.strip().lower() for t in targets}) != len(targets):
        problems.append("duplicate match_targets text")
    pairs = [(a[0], int(a[1:])) for a in q.answer if len(a) == 2]
    if len(pairs) != len(q.answer) or sorted(k for k, _ in pairs) != sorted(keys):
        problems.append('a matching answer pairs every option key once with a target number, like "A2"')
    elif any(not 1 <= n <= len(targets) for _, n in pairs) or len({n for _, n in pairs}) != len(pairs):
        problems.append("each matching answer must use a different target number from match_targets")
    if not _MATCH_WORDS.search(q.stem):
        problems.append("a matching stem must ask to match the items")
    if any(o.role not in (None, "best") for o in q.options):
        problems.append("matching items take no roles (every item is part of the answer)")
    return problems


_STOP = {"and", "the", "for", "with", "attack", "attacks", "formerly", "change", "avoid", "common"}


def objective_terms(name: str) -> set[str]:
    """Key words of an objective name, e.g. 'Whaling' -> {'whaling'}. A question about an
    objective should use at least one of them somewhere (stem, options, or explanation)."""
    return {w for w in _words(name) if len(w) >= 3 and w not in _STOP}


def repair(q: GeneratedQuestion) -> GeneratedQuestion:
    """Mechanical fixes only (never content): add the missing '(Choose N.)' to multi-select stems."""
    if q.type == "multi" and len(q.answer) in (2, 3) and not _CHOOSE.search(q.stem):
        word = {2: "two", 3: "three"}[len(q.answer)]
        return q.model_copy(update={"stem": f"{q.stem.rstrip()} (Choose {word}.)"})
    return q


def shuffle_options(q: GeneratedQuestion, rng: random.Random) -> GeneratedQuestion:
    """Authors favour early answer positions; reshuffle and relabel A, B, C... An ordering question's
    steps are never left in the right order; a matching question's targets are shuffled too."""
    for _ in range(20):
        opts = list(q.options)
        rng.shuffle(opts)
        relabel = {o.key: chr(ord("A") + i) for i, o in enumerate(opts)}
        if q.type != "ordering" or [relabel[a] for a in q.answer] != sorted(relabel.values()):
            break
    new_opts = [o.model_copy(update={"key": relabel[o.key]}) for o in opts]
    if q.type == "ordering":
        return q.model_copy(update={"options": new_opts, "answer": [relabel[a] for a in q.answer]})
    if q.type == "matching":
        order = list(range(len(q.match_targets)))
        rng.shuffle(order)  # order[new position] = old index
        renumber = {old + 1: new + 1 for new, old in enumerate(order)}
        return q.model_copy(update={
            "options": new_opts, "match_targets": [q.match_targets[old] for old in order],
            "answer": sorted(f"{relabel[a[0]]}{renumber[int(a[1:])]}" for a in q.answer)})
    return q.model_copy(update={"options": new_opts, "answer": sorted(relabel[a] for a in q.answer)})


def parse_items(text: str) -> list:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start:end + 1])
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("output has no 'questions' array")
    return items


def import_items(cert_id: str, section_code: str, items: list, provider_name: str, model: str,
                 seed: int | None = None, strict: bool = True) -> BatchResult:
    """Add authored questions (e.g. written in a Claude chat or a Claude Code session) to one
    section's pool. Each item's own objective/angle/type is its target.
    `strict=False` skips the v2 surface-cue checks (only for loading the original v1 pools)."""
    section = load_section(cert_id, section_code)
    targets = []
    for item in items:
        objs = item.get("objectives") if isinstance(item, dict) else None
        targets.append(Target(objs[0] if objs else "?", item.get("angle", "?"), item.get("type", "?")))
    result = BatchResult(requested=len(items), model=model)
    _store(section, items, targets, provider_name, model, random.Random(seed), result, strict)
    return result


def _loc(loc: tuple) -> str:
    """A schema error location in plain words: ("options", 2, "text") -> "options[2].text"."""
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "question"


def _store(section: Section, items: list, targets: list[Target], provider_name: str, model: str,
           rng: random.Random, result: BatchResult, strict: bool = True) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def build(existing: list[Question]) -> list[Question]:
        # Retired questions are never served, so they don't block a corrected replacement.
        seen = [content_words(q) for q in existing if q.status != "retired"]
        valid: list[GeneratedQuestion] = []
        result.accepted_index = []
        for i, target in enumerate(targets):
            if i >= len(items):
                result.rejected.append({"index": i, "target": target.objective, "problems": ["missing from output"]})
                continue
            try:
                q = repair(GeneratedQuestion.model_validate(items[i]))
            except ValidationError as e:
                result.rejected.append({"index": i, "target": target.objective,
                                        "problems": [f"{_loc(err['loc'])}: {err['msg']}" for err in e.errors()]})
                continue
            problems = check(q, target, section, seen, strict)
            if problems:
                result.rejected.append({"index": i, "target": target.objective, "problems": problems})
                continue
            seen.append(content_words(q))
            valid.append(shuffle_options(q, rng))
            result.accepted_index.append(i)
        ids = pool.next_ids(section.code, existing, len(valid))
        return [
            Question(
                **q.model_dump(),
                id=qid,
                section=section.code,
                domain=section.domain,
                source_ref=f"objectives/{section.code}.md#{q.objectives[0]}",
                provider=provider_name,
                model=model,
                status="unreviewed",
                created_at=now,
            )
            for qid, q in zip(ids, valid)
        ]

    result.accepted = pool.add(section.cert_id, section.code, build)
