"""Certification packs (v2 plan section 9, SR-5): export a certification as a .zip, import one under a new id.

A pack holds manifest.json (format, version, certification, the file list with SHA-256 hashes and sizes),
cert.json, objectives/<CODE>.md and questions/<CODE>.json. Progress never leaves the machine: questions the
learner has only answered travel as Unreviewed, without first-seen times, and disputed ones stay behind.

An imported pack is checked completely in memory before anything is written: total size and entry count;
names against fixed patterns (no absolute paths, "..", links, directories or duplicates); encryption;
per-file size and compression ratio (zip bombs); hashes against the manifest; strict UTF-8; and every file
against its schema. Only then is the folder written, under a hidden name renamed into place."""

import hashlib
import io
import json
import re
import stat
import struct
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import ValidationError

from . import certs, pool, security
from .config import APP_NAME
from .objectives import load_sections, parse_objectives
from .schema import SERVED_STATUSES, Question

PACK_FORMAT = "certprep-pack"
PACK_VERSION = 1
MAX_PACK_BYTES = security.MAX_PACK_BYTES
MAX_ENTRIES = 2000
MAX_TOTAL_BYTES = 100_000_000  # all files, uncompressed
MAX_RATIO = 100                 # uncompressed / compressed, per file
LIMITS = {"manifest.json": 1_000_000, "cert.json": 200_000, "objectives": 1_000_000, "questions": 20_000_000}
CELL_LIMITS = (200, 600, 600, 20)  # objective, core idea, discriminator, ref
_NAME = re.compile(r"^(manifest\.json|cert\.json|(objectives)/([A-Z]{1,3}\d{2})\.md|(questions)/([A-Z]{1,3}\d{2})\.json)$")
_MANIFEST_KEYS = {"format", "format_version", "cert", "name", "short_name", "created", "app", "includes_retired", "files"}
# What a damaged or hostile zip can raise while it is opened or read.
_ZIP_ERRORS = (zipfile.BadZipFile, zlib.error, struct.error, ValueError, OSError, EOFError, RuntimeError,
               NotImplementedError)


class PackError(ValueError):
    pass


# ---- export -----------------------------------------------------------------------

def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _exported(q: Question) -> dict:
    """A question as it travels: the learner's own traces removed."""
    data = q.stored()
    if q.status == "passive":
        data["status"] = "unreviewed"
    data["seen_at"] = None
    return data


