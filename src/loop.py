"""Main experiment loop (Phase 5).

Wires agent -> judge -> optimiser for N iterations, producing
results/run_001.json. All component functions are imported — this
module does orchestration, accumulation, and file I/O only.

Design: D-01..D-12 from 05-CONTEXT.md.
"""

import json
import logging
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent import ITERATION_ZERO_SYSTEM_PROMPT, run_agent
from src.config import config
from src.judge import run_judge
from src.models import ExperimentRun, IterationResult
from src.optimiser import run_optimiser
from src.pre_loop_test import _print_banner, run_pre_loop_test

logger = logging.getLogger("jitc.loop")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _REPO_ROOT / "data"
_RESULTS_DIR = _REPO_ROOT / "results"
_RESULTS_FILE = _RESULTS_DIR / "run_001.json"


def _get_ollama_version() -> str:
    """Fetch the running Ollama version from the local API.

    Returns "unknown" on any failure (timeout, connection refused, parse error).
    T-05-03 mitigation: 5-second timeout on urlopen.
    """
    try:
        with urllib.request.urlopen(
            "http://localhost:11434/api/version", timeout=5
        ) as resp:
            data = json.loads(resp.read().decode())
            return data.get("version", "unknown")
    except Exception:
        return "unknown"


def _compute_deltas(
    iterations: list[IterationResult],
) -> list[dict[str, int] | None]:
    """Compute per-item score deltas relative to the previous valid iteration.

    D-03, D-04, D-05:
    - iterations[0] always returns None (no prior to compare against)
    - sentinel iterations (scores==[]) return None
    - deltas are computed against the last iteration with non-empty scores
    - last_valid_scores tracks the most recent valid iteration scores

    Returns a list of the same length as `iterations`. Each entry is either
    None (first iteration or sentinel) or a dict mapping item_id -> delta int.
    """
    result: list[dict[str, int] | None] = []
    last_valid_scores: dict[str, int] | None = None

    for i, it in enumerate(iterations):
        if i == 0 or last_valid_scores is None or not it.scores:
            result.append(None)
        else:
            current = {s.item_id: s.score for s in it.scores}
            delta = {
                k: current.get(k, 0) - last_valid_scores.get(k, 0) for k in current
            }
            result.append(delta)

        if it.scores:
            last_valid_scores = {s.item_id: s.score for s in it.scores}

    return result


def _write_results(
    run: ExperimentRun,
    deltas: list[dict[str, int] | None],
    path: Path,
) -> None:
    """Serialize ExperimentRun + deltas to JSON at `path`.

    D-04 / Pitfall 3: uses model_dump() (NOT model_dump_json) to get a dict,
    then injects `deltas` before JSON serialisation. `default=str` is a
    safety net for any non-JSON-native types.
    """
    data = run.model_dump()
    data["deltas"] = deltas
    path.write_text(json.dumps(data, indent=2, default=str))


def run_experiment() -> ExperimentRun | None:
    """Run the full experiment: pre-loop gate, N iterations of agent->judge->optimiser.

    D-01: returns ExperimentRun on go, None on no-go.
    D-06: writes results file after every completed iteration.
    D-12: optimiser is NOT called after the last iteration.

    Returns:
        ExperimentRun on success, None if the pre-loop gate blocks.
    """
    _RESULTS_DIR.mkdir(exist_ok=True)  # Pitfall 6

    # Pre-loop gate (D-01, D-02)
    pre_loop_result = run_pre_loop_test()

    if pre_loop_result.decision == "no-go":
        _print_banner(pre_loop_result)
        logger.warning("pre-loop gate: no-go — aborting")
        return None

    _print_banner(pre_loop_result)  # go banner for visibility

    # Metadata
    ollama_version = _get_ollama_version()

    run = ExperimentRun(
        experiment_id="run_001",
        timestamp=datetime.now(timezone.utc).isoformat(),
        config={
            "model": config.model,
            "temperature": config.temperature,
            "num_ctx": config.num_ctx,
            "num_iterations": config.num_iterations,
            "ollama_version": ollama_version,
        },
        nda_file="data/nda.md",
        rubric_file="data/rubric.json",
        playbook_file="data/playbook.md",
        pre_loop_test=pre_loop_result,
    )

    # Load static data
    nda = (_DATA_DIR / "nda.md").read_text()
    rubric = (_DATA_DIR / "rubric.json").read_text()
    playbook = (_DATA_DIR / "playbook.md").read_text()

    current_system_prompt = ITERATION_ZERO_SYSTEM_PROMPT

    for i in range(config.num_iterations):
        logger.info("[iter %d/%d] agent call", i + 1, config.num_iterations)
        agent_output = run_agent(current_system_prompt, nda)

        judge_result = run_judge(nda, agent_output, rubric, playbook)
        if not judge_result.scores:
            logger.error("judge sentinel at iter %d — continuing", i + 1)

        iter_result = IterationResult(
            iteration=i,
            system_prompt=current_system_prompt,
            agent_output=agent_output,
            scores=judge_result.scores,
        )

        # D-12: only call optimiser if NOT the last iteration
        if i < config.num_iterations - 1:
            opt_result = run_optimiser(current_system_prompt, judge_result)
            current_system_prompt = (
                opt_result.new_system_prompt
            )  # D-11: works for both success and failed
            iter_result.optimiser_feedback_seen = opt_result.feedback_seen
            iter_result.prompt_diff = opt_result.prompt_diff
            iter_result.prompt_word_count = opt_result.prompt_word_count
            if opt_result.vocab_warning:
                logger.warning(
                    "[iter %d/%d] vocab_warning — P5 signal",
                    i + 1,
                    config.num_iterations,
                )

        run.iterations.append(iter_result)

        # D-06: write results after every iteration
        deltas = _compute_deltas(run.iterations)
        _write_results(run, deltas, _RESULTS_FILE)

        # D-07: progress line
        prev_total = run.iterations[i - 1].total_score if i > 0 else 0
        delta_total = iter_result.total_score - prev_total
        delta_sign = "+" if delta_total >= 0 else ""
        words = (
            iter_result.prompt_word_count
            if iter_result.prompt_word_count > 0
            else len(current_system_prompt.split())
        )
        print(
            f"[iter {i + 1}/{config.num_iterations}] "
            f"total={iter_result.total_score} "
            f"ext={iter_result.extraction_score} "
            f"jud={iter_result.judgment_score} "
            f"delta={delta_sign}{delta_total} "
            f"words={words}"
        )

    print(
        f"\nExperiment complete — {len(run.iterations)} iterations — see {_RESULTS_FILE}"
    )
    return run


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    result = run_experiment()
    if result is None:
        sys.exit(1)
