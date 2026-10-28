"""Focus mode (v2 plan 7.2): match a pasted objective list against the certification's objectives.

The pasted text is data only (v2 SR-2): it is cleaned (NFKC, no control or invisible characters),
size-capped, split into lines, and compared with the objectives by plain word matching. It is never
used in a path, a query, a regular expression or a shell command. Objectives are reached only through
the certification's own index of its objective files (SR-3), and results carry only objective IDs,
names and question counts, never file contents or paths (SR-7)."""

import math
import re
from collections import defaultdict
from dataclasses import dataclass

from . import certs, pool
from .objectives import load_sections
from .security import clean_text

MAX_CHARS = 8000
MAX_LINES = 60
MAX_LINE_CHARS = 300
MAX_CANDIDATES = 5
MAX_OBJECTIVES = 300  # objectives one focus session may cover
# Match labels by score (0-1). Below LOW a line is reported as not in the objective list.
HIGH, MEDIUM, LOW = 0.6, 0.4, 0.25

# Fixed patterns, applied to the text (the text itself never becomes a pattern).
_MARKER = re.compile(r"^(?:[-*+>#•◦▪‣·–—]+\s*|\[[ xX]?\]\s*|\(?\d{1,2}[.)]\s+|\(?[a-zA-Z][.)]\s+)")
_INLINE_BULLET = re.compile(r"\s*[•◦▪‣]\s*")
_OBJECTIVE_ID = re.compile(r"\b([A-Z]{1,3}\d{2}-\d{2})\b")
_REFERENCE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,3})(?![\d.])")
_WORD = re.compile(r"[a-z0-9]+")
_AND_OR = re.compile(r"\s+(?:and|or|&)\s+")

STOPWORDS = frozenset("""
a an and are as at be been by can do for from has have how if in into is it its of on or that the their them
these this those to was were what when where which while who why will with within without you your vs versus
via about across also any both each etc such than then there per other
explain describe define identify implement understand demonstrate apply compare contrast recognize recognise
summarize summarise discuss list outline given scenario concept concepts basic basics common type types various
including include includes key main general overview introduction set up use used using
does did work works happen happens know
""".split())


class FocusError(ValueError):
    pass


def _stem(w: str) -> str:
    """A crude, consistent stemmer: both sides of every comparison go through it."""
    if len(w) >= 5 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) >= 5 and w.endswith(("shes", "ches", "xes", "sses", "zes")):
        w = w[:-2]
    elif len(w) >= 4 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    if len(w) >= 6 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) >= 5 and w.endswith("ed"):
        w = w[:-2]
    return w


def _tokens(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower()) if w not in STOPWORDS and (len(w) > 1 or w.isdigit())}


def _acronym(text: str) -> str | None:
    """Initials of a name of three or more words (Multi-factor authentication -> mfa)."""
    words = [w for w in _WORD.findall(text.lower()) if w not in STOPWORDS]
    return "".join(w[0] for w in words) if 3 <= len(words) <= 6 else None


def _same(a: str, b: str) -> bool:
    """Equal, or one a short extension of the other (encrypt / encryption, but not power / powershell)."""
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return a == b or (len(short) >= 5 and len(long_) - len(short) <= 4 and long_.startswith(short))


@dataclass
class _Entry:
    id: str
    section: str
    name: str
    ref: str
    name_t: set[str]
    core_t: set[str]
    group_t: set[str]
    acronym: str | None


