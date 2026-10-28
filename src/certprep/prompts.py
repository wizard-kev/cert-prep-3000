"""Ready-made prompts for a Claude chat (v2 plan section 5). The app never sends them anywhere: the
user copies them into claude.ai. Each prompt states Claude's role and context, gives the source
objectives, the rules the import enforces, and (for question prompts) the exact reply format with
its version, so the reply can be pasted back into the app as-is."""

import json
import random

from . import certs, generator, pool, tracker
from .objectives import Objective, Section, find_objective

QUESTIONS_FORMAT = "certprep-questions"
QUESTIONS_FORMAT_VERSION = 1
MAX_TARGETS = 30           # questions asked for in one prompt
MAX_OBJECTIVES = 30
WRONG_CHOICES_PER_OBJECTIVE = 3

# Angles offered to Claude: how a question approaches its objective. Topic-specific v1 angles
# (ports, subnetting, NAT...) and "which-is-not" (avoided in v2) are left out.
PROMPT_ANGLES = {
    "symptom-to-attack": "describe observed symptoms; ask which attack, fault, or concept explains them",
    "attack-to-mitigation": "describe a threat or problem; ask for the BEST mitigation or fix",
    "mitigation-to-threat": "describe a control or practice; ask which threat or problem it addresses",
    "neighbor-discrimination": "two look-alike concepts; ask for the fact that separates them, or which one fits",
    "scenario-with-distractor": "a scenario with one detail that points to a different concept; the answer depends on the discriminator",
    "root-cause-vs-symptom": "separate the underlying cause from what was observed",
    "cause-and-effect-ordering": "ask for the correct sequence, or the effect of a cause",
    "choose-response": "a situation; ask for the BEST or FIRST action",
    "choose-tool": "a goal; ask which tool, technology, or method fits it best",
    "classify-element": "describe something concrete; ask what it is or which category it belongs to",
    "assess-risk": "a situation; ask for the MAIN risk or the most likely consequence",
    "find-missing-element": "a process, plan, or record with a gap; ask what is MOST clearly missing",
    "interpret-output": "an exhibit (log, command output, report); ask what it shows",
    "interpret-config": "an exhibit with a configuration or settings; ask what it does or allows",
}

RULES = """1. Test the DISCRIMINATOR of the assigned objective, not a bare definition. Describe a situation instead of naming the concept, so the learner has to recognise it. The stem asks one thing, unambiguously.
2. Mention the objective's key term somewhere (the stem, an option, or the explanation). The import rejects a question that never mentions its objective.
3. type "single": exactly 4 options, keys A-D, exactly 1 answer. type "multi": exactly 5 options, keys A-E, exactly 2 answers, and the stem ends with "(Choose two.)".
4. Every option has a "role": "best" (the keyed answer), "partial" (technically correct but not the best answer), "related" (a neighbouring concept, protocol, or practice), or "wrong" (a plausible misconception). In a single-answer question use one of each where it fits. If any option is "partial", the stem must ask for the BEST, MOST, FIRST, or MAIN answer. The keyed answers must be exactly the options whose role is "best".
5. Distractors are genuine look-alikes; prefer the neighbouring objectives listed below. No "all of the above" or "none of the above", no joke options, no two options with the same text.
6. No surface cues. The import measures these and rejects questions that fail:
   - The correct answer is not noticeably longer or shorter than the wrong options: keep it within about 25% of their average length, and never clearly the longest.
   - Across your questions, the correct answer is the longest option in only about 1 question in 4, and the shortest in about 1 in 4. Vary it.
   - Absolute words (always, never, only, all, every, none, cannot, can't, impossible, guaranteed, completely, entirely) must not appear only in wrong options. The easiest way is to keep them out of options.
   - The correct answer does not reuse the stem's words more than the wrong options do.
   - All options share the same grammatical form and level of detail.
7. Every option has a "rationale": why it is correct, or which different concept it actually describes. Never refer to options by letter (the app shuffles them), and never write "according to the book".
8. "explanation": 1 to 3 sentences that teach the discriminator. "discriminator_tested": one sentence naming the distinguishing fact, worded differently from the explanation.
9. "difficulty": 1 = recall in context, 2 = apply to a scenario, 3 = choose the best of several valid options, or reason in two steps.
10. "exhibit": a short log, configuration, or command output (at most 30 lines and 1500 characters) that the question depends on. Required for the interpret-output and interpret-config angles, otherwise usually null. Use made-up hosts, names, and addresses (192.0.2.x, 198.51.100.x, 203.0.113.x, example.com).
11. "objectives": the assigned ID first, then at most 2 look-alike IDs taken from the lists in this prompt.
12. Original content only: never reproduce real exam questions. Never invent specific-looking CVE numbers.
13. Length limits: stem 1200 characters, option text 400, rationale 600, explanation 1200, discriminator_tested 400."""

