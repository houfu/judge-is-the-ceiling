"""Shared test fixtures for Phase 2."""

import copy
import json
from types import SimpleNamespace

import pytest


class _FakeChatCompletions:
    """Captures kwargs from every chat.completions.create call and pops
    a canned string from `responses` to build a minimal OpenAI-compatible
    response object. Tests inspect `.calls` to verify what was sent.

    Kwargs are deep-copied at capture time so that callers (e.g. run_judge)
    that mutate a persistent `messages` list across retries do not clobber
    earlier call history. Without this, `client.calls[0]["messages"]` would
    alias the live list and always appear to be the most recent state.
    """

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        # Snapshot kwargs so subsequent in-place mutation by the caller
        # (e.g. judge retry loop appending to `messages`) does not rewrite
        # history. deepcopy is fine — messages are small dicts of strings.
        self.calls.append(copy.deepcopy(kwargs))
        if not self._responses:
            raise AssertionError(
                "FakeChatCompletions ran out of canned responses; "
                "test declared fewer than the code attempted"
            )
        content = self._responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class FakeClient:
    """Minimal shim matching the subset of openai.OpenAI used by Phase 2."""

    def __init__(self, responses: list[str]):
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(responses))

    @property
    def calls(self) -> list[dict]:
        return self.chat.completions.calls


@pytest.fixture
def fake_client(monkeypatch):
    """Factory fixture.

    Usage:
        def test_something(fake_client):
            client = fake_client(["canned response 1", "canned response 2"])
            # now src.llm.get_client() returns `client`
            ...
    """

    def _make(responses: list[str]) -> FakeClient:
        client = FakeClient(responses)
        import src.llm

        # Reset any previously cached real client, then install ours.
        monkeypatch.setattr(src.llm, "_client", client)
        return client

    return _make


# A realistic 8-item VALID JudgeResult JSON payload matching data/rubric.json.
# Used by Plan 02-03 judge tests as the "happy path" canned response.
VALID_JUDGE_JSON = json.dumps(
    {
        "scores": [
            {
                "item_id": f"{issue}{letter}",
                "item_type": item_type,
                "issue_number": issue,
                "score": 2,
                "evidence": f"Clause {issue}.1 cited.",
                "reasoning": f"The review addresses item {issue}{letter} directly.",
                "feedback": "Good.",
            }
            for issue in (1, 2, 3, 4)
            for letter, item_type in (("a", "extraction"), ("b", "judgment"))
        ]
    }
)


@pytest.fixture
def valid_judge_json() -> str:
    return VALID_JUDGE_JSON
