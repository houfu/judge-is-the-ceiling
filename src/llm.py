"""Shared OpenAI client factory (D-01).

Both agent and judge call get_client() rather than constructing OpenAI
directly, so base_url / api_key / timeouts live in one place. The module
is deliberately single-threaded (see RESEARCH.md open question #6).
"""

from openai import OpenAI

from src.config import config

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Return a lazily-created sync OpenAI client configured for Ollama."""
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )
    return _client
