"""Tests for src/agent.py.

AGNT-01: run_agent returns a non-empty string and issues one chat.completions.create
         call with the expected messages, temperature, and extra_body.
AGNT-02: ITERATION_ZERO_SYSTEM_PROMPT contains no rubric/playbook/evaluation vocabulary.
"""

from src.config import config

# P8 banned-token list (cited in RESEARCH.md §Discretion Resolution #6 and §P8 mitigation).
_BANNED_TOKENS = [
    "rubric",
    "playbook",
    "score",
    "scoring",
    "evidence",
    "extraction",
    "judgment item",
    "criteria",
    "criterion",
    "evaluate",
    "evaluation",
    "item_id",
    "0/1/2",
]


def test_run_agent_returns_content(fake_client):
    from src.agent import run_agent

    client = fake_client(["MY REVIEW"])
    result = run_agent("sys", "NDA text")

    assert result == "MY REVIEW"
    assert len(client.calls) == 1


def test_run_agent_calls_create_with_two_messages(fake_client):
    from src.agent import run_agent

    client = fake_client(["anything"])
    run_agent("SYSTEM PROMPT", "NDA BODY")

    kwargs = client.calls[0]
    assert kwargs["messages"] == [
        {"role": "system", "content": "SYSTEM PROMPT"},
        {"role": "user", "content": "NDA BODY"},
    ]


def test_run_agent_passes_num_ctx_and_temperature(fake_client):
    from src.agent import run_agent

    client = fake_client(["anything"])
    run_agent("sys", "NDA")

    kwargs = client.calls[0]
    assert kwargs["temperature"] == config.temperature
    assert kwargs["extra_body"] == {"options": {"num_ctx": config.num_ctx}}
    assert kwargs["model"] == config.model
    # P4: no response_format, no stream, no beta parse.
    assert "response_format" not in kwargs
    assert "stream" not in kwargs


def test_run_agent_handles_none_content(fake_client):
    """Ollama occasionally returns message.content=None; agent must fall back
    to an empty string rather than raising AttributeError downstream."""
    from src.agent import run_agent

    fake_client([None])
    result = run_agent("sys", "NDA")
    assert result == ""


def test_prompt_scrubbed_of_rubric_vocab():
    """AGNT-02 / P8: the iteration-zero agent prompt must not contain any
    rubric, playbook, or evaluation vocabulary. This is a regression gate
    that survives into Phase 5, where the optimiser may rewrite this prompt.
    """
    from src.agent import ITERATION_ZERO_SYSTEM_PROMPT

    lowered = ITERATION_ZERO_SYSTEM_PROMPT.lower()
    for token in _BANNED_TOKENS:
        assert token not in lowered, (
            f"ITERATION_ZERO_SYSTEM_PROMPT contains banned token "
            f"{token!r} (P8/AGNT-02 violation)"
        )
    # Sanity: the prompt is non-trivial.
    assert len(ITERATION_ZERO_SYSTEM_PROMPT.strip()) >= 50
