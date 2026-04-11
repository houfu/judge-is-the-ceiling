"""Tests for src/llm.py get_client factory."""

from src.llm import get_client


def test_get_client_returns_singleton():
    """D-01: get_client must cache the client so both agent.py and judge.py
    share one OpenAI instance per process."""
    a = get_client()
    b = get_client()
    assert a is b
