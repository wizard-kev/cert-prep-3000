"""Command-line tools for the question pool, e.g.:
python -m certprep.cli import --section C01 --file data\\certs\\ccst-cyber\\imports\\ch01_v2_set1a.json --model claude-opus-5-5 --dry-run

--cert defaults to the only installed certification; give it when there are several."""

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from . import certs, pool
from .audit import coverage
from .generator import Target, check, content_words, import_items, parse_items, repair
from .objectives import load_section
from .schema import GeneratedQuestion


def coverage_report(cert_id: str, sections: list[str], minimum: int) -> bool:
    """Check each objective in the objective files has >= minimum active questions on
    >= 2 distinct angles, and that no question points at an ID missing from the file."""
    all_ok = True
    for r in coverage(cert_id, sections, minimum):
        if not r["active"]:
            print(f"{r['code']}: no questions yet")
            continue
        all_ok &= r["ok"]
        print(f"{r['code']}: {r['objectives']} objectives, {r['active']} active | per objective "
              f"{r['fewest']}-{r['most']} | below {minimum}: {r['below_minimum'] or 'none'} | "
              f"single angle: {r['single_angle'] or 'none'} | unknown IDs: {r['unknown_ids'] or 'none'} -> "
              f"{'PASS' if r['ok'] else 'FAIL'}")
    return all_ok


def _cert(parser: argparse.ArgumentParser, cert_id: str | None) -> certs.Cert:
    installed = certs.cert_ids()
    if cert_id is None:
        if len(installed) != 1:
            parser.error(f"give --cert (installed: {', '.join(installed) or 'none'})")
        cert_id = installed[0]
    try:
        return certs.get_cert(cert_id)
    except certs.UnknownCert:
        parser.error(f"unknown certification {cert_id!r} (installed: {', '.join(installed) or 'none'})")


def _sections(parser: argparse.ArgumentParser, cert: certs.Cert, codes: list[str] | None) -> list[str]:
    try:
        return [cert.section(c).code for c in codes] if codes else cert.section_codes
    except certs.UnknownSection as e:
        parser.error(str(e))


def main() -> None:
    parser = argparse.ArgumentParser(prog="certprep")
    parser.add_argument("--cert", help="certification id (folder name under data/certs)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import", help="validate and add authored questions as draft")
    imp.add_argument("--section", required=True, help="section code, e.g. C01")
    imp.add_argument("--file", required=True, help='JSON file: {"questions": [...]}')
    imp.add_argument("--provider", default="claude", help="who wrote the questions (provenance only)")
    imp.add_argument("--model", required=True, help="model that wrote the questions")
    imp.add_argument("--seed", type=int)
    imp.add_argument("--dry-run", action="store_true", help="check only; write nothing")
    cov = sub.add_parser("coverage", help="check every objective has enough active questions and angles")
    cov.add_argument("--sections", nargs="+", help="section codes (default: all)")
    cov.add_argument("--min", type=int, default=2, help="minimum active questions per objective")
    aud = sub.add_parser("audit", help="measure surface cues (answer length, absolutes, stem echo) in the active pool")
    aud.add_argument("--sections", nargs="+", help="section codes (default: all)")
    ret = sub.add_parser("retire", help="retire active questions with a reason (never edit in place)")
    ret.add_argument("--section", required=True)
    ret.add_argument("--reason", required=True)
    which = ret.add_mutually_exclusive_group(required=True)
    which.add_argument("--ids", nargs="+", help="question IDs to retire")
    which.add_argument("--all-active", action="store_true", help="retire every draft and verified question in the section")
    ret.add_argument("--superseded", action="store_true",
                     help="replaced by a rewrite, not flawed: the learner's answers keep counting")
    args = parser.parse_args()
    cert = _cert(parser, args.cert)

    if args.cmd == "coverage":
        raise SystemExit(0 if coverage_report(cert.id, _sections(parser, cert, args.sections), args.min) else 1)

    if args.cmd == "audit":
        from .audit import print_audit
        raise SystemExit(0 if print_audit(cert.id, _sections(parser, cert, args.sections)) else 1)

    if args.cmd == "retire":
        (code,) = _sections(parser, cert, [args.section])
        ids = {q.id for q in pool.active(cert.id, [code])} if args.all_active else set(args.ids)
        reason = args.reason
        if args.superseded and not reason.startswith(pool.SUPERSEDED_PREFIX):
            reason = f"{pool.SUPERSEDED_PREFIX}: {reason}"
        done = pool.retire_many(cert.id, code, ids, reason)
        print(f"Retired {len(done)} question(s) in {code}" + (f"; not active: {sorted(ids - set(done))}" if ids - set(done) else ""))
        return

    if args.cmd == "import":
        (code,) = _sections(parser, cert, [args.section])
        items = parse_items(Path(args.file).read_text(encoding="utf-8"))
        if args.dry_run:
            section = load_section(cert.id, code)
            # Same duplicate baseline as a real import: everything already in the pool.
            seen = [content_words(q) for q in pool.load(cert.id, code) if q.status != "retired"]
            for item in items:
                # Report schema errors per question, as a real import does, instead of stopping.
                try:
                    q = repair(GeneratedQuestion.model_validate(item))
                except ValidationError as e:
                    label = (item.get("objectives") or ["?"])[0] if isinstance(item, dict) else "?"
                    print(f"{label}: {['schema: ' + str(err['loc']) + ' ' + err['msg'] for err in e.errors()]}")
                    continue
                problems = check(q, Target(q.objectives[0], q.angle, q.type), section, seen)
                seen.append(content_words(q))
                print(f"{q.objectives[0]}: {'OK' if not problems else problems}")
            return
        result = import_items(cert.id, code, items, args.provider, args.model, args.seed)
        print(json.dumps(result.summary(), indent=2))


if __name__ == "__main__":
    main()
