"""Live Ollama smoke tests for Phase 2.

These tests require a running Ollama instance with the configured model
pulled. They are gated behind @pytest.mark.integration so they are skipped
by the default `uv run pytest -q -m "not integration"` invocation.

Run with: `uv run pytest -q -m integration tests/test_smoke_ollama.py`

If you see `ConnectionError` or similar, start Ollama:
    ollama serve &
    ollama pull qwen2.5:32b   # or whatever MODEL env var points at

These smoke tests cover:
- AGNT-01: run_agent against real Ollama produces non-empty output
- JUDG-01: run_judge against real Ollama produces a valid JudgeResult

Security note: the diagnostic `print()` statements in these tests dump
truncated `reasoning` strings to stdout for the human checkpoint. Do NOT
paste `-s` output into public issues or chat — it may contain fragments
of `data/nda.md`. Integration tests are local-only by design (T-02-S01).
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

DATA = Path(__file__).parent.parent / "data"


def _load(name: str) -> str:
    path = DATA / name
    assert path.exists(), f"fixture missing: {path}"
    return path.read_text()


def test_agent_smoke():
    """AGNT-01 live round-trip: iteration-zero prompt + real NDA → non-empty review."""
    from src.agent import ITERATION_ZERO_SYSTEM_PROMPT, run_agent

    nda = _load("nda.md")
    result = run_agent(ITERATION_ZERO_SYSTEM_PROMPT, nda)

    assert result is not None
    assert result.strip(), "agent returned empty string"
    # Loose sanity — a real review will be at least a few sentences.
    assert len(result) >= 100, (
        f"agent review suspiciously short ({len(result)} chars); "
        f"head={result[:200]!r}"
    )


def test_judge_smoke():
    """JUDG-01 live round-trip: real Ollama judges the canonical good review.

    Uses output_a.md (the deliberately-correct reference review from Phase 1)
    because we need the judge to produce PARSEABLE output, not necessarily
    high scores. Phase 3 will do the real score calibration.
    """
    from src.judge import run_judge

    nda = _load("nda.md")
    agent_output = _load("output_a.md")
    rubric = _load("rubric.json")
    playbook = _load("playbook.md")

    result = run_judge(nda, agent_output, rubric, playbook)

    # Sentinel detection: if run_judge exhausted retries, result.scores is [].
    assert result.scores, (
        "run_judge returned empty scores list — retry loop exhausted. "
        "Check logs for the raw output that failed to parse, and verify "
        "data/rubric.json + data/playbook.md fit within num_ctx."
    )

    # Smoke assertion: at least one valid score came back.
    assert len(result.scores) >= 1

    # Diagnostic: print reasoning-length stats for the human checkpoint task.
    print(f"\njudge smoke: {len(result.scores)} scores returned")
    for s in result.scores[:3]:
        print(
            f"  {s.item_id} ({s.item_type}) score={s.score} "
            f"reasoning_chars={len(s.reasoning)} "
            f"reasoning_head={s.reasoning[:120]!r}"
        )