class _Index:
    """The certification's objectives, tokenized, with an inverted index for quick candidate lookup."""

    def __init__(self, cert_id: str):
        objectives = [(s, o) for s in load_sections(cert_id) for o in s.objectives.values()]
        # Acronyms the objectives write in capitals (DNS, MitM, WPA3). Only these are used: initials
        # alone make false acronyms ("IPv6 shortened expression" is not ISE).
        self.acronyms = {w.lower() for _, o in objectives for w in re.findall(r"[A-Za-z0-9]+", f"{o.objective} {o.core_idea}")
                         if sum(c.isupper() for c in w) >= 2}
        self.entries: list[_Entry] = []
        for s, o in objectives:
            name_t = _tokens(o.objective)
            acronym = _acronym(o.objective)
            known = acronym in self.acronyms and acronym not in name_t
            self.entries.append(_Entry(o.id, s.code, o.objective, o.ref.strip(), name_t, _tokens(o.core_idea),
                                       _tokens(o.group), acronym if known else None))
        self.by_id = {e.id: e for e in self.entries}
        self.lookup: dict[str, set[int]] = defaultdict(set)
        df: dict[str, int] = defaultdict(int)
        for i, e in enumerate(self.entries):
            for t in e.name_t | e.core_t | e.group_t | ({e.acronym} if e.acronym else set()):
                self.lookup[t].add(i)
                if len(t) >= 5:
                    self.lookup[t[:5]].add(i)
            for t in e.name_t | e.core_t:
                df[t] += 1
        n = max(1, len(self.entries))
        self.idf = {t: math.log(1 + n / c) for t, c in df.items()}
        self.unknown_idf = math.log(1 + n)

    def weight(self, t: str) -> float:
        return self.idf.get(t, self.unknown_idf)

    def _variants(self, text: str) -> list[set[str]]:
        """The text's tokens, and (when it differs) the same with a run of 3-5 words replaced by an
        acronym the objectives use (man in the middle -> mitm)."""
        raw = _WORD.findall(text.lower())
        out: list[str] = []
        i = 0
        while i < len(raw):
            for n in (5, 4, 3):
                initials = "".join(w[0] for w in raw[i:i + n])
                if i + n <= len(raw) and initials in self.acronyms:
                    out.append(initials)
                    i += n
                    break
            else:
                out.append(raw[i])
                i += 1
        plain = _tokens(text)
        folded = _tokens(" ".join(out))
        return [plain] if folded == plain else [plain, folded]

    def _score(self, words: set[str], e: _Entry) -> float:
        """How much of the text the objective explains (rarer words count more), times how much of the
        objective's name the text covers. An exact name scores 1."""
        if " ".join(sorted(words)) == " ".join(sorted(e.name_t)):
            return 1.0
        got = 0.0
        by_acronym = False
        for t in words:
            if t == e.acronym or any(_same(t, x) for x in e.name_t):
                got += self.weight(t)
                by_acronym |= t == e.acronym
            elif any(_same(t, x) for x in e.core_t):
                got += 0.4 * self.weight(t)
            elif any(_same(t, x) for x in e.group_t):
                got += 0.2 * self.weight(t)
        total = sum(self.weight(t) for t in words)
        name_total = sum(self.weight(x) for x in e.name_t) or 1.0
        name_got = name_total if by_acronym else sum(self.weight(x) for x in e.name_t if any(_same(x, t) for t in words))
        return (got / total) * (0.3 + 0.7 * name_got / name_total)

    def best(self, text: str, limit: int = MAX_CANDIDATES) -> list[tuple[float, _Entry]]:
        scores: dict[int, float] = {}
        for words in self._variants(text):
            if not words:
                continue
            near = set()
            for t in words:
                near |= self.lookup.get(t, set()) | (self.lookup.get(t[:5], set()) if len(t) >= 5 else set())
            for i in near:
                scores[i] = max(scores.get(i, 0.0), self._score(words, self.entries[i]))
        ranked = sorted(((round(s, 3), self.entries[i]) for i, s in scores.items()), key=lambda x: (-x[0], x[1].id))
        return ranked[:limit]


def split_lines(text: str) -> list[str]:
    """Cleaned, non-empty lines with list markers removed (1., a), -, •, [ ]...)."""
    cleaned = clean_text(text, MAX_CHARS, multiline=True)
    lines = []
    for raw in cleaned.splitlines():
        for piece in _INLINE_BULLET.split(raw):
            line = " ".join(piece.split())  # tabs and runs of spaces become one space
            for _ in range(2):  # "- 1. Explain..." has two markers
                line = _MARKER.sub("", line).strip()
            if line:
                lines.append(line)
    if not lines:
        raise FocusError("Paste at least one objective, one per line.")
    if len(lines) > MAX_LINES:
        raise FocusError(f"That's {len(lines)} lines; paste at most {MAX_LINES} at a time.")
    return lines


def _confidence(score: float) -> str:
    return "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"


