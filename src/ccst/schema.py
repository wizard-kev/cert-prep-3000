"""Question schema (plan section 8.3) and the JSON schema sent to the model."""

from typing import Literal

from pydantic import BaseModel, Field

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
# Chapter-specific angles from plan section 11 (network chapters).
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
    """What the model returns. Everything else is filled in by the backend."""
    objectives: list[str] = Field(min_length=1, max_length=3)
    type: Literal["single", "multi"]
    angle: Literal[ANGLES]  # type: ignore[valid-type]
    difficulty: int = Field(ge=1, le=3)
    stem: str = Field(min_length=10, max_length=1200)
    # Optional log excerpt, config snippet, or command output shown in monospace under the stem.
    exhibit: str | None = Field(default=None, max_length=1500)
    options: list[Option] = Field(min_length=4, max_length=6)
    answer: list[str] = Field(min_length=1, max_length=3)
    explanation: str = Field(min_length=1, max_length=1200)
    discriminator_tested: str = Field(min_length=1, max_length=400)


class GeneratedBatch(BaseModel):
    questions: list[GeneratedQuestion]


class Question(GeneratedQuestion):
    id: str
    chapter: int
    domain: str | None
    source_ref: str
    provider: Literal["claude", "ollama"]
    model: str
    status: Literal["draft", "verified", "retired"] = "draft"
    created_at: str
    verified_at: str | None = None
    retired_reason: str | None = None


def model_output_schema(n: int) -> dict:
    """Plain JSON schema for structured outputs. Kept free of $refs so local models
    can follow it; Ollama ignores 'description', so field guidance lives in the prompt."""
    option = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "enum": ["A", "B", "C", "D", "E"]},
            "text": {"type": "string"},
            "rationale": {"type": "string"},
            "role": {"type": "string", "enum": list(ROLES)},
        },
        "required": ["key", "text", "rationale", "role"],
    }
    question = {
        "type": "object",
        "properties": {
            "objectives": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
            "type": {"type": "string", "enum": list(QUESTION_TYPES)},
            "angle": {"type": "string", "enum": list(GENERIC_ANGLES)},
            "difficulty": {"type": "integer", "enum": [1, 2, 3]},
            "stem": {"type": "string"},
            "options": {"type": "array", "items": option, "minItems": 4, "maxItems": 5},
            "answer": {"type": "array", "items": {"type": "string", "enum": ["A", "B", "C", "D", "E"]},
                       "minItems": 1, "maxItems": 3},
            "explanation": {"type": "string"},
            "discriminator_tested": {"type": "string"},
        },
        "required": ["objectives", "type", "angle", "difficulty", "stem", "options",
                     "answer", "explanation", "discriminator_tested"],
    }
    return {
        "type": "object",
        "properties": {"questions": {"type": "array", "items": question, "minItems": n, "maxItems": n}},
        "required": ["questions"],
    }
