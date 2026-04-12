"""Tests for src/loop.py — FakeClient-backed unit tests.

Tests cover:
- Happy path: 3 iterations, correct structure
- Optimiser skipped on last iteration
- Results file written with all iterations
- Deltas key in output JSON
- Metadata envelope (config keys)
- Judge sentinel continues loop
- Optimiser sentinel continues loop
- No-go returns None, no file written
- Delta null on sentinel iteration
- Vocab warning logged
"""

import json
import logging

import pytest

from tests.conftest import VALID_JUDGE_JSON
from src.models import (
    IterationResult,
    PreLoopTestResult,
    RubricScore,
)


# -------------------------------------------------------------------------
# Helpers for building PreLoopTestResult fixtures
# -------------------------------------------------------------------------


def _make_rubric_scores(score: int) -> list[RubricScore]:
    """Build 8 RubricScore entries all with the same score."""
    scores = []
    for issue in (1, 2, 3, 4):
        for letter, item_type in (("a", "extraction"), ("b", "judgment")):
            scores.append(
                RubricScore(
                    item_id=f"{issue}{letter}",
                    item_type=item_type,
                    issue_number=issue,
                    score=score,
                    evidence=f"Clause {issue}.1 cited.",
                    reasoning=f"Reason for {issue}{letter}.",
                    feedback=f"Feedback for {issue}{letter}.",
                )
            )
    return scores


def _make_iteration_result(iteration: int, score: int) -> IterationResult:
    """Build an IterationResult with 8 scores all set to `score`."""
    return IterationResult(
        iteration=iteration,
        system_prompt="<sentinel>",
        agent_output="agent output text",
        scores=_make_rubric_scores(score),
    )


def _make_go_result() -> PreLoopTestResult:
    """Build a PreLoopTestResult with decision='go'.

    output_a: score=2 on all items (extraction=8, judgment=8, total=16)
    output_b: score=0 on judgment items only (extraction=8, judgment=0, total=8)
    gap = 16 - 8 = 8.0 >= 2.0, judgment_gap = 8 - 0 = 8 > 0  → go
    """
    # output_a: all 2s
    a_scores_high = _make_rubric_scores(2)
    # output_b: extraction=2, judgment=0 (alternating by item_type)
    b_scores = []
    for issue in (1, 2, 3, 4):
        b_scores.append(
            RubricScore(
                item_id=f"{issue}a",
                item_type="extraction",
                issue_number=issue,
                score=2,
                evidence="Clause cited.",
                reasoning="reason",
                feedback="feedback",
            )
        )
        b_scores.append(
            RubricScore(
                item_id=f"{issue}b",
                item_type="judgment",
                issue_number=issue,
                score=0,
                evidence="Clause cited.",
                reasoning="reason",
                feedback="feedback",
            )
        )

    a_run1 = IterationResult(
        iteration=1,
        system_prompt="<sentinel>",
        agent_output="good review",
        scores=a_scores_high,
    )
    a_run2 = IterationResult(
        iteration=2,
        system_prompt="<sentinel>",
        agent_output="good review",
        scores=a_scores_high,
    )
    b_run1 = IterationResult(
        iteration=1,
        system_prompt="<sentinel>",
        agent_output="bad review",
        scores=b_scores,
    )
    b_run2 = IterationResult(
        iteration=2,
        system_prompt="<sentinel>",
        agent_output="bad review",
        scores=b_scores,
    )

    return PreLoopTestResult(
        output_a_runs=[a_run1, a_run2],
        output_b_runs=[b_run1, b_run2],
        rationale="Test go rationale.",
        model="test-model",
        temperature=0.0,
        num_ctx=16384,
        timestamp="2026-01-01T00:00:00+00:00",
    )


def _make_nogo_result() -> PreLoopTestResult:
    """Build a PreLoopTestResult with decision='no-go'.

    output_a and output_b both score 0 on everything.
    gap = 0.0 < 2.0 → no-go
    """
    zero_scores = _make_rubric_scores(0)
    run1 = IterationResult(
        iteration=1,
        system_prompt="<sentinel>",
        agent_output="no review",
        scores=zero_scores,
    )
    run2 = IterationResult(
        iteration=2,
        system_prompt="<sentinel>",
        agent_output="no review",
        scores=zero_scores,
    )
    return PreLoopTestResult(
        output_a_runs=[run1, run2],
        output_b_runs=[run1, run2],
        rationale="Test no-go rationale.",
        model="test-model",
        temperature=0.0,
        num_ctx=16384,
        timestamp="2026-01-01T00:00:00+00:00",
    )


# -------------------------------------------------------------------------
# Response builders
# -------------------------------------------------------------------------


def _happy_responses(num_iterations: int = 3) -> list[str]:
    """Build canned responses for a happy-path run.

    Per iteration: agent response + valid judge JSON.
    For all but last iteration: also optimiser response.
    Total for 3 iters: 3 agent + 3 judge + 2 optimiser = 8 responses.
    """
    responses = []
    for i in range(num_iterations):
        responses.append(f"Agent review text for iteration {i}")
        responses.append(VALID_JUDGE_JSON)
        if i < num_iterations - 1:
            responses.append("Rewritten prompt " + "word " * 50)
    return responses