# Added to RULES when a prompt asks for ordering or matching questions (v2 plan 7.4, P10).
FORMAT_RULES = {
    "ordering": 'type "ordering": 3 to 6 options (keys A-F), each one step of a process or sequence. "answer" lists '
                "EVERY key exactly once, first step first. The stem asks for the order (\"In what order...\", \"Put these "
                'steps in sequence\"). Options take no "role"; each "rationale" says why the step comes where it does. '
                "Rules 4 and 6 don't apply.",
    "matching": 'type "matching": 3 to 6 options (keys A-F) are the items, and "match_targets" lists 3 to 8 descriptions '
                "(one or two may match nothing). \"answer\" pairs every key with the number of its description (1 = the "
                'first in match_targets), like ["A2", "B1", "C3"], using each number at most once. The stem asks to match '
                'them. Options take no "role"; each "rationale" says why the pair belongs together. Rules 4 and 6 don\'t apply.',
}
EXTRA_TYPE_SHARE = 0.1  # of questions asked for, per extra format the exam uses


def extra_types(cert: certs.Cert) -> dict[str, float]:
    """Ordering and matching questions, for certifications whose exam uses those formats."""
    formats = {f.format for f in cert.exam.question_formats}
    out = {}
    if "ordering" in formats:
        out["ordering"] = EXTRA_TYPE_SHARE
    if formats & {"matching", "drag-and-drop"}:
        out["matching"] = EXTRA_TYPE_SHARE
    return out


class PromptError(ValueError):
    pass


def _row(o: Objective) -> str:
    return f"- {o.id} | {o.objective} | core idea: {o.core_idea} | discriminator: {o.discriminator}"


def _resolve(cert_id: str, objective_ids: list[str]) -> list[tuple[Section, Objective]]:
    if not objective_ids:
        raise PromptError("choose at least one objective")
    if len(objective_ids) > MAX_OBJECTIVES:
        raise PromptError(f"choose at most {MAX_OBJECTIVES} objectives at a time")
    seen, out = set(), []
    for oid in objective_ids:
        if oid not in seen:
            seen.add(oid)
            out.append(find_objective(cert_id, oid))
    return out


def _neighbours(resolved: list[tuple[Section, Objective]]) -> list[str]:
    """Every objective in the sections involved, as `ID name`, for look-alike distractors."""
    chosen = {o.id for _, o in resolved}
    lines = []
    for section in {s.code: s for s, _ in resolved}.values():
        others = [f"{o.id} {o.objective}" for o in section.objectives.values() if o.id not in chosen]
        if others:
            lines.append(f"- {section.name}: " + "; ".join(others))
    return lines


def _exam_label(cert: certs.Cert) -> str:
    code = " ".join(x for x in (cert.vendor, cert.exam_code) if x)
    return f"{cert.name} ({code})" if code else cert.name


def _option_line(o, keyed: bool) -> str:
    return f"{o.key}. {o.text}" + ("   <- keyed answer" if keyed else "")


