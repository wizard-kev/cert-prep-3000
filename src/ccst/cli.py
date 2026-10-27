"""Command-line generation, e.g.: python -m ccst.cli generate --chapter 1 --count 5"""

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import ValidationError

from . import pool
from .generator import Target, check, content_words, generate_batch, import_items, parse_items, repair
from .objectives import load_chapter
from .providers import get_provider
from .schema import GeneratedQuestion


def coverage_report(chapters: list[int], minimum: int) -> bool:
    """Check each objective in the objective files has >= minimum active questions on
    >= 2 distinct angles, and that no question points at an ID missing from the file."""
    import collections

    all_ok = True
    for ch in chapters:
        objs = list(load_chapter(ch).objectives)
        active = [q for q in pool.load(ch) if q.status != "retired"]
        if not active:
            print(f"Ch{ch}: no questions yet")
            continue
        prim = collections.Counter(q.objectives[0] for q in active)
        angles = collections.defaultdict(set)
        for q in active:
            angles[q.objectives[0]].add(q.angle)
        short = [o for o in objs if prim[o] < minimum]
        one_angle = [o for o in objs if prim[o] >= 2 and len(angles[o]) < 2]
        stray = sorted(set(prim) - set(objs))
        ok = not short and not one_angle and not stray
        all_ok &= ok
        print(f"Ch{ch}: {len(objs)} objectives, {len(active)} active | per objective "
              f"{min(prim[o] for o in objs)}-{max(prim[o] for o in objs)} | below {minimum}: {short or 'none'} | "
              f"single angle: {one_angle or 'none'} | unknown IDs: {stray or 'none'} -> {'PASS' if ok else 'FAIL'}")
    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(prog="ccst")
    sub = parser.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("generate", help="generate a batch of draft questions")
    gen.add_argument("--chapter", type=int, required=True)
    gen.add_argument("--count", type=int, default=5)
    gen.add_argument("--seed", type=int)
    imp = sub.add_parser("import", help="validate and add authored questions as draft")
    imp.add_argument("--chapter", type=int, required=True)
    imp.add_argument("--file", required=True, help='JSON file: {"questions": [...]}')
    imp.add_argument("--provider", choices=["claude", "ollama"], default="claude")
    imp.add_argument("--model", required=True, help="model that wrote the questions")
    imp.add_argument("--seed", type=int)
    imp.add_argument("--dry-run", action="store_true", help="check only; write nothing")
    cov = sub.add_parser("coverage", help="check every objective has enough active questions and angles")
    cov.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 14)))
    cov.add_argument("--min", type=int, default=2, help="minimum active questions per objective")
    aud = sub.add_parser("audit", help="measure surface cues (answer length, absolutes, stem echo) in the active pool")
    aud.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 14)))
    ret = sub.add_parser("retire", help="retire active questions with a reason (never edit in place)")
    ret.add_argument("--chapter", type=int, required=True)
    ret.add_argument("--reason", required=True)
    which = ret.add_mutually_exclusive_group(required=True)
    which.add_argument("--ids", nargs="+", help="question IDs to retire")
    which.add_argument("--all-active", action="store_true", help="retire every draft and verified question in the chapter")
    ret.add_argument("--superseded", action="store_true",
                     help="replaced by a rewrite, not flawed: the learner's answers keep counting")
    args = parser.parse_args()

    if args.cmd == "coverage":
        raise SystemExit(0 if coverage_report(args.chapters, args.min) else 1)

    if args.cmd == "audit":
        from .audit import print_audit
        raise SystemExit(0 if print_audit(args.chapters) else 1)

    if args.cmd == "retire":
        ids = {q.id for q in pool.active([args.chapter])} if args.all_active else set(args.ids)
        reason = args.reason
        if args.superseded and not reason.startswith(pool.SUPERSEDED_PREFIX):
            reason = f"{pool.SUPERSEDED_PREFIX}: {reason}"
        done = pool.retire_many(args.chapter, ids, reason)
        print(f"Retired {len(done)} question(s) in Ch{args.chapter}" + (f"; not active: {sorted(ids - set(done))}" if ids - set(done) else ""))
        return

    if args.cmd == "import":
        items = parse_items(Path(args.file).read_text(encoding="utf-8"))
        if args.dry_run:
            chapter = load_chapter(args.chapter)
            # Same duplicate baseline as a real import: everything already in the pool.
            seen = [content_words(q) for q in pool.load(args.chapter) if q.status != "retired"]
            for item in items:
                # Report schema errors per question, as a real import does, instead of stopping.
                try:
                    q = repair(GeneratedQuestion.model_validate(item))
                except ValidationError as e:
                    label = (item.get("objectives") or ["?"])[0] if isinstance(item, dict) else "?"
                    print(f"{label}: {['schema: ' + str(err['loc']) + ' ' + err['msg'] for err in e.errors()]}")
                    continue
                problems = check(q, Target(q.objectives[0], q.angle, q.type), chapter, seen)
                seen.append(content_words(q))
                print(f"{q.objectives[0]}: {'OK' if not problems else problems}")
            return
        result = import_items(args.chapter, items, args.provider, args.model, args.seed)
        print(json.dumps(result.summary(), indent=2))
        return

    if args.cmd == "generate":
        if not 1 <= args.count <= 10:
            parser.error("--count must be 1 to 10")
        result = asyncio.run(generate_batch(get_provider(), args.chapter, args.count, args.seed))
        print(json.dumps(result.summary(), indent=2))


if __name__ == "__main__":
    main()
