"""Tests for src/optimiser.py.

OPTM-01: run_optimiser signature excludes NDA (compile-time, not tested).
OPTM-02: feedback pass-through via OptimiserResult.feedback_seen.
OPTM-03: prompt_diff via difflib.unified_diff.
P5: post-hoc vocab scrub sets vocab_warning=True but does NOT retry.
P8: banned-vocab check reuses BANNED_RUBRIC_VOCAB_TOKENS source of truth.
P11: WORD_LIMIT=300 enforced via retry loop; sentinel on exhaustion.
"""

import logging

import pytest
from pydantic import ValidationError

from src.config import config
from src.models import JudgeResult, OptimiserResult, RubricScore

# ------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------

_SHORT_REWRITE = " ".join(["word"] * 70)  # 70 words, under WORD_LIMIT
_OVER_LIMIT = " ".join(["word"] * 350)  # 350 words, over WORD_LIMIT
_MEDIUM_REWRITE = " ".join(["step"] * 100)  # 100 words


def _synthetic_judge_result(scores_by_item: list[int] | None = None) -> JudgeResult:
    """Build a JudgeResult with 8 entries. Optionally override per-item scores.

    Note: feedback text is deliberately free of item-id tokens (e.g. "1a", "2b")
    so that the item-id strip assertion in test_feedback_block_sorted_ascending
    tests the _build_feedback_block behaviour (stripping metadata) rather than
    accidentally passing because the feedback text has no item ids to begin with.
    Use descriptive words only.
    """
    if scores_by_item is None:
        scores_by_item = [0, 1, 2, 0, 1, 2, 0, 1]
    assert len(scores_by_item) == 8
    entries = []
    idx = 0
    descriptors = [
        "confidentiality duration clarity",
        "duration risk judgment text",
        "permitted use breadth clarity",
        "permitted use risk framing",
        "return destruction obligation",
        "return destruction consequence framing",
        "remedies and enforcement clarity",
        "remedies proportionality framing",
    ]
    for issue in (1, 2, 3, 4):
        for letter, item_type in (("a", "extraction"), ("b", "judgment")):
            entries.append(
                RubricScore(
                    item_id=f"{issue}{letter}",
                    item_type=item_type,
                    issue_number=issue,
                    score=scores_by_item[idx],
                    evidence=f"Clause {issue}.1 cited.",
                    reasoning=f"Reason about the {descriptors[idx]}.",
                    feedback=f"Feedback about the {descriptors[idx]}.",
                )
            )
            idx += 1
    return JudgeResult(scores=entries)


_OLD_PROMPT = (
    "You are reviewing a Non-Disclosure Agreement. Identify issues and "
    "assess significance. Output findings as a list."
)


# ------------------------------------------------------------------------
# 1. Happy path
# ------------------------------------------------------------------------


def test_happy_path_returns_optimiser_result(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_SHORT_REWRITE])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert isinstance(result, OptimiserResult)
    assert result.failed is False
    assert result.retry_count == 0
    assert result.prompt_word_count == 70
    assert result.old_word_count == len(_OLD_PROMPT.split())
    assert result.vocab_warning is False
    assert len(result.feedback_seen) == 8
    assert len(client.calls) == 1


# ------------------------------------------------------------------------
# 2. Retry recovery
# ------------------------------------------------------------------------


def test_retry_recovers_on_second_attempt(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_OVER_LIMIT, _SHORT_REWRITE])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert result.failed is False
    assert result.retry_count == 1
    assert result.prompt_word_count == 70
    assert len(client.calls) == 2

    msgs_2 = client.calls[1]["messages"]
    # system + user + assistant (raw overrun) + user (correction)
    assert len(msgs_2) == 4
    assert msgs_2[2]["role"] == "assistant"
    assert msgs_2[2]["content"] == _OVER_LIMIT
    assert msgs_2[3]["role"] == "user"
    assert "350" in msgs_2[3]["content"]
    assert "300" in msgs_2[3]["content"]


# ------------------------------------------------------------------------
# 3. Retry exhaustion → sentinel
# ------------------------------------------------------------------------


def test_retry_exhaustion_returns_sentinel(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_OVER_LIMIT, _OVER_LIMIT, _OVER_LIMIT])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert result.failed is True
    assert result.retry_count == 3
    # D-11 byte-identical preservation of old prompt
    assert result.new_system_prompt == _OLD_PROMPT
    assert result.prompt_diff == ""
    assert result.prompt_word_count == len(_OLD_PROMPT.split())
    assert result.old_word_count == len(_OLD_PROMPT.split())
    assert result.vocab_warning is False
    assert len(client.calls) == 3


# ------------------------------------------------------------------------
# 4. Retry message carries word count feedback
# ------------------------------------------------------------------------


def test_word_overrun_triggers_retry_with_word_count_in_message(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_OVER_LIMIT, _SHORT_REWRITE])
    run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    retry_msg = client.calls[1]["messages"][-1]["content"]
    assert "350" in retry_msg  # observed word count
    assert "300" in retry_msg  # the limit
    assert "Rewrite again" in retry_msg
    assert "no preamble" in retry_msg.lower()


# ------------------------------------------------------------------------
# 5. Vocab warning on banned token — does NOT retry (D-15)
# ------------------------------------------------------------------------


