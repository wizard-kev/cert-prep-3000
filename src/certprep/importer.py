"""Import a Claude reply into the question pool (v2 plan 5.2, SR-2, SR-8).

The reply is JSON text (pasted, or read from a file in the browser) in the format the prompts ask
for. It is parsed as data only, every field is checked (unknown fields are rejected), free text is
cleaned, and each question then goes through the same checks as any authored question. Accepted
questions enter as draft; the cleaned reply is archived under the certification's imports/ folder
with a name the server chooses."""

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import ValidationError

from . import certs, generator, pool, security
from .audit import audit, cue_failures
from .objectives import load_section
from .prompts import QUESTIONS_FORMAT, QUESTIONS_FORMAT_VERSION, repair_prompt
from .schema import GeneratedQuestion, Option

MAX_QUESTIONS = 50
MAX_TEXT_CHARS = 900_000
PROVIDER, MODEL = "claude", "claude-chat"
_ENVELOPE_KEYS = {"format", "format_version", "cert", "questions"}
_QUESTION_KEYS = set(GeneratedQuestion.model_fields)
_OPTION_KEYS = set(Option.model_fields)
# Schema length limits, so text is checked after it is cleaned.
_SINGLE_LINE = {"stem": 1200, "explanation": 1200, "discriminator_tested": 400}
_OPTION_TEXT = {"text": 400, "rationale": 600}
_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*?)\n\s*```\s*$", re.S)


class ImportProblem(ValueError):
    """The reply as a whole can't be imported (not JSON, wrong format or certification...)."""


@dataclass
class ImportResult:
    accepted: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    archive: str | None = None
    warnings: list[str] = field(default_factory=list)
    repair_prompt: str | None = None

    def as_dict(self) -> dict:
        def brief(r: dict) -> dict:
            stem = r["item"].get("stem") if isinstance(r.get("item"), dict) else None
            return {"index": r["index"], "objective": r.get("objective"), "problems": r["problems"],
                    "stem": stem[:200] if isinstance(stem, str) else None}
        return {"accepted": self.accepted, "rejected": [brief(r) for r in self.rejected],
                "archive": self.archive, "warnings": self.warnings, "repair_prompt": self.repair_prompt}


def parse_reply(text: str) -> dict:
    """The JSON object in a reply, allowing a ```json code fence or a sentence around it."""
    if not isinstance(text, str) or not text.strip():
        raise ImportProblem("Paste Claude's reply first.")
    if len(text) > MAX_TEXT_CHARS:
        raise ImportProblem("The reply is too long to import at once. Ask for fewer questions per prompt.")
    body = text.strip().lstrip("﻿")
    if m := _FENCE.match(body):
        body = m.group(1)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        start, end = body.find("{"), body.rfind("}")
        try:
            data = json.loads(body[start:end + 1]) if 0 <= start < end else None
        except json.JSONDecodeError:
            data = None
        if data is None:
            raise ImportProblem("The reply isn't valid JSON. Copy Claude's whole code block (or download its file) "
                                "and paste it again.") from None
    if not isinstance(data, dict):
        raise ImportProblem("The reply must be a JSON object with a \"questions\" list.")
    return data


def _check_envelope(data: dict, cert_id: str) -> list:
    extra = sorted(set(data) - _ENVELOPE_KEYS)
    if extra:
        raise ImportProblem(f"Unexpected fields in the reply: {', '.join(extra)}.")
    if data.get("format") != QUESTIONS_FORMAT or data.get("format_version") != QUESTIONS_FORMAT_VERSION:
        raise ImportProblem("This isn't a question file from this app's prompts (format "
                            f"\"{QUESTIONS_FORMAT}\" version {QUESTIONS_FORMAT_VERSION}). Build a new prompt and try again.")
    if data.get("cert") != cert_id:
        raise ImportProblem(f"These questions are for \"{data.get('cert')}\", not the certification you're studying "
                            f"(\"{cert_id}\"). Switch certification first, or build the prompt again.")
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ImportProblem("The reply has no questions.")
    if len(questions) > MAX_QUESTIONS:
        raise ImportProblem(f"Import at most {MAX_QUESTIONS} questions at a time.")
    return questions


def _clean_item(item) -> tuple[dict | None, list[str]]:
    """Unknown fields and over-long text become problems; free text is cleaned (SR-2)."""
    if not isinstance(item, dict):
        return None, ["not a JSON object"]
    problems = [f"unknown field \"{k}\"" for k in sorted(set(item) - _QUESTION_KEYS)]
    out = dict(item)
    for key, limit in _SINGLE_LINE.items():
        if isinstance(out.get(key), str):
            try:
                out[key] = security.clean_text(out[key], limit)
            except ValueError:
                problems.append(f"{key} is longer than {limit} characters")
    if isinstance(out.get("exhibit"), str):
        try:
            out["exhibit"] = security.clean_text(out["exhibit"], 1500, multiline=True) or None
        except ValueError:
            problems.append("exhibit is longer than 1500 characters")
    if isinstance(out.get("options"), list):
        opts = []
        for i, o in enumerate(out["options"]):
            if not isinstance(o, dict):
                problems.append(f"options[{i}] is not a JSON object")
                continue
            problems += [f"unknown field \"{k}\" in options[{i}]" for k in sorted(set(o) - _OPTION_KEYS)]
            o = dict(o)
            for key, limit in _OPTION_TEXT.items():
                if isinstance(o.get(key), str):
                    try:
                        o[key] = security.clean_text(o[key], limit)
                    except ValueError:
                        problems.append(f"options[{i}].{key} is longer than {limit} characters")
            opts.append(o)
        out["options"] = opts
    return out, problems


def _other_problems(cert_id: str, section_code: str, item: dict) -> list[str]:
    """For a question already rejected (unknown fields, over-long text): what the full checks would
    also say, so one repair round can fix everything. Nothing is stored."""
    known = {k: v for k, v in item.items() if k in _QUESTION_KEYS}
    if isinstance(known.get("options"), list):
        known["options"] = [{k: v for k, v in o.items() if k in _OPTION_KEYS} if isinstance(o, dict) else o
                            for o in known["options"]]
    try:
        q = generator.repair(GeneratedQuestion.model_validate(known))
    except ValidationError as e:
        return [f"{generator._loc(err['loc'])}: {err['msg']}" for err in e.errors()]
    section = load_section(cert_id, section_code)
    seen = [generator.content_words(p) for p in pool.load(cert_id, section_code) if p.status != "retired"]
    return generator.check(q, generator.Target(q.objectives[0], q.angle, q.type), section, seen)


def _primary(item: dict | None) -> str | None:
    objs = item.get("objectives") if item else None
    return objs[0] if isinstance(objs, list) and objs and isinstance(objs[0], str) else None


def import_reply(cert_id: str, text: str) -> ImportResult:
    cert = certs.get_cert(cert_id)
    data = parse_reply(text)
    questions = _check_envelope(data, cert.id)
    result = ImportResult()
    cleaned: list[dict | None] = []
    by_section: dict[str, list[int]] = defaultdict(list)
    for i, raw in enumerate(questions):
        item, problems = _clean_item(raw)
        cleaned.append(item)
        primary = _primary(item)
        section = primary.split("-")[0] if primary and re.match(certs.OBJECTIVE_ID, primary) else None
        if section and section not in cert.section_codes:
            problems.append(f"objective {primary} isn't in {cert.short_name}")
        elif not section:
            problems.append("\"objectives\" must start with an objective ID such as " + f"{cert.section_codes[0]}-01")
        if problems:
            if item is not None and section in cert.section_codes:
                problems += [p for p in _other_problems(cert.id, section, item) if p not in problems]
            result.rejected.append({"index": i, "objective": primary, "problems": problems, "item": item or raw})
        else:
            by_section[section].append(i)

    for code, indexes in by_section.items():
        batch = generator.import_items(cert.id, code, [cleaned[i] for i in indexes], PROVIDER, MODEL)
        for q, k in zip(batch.accepted, batch.accepted_index):
            result.accepted.append({"index": indexes[k], "id": q.id, "objective": q.objectives[0], "section": code})
        for r in batch.rejected:
            i = indexes[r["index"]]
            result.rejected.append({"index": i, "objective": r["target"], "problems": r["problems"], "item": cleaned[i]})
    result.accepted.sort(key=lambda a: a["index"])
    result.rejected.sort(key=lambda r: r["index"])

    for code in sorted(by_section):
        failures = cue_failures(audit(cert.id, [code]))
        if failures:
            result.warnings.append(f"{code} answer-pattern balance: " + "; ".join(failures)
                                   + ". Ask for the opposite pattern in the next batch.")
    if result.rejected:
        result.repair_prompt = repair_prompt(cert.id, [{"problems": r["problems"], "item": r["item"]}
                                                       for r in result.rejected])
    result.archive = _archive(cert.id, data | {"questions": [c if c is not None else q for c, q in
                                                              zip(cleaned, questions)]})
    return result


def _archive(cert_id: str, data: dict) -> str:
    """Keep the cleaned reply (accepted and rejected) under imports/, named by the server."""
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    name = f"claude-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{digest}.json"
    folder = certs.cert_dir(cert_id) / "imports"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(payload, encoding="utf-8")
    return name
