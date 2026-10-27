"""Question schema (plan section 8.3)."""

from typing import Literal

from pydantic import BaseModel, Field

from .certs import QUESTION_ID, SECTION_CODE

GENERIC_ANGLES = (
    "symptom-to-attack",
    "attack-to-mitigation",
    "mitigation-to-threat",
    "neighbor-discrimination",
    "scenario-with-distractor",
    "which-is-not",
    "root-cause-vs-symptom",
    "cause-and-effect-ordering",
)
# Topic-specific angles (v1 plan section 11), usable by any certification.
CHAPTER_ANGLES = (
    "identify-from-port",
    "secure-replacement",
    "classify-address",
    "nat-scenario",
    "ipv6-shorten-or-type",
    "choose-protocol",
    "choose-band-or-standard",
    "choose-device",
    "classify-factor",
    "interpret-config",
    "complete-config",
    "find-config-error",
    "interpret-output",
    "compute-permissions",
    "choose-tool",
    "classify-element",
    "assess-risk",
    "choose-response",
    "find-missing-element",
)
ANGLES = GENERIC_ANGLES + CHAPTER_ANGLES
# Phase 1 builds single and multi first (Phase 0 decision); ordering/matching come later.
QUESTION_TYPES = ("single", "multi")
STATUSES = ("draft", "verified", "retired")
# Option roles (v2 pools): best = the keyed answer; partial = technically correct but not the best
# answer the stem asks for; related = a neighbouring concept, protocol, or practice; wrong = a
# plausible misconception. Shown to the learner only after answering.
ROLES = ("best", "partial", "related", "wrong")
EXHIBIT_MAX_LINES = 30


class Option(BaseModel):
    key: str = Field(pattern=r"^[A-F]$")
    text: str = Field(min_length=1, max_length=400)
    rationale: str = Field(min_length=1, max_length=600)
    role: Literal[ROLES] | None = None  # type: ignore[valid-type]


class GeneratedQuestion(BaseModel):
    """What the question author (Claude) supplies. Everything else is filled in by the backend."""
    objectives: list[str] = Field(min_length=1, max_length=3)
    type: Literal[QUESTION_TYPES]  # type: ignore[valid-type]
    angle: Literal[ANGLES]  # type: ignore[valid-type]
    difficulty: int = Field(ge=1, le=3)
    stem: str = Field(min_length=10, max_length=1200)
    # Optional log excerpt, config snippet, or command output shown in monospace under the stem.
    exhibit: str | None = Field(default=None, max_length=1500)
    options: list[Option] = Field(min_length=4, max_length=6)
    answer: list[str] = Field(min_length=1, max_length=3)
    explanation: str = Field(min_length=1, max_length=1200)
    discriminator_tested: str = Field(min_length=1, max_length=400)


class Question(GeneratedQuestion):
    id: str = Field(pattern=QUESTION_ID)
    section: str = Field(pattern=SECTION_CODE)
    domain: str | None
    source_ref: str
    # Who wrote the question (provenance only), e.g. provider "claude", model "claude-opus-5-5".
    provider: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,31}$")
    model: str
    status: Literal["draft", "verified", "retired"] = "draft"
    created_at: str
    verified_at: str | None = None
    retired_reason: str | None = None
