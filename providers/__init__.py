"""
Provider adapters for k8ai agent.
Each provider implements the same BaseProvider interface
so agent.py never needs to know which model it is talking to.
"""

from providers.base import BaseProvider


def load_provider() -> BaseProvider:
    """
    Load provider based on AI_PROVIDER env var.

    Supported values:
      AI_PROVIDER=azure   → Azure OpenAI
      AI_PROVIDER=openai  → OpenAI direct
      AI_PROVIDER=claude  → Anthropic Claude
    """
    import os

    provider = os.getenv("AI_PROVIDER", "").strip().lower()

    if provider == "azure":
        from providers.azure import AzureOpenAIProvider
        return AzureOpenAIProvider()

    elif provider == "openai":
        from providers.openai import OpenAIProvider
        return OpenAIProvider()

    elif provider == "claude":
        from providers.claude import ClaudeProvider
        return ClaudeProvider()

    else:
        raise EnvironmentError(
            "AI_PROVIDER not set or invalid.\n\n"
            "Add this to your .env file:\n"
            "  AI_PROVIDER=azure   → Azure OpenAI\n"
            "  AI_PROVIDER=openai  → OpenAI direct\n"
            "  AI_PROVIDER=claude  → Anthropic Claude"
        )