def _answer_lines(q) -> list[str]:
    """The options and the key, in the shape of the question's type."""
    if q.type == "ordering":
        return [*[f"{o.key}. {o.text}" for o in q.options], "", "Correct order: " + ", ".join(q.answer)]
    if q.type == "matching":
        return [*[f"{o.key}. {o.text}" for o in q.options], "", "Descriptions:",
                *[f"{i}. {t}" for i, t in enumerate(q.match_targets or [], 1)], "",
                "Correct pairs (item and description number): " + ", ".join(q.answer)]
    return [_option_line(o, o.key in q.answer) for o in q.options]


def learner_notes(cert_id: str, objective_ids: list[str]) -> list[str]:
    """What the learner's history says about each objective: status, recent accuracy, main error
    type, and the wrong options they recently picked (with what those options really are)."""
    flawed = pool.flawed_ids(cert_id)
    attempts = tracker.all_attempts(cert_id, exclude_questions=flawed)
    stats = tracker.objective_stats(attempts)
    lines = []
    for oid in objective_ids:
        s = stats.get(oid)
        if s is None:
            lines.append(f"- {oid}: not practiced yet")
            continue
        acc = f"{round(100 * s.last5_accuracy)}%" if s.last5_accuracy is not None else "n/a"
        bits = [f"{s.status}", f"{s.attempts} answered", f"last five {acc}"]
        if s.sure_wrong_recent:
            bits.append("recently wrong while sure")
        if s.errors:
            bits.append(f"main error: {s.errors.most_common(1)[0][0]}")
        lines.append(f"- {oid}: " + ", ".join(bits))
        wrong = [a for a in attempts if a["objective"] == oid and not a["correct"]][-WRONG_CHOICES_PER_OBJECTIVE:]
        for a in wrong:
            q = pool.get(cert_id, a["question_id"])
            if q is None:
                continue
            picked = [o for o in q.options if o.key in json.loads(a["selected"])]
            for o in picked:
                lines.append(f"  - chose \"{o.text}\" ({o.role or 'wrong'}: {o.rationale}) in: {q.stem[:160]}")
    return lines


