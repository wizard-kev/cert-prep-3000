"""Question schema (plan section 8.3)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

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
# single and multi (choose N) serve every certification. ordering (put the options in sequence) and
# matching (pair each option with one of `match_targets`) are offered to certifications whose exam
# uses them (v2 plan 7.4, phase P10). Answers: single/multi = keys; ordering = every key, in order;
# matching = one "<key><target number>" pair per option, e.g. "A2".
QUESTION_TYPES = ("single", "multi", "ordering", "matching")
MAX_MATCH_TARGETS = 8
# Question lifecycle (v2 plan section 6). Unreviewed: passed the import checks. Passive
# (Passively-Validated): answered at least once without a dispute. Validated: the learner marked it
# "Looks right". Disputed: reported, waiting for the learner to confirm or undo; not served.
STATUSES = ("unreviewed", "passive", "validated", "disputed", "retired")
SERVED_STATUSES = ("unreviewed", "passive", "validated")
STATUS_LABELS = {"unreviewed": "Unreviewed", "passive": "Passively-Validated", "validated": "Validated",
                 "disputed": "Disputed", "retired": "Retired"}
LEGACY_STATUSES = {"draft": "unreviewed", "verified": "validated"}  # v1 names, still read
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
    options: list[Option] = Field(min_length=3, max_length=6)
    answer: list[Annotated[str, Field(pattern=r"^[A-F][1-8]?$")]] = Field(min_length=1, max_length=6)
    # Matching only: the descriptions the options are paired with (numbered from 1; may include extras).
    match_targets: list[Annotated[str, Field(min_length=1, max_length=200)]] | None = Field(
        default=None, min_length=3, max_length=MAX_MATCH_TARGETS)
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
    status: Literal[STATUSES] = "unreviewed"  # type: ignore[valid-type]
    created_at: str
    verified_at: str | None = None    # when the learner marked it "Looks right" (Validated)
    seen_at: str | None = None        # first answered, in any mode (passive validation)
    retired_reason: str | None = None
    disputed_reason: str | None = None
    disputed_at: str | None = None
    disputed_session: str | None = None
    status_before_dispute: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _v1_status(cls, v):
        return LEGACY_STATUSES.get(v, v)

    @property
    def served(self) -> bool:
        return self.status in SERVED_STATUSES

    def stored(self) -> dict:
        """As written to a pool file: `match_targets` only on matching questions, so the pools of the
        other types don't change shape."""
        data = self.model_dump()
        if data.get("match_targets") is None:
            data.pop("match_targets", None)
        return data