def _invalid_judge_responses(num_retries: int = 3) -> list[str]:
    """Build 3 identical invalid JSON strings to exhaust judge retries."""
    return ["not json"] * num_retries


def _over_limit_optimiser_responses(num_retries: int = 3) -> list[str]:
    """Build 3 over-300-word responses to exhaust optimiser retries."""
    return [" ".join(["word"] * 350)] * num_retries


# -------------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------------


def test_happy_path_three_iterations(fake_client, monkeypatch, tmp_path):
    """3-iteration run returns ExperimentRun with 3 IterationResults."""
    import src.loop as loop

    fake_client(_happy_responses(3))
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", tmp_path / "run_001.json")
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    result = loop.run_experiment()

    assert result is not None
    assert len(result.iterations) == 3
    assert result.iterations[0].iteration == 0
    assert result.iterations[2].iteration == 2
    for it in result.iterations:
        assert it.agent_output != ""
        assert len(it.scores) == 8


def test_optimiser_skipped_on_last_iteration(fake_client, monkeypatch, tmp_path):
    """3-iteration run uses 8 LLM calls total (3 agent + 3 judge + 2 optimiser)."""
    import src.loop as loop

    client = fake_client(_happy_responses(3))
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", tmp_path / "run_001.json")
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    loop.run_experiment()

    # 3 agent + 3 judge + 2 optimiser = 8 total LLM calls
    assert len(client.calls) == 8

    last_iter = loop.run_experiment.__module__
    # Check last iteration has no optimiser data — re-run to inspect
    # (we already consumed the client, so we need to re-setup)


def test_optimiser_fields_empty_on_last_iteration(fake_client, monkeypatch, tmp_path):
    """Last iteration has empty optimiser audit fields."""
    import src.loop as loop

    fake_client(_happy_responses(3))
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", tmp_path / "run_001.json")
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    result = loop.run_experiment()

    last = result.iterations[2]
    assert last.optimiser_feedback_seen == []
    assert last.prompt_diff == ""
    assert last.prompt_word_count == 0


def test_results_file_written_with_all_iterations(fake_client, monkeypatch, tmp_path):
    """Results file is written and contains all iterations + deltas key."""
    import src.loop as loop

    results_path = tmp_path / "run_001.json"
    fake_client(_happy_responses(3))
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", results_path)
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    loop.run_experiment()

    assert results_path.exists()
    data = json.loads(results_path.read_text())
    assert "iterations" in data
    assert len(data["iterations"]) == 3
    assert "deltas" in data


def test_deltas_key_in_output_json(fake_client, monkeypatch, tmp_path):
    """deltas[0] is None, deltas[1] and [2] are dicts with 8 keys."""
    import src.loop as loop

    results_path = tmp_path / "run_001.json"
    fake_client(_happy_responses(3))
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", results_path)
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    loop.run_experiment()

    data = json.loads(results_path.read_text())
    deltas = data["deltas"]
    assert deltas[0] is None
    assert isinstance(deltas[1], dict)
    assert len(deltas[1]) == 8
    assert isinstance(deltas[2], dict)
    assert len(deltas[2]) == 8


def test_run_metadata_envelope(fake_client, monkeypatch, tmp_path):
    """result.config contains model, temperature, num_ctx, num_iterations, ollama_version."""
    import src.loop as loop

    fake_client(_happy_responses(3))
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", tmp_path / "run_001.json")
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    result = loop.run_experiment()

    assert result is not None
    for key in ("model", "temperature", "num_ctx", "num_iterations", "ollama_version"):
        assert key in result.config, f"Missing config key: {key}"
    assert result.config["ollama_version"] == "0.5.13"


def test_judge_sentinel_continues_loop(fake_client, monkeypatch, tmp_path):
    """Judge sentinel mid-loop (iteration 1) does not crash; loop produces 3 iterations."""
    import src.loop as loop

    # Iteration 0: agent + judge (valid)
    # Iteration 1: agent + judge (3x sentinel responses) + optimiser (skipped? no — iter 1 is not last)
    # Actually: iter 1 judge gets 3 bad responses, then optimiser is called for iter 1 since it's not last
    # Iteration 2: agent + judge (valid) [no optimiser — last iteration]
    responses = []
    # iter 0: agent + judge (valid)
    responses.append("Agent review iter 0")
    responses.append(VALID_JUDGE_JSON)
    # iter 0 optimiser (not last)
    responses.append("Rewritten prompt " + "word " * 50)
    # iter 1: agent + judge (3x invalid = sentinel)
    responses.append("Agent review iter 1")
    responses += _invalid_judge_responses(3)  # 3 invalid responses
    # iter 1 optimiser (not last, but judge sentinel so scores=[])
    responses.append("Rewritten prompt 2 " + "word " * 50)
    # iter 2: agent + judge (valid) — no optimiser (last)
    responses.append("Agent review iter 2")
    responses.append(VALID_JUDGE_JSON)

    fake_client(responses)
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", tmp_path / "run_001.json")
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    result = loop.run_experiment()

    assert result is not None
    assert len(result.iterations) == 3
    assert result.iterations[1].scores == []
    assert result.iterations[1].total_score == 0