def match(cert_id: str, text: str) -> dict:
    """Each pasted line's best objective matches, with alternatives for the preview."""
    cert = certs.get_cert(cert_id)
    index = _Index(cert_id)
    counts: dict[str, int] = defaultdict(int)
    for q in pool.active(cert_id):
        counts[q.objectives[0]] += 1
    not_known = f"This objective is not in the objective list for {cert.name}."
    no_questions = "No questions exist for this objective yet."
    domains = {d.id: d.name for d in cert.domains}

    def view(e: _Entry, how: str, score: float | None, via: str | None) -> dict:
        n = counts.get(e.id, 0)
        return {"objective": e.id, "name": e.name, "section": e.section, "questions": n, "how": how,
                "confidence": "exact" if score is None else _confidence(score),
                "via": via, **({"note": no_questions} if n == 0 else {})}

    out = []
    for n, line in enumerate(split_lines(text), 1):
        item = {"line": n, "text": line, "matches": [], "candidates": []}
        out.append(item)
        if len(line) > MAX_LINE_CHARS:
            item.update(status="too-long", message=f"This line is longer than {MAX_LINE_CHARS} characters, so it "
                                                   "wasn't matched. Split it into shorter lines.")
            continue
        named = list(dict.fromkeys(_OBJECTIVE_ID.findall(line.upper())))
        if named:  # the learner named objective IDs: use exactly those
            known = [index.by_id[i] for i in named if i in index.by_id]
            item["matches"] = [view(e, "id", None, e.id) for e in known]
            unknown = [i for i in named if i not in index.by_id]
            if unknown:
                item["unknown_ids"] = unknown
        elif (ref := _REFERENCE.match(line)) and ref[1] in domains:
            item.update(status="heading", message=f"Domain heading ({ref[1]} {domains[ref[1]]}): skipped. "
                                                  "The lines under it are matched one by one.")
            continue
        else:
            hits = [e for e in index.entries if ref and e.ref and (e.ref == ref[1] or e.ref.startswith(ref[1] + "."))]
            if hits:
                item["matches"] = [view(e, "reference", None, ref[1]) for e in hits]
            else:
                item["matches"], item["candidates"] = _by_words(line, index, view, counts)
        if item["matches"]:
            item["status"] = "matched"
        else:
            item.update(status="not-known", message=not_known)
    return {"cert": cert.id, "cert_name": cert.name, "lines": out}


def _topics(rest: str) -> list[tuple[str, bool]]:
    """Split a topic list into (topic, inside parentheses) pairs, on commas, semicolons, parentheses,
    "and" and "or"."""
    out: list[tuple[str, bool]] = []
    buf: list[str] = []
    depth = 0

    def flush():
        for p in _AND_OR.split("".join(buf)):
            if len(p.strip()) >= 2:
                out.append((p.strip(), depth > 0))
        buf.clear()

    for ch in rest:
        if ch in "(),;":
            flush()
            depth = depth + 1 if ch == "(" else max(0, depth - 1) if ch == ")" else depth
        else:
            buf.append(ch)
    flush()
    return out


def _by_words(line: str, index: _Index, view, counts: dict[str, int]) -> tuple[list[dict], list[dict]]:
    """A line that lists topics ("1.2 Explain threats: malware, ransomware, DoS") is matched topic by
    topic; any other line as a whole. Values in parentheses are often examples ("risk levels (low,
    high)"), so they need a strong match. Returns (matches, other candidates for the whole line)."""
    _head, colon, rest = line.partition(":")
    parts = _topics(rest) if colon else []
    found: dict[str, dict] = {}
    if len(parts) >= 2:
        for p, in_parens in parts:
            best = index.best(p, 1)
            if best and best[0][0] >= (HIGH if in_parens else LOW) and best[0][1].id not in found:
                found[best[0][1].id] = view(best[0][1], "words", best[0][0], p)
    whole = index.best(line)
    if not found and whole and whole[0][0] >= LOW:
        score, e = whole[0]
        found[e.id] = view(e, "words", score, None)
    candidates = [{"objective": e.id, "name": e.name, "section": e.section, "questions": counts.get(e.id, 0)}
                  for s, e in whole if e.id not in found and s >= LOW / 2]
    return list(found.values()), candidates[:MAX_CANDIDATES]


def objective_sections(cert_id: str, objective_ids: list[str]) -> list[str]:
    """Section codes of known objectives, in cert.json order; raises KeyError for an unknown ID."""
    known = {o.id: s.code for s in load_sections(cert_id) for o in s.objectives.values()}
    for oid in objective_ids:
        if oid not in known:
            raise KeyError(oid)
    codes = {known[o] for o in objective_ids}
    return [c for c in certs.get_cert(cert_id).section_codes if c in codes]
