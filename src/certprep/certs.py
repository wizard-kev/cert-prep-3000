"""Certifications: one folder per certification under `settings.certs_dir`, described by cert.json.

A certification id is the folder name; section codes come from cert.json. Both are checked
against a pattern and must exist in the registry read from disk, so nothing the browser sends
is ever used to build a file path (v2 SR-3)."""

import json
import os
import re
import secrets
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import settings

CERT_ID = r"^[a-z0-9][a-z0-9-]{1,31}$"
SECTION_CODE = r"^[A-Z]{1,3}\d{2}$"
QUESTION_ID = r"^Q-[A-Z]{1,3}\d{2}-\d{4}$"
OBJECTIVE_ID = r"^[A-Z]{1,3}\d{2}-\d{2}$"
_CERT_ID = re.compile(CERT_ID)
_SECTION_CODE = re.compile(SECTION_CODE)
_QUESTION_ID = re.compile(r"^Q-([A-Z]{1,3}\d{2})-\d{4}$")

FactConfidence = Literal["official", "estimate", "unknown"]


class UnknownCert(ValueError):
    pass


class UnknownSection(ValueError):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fact(_Strict):
    """One exam fact with where it stands: published by the vendor, estimated, or unknown."""
    value: int | float | str | None = None
    confidence: FactConfidence = "unknown"
    note: str = Field(default="", max_length=500)


class QuestionFormat(_Strict):
    format: str = Field(min_length=1, max_length=40)
    served: bool = False  # whether this app can serve the format
    note: str = Field(default="", max_length=500)


class Exam(_Strict):
    minutes: Fact
    question_count: Fact
    passing_score: Fact
    question_formats: list[QuestionFormat] = Field(default_factory=list, max_length=20)


class Domain(_Strict):
    id: str = Field(pattern=r"^[A-Za-z0-9.]{1,10}$")
    name: str = Field(min_length=1, max_length=200)
    weight: float = Field(gt=0, le=1000)


class Weights(_Strict):
    confidence: FactConfidence = "unknown"
    note: str = Field(default="", max_length=500)


class SectionInfo(_Strict):
    code: str = Field(pattern=SECTION_CODE)
    name: str = Field(min_length=1, max_length=200)
    domain: str | None = None


class Source(_Strict):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(pattern=r"^https://\S+$", max_length=500)


class Cert(_Strict):
    format_version: Literal[1]
    id: str = Field(pattern=CERT_ID)
    name: str = Field(min_length=1, max_length=200)
    short_name: str = Field(min_length=1, max_length=60)
    vendor: str = Field(default="", max_length=100)
    exam_code: str = Field(default="", max_length=40)
    objectives_source: str = Field(default="", max_length=500)
    facts_gathered: str = Field(default="", max_length=40)
    exam: Exam
    domains: list[Domain] = Field(default_factory=list, max_length=50)
    weights: Weights = Weights()
    untagged_weight: float = Field(default=1.0, gt=0, le=1000)  # sections with no domain
    sections: list[SectionInfo] = Field(min_length=1, max_length=200)
    sources: list[Source] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _consistent(self):
        codes = [s.code for s in self.sections]
        if len(set(codes)) != len(codes):
            raise ValueError("section codes must be unique")
        domains = [d.id for d in self.domains]
        if len(set(domains)) != len(domains):
            raise ValueError("domain ids must be unique")
        stray = sorted({s.domain for s in self.sections if s.domain is not None} - set(domains))
        if stray:
            raise ValueError(f"sections refer to unknown domains: {stray}")
        return self

    @property
    def section_codes(self) -> list[str]:
        return [s.code for s in self.sections]

    def section(self, code: object) -> SectionInfo:
        if not isinstance(code, str) or not _SECTION_CODE.match(code):
            raise UnknownSection(f"not a section code: {code!r}")
        for s in self.sections:
            if s.code == code:
                return s
        raise UnknownSection(f"{self.short_name} has no section {code}")

    def domain_weight(self, domain_id: str | None) -> float:
        return next((d.weight for d in self.domains if d.id == domain_id), self.untagged_weight)


def cert_ids() -> list[str]:
    """Installed certifications: folders with a valid-looking id that contain cert.json."""
    root = settings.certs_dir
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and _CERT_ID.match(p.name) and (p / "cert.json").is_file())


def _checked_id(cert_id: object) -> str:
    if not isinstance(cert_id, str) or not _CERT_ID.match(cert_id) or cert_id not in cert_ids():
        raise UnknownCert(f"unknown certification: {cert_id!r}")
    return cert_id


def cert_dir(cert_id: object) -> Path:
    # Built only from an id that matched the pattern and exists on disk.
    return settings.certs_dir / _checked_id(cert_id)


@lru_cache(maxsize=None)
def _load(cert_id: str) -> Cert:
    data = json.loads((settings.certs_dir / cert_id / "cert.json").read_text(encoding="utf-8"))
    cert = Cert.model_validate(data)
    if cert.id != cert_id:
        raise ValueError(f"cert.json id {cert.id!r} doesn't match its folder {cert_id!r}")
    return cert


def get_cert(cert_id: object) -> Cert:
    return _load(_checked_id(cert_id))


def list_certs() -> list[Cert]:
    """Every installed certification whose cert.json is valid (invalid ones are skipped)."""
    out = []
    for cid in cert_ids():
        try:
            out.append(_load(cid))
        except (OSError, ValueError):
            continue
    return out


def section_of(question_id: str) -> str:
    """Section code from a question ID: Q-C01-0195 -> C01."""
    m = _QUESTION_ID.match(question_id or "")
    if not m:
        raise ValueError(f"not a question id: {question_id!r}")
    return m.group(1)


_RELATIVE = re.compile(r"^(cert\.json|objectives/[A-Z]{1,3}\d{2}\.md|questions/[A-Z]{1,3}\d{2}\.json)$")


def install(cert_id: str, files: dict[str, str]) -> Path:
    """Create a certification folder from {relative path: text} in one step: written under a hidden
    name, then renamed into place, so a half-written certification never appears. Paths must be
    cert.json, objectives/<CODE>.md or questions/<CODE>.json."""
    if not isinstance(cert_id, str) or not _CERT_ID.match(cert_id):
        raise ValueError(f"not a certification id: {cert_id!r}")
    if cert_id in cert_ids() or (settings.certs_dir / cert_id).exists():
        raise FileExistsError(cert_id)
    bad = [p for p in files if not _RELATIVE.match(p)]
    if bad:
        raise ValueError(f"unexpected paths: {bad}")
    root = settings.certs_dir
    tmp = root / f".installing-{cert_id}-{secrets.token_hex(4)}"
    final = root / cert_id
    try:
        for sub in ("objectives", "questions", "imports"):
            (tmp / sub).mkdir(parents=True)
        for rel, text in files.items():
            (tmp / rel).write_text(text, encoding="utf-8")
        os.rename(tmp, final)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    reload()
    return final


def remove(cert_id: str) -> None:
    """Delete an installed certification folder (used to undo an install that didn't read back)."""
    shutil.rmtree(cert_dir(cert_id))
    reload()


def reload() -> None:
    """Forget cached cert.json and objective files (after files change on disk)."""
    from .objectives import load_section
    _load.cache_clear()
    load_section.cache_clear()