def question_prompt(cert_id: str, objective_ids: list[str], per_objective: int = 1,
                    rng: random.Random | None = None, harder: bool = False) -> dict:
    """Prompt asking Claude for new questions on the chosen objectives, on angles they lack.
    `harder` asks for difficulty 3 throughout (for objectives the learner finds too easy)."""
    cert = certs.get_cert(cert_id)
    if not 1 <= per_objective <= 3:
        raise PromptError("questions per objective must be 1 to 3")
    resolved = _resolve(cert_id, objective_ids)
    if len(resolved) * per_objective > MAX_TARGETS:
        raise PromptError(f"that would be more than {MAX_TARGETS} questions; choose fewer objectives")
    rng = rng or random.Random()
    targets = []
    for section in {s.code: s for s, _ in resolved}.values():
        ids = [o.id for s, o in resolved if s.code == section.code]
        targets += generator.targets_for(ids, pool.load(cert_id, section.code), per_objective,
                                         list(PROMPT_ANGLES), rng, extra_types(cert))
    names = {o.id: o.objective for _, o in resolved}
    types = list(dict.fromkeys(t.type for t in targets))
    level = 3 if harder else 2

    def sample(t: generator.Target) -> dict:
        base = {"objectives": [t.objective], "type": t.type, "angle": t.angle, "difficulty": level, "stem": "...",
                "exhibit": None}
        if t.type == "ordering":
            return {**base, "options": [{"key": k, "text": "a step", "rationale": "why it comes here"} for k in "ABCD"],
                    "answer": ["C", "A", "D", "B"], "explanation": "...", "discriminator_tested": "..."}
        if t.type == "matching":
            return {**base, "options": [{"key": k, "text": "an item", "rationale": "why this pair"} for k in "ABC"],
                    "match_targets": ["description 1", "description 2", "description 3", "description 4"],
                    "answer": ["A2", "B4", "C1"], "explanation": "...", "discriminator_tested": "..."}
        return {**base, "options": [{"key": k, "text": "...", "rationale": "...", "role": r}
                                    for k, r in zip("ABCD", ("best", "partial", "related", "wrong"))],
                "answer": ["A"], "explanation": "...", "discriminator_tested": "..."}

    # One template per question type in this batch (single and multi share one shape).
    shown = {}
    for t in targets:
        shown.setdefault("choice" if t.type in ("single", "multi") else t.type, t)
    example = {"format": QUESTIONS_FORMAT, "format_version": QUESTIONS_FORMAT_VERSION, "cert": cert.id,
               "questions": [sample(t) for t in shown.values()]}
    rules = RULES + "".join(f"\n{14 + i}. {FORMAT_RULES[t]}" for i, t in enumerate(t for t in types if t in FORMAT_RULES))
    notes = learner_notes(cert_id, [o.id for _, o in resolved])
    has_history = any("not practiced yet" not in n for n in notes)
    parts = [
        f"You are writing original practice questions for the {_exam_label(cert)} exam, for one learner's "
        "personal study app. The app checks and imports your reply automatically, so follow the rules and the "
        "output format exactly.",
        "",
        f"## What to write ({len(targets)} question{'s' if len(targets) != 1 else ''}, in this order)",
        "Each line gives the objective the question must test (its ID goes first in \"objectives\"), the angle "
        "(how the question approaches it), and the type.",
        *[f"{i}. {t.objective} {names[t.objective]} | angle: {t.angle} | type: {t.type}"
          + (" | difficulty: 3" if harder else "")
          for i, t in enumerate(targets, 1)],
        *(["", "The learner already answers these objectives correctly and with full confidence, so make every "
               "question difficulty 3: choosing the best of several valid options, or a scenario that needs two "
               "steps of reasoning. Harder means subtler distinctions, not obscure trivia."] if harder else []),
        "",
        "## The objectives (your source of truth)",
        "ID | objective | core idea | discriminator (the one fact that separates it from look-alike concepts):",
        *[_row(o) for _, o in resolved],
        "",
        "## Neighbouring objectives (for look-alike distractors and secondary IDs)",
        *_neighbours(resolved),
        "",
        "## Angles used above",
        *[f"- {a}: {PROMPT_ANGLES[a]}" for a in dict.fromkeys(t.angle for t in targets)],
    ]
    if has_history:
        parts += ["", "## What this learner gets wrong (write distractors that test these misconceptions)", *notes]
    parts += [
        "", "## Rules (the import rejects questions that break them)", rules,
        "", "## Output format",
        f"Reply with exactly one JSON code block and nothing else. Keep \"format\", \"format_version\" and \"cert\" "
        f"exactly as shown, and put {'the question' if len(targets) == 1 else f'the {len(targets)} questions'} in "
        "\"questions\" in the order listed above. Template (replace every \"...\"; options can be in any order"
        + ("; the template shows one question of each type in this batch" if len(example["questions"]) > 1 else "") + "):",
        "```json", json.dumps(example, indent=2), "```",
    ]
    return {"prompt": "\n".join(parts), "targets": [t.__dict__ for t in targets]}


def repair_prompt(cert_id: str, rejected: list[dict]) -> str:
    """Prompt asking Claude to fix questions the import rejected, each with its problems."""
    cert = certs.get_cert(cert_id)
    blocks = []
    rows = {}
    for i, r in enumerate(rejected, 1):
        blocks += [f"### Question {i}", "Problems found by the import:", *[f"- {p}" for p in r["problems"]],
                   "```json", json.dumps(r["item"], indent=2, ensure_ascii=False), "```", ""]
        objs = r["item"].get("objectives") if isinstance(r["item"], dict) else None
        for oid in objs if isinstance(objs, list) else []:
            try:
                rows[oid] = _row(find_objective(cert_id, oid)[1])
            except Exception:  # noqa: BLE001 - an unknown ID is already listed as a problem
                continue
    return "\n".join([
        f"You wrote practice questions for the {_exam_label(cert)} exam for a learner's study app. The app's "
        f"import rejected {len(rejected)} of them. Fix each one so it passes every rule below: keep its objective "
        "and angle, change only what the problems require, and make sure a fix doesn't break another rule "
        "(for example, shortening the correct answer must not make it clearly the shortest option).",
        "",
        "## Rejected questions",
        *blocks,
        "## Objectives they test",
        *rows.values(),
        "",
        "## Rules", RULES,
        "", "## Output format",
        "Reply with exactly one JSON code block and nothing else, containing only the corrected questions:",
        "```json",
        json.dumps({"format": QUESTIONS_FORMAT, "format_version": QUESTIONS_FORMAT_VERSION, "cert": cert.id,
                    "questions": ["...corrected questions..."]}, indent=2),
        "```",
    ])