def test_optimiser_sentinel_continues_loop(fake_client, monkeypatch, tmp_path):
    """Optimiser sentinel (word-limit exhaustion) keeps old prompt and loop continues."""
    from src.agent import ITERATION_ZERO_SYSTEM_PROMPT
    import src.loop as loop

    responses = []
    # iter 0: agent + judge (valid)
    responses.append("Agent review iter 0")
    responses.append(VALID_JUDGE_JSON)
    # iter 0 optimiser: 3x over-limit (sentinel)
    responses += _over_limit_optimiser_responses(3)
    # iter 1: agent + judge (valid)
    responses.append("Agent review iter 1")
    responses.append(VALID_JUDGE_JSON)
    # iter 1 optimiser: valid
    responses.append("Rewritten prompt iter1 " + "word " * 50)
    # iter 2: agent + judge (valid) — no optimiser
    responses.append("Agent review iter 2")
    responses.append(VALID_JUDGE_JSON)

    fake_client(responses)
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", tmp_path / "run_001.json")
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    result = loop.run_experiment()

    assert result is not None
    assert len(result.iterations) == 3
    # iteration 1 should use ITERATION_ZERO_SYSTEM_PROMPT (old prompt preserved)
    assert result.iterations[1].system_prompt == ITERATION_ZERO_SYSTEM_PROMPT


def test_nogo_returns_none_no_file_written(fake_client, monkeypatch, tmp_path):
    """No-go pre-loop gate: run_experiment() returns None, no results file written."""
    import src.loop as loop

    results_path = tmp_path / "run_001.json"
    # No LLM calls should happen
    fake_client([])
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_nogo_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", results_path)
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    result = loop.run_experiment()

    assert result is None
    assert not results_path.exists()


def test_delta_null_on_sentinel_iteration(fake_client, monkeypatch, tmp_path):
    """deltas[1] is None when iteration 1 judge returns sentinel; deltas[2] computed against iter 0."""
    import src.loop as loop

    results_path = tmp_path / "run_001.json"

    responses = []
    # iter 0: agent + judge (valid)
    responses.append("Agent review iter 0")
    responses.append(VALID_JUDGE_JSON)
    # iter 0 optimiser
    responses.append("Rewritten prompt 0 " + "word " * 50)
    # iter 1: agent + judge (sentinel — 3 invalid)
    responses.append("Agent review iter 1")
    responses += _invalid_judge_responses(3)
    # iter 1 optimiser (judge sentinel, scores=[], still called since not last)
    responses.append("Rewritten prompt 1 " + "word " * 50)
    # iter 2: agent + judge (valid) — no optimiser
    responses.append("Agent review iter 2")
    responses.append(VALID_JUDGE_JSON)

    fake_client(responses)
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", results_path)
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)

    loop.run_experiment()

    data = json.loads(results_path.read_text())
    deltas = data["deltas"]
    assert deltas[0] is None  # first iteration always None
    assert deltas[1] is None  # sentinel → None
    assert isinstance(deltas[2], dict)  # computed against iter 0 (last valid)
    assert len(deltas[2]) == 8


def test_vocab_warning_logged(fake_client, monkeypatch, tmp_path, caplog):
    """vocab_warning=True from optimiser triggers logger.warning with 'vocab_warning' substring."""
    import src.loop as loop
    from src.models import OptimiserResult
    from src.agent import ITERATION_ZERO_SYSTEM_PROMPT

    # Build a mock optimiser that returns vocab_warning=True on first call
    call_count = [0]

    def mock_run_optimiser(system_prompt, judge_result):
        call_count[0] += 1
        rewrite = "Clean system prompt text " + "word " * 50
        return OptimiserResult(
            new_system_prompt=rewrite,
            feedback_seen=["feedback item 1"],
            prompt_diff="--- old\n+++ new\n- old line\n+ new line",
            prompt_word_count=len(rewrite.split()),
            old_word_count=len(system_prompt.split()),
            vocab_warning=True,
            retry_count=0,
            failed=False,
        )

    fake_client(_happy_responses(3))
    monkeypatch.setattr(loop, "run_pre_loop_test", lambda: _make_go_result())
    monkeypatch.setattr(loop, "_get_ollama_version", lambda: "0.5.13")
    monkeypatch.setattr(loop, "_RESULTS_FILE", tmp_path / "run_001.json")
    monkeypatch.setattr(loop, "_RESULTS_DIR", tmp_path)
    monkeypatch.setattr(loop.config, "num_iterations", 3)
    monkeypatch.setattr(loop, "run_optimiser", mock_run_optimiser)

    with caplog.at_level(logging.WARNING, logger="jitc.loop"):
        loop.run_experiment()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("vocab_warning" in r.getMessage().lower() for r in warnings), (
        f"Expected 'vocab_warning' in warning log. Got: {[r.getMessage() for r in warnings]}"
    )
