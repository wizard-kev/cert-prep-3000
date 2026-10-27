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
from .objectives import Chapter, load_chapter
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
    rejected: list[dict] = field(default_factory=list)
    model: str = ""

    def summary(self) -> dict:
        return {
            "requested": self.requested,
            "accepted": [q.id for q in self.accepted],
            "rejected": self.rejected,
            "model": self.model,
        }


def plan_targets(chapter: Chapter, existing: list[Question], n: int, rng: random.Random) -> list[Target]:
    """Least-covered objectives first; never repeat an objective's previous angle (section 10.1)."""
    cover = pool.coverage(existing)
    last = pool.last_angle(existing)
    angles_used: dict[str, Counter] = {}
    for q in existing:
        angles_used.setdefault(q.objectives[0], Counter())[q.angle] += 1

    ids = list(chapter.objectives)
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
    return _words(" ".join([q.stem] + [o.text for o in q.options]))


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


def check(q: GeneratedQuestion, target: Target, chapter: Chapter, seen_stems: list[set[str]],
          strict: bool = True) -> list[str]:
    """Automated checks from section 10.2, plus the surface-cue checks for v2 pools when `strict`.
    Returns a list of problems (empty = pass)."""
    problems = []
    if q.exhibit is not None and len(q.exhibit.strip().splitlines()) > EXHIBIT_MAX_LINES:
        problems.append(f"exhibit longer than {EXHIBIT_MAX_LINES} lines")
    if q.exhibit is not None and not q.exhibit.strip():
        problems.append("empty exhibit")
    unknown = [o for o in q.objectives if o not in chapter.objectives]
    if unknown:
        problems.append(f"unknown objective IDs {unknown}")
    if q.objectives[0] != target.objective:
        problems.append(f"primary objective {q.objectives[0]} != assigned {target.objective}")
    keys = [o.key for o in q.options]
    if keys != [chr(ord("A") + i) for i in range(len(keys))]:
        problems.append(f"option keys not sequential from A: {keys}")
    if len(set(q.answer)) != len(q.answer) or not set(q.answer) <= set(keys):
        problems.append(f"answer keys {q.answer} not a subset of options {keys}")
    texts = [o.text.strip().lower() for o in q.options]
    if len(set(texts)) != len(texts):
        problems.append("duplicate option text")
    if any(t in ("all of the above", "none of the above") for t in texts):
        problems.append("all/none of the above")
    if any(not o.rationale.strip() for o in q.options):
        problems.append("missing rationale")
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
    prose = " ".join([q.explanation] + [o.rationale for o in q.options])
    if _LETTER_REF.search(prose):
        problems.append("rationale/explanation refers to an option letter")
    if _BOOK_REF.search(q.stem + " " + prose):
        problems.append("'per the book' wording")
    if _similar(_words(q.discriminator_tested), _words(q.explanation)) >= NEAR_DUPLICATE:
        problems.append("discriminator_tested just repeats the explanation")
    if q.objectives[0] in chapter.objectives:
        terms = objective_terms(chapter.objectives[q.objectives[0]].objective)
        body = _words(" ".join([q.stem, q.explanation, q.discriminator_tested] + [o.text for o in q.options]))
        if terms and not terms & body:
            problems.append(f"never mentions its objective ({', '.join(sorted(terms))}); likely tests a different concept")
    words = content_words(q)
    if any(_similar(words, s) >= NEAR_DUPLICATE for s in seen_stems):
        problems.append("near-duplicate question")
    if strict:
        problems += cue_problems(q)
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
    """Authors favour early answer positions; reshuffle and relabel A, B, C...
    Ordering questions are shuffled too: each option is a complete sequence."""
    opts = list(q.options)
    rng.shuffle(opts)
    relabel = {o.key: chr(ord("A") + i) for i, o in enumerate(opts)}
    new_opts = [o.model_copy(update={"key": relabel[o.key]}) for o in opts]
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


def import_items(chapter_no: int, items: list, provider_name: str, model: str, seed: int | None = None,
                 strict: bool = True) -> BatchResult:
    """Add authored questions (e.g. written in a Claude chat or a Claude Code session).
    Each item's own objective/angle/type is its target.
    `strict=False` skips the v2 surface-cue checks (only for loading the original v1 pools)."""
    chapter = load_chapter(chapter_no)
    targets = []
    for item in items:
        objs = item.get("objectives") if isinstance(item, dict) else None
        targets.append(Target(objs[0] if objs else "?", item.get("angle", "?"), item.get("type", "?")))
    result = BatchResult(requested=len(items), model=model)
    _store(chapter, items, targets, provider_name, model, random.Random(seed), result, strict)
    return result


def _store(chapter: Chapter, items: list, targets: list[Target], provider_name: str, model: str,
           rng: random.Random, result: BatchResult, strict: bool = True) -> None:
    chapter_no = chapter.number
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def build(existing: list[Question]) -> list[Question]:
        # Retired questions are never served, so they don't block a corrected replacement.
        seen = [content_words(q) for q in existing if q.status != "retired"]
        valid: list[GeneratedQuestion] = []
        for i, target in enumerate(targets):
            if i >= len(items):
                result.rejected.append({"target": target.objective, "problems": ["missing from output"]})
                continue
            try:
                q = repair(GeneratedQuestion.model_validate(items[i]))
            except ValidationError as e:
                result.rejected.append({"target": target.objective,
                                        "problems": [f"schema: {err['loc']} {err['msg']}" for err in e.errors()]})
                continue
            problems = check(q, target, chapter, seen, strict)
            if problems:
                result.rejected.append({"target": target.objective, "problems": problems})
                continue
            seen.append(content_words(q))
            valid.append(shuffle_options(q, rng))
        ids = pool.next_ids(chapter_no, existing, len(valid))
        return [
            Question(
                **q.model_dump(),
                id=qid,
                chapter=chapter_no,
                domain=chapter.domain,
                source_ref=f"CCST_Ch{chapter_no:02d}.md#{q.objectives[0]}",
                provider=provider_name,
                model=model,
                status="draft",
                created_at=now,
            )
            for qid, q in zip(ids, valid)
        ]

    result.accepted = pool.add(chapter_no, build)