def test_vocab_warning_set_when_banned_token_present(fake_client, caplog):
    from src.optimiser import run_optimiser

    # 75 words including "rubric" — under WORD_LIMIT so no retry;
    # but contains a banned token so vocab_warning must fire.
    contaminated = (
        "Use the rubric to guide your review of confidentiality clauses. "
        + " ".join(["word"] * 70)
    )
    client = fake_client([contaminated])

    with caplog.at_level(logging.WARNING, logger="jitc.optimiser"):
        result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert result.failed is False
    assert result.vocab_warning is True
    assert result.retry_count == 0  # D-15: no retry on vocab hit
    assert len(client.calls) == 1
    # Warning log contains the hit tokens
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("rubric" in r.getMessage().lower() for r in warnings)


# ------------------------------------------------------------------------
# 6. Clean output → vocab_warning stays False
# ------------------------------------------------------------------------


def test_vocab_warning_false_on_clean_output(fake_client):
    from src.optimiser import run_optimiser

    clean = (
        "Read the confidentiality agreement carefully. "
        "Identify clauses that may be unfair. Note duration and scope. "
        + " ".join(["term"] * 60)
    )
    fake_client([clean])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert result.vocab_warning is False


# ------------------------------------------------------------------------
# 7. Unified diff format
# ------------------------------------------------------------------------


def test_prompt_diff_is_unified_diff_format(fake_client):
    from src.optimiser import run_optimiser

    new_prompt = "Completely different content. " + " ".join(["alt"] * 60)
    fake_client([new_prompt])
    result = run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert "--- old_system_prompt" in result.prompt_diff
    assert "+++ new_system_prompt" in result.prompt_diff
    # At least one - and one + line (ignoring the headers)
    body_lines = [
        ln
        for ln in result.prompt_diff.splitlines()
        if ln and not ln.startswith(("---", "+++"))
    ]
    assert any(ln.startswith("-") for ln in body_lines)
    assert any(ln.startswith("+") for ln in body_lines)


# ------------------------------------------------------------------------
# 8. Feedback block sorted ascending, item_id stripped
# ------------------------------------------------------------------------


def test_feedback_block_sorted_ascending_and_strips_item_ids():
    from src.optimiser import _build_feedback_block

    jr = _synthetic_judge_result(scores_by_item=[2, 0, 1, 2, 0, 1, 2, 0])
    block = _build_feedback_block(jr)

    assert len(block) == 8
    assert block[0].startswith("1. [score=0]")
    assert block[-1].startswith("8. [score=2]")
    # item_id tokens must not appear
    joined = " ".join(block)
    for bad in ("1a", "1b", "2a", "2b", "3a", "3b", "4a", "4b"):
        assert bad not in joined


# ------------------------------------------------------------------------
# 9. All 8 feedback items included in optimiser call
# ------------------------------------------------------------------------


def test_all_eight_feedback_items_included_in_user_message(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_SHORT_REWRITE])
    jr = _synthetic_judge_result()
    result = run_optimiser(_OLD_PROMPT, jr)

    assert len(result.feedback_seen) == 8
    user_msg = client.calls[0]["messages"][1]["content"]
    for entry in result.feedback_seen:
        assert entry in user_msg


# ------------------------------------------------------------------------
# 10. OptimiserResult structural invariants
# ------------------------------------------------------------------------


def test_structural_invariants_rejected_by_validator():
    # Word count mismatch
    with pytest.raises(ValidationError):
        OptimiserResult(
            new_system_prompt="one two three",
            feedback_seen=[],
            prompt_diff="",
            prompt_word_count=99,  # lies — actual is 3
            old_word_count=5,
            vocab_warning=False,
            retry_count=0,
            failed=False,
        )
    # Negative old_word_count
    with pytest.raises(ValidationError):
        OptimiserResult(
            new_system_prompt="x",
            feedback_seen=[],
            prompt_diff="",
            prompt_word_count=1,
            old_word_count=-1,
            vocab_warning=False,
            retry_count=0,
            failed=False,
        )
    # retry_count out of range
    with pytest.raises(ValidationError):
        OptimiserResult(
            new_system_prompt="x",
            feedback_seen=[],
            prompt_diff="",
            prompt_word_count=1,
            old_word_count=0,
            vocab_warning=False,
            retry_count=4,  # > 3
            failed=False,
        )


# ------------------------------------------------------------------------
# 11. num_ctx on every call (P6 mitigation)
# ------------------------------------------------------------------------


def test_num_ctx_in_every_call(fake_client):
    from src.optimiser import run_optimiser

    client = fake_client([_OVER_LIMIT, _OVER_LIMIT, _SHORT_REWRITE])
    run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    assert len(client.calls) == 3
    for i, kwargs in enumerate(client.calls):
        assert kwargs["extra_body"] == {
            "options": {"num_ctx": config.num_ctx}
        }, f"call {i} missing extra_body"
        assert kwargs["temperature"] == config.temperature
        assert kwargs["model"] == config.model
        assert "response_format" not in kwargs
        assert "stream" not in kwargs


# ------------------------------------------------------------------------
# 12. Retry exhaustion logs at ERROR (D-12)
# ------------------------------------------------------------------------


def test_retry_exhaustion_logs_error_at_jitc_optimiser(fake_client, caplog):
    from src.optimiser import run_optimiser

    fake_client([_OVER_LIMIT, _OVER_LIMIT, _OVER_LIMIT])
    with caplog.at_level(logging.ERROR, logger="jitc.optimiser"):
        run_optimiser(_OLD_PROMPT, _synthetic_judge_result())

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("exhausted" in r.getMessage().lower() for r in errors)
    combined = " ".join(r.getMessage() for r in errors)
    assert "350" in combined  # final overrun word count
