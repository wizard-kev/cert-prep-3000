"""Provider interface (D3). The backend never knows which model it is talking to."""

from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    pass


class TruncatedOutput(ProviderError):
    """The model stopped at its token limit, so the JSON is incomplete (SR8)."""


@dataclass
class Completion:
    text: str
    model: str
    stop_reason: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    seconds: float | None = None


class Provider(Protocol):
    name: str
    model: str

    async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> Completion:
        """Return model output constrained to `schema`. Raises TruncatedOutput on a cut-off."""
        ...

    async def health(self) -> dict:
        ...
