"""
Provider adapters for k8ai agent.
Each provider implements the same BaseProvider interface
so agent.py never needs to know which model it is talking to.
"""

from k8ai.providers.base import BaseProvider


def load_provider() -> BaseProvider:
    """
    Load provider based on AI_PROVIDER env var.

    Supported values:
      AI_PROVIDER=azure   -> Azure OpenAI
      AI_PROVIDER=openai  -> OpenAI direct
      AI_PROVIDER=claude  -> Anthropic Claude
    """
    import os

    provider = os.getenv("AI_PROVIDER", "").strip().lower()

    if provider == "azure":
        from k8ai.providers.azure import AzureOpenAIProvider
        return AzureOpenAIProvider()

    elif provider == "openai":
        from k8ai.providers.openai import OpenAIProvider
        return OpenAIProvider()

    elif provider == "claude":
        from k8ai.providers.claude import ClaudeProvider
        return ClaudeProvider()

    else:
        raise EnvironmentError(
            "AI_PROVIDER not set or invalid.\n\n"
            "Run 'k8ai init' to configure your AI provider.\n\n"
            "Supported providers:\n"
            "  azure   -> Azure OpenAI\n"
            "  openai  -> OpenAI direct\n"
            "  claude  -> Anthropic Claude"
        )
