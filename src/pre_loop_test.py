"""Pre-loop validation gate (Phase 3).

Runs data/output_a.md and data/output_b.md through run_judge twice each
and emits a go/no-go decision to:
  - results/pre_loop_test.json   (structured — PreLoopTestResult dump)
  - stdout                        (human-readable banner via __main__)

Design notes:
- D-07: 2 runs per output (4 judge calls total). Run 1 authoritative;
  run 2 drives variance_warning only.
- D-06: judge sentinel (scores==[]) forces decision=no-go, does NOT raise.
- D-10: _print_banner is module-private and called only from __main__.
  Library consumers (Phase 4/5) import run_pre_loop_test and never see
  stdout spam.
- run_judge's retry/fence/graceful-failure contract is inherited from
  Phase 2; this module does NOT add a second retry layer.

P1: the gate exists to falsify self-reference collapse before building
the optimiser. P3: dual runs + metadata snapshot enable drift detection.
P10: the 2.0-point threshold is load-bearing and intentionally hard-coded
(not an env var).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.config import config
from src.judge import run_judge
from src.models import IterationResult, PreLoopTestResult

logger = logging.getLogger("jitc.preloop")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _REPO_ROOT / "data"
_RESULTS_DIR = _REPO_ROOT / "results"
_RESULTS_FILE = _RESULTS_DIR / "pre_loop_test.json"

_FIXTURE_A = _DATA_DIR / "output_a.md"
_FIXTURE_B = _DATA_DIR / "output_b.md"
_SENTINEL_A = "<pre-loop fixture: data/output_a.md>"  # D-03
_SENTINEL_B = "<pre-loop fixture: data/output_b.md>"


def _judge_one(
    fixture_label: str,
    iteration: int,
    nda: str,
    agent_output: str,
    rubric: str,
    playbook: str,
    system_prompt_sentinel: str,
) -> IterationResult:
    """Run run_judge once and wrap the result in an IterationResult.

    `iteration` is the run-number-within-this-output (1 or 2), not a
    loop iteration counter. The field name matches IterationResult's
    schema (TEST-02 — same schema as loop iterations).
    """
    logger.info("judging %s run %d/2", fixture_label, iteration)
    result = run_judge(nda, agent_output, rubric, playbook)
    if not result.scores:
        logger.error(
            "judge sentinel failure for %s run %d — gate decision will be no-go",
            fixture_label,
            iteration,
        )
    return IterationResult(
        iteration=iteration,
        system_prompt=system_prompt_sentinel,
        agent_output=agent_output,
        scores=result.scores,
    )


def _build_rationale(
    a_runs: list[IterationResult],
    b_runs: list[IterationResult],
    gap: float,
    judgment_gap: int,
    threshold: float,
    decision: str,
) -> str:
    """Build the rationale string per resolution #4 — three branches."""
    a1 = a_runs[0]
    b1 = b_runs[0]

    # Sentinel branch (Case 3).
    sentinel_failures = []
    if not a1.scores:
        sentinel_failures.append("data/output_a.md run 1")
    if not b1.scores:
        sentinel_failures.append("data/output_b.md run 1")
    if sentinel_failures:
        return (
            f"judge retry exhausted for {', '.join(sentinel_failures)} — "
            f"see jitc.judge ERROR logs for raw output. Gate forced to "
            f"no-go. Investigate prompt construction or num_ctx before "
            f"re-running."
        )

    if decision == "go":
        return (
            f"output_a total_score={a1.total_score} "
            f"(extraction={a1.extraction_score}, judgment={a1.judgment_score}) "
            f"outscored output_b total_score={b1.total_score} "
            f"(extraction={b1.extraction_score}, judgment={b1.judgment_score}) "
            f"by gap={gap:.2f} against threshold={threshold:.2f}; "
            f"judgment_gap={judgment_gap} is positive. "
            f"Gate passes — loop is worth building."
        )
    return (
        f"output_a total_score={a1.total_score} "
        f"(extraction={a1.extraction_score}, judgment={a1.judgment_score}); "
        f"output_b total_score={b1.total_score} "
        f"(extraction={b1.extraction_score}, judgment={b1.judgment_score}); "
        f"gap={gap:.2f} vs threshold={threshold:.2f}; "
        f"judgment_gap={judgment_gap}. "
        f"Gate fails — the judge is not reliably distinguishing the good "
        f"review from the flawed one, so the loop is not worth building. "
        f"Investigate playbook specificity for judgment items and re-run."
    )


