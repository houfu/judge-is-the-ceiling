"""Tests for src/judge.py.

JUDG-01: happy path — returns JudgeResult on valid JSON.
JUDG-02: retries 3 times on ValidationError, feeds error back to model.
JUDG-03: _extract_json strips markdown fences.
JUDG-04: every create() call passes extra_body.options.num_ctx.
JUDG-05: retry exhaustion returns JudgeResult(scores=[]) and logs at ERROR.
"""

import logging

import pytest

from src.config import config
from src.models import JudgeResult
from tests.conftest import VALID_JUDGE_JSON

# Shared fixture inputs.
NDA = "# NDA\n1. The Term shall be seven (7) years.\n"
AGENT_OUT = "## Review\nThe term is 7 years.\n"
RUBRIC = '{"items": [{"item_id": "1a"}]}'  # minimal stub — judge doesn't parse this
PLAYBOOK = "Precise extraction guidance."


# =========================================================================
# JUDG-01: happy path
# =========================================================================


def test_happy_path_returns_judge_result(fake_client):
    from src.judge import run_judge

    client = fake_client([VALID_JUDGE_JSON])
    result = run_judge(NDA, AGENT_OUT, RUBRIC, PLAYBOOK)

    assert isinstance(result, JudgeResult)
    assert len(result.scores) == 8
    assert len(client.calls) == 1


def test_happy_path_returns_judge_result_from_fenced_json(fake_client):
    """JUDG-03 end-to-end: fenced valid JSON → stripped → parsed → returned."""
    from src.judge import run_judge

    fenced = "```json\n" + VALID_JUDGE_JSON + "\n```"
    client = fake_client([fenced])
    result = run_judge(NDA, AGENT_OUT, RUBRIC, PLAYBOOK)

    assert len(result.scores) == 8
    assert len(client.calls) == 1


# =========================================================================
# JUDG-02: retry with error feedback
# =========================================================================


def test_retries_three_times_with_error_feedback(fake_client):
    """First 2 attempts return invalid JSON; 3rd returns valid.
    Verifies: retry count, error feedback appended, final success."""
    from src.judge import run_judge

    client = fake_client(["not json", "still not json", VALID_JUDGE_JSON])
    result = run_judge(NDA, AGENT_OUT, RUBRIC, PLAYBOOK)

    assert len(result.scores) == 8
    assert len(client.calls) == 3

    # Attempt 1: 2 messages (system, user)
    msgs_1 = client.calls[0]["messages"]
    assert len(msgs_1) == 2
    assert msgs_1[0]["role"] == "system"
    assert msgs_1[1]["role"] == "user"

    # Attempt 2: original 2 + (assistant raw, user error-feedback) = 4
    msgs_2 = client.calls[1]["messages"]
    assert len(msgs_2) == 4
    assert msgs_2[2]["role"] == "assistant"
    assert msgs_2[2]["content"] == "not json"
    assert msgs_2[3]["role"] == "user"
    assert msgs_2[3]["content"].startswith(
        "Your previous response could not be parsed. Error:"
    )

    # Attempt 3: 4 + (assistant raw, user error-feedback) = 6
    msgs_3 = client.calls[2]["messages"]
    assert len(msgs_3) == 6
    assert msgs_3[4]["role"] == "assistant"
    assert msgs_3[4]["content"] == "still not json"
    assert msgs_3[5]["role"] == "user"
    assert msgs_3[5]["content"].startswith(
        "Your previous response could not be parsed. Error:"
    )


def test_retry_recovers_on_second_attempt(fake_client):
    from src.judge import run_judge

    client = fake_client(["garbage", VALID_JUDGE_JSON])
    result = run_judge(NDA, AGENT_OUT, RUBRIC, PLAYBOOK)

    assert len(result.scores) == 8
    assert len(client.calls) == 2


# =========================================================================
# JUDG-03: markdown fence stripping
# =========================================================================


def test_extract_json_strips_fences():
    from src.judge import _extract_json

    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _extract_json('```\n{"a": 1}\n```') == '{"a": 1}'
    assert _extract_json('{"a": 1}') == '{"a": 1}'


def test_extract_json_strips_prose_preamble():
    from src.judge import _extract_json

    assert _extract_json('Sure, here is the JSON: {"a": 1} Let me know!') == '{"a": 1}'


def test_extract_json_handles_nested_objects():
    from src.judge import _extract_json

    raw = 'noise {"outer": {"inner": 2}} trailing'
    assert _extract_json(raw) == '{"outer": {"inner": 2}}'


def test_extract_json_falls_back_to_raw_when_no_braces():
    from src.judge import _extract_json

    assert _extract_json("no braces here") == "no braces here"
    assert _extract_json("") == ""