def study_prompt(cert_id: str, objective_ids: list[str]) -> str:
    """Prompt that sets Claude up as a tutor for a study dialogue on the chosen objectives."""
    cert = certs.get_cert(cert_id)
    resolved = _resolve(cert_id, objective_ids)
    return "\n".join([
        f"You are a patient, practical tutor helping one learner prepare for the {_exam_label(cert)} exam. "
        "Run an interactive study session on the objectives below.",
        "",
        "## How to run the session",
        "- Work through one objective at a time, in the order given.",
        "- Start each one with a short question to find out what I already know; don't lecture first.",
        "- Explain with concrete, realistic scenarios, and contrast each objective with its look-alikes using its "
        "discriminator (the fact that separates it from similar concepts).",
        "- After each objective, give me one scenario question and wait for my answer before moving on. If I'm "
        "wrong, name the misconception, explain it, and try a different scenario.",
        "- Pay extra attention to the mistakes listed under \"My progress\".",
        "- Keep replies under about 200 words unless I ask for more. Stay on these objectives.",
        "- At the end, give me a 5-question mixed quiz (one question at a time), then a short list of what to review.",
        "- Everything must be original; never present real exam questions.",
        "",
        "## Objectives (ID | objective | core idea | discriminator)",
        *[_row(o) for _, o in resolved],
        "",
        "## My progress so far",
        *learner_notes(cert_id, [o.id for _, o in resolved]),
        "",
        "Begin by greeting me in one sentence, then ask your first question.",
    ])


def ask_prompt(cert_id: str, question_id: str, selected: list[str] | None = None) -> str:
    """Prompt asking Claude to explain one practice question (replaces the v1 local-model Explain)."""
    cert = certs.get_cert(cert_id)
    q = pool.get(cert_id, question_id)
    if q is None:
        raise PromptError("unknown question")
    keys = {o.key for o in q.options}
    selected = [k for k in (selected or []) if k[:1] in keys and (len(k) == 2) == (q.type == "matching")]
    right = selected == q.answer if q.type == "ordering" else sorted(selected) == sorted(q.answer)
    rows = []
    for oid in q.objectives:
        try:
            rows.append(_row(find_objective(cert_id, oid)[1]))
        except Exception:  # noqa: BLE001 - keep the prompt useful even if an objective was removed
            continue
    mine = (", ".join(selected) + (" (correct)" if right else " (wrong)")) if selected else "not given"
    return "\n".join([
        f"I'm studying for the {_exam_label(cert)} exam with a practice question from my study app. Help me "
        "understand it.",
        "",
        "## The question",
        q.stem,
        *(["", "Exhibit:", "```", q.exhibit, "```"] if q.exhibit else []),
        "",
        *_answer_lines(q),
        "",
        f"My answer: {mine}",
        "",
        "## What the app says about each option",
        *[f"- {o.key} ({o.role or 'unlabelled'}): {o.rationale}" for o in q.options],
        f"Explanation: {q.explanation}",
        f"Key fact tested: {q.discriminator_tested}",
        "",
        "## Objective (ID | objective | core idea | discriminator)",
        *rows,
        "",
        "## Please",
        "1. Explain why the keyed answer is correct, using the objective's discriminator.",
        "2. Explain why my answer is wrong; if I got it right, explain why the most tempting wrong option is wrong.",
        "3. Give me one new short scenario that checks I've understood, and wait for my answer.",
        "4. If you think the keyed answer is actually wrong, or more than one option fits, say so plainly and "
        "explain why, so I can report the question in the app.",
    ])