def run_pre_loop_test() -> PreLoopTestResult:
    """Run the pre-loop validation gate and write results/pre_loop_test.json.

    Reads data/nda.md, data/output_a.md, data/output_b.md, data/rubric.json,
    and data/playbook.md. Calls run_judge 4 times (2 outputs × 2 runs).
    Aggregates into a PreLoopTestResult via the model validator. Writes
    the JSON artifact. Returns the result.

    Does NOT print to stdout (D-10). Does NOT raise on judge sentinel
    failure (D-06) — the sentinel path produces a no-go PreLoopTestResult
    which the caller can inspect.
    """
    _RESULTS_DIR.mkdir(exist_ok=True)

    # Capture metadata BEFORE any judge call (resolution #3 / P3).
    timestamp = datetime.now(timezone.utc).isoformat()
    model = config.model
    temperature = config.temperature
    num_ctx = config.num_ctx
    logger.info(
        "pre-loop gate start: model=%s temperature=%.2f num_ctx=%d",
        model,
        temperature,
        num_ctx,
    )

    nda = (_DATA_DIR / "nda.md").read_text()
    output_a = _FIXTURE_A.read_text()
    output_b = _FIXTURE_B.read_text()
    rubric = (_DATA_DIR / "rubric.json").read_text()
    playbook = (_DATA_DIR / "playbook.md").read_text()

    # D-07: 2 runs per output, run 1 is authoritative.
    output_a_runs = [
        _judge_one("data/output_a.md", 1, nda, output_a, rubric, playbook, _SENTINEL_A),
        _judge_one("data/output_a.md", 2, nda, output_a, rubric, playbook, _SENTINEL_A),
    ]
    output_b_runs = [
        _judge_one("data/output_b.md", 1, nda, output_b, rubric, playbook, _SENTINEL_B),
        _judge_one("data/output_b.md", 2, nda, output_b, rubric, playbook, _SENTINEL_B),
    ]

    # First pass: construct a probe to let the validator compute gap/decision,
    # then build the rationale string, then construct the final result. The
    # probe pattern keeps rationale assembly out of the model validator
    # (Resolution #1 — validator owns arithmetic only).
    probe = PreLoopTestResult(
        output_a_runs=output_a_runs,
        output_b_runs=output_b_runs,
        rationale="<probe>",
        model=model,
        temperature=temperature,
        num_ctx=num_ctx,
        timestamp=timestamp,
    )
    rationale = _build_rationale(
        output_a_runs,
        output_b_runs,
        probe.gap,
        probe.judgment_gap,
        probe.threshold,
        probe.decision,
    )

    result = PreLoopTestResult(
        output_a_runs=output_a_runs,
        output_b_runs=output_b_runs,
        rationale=rationale,
        model=model,
        temperature=temperature,
        num_ctx=num_ctx,
        timestamp=timestamp,
    )

    _RESULTS_FILE.write_text(result.model_dump_json(indent=2))
    log_level = logging.INFO if result.decision == "go" else logging.WARNING
    logger.log(
        log_level,
        "pre-loop gate complete: decision=%s gap=%.2f judgment_gap=%d variance=%s",
        result.decision,
        result.gap,
        result.judgment_gap,
        result.variance_warning,
    )
    return result


def _print_banner(result: PreLoopTestResult) -> None:
    """Module-private banner printer. Called ONLY from __main__ (D-10)."""
    sep = "=" * 43
    a1 = result.output_a_runs[0]
    b1 = result.output_b_runs[0]

    # Sentinel variant — error banner.
    if not a1.scores or not b1.scores:
        print(sep)
        print("  PRE-LOOP VALIDATION GATE — ERROR")
        print(sep)
        print(f"Model:       {result.model}")
        print(f"Timestamp:   {result.timestamp}")
        print()
        print("Judge sentinel failure detected:")
        if not a1.scores:
            print("  - output_a run 1: scores=[] (retry exhausted)")
        if not b1.scores:
            print("  - output_b run 1: scores=[] (retry exhausted)")
        if not result.output_a_runs[1].scores:
            print("  - output_a run 2: scores=[] (retry exhausted)")
        if not result.output_b_runs[1].scores:
            print("  - output_b run 2: scores=[] (retry exhausted)")
        print()
        print(f"Decision:    {result.decision.upper()}")
        rationale_snip = result.rationale[:140] + (
            "..." if len(result.rationale) > 140 else ""
        )
        print(f"Rationale:   {rationale_snip}")
        print("See jitc.judge ERROR logs above for the raw model output.")
        print(sep)
        return

    # Normal variant.
    print(sep)
    print("  PRE-LOOP VALIDATION GATE")
    print(sep)
    print(f"Model:       {result.model}")
    print(f"Temperature: {result.temperature}")
    print(f"num_ctx:     {result.num_ctx}")
    print(f"Timestamp:   {result.timestamp}")
    print()
    print(
        f"output_a:    total={a1.total_score}  "
        f"extraction={a1.extraction_score}  judgment={a1.judgment_score}"
    )
    print(
        f"output_b:    total={b1.total_score}  "
        f"extraction={b1.extraction_score}  judgment={b1.judgment_score}"
    )
    print()
    print(f"Gap:         {result.gap:.2f}  (threshold: {result.threshold:.2f})")
    if result.judgment_gap > 0:
        print(f"Judgment:    output_a leads by {result.judgment_gap}")
    elif result.judgment_gap < 0:
        print(f"Judgment:    output_b leads by {-result.judgment_gap}")
    else:
        print("Judgment:    tie")
    variance_text = (
        "WARNING — per-item scores diverged between runs"
        if result.variance_warning
        else "no warning"
    )
    print(f"Variance:    {variance_text}")
    print(f"Decision:    {result.decision.upper()}")
    rationale_snip = result.rationale[:140] + (
        "..." if len(result.rationale) > 140 else ""
    )
    print(f"Rationale:   {rationale_snip}")
    print(sep)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    _result = run_pre_loop_test()
    _print_banner(_result)