def export_pack(cert_id: str, include_retired: bool = False) -> bytes:
    cert = certs.get_cert(cert_id)
    folder = certs.cert_dir(cert.id)
    files: dict[str, bytes] = {"cert.json": (folder / "cert.json").read_bytes()}
    for s in load_sections(cert.id):
        files[f"objectives/{s.code}.md"] = s.text.encode("utf-8")
        keep = [q for q in pool.load(cert.id, s.code)
                if q.status in SERVED_STATUSES or (include_retired and q.status == "retired")]
        if keep:
            payload = {"section": s.code, "questions": [_exported(q) for q in keep]}
            files[f"questions/{s.code}.json"] = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    manifest = {
        "format": PACK_FORMAT, "format_version": PACK_VERSION, "cert": cert.id, "name": cert.name,
        "short_name": cert.short_name, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app": APP_NAME, "includes_retired": include_retired,
        "files": [{"path": p, "sha256": _sha(b), "size": len(b)} for p, b in files.items()],
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for path, body in files.items():
            z.writestr(path, body)
    return out.getvalue()


# ---- import -------------------------------------------------------------------------

@dataclass
class Pack:
    manifest: dict
    cert: certs.Cert
    objective_texts: dict[str, str]
    questions: dict[str, list[Question]] = field(default_factory=dict)

    def summary(self) -> dict:
        objectives = {code: parse_objectives(text, code) for code, text in self.objective_texts.items()}
        return {"cert": self.cert.id, "name": self.cert.name, "short_name": self.cert.short_name,
                "vendor": self.cert.vendor, "exam_code": self.cert.exam_code, "created": self.manifest.get("created"),
                "sections": len(self.cert.sections), "objectives": sum(len(o) for o in objectives.values()),
                "questions": sum(1 for qs in self.questions.values() for q in qs if q.status in SERVED_STATUSES),
                "retired": sum(1 for qs in self.questions.values() for q in qs if q.status == "retired")}


def _entries(data: bytes) -> dict[str, bytes]:
    """Every file in the zip, read under the SR-5 limits. Names are only compared with fixed patterns;
    they are never used to build a path."""
    if len(data) > MAX_PACK_BYTES:
        raise PackError(f"The pack is larger than {MAX_PACK_BYTES // 1_000_000} MB.")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        infos = z.infolist()
    except _ZIP_ERRORS:
        raise PackError("That file isn't a zip file (a certification pack is a .zip exported by this app).") from None
    if len(infos) > MAX_ENTRIES:
        raise PackError(f"The pack has more than {MAX_ENTRIES} files.")
    out: dict[str, bytes] = {}
    total = 0
    for info in infos:
        name = info.filename
        shown = repr(name[:80])
        if name in ("objectives/", "questions/"):
            continue  # folder entries some zip tools add
        if info.flag_bits & 0x1:
            raise PackError(f"{shown} is encrypted; packs can't contain encrypted files.")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise PackError(f"{shown} is a link; packs can't contain links.")
        m = _NAME.match(name)
        if not m or info.is_dir():
            raise PackError(f"Unexpected file in the pack: {shown}. A pack holds only manifest.json, cert.json, "
                            "objectives/<CODE>.md and questions/<CODE>.json.")
        if name in out:
            raise PackError(f"{shown} appears twice in the pack.")
        limit = LIMITS[m[2] or m[4] or name]
        if info.file_size > limit:
            raise PackError(f"{shown} is larger than {limit // 1000:,} KB.")
        if info.file_size > MAX_RATIO * max(info.compress_size, 1) and info.file_size > 10_000:
            raise PackError(f"{shown} is compressed suspiciously well (over {MAX_RATIO}:1); it was refused.")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise PackError(f"The pack unpacks to more than {MAX_TOTAL_BYTES // 1_000_000} MB.")
        try:
            with z.open(info) as f:
                body = f.read(limit + 1)
        except _ZIP_ERRORS:
            raise PackError(f"{shown} can't be read from the zip.") from None
        if len(body) != info.file_size:
            raise PackError(f"{shown} isn't the size the zip says it is.")
        out[name] = body
    return out


def _text(name: str, body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        raise PackError(f"{name} isn't valid UTF-8 text.") from None


def _json(name: str, body: bytes):
    try:
        return json.loads(_text(name, body))
    except json.JSONDecodeError:
        raise PackError(f"{name} isn't valid JSON.") from None


def _check_cells(code: str, text: str) -> dict:
    objectives = parse_objectives(text, code)
    if not objectives:
        raise PackError(f"objectives/{code}.md has no objective rows.")
    for o in objectives.values():
        for cell, limit in zip((o.objective, o.core_idea, o.discriminator, o.ref), CELL_LIMITS):
            try:
                clean = security.clean_text(cell, limit)
            except ValueError:
                raise PackError(f"{o.id}: a field is longer than {limit} characters.") from None
            if clean != cell:
                raise PackError(f"{o.id}: a field contains control or invisible characters.")
        if not o.objective:
            raise PackError(f"{o.id} has no objective name.")
    return objectives


def check_pack(data: bytes) -> Pack:
    entries = _entries(data)
    if "manifest.json" not in entries or "cert.json" not in entries:
        raise PackError("This isn't a certification pack: it needs manifest.json and cert.json.")
    manifest = _json("manifest.json", entries["manifest.json"])
    if not isinstance(manifest, dict) or manifest.get("format") != PACK_FORMAT:
        raise PackError("This isn't a certification pack from this app (manifest format).")
    if manifest.get("format_version") != PACK_VERSION:
        raise PackError(f"This pack is version {manifest.get('format_version')!r}; this app reads version {PACK_VERSION}.")
    extra = sorted(set(manifest) - _MANIFEST_KEYS)
    if extra:
        raise PackError(f"Unexpected fields in manifest.json: {', '.join(map(str, extra))[:200]}.")
    listed = manifest.get("files")
    if not isinstance(listed, list) or not all(isinstance(f, dict) and set(f) == {"path", "sha256", "size"} for f in listed):
        raise PackError("manifest.json has no valid file list.")
    by_path = {f["path"]: f for f in listed if isinstance(f["path"], str)}
    present = set(entries) - {"manifest.json"}
    if set(by_path) != present or len(by_path) != len(listed):
        raise PackError("The files in the pack don't match its manifest.")
    for path in sorted(present):
        if by_path[path]["sha256"] != _sha(entries[path]) or by_path[path]["size"] != len(entries[path]):
            raise PackError(f"{path} doesn't match its checksum in the manifest; the pack may be damaged.")

    try:
        cert = certs.Cert.model_validate(_json("cert.json", entries["cert.json"]))
    except ValidationError as e:
        raise PackError(f"cert.json isn't valid: {e.errors()[0]['loc']} {e.errors()[0]['msg']}"[:300]) from None
    if cert.id != manifest.get("cert"):
        raise PackError("cert.json and the manifest name different certifications.")
    codes = set(cert.section_codes)
    files_codes = {p.split("/")[1].split(".")[0] for p in present if p != "cert.json"}
    stray = sorted(files_codes - codes)
    if stray:
        raise PackError(f"The pack has files for sections cert.json doesn't list: {', '.join(stray)}.")

    texts, objectives = {}, {}
    for code in cert.section_codes:
        name = f"objectives/{code}.md"
        if name not in entries:
            raise PackError(f"The pack is missing {name}.")
        texts[code] = _text(name, entries[name])
        objectives[code] = _check_cells(code, texts[code])
    known = {oid for objs in objectives.values() for oid in objs}

    questions: dict[str, list[Question]] = {}
    for code in cert.section_codes:
        name = f"questions/{code}.json"
        if name not in entries:
            continue
        data = _json(name, entries[name])
        if not isinstance(data, dict) or set(data) != {"section", "questions"} or data["section"] != code \
                or not isinstance(data["questions"], list):
            raise PackError(f"{name} isn't a question file for section {code}.")
        seen = set()
        qs = []
        for i, raw in enumerate(data["questions"]):
            try:
                q = Question.model_validate(raw)
            except ValidationError as e:
                raise PackError(f"{name}, question {i + 1}: {e.errors()[0]['loc']} {e.errors()[0]['msg']}"[:300]) from None
            if q.section != code or not q.id.startswith(f"Q-{code}-") or q.id in seen:
                raise PackError(f"{name}: question {q.id} is in the wrong file or appears twice.")
            if q.objectives[0] not in objectives[code] or not set(q.objectives) <= known:
                raise PackError(f"{name}: {q.id} refers to objectives this pack doesn't define.")
            if q.status == "disputed":
                raise PackError(f"{name}: {q.id} is disputed; packs carry no disputes.")
            seen.add(q.id)
            qs.append(q)
        questions[code] = qs
    return Pack(manifest, cert, texts, questions)


def suggest_id(cert_id: str) -> str:
    from .wizard import list_drafts  # drafts reserve their ids too
    taken = set(certs.cert_ids()) | {d["id"] for d in list_drafts()}
    if cert_id not in taken:
        return cert_id
    for n in range(2, 100):
        candidate = f"{cert_id[:29].rstrip('-')}-{n}"
        if candidate not in taken:
            return candidate
    raise PackError("Too many certifications with that id already.")


def install_pack(pack: Pack, new_id: str, short_name: str | None = None) -> str:
    """Write a checked pack as a new certification. Existing certifications are never overwritten."""
    if new_id != suggest_id(new_id):
        raise PackError(f"A certification or set-up called {new_id} already exists; choose another id.")
    data = pack.cert.model_dump()
    data["id"] = new_id
    if short_name:
        data["short_name"] = short_name
    try:
        cert = certs.Cert.model_validate(data)
    except ValidationError:
        raise PackError("That short name isn't valid (1 to 60 characters).") from None
    files = {"cert.json": json.dumps(cert.model_dump(), indent=2, ensure_ascii=False),
             **{f"objectives/{code}.md": text for code, text in pack.objective_texts.items()},
             **{f"questions/{code}.json": json.dumps({"section": code, "questions": [q.stored() for q in qs]},
                                                     indent=2, ensure_ascii=False)
                for code, qs in pack.questions.items() if qs}}
    try:
        certs.install(new_id, files)
    except FileExistsError:
        raise PackError(f"A folder named {new_id} already exists in the certifications folder.") from None
    if {s.code for s in load_sections(new_id)} != set(pack.objective_texts):
        certs.remove(new_id)
        raise PackError("The pack's objective files didn't read back correctly, so nothing was installed.")
    return new_id