# =========================================================================
# JUDG-04: num_ctx in every call
# =========================================================================


def test_num_ctx_in_every_call(fake_client):
    """D-04 / P6: num_ctx must appear on EVERY call, including retry calls."""
    from src.judge import run_judge

    client = fake_client(["bad", "still bad", VALID_JUDGE_JSON])
    run_judge(NDA, AGENT_OUT, RUBRIC, PLAYBOOK)

    assert len(client.calls) == 3
    for i, kwargs in enumerate(client.calls):
        assert kwargs["extra_body"] == {
            "options": {"num_ctx": config.num_ctx}
        }, f"call {i} missing extra_body"
        assert kwargs["temperature"] == config.temperature
        assert kwargs["model"] == config.model
        # P4: no response_format.
        assert "response_format" not in kwargs


# =========================================================================
# JUDG-05: graceful failure on retry exhaustion
# =========================================================================


def test_graceful_failure_on_retry_exhaustion(fake_client):
    from src.judge import run_judge

    client = fake_client(["bad 1", "bad 2", "bad 3"])
    result = run_judge(NDA, AGENT_OUT, RUBRIC, PLAYBOOK)

    assert isinstance(result, JudgeResult)
    assert result.scores == []  # sentinel
    assert len(client.calls) == 3


def test_graceful_failure_logs_raw_output(fake_client, caplog):
    from src.judge import run_judge

    fake_client(["bad A", "bad B", "bad C"])
    with caplog.at_level(logging.ERROR, logger="jitc.judge"):
        run_judge(NDA, AGENT_OUT, RUBRIC, PLAYBOOK)

    # At least one ERROR record mentions exhaustion AND a raw output string.
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("exhausted" in r.getMessage().lower() for r in error_records)
    combined = " ".join(r.getMessage() for r in error_records)
    assert "bad C" in combined  # the final raw output should be logged


def test_warning_logged_on_every_parse_failure(fake_client, caplog):
    """P7: every parse failure (including successful retries) must leave a WARNING trail."""
    from src.judge import run_judge

    fake_client(["garbage 1", VALID_JUDGE_JSON])
    with caplog.at_level(logging.WARNING, logger="jitc.judge"):
        run_judge(NDA, AGENT_OUT, RUBRIC, PLAYBOOK)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) >= 1
    assert any("parse failed" in r.getMessage().lower() for r in warnings)


# =========================================================================
# Helper / plumbing tests
# =========================================================================


def test_retry_user_message_includes_error_and_reminder():
    from src.judge import _retry_user_message

    msg = _retry_user_message(ValueError("bad json at line 5"))
    assert "bad json at line 5" in msg
    assert "valid JSON" in msg
    assert "No preamble" in msg
    assert "No markdown" in msg


def test_retry_user_message_bounded():
    from src.judge import _retry_user_message, MAX_ERROR_CHARS

    huge = ValueError("x" * 5000)
    msg = _retry_user_message(huge)
    # Error text is truncated, but the reminder adds ~200 chars of fixed text.
    assert len(msg) <= MAX_ERROR_CHARS + 400
    assert "truncated" in msg


def test_build_user_message_uses_top_level_headings():
    """D-06/D-07: sections use distinctive `# === JITC_*_START/END ===` envelope
    markers so neither the NDA (which may itself contain top-level `#` headings)
    nor the agent's markdown can collide with our section dividers."""
    from src.judge import _build_user_message

    result = _build_user_message(
        "NDA BODY", "AGENT REVIEW", "RUBRIC JSON", "PLAYBOOK TEXT"
    )
    # Distinctive envelope markers for each section.
    assert "# === JITC_NDA_START ===" in result
    assert "# === JITC_NDA_END ===" in result
    assert "# === JITC_AGENT_OUTPUT_START ===" in result
    assert "# === JITC_AGENT_OUTPUT_END ===" in result
    assert "# === JITC_RUBRIC_START ===" in result
    assert "# === JITC_RUBRIC_END ===" in result
    assert "# === JITC_PLAYBOOK_START ===" in result
    assert "# === JITC_PLAYBOOK_END ===" in result
    # Payload bodies preserved verbatim.
    assert "NDA BODY" in result
    assert "AGENT REVIEW" in result
    assert "RUBRIC JSON" in result
    assert "PLAYBOOK TEXT" in result
    # Fixed ordering (D-06): NDA → Agent Output → Rubric → Playbook.
    assert result.index("JITC_NDA_START") < result.index("JITC_AGENT_OUTPUT_START")
    assert result.index("JITC_AGENT_OUTPUT_START") < result.index("JITC_RUBRIC_START")
    assert result.index("JITC_RUBRIC_START") < result.index("JITC_PLAYBOOK_START")
