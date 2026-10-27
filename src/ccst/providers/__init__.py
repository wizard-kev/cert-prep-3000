from ..config import settings
from .base import Completion, Provider, ProviderError, TruncatedOutput


def get_provider() -> Provider:
    if settings.provider == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider()
    if settings.provider == "claude":
        from .claude import ClaudeProvider
        return ClaudeProvider()
    raise ValueError(f"unknown CCST_PROVIDER {settings.provider!r} (use 'ollama' or 'claude')")


__all__ = ["Completion", "Provider", "ProviderError", "TruncatedOutput", "get_provider"]
