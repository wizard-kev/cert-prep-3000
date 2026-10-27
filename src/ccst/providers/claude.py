"""Claude API provider: tabled until Phase 2 (see plan section 16).

When implemented: key from ANTHROPIC_API_KEY only (SR1), prompt caching with the
breakpoint at the end of the static chapter content, structured outputs via
output_config.format, and a stop_reason == "max_tokens" check (SR8).
"""

from .base import Completion, ProviderError


class ClaudeProvider:
    name = "claude"
    model = "not-configured"

    async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> Completion:
        raise ProviderError("Claude provider is not enabled yet (Phase 2). Set CCST_PROVIDER=ollama.")

    async def health(self) -> dict:
        return {"reachable": False, "model_present": False, "note": "Phase 2"}
