# Phase 5: Main Loop - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `src/loop.py` — a library function `run_experiment() -> ExperimentRun` plus a `__main__` script wrapper that executes the full experiment: pre-loop gate -> N iterations of agent -> judge -> optimiser -> write results. Produces `results/run_001.json` containing a complete `ExperimentRun` artifact with all iteration data, per-item deltas, and run metadata.

**In scope:** The main loop function, the `__main__` script wrapper, pre-loop gate integration (run gate first, exit on no-go), per-iteration result accumulation and incremental file writes, per-item delta computation at write time, per-iteration progress banners, run metadata envelope (model with quantisation tag, Ollama version, temperature, timestamp), and resilient iteration failure handling (LOOP-04).

**Out of scope:** Streamlit dashboard (v2), human review tooling, multi-model comparison, any modification to `src/agent.py`, `src/judge.py`, `src/optimiser.py`, or `src/pre_loop_test.py`. Feedback deduplication across iterations (Phase 4 deferred — not this phase). Score trajectory analysis or plateau detection (v2 VIZ/ANAL requirements).

</domain>

<decisions>
## Implementation Decisions

### Pre-Loop Gate Integration

- **D-01:** `loop.py` calls `run_pre_loop_test()` at the start of `run_experiment()`. If `result.decision == "no-go"`, log the result, print the pre-loop banner via `_print_banner()`, and exit cleanly (return `None` or raise `SystemExit`). The gate is embedded — user runs one command (`uv run python src/loop.py`) for the full experiment.

- **D-02:** On no-go, **no results file is created**. Only the banner is printed and the process exits. `results/` stays clean — only successful (or partially successful) runs produce files.

### Delta Tracking

- **D-03:** Per-item deltas — 8 delta values per iteration, keyed by `item_id`. For each rubric item, `delta = current_score - previous_score`. Iteration 0 has no deltas (no previous iteration to compare against).

- **D-04:** Deltas are computed at write time, NOT stored on `IterationResult`. The loop computes deltas when assembling the final `ExperimentRun` JSON. This avoids adding new fields to `IterationResult` (no backward-compat concerns) and avoids Pydantic model changes. The deltas are stored as a top-level key in the JSON output alongside `iterations`, e.g.:
  ```json
  {
    "experiment_id": "...",
    "iterations": [...],
    "deltas": [
      null,
      {"1a": 0, "1b": 1, "2a": 0, "2b": -1, "3a": 1, "3b": 0, "4a": 0, "4b": 0},
      ...
    ]
  }
  ```
  First entry is `null` (iteration 0 has no predecessor). Subsequent entries are `dict[str, int]` mapping `item_id` to score change.

- **D-05:** Delta computation must handle judge sentinel failure gracefully. If iteration N has `scores == []` (judge failed), that iteration's delta entry is `null` and iteration N+1's delta is computed against the last iteration that had valid scores (or `null` if no valid predecessor exists).

### Partial Write Strategy

- **D-06:** Write `results/run_001.json` after every completed iteration. Overwrite the file each time with the full `ExperimentRun` (including all completed iterations + their deltas). If the process dies mid-iteration, at most 1 iteration of work is lost. The file always contains a valid, parseable `ExperimentRun`.

- **D-07:** Per-iteration progress summary printed to stdout after each iteration completes. Format: a short line showing iteration number, total/extraction/judgment scores, delta from previous iteration's total, and word count of the new system prompt. Gives real-time visibility during a long run (~30+ minutes for 5 iterations against gemma4:26b).

### Run Metadata Envelope

- **D-08:** `ExperimentRun.config` dict populated at run start with: `model` (from `config.model`, includes quantisation tag e.g. `gemma4:26b`), `temperature` (from `config.temperature`), `num_ctx` (from `config.num_ctx`), `num_iterations` (from `config.num_iterations`), `ollama_version` (fetched via HTTP GET to `http://localhost:11434/api/version` — if the call fails, store `"unknown"`).

- **D-09:** Run file naming: `results/run_001.json` as stated in SC-1. For simplicity, use a fixed filename. If the user wants multiple runs, they can rename the file between runs. Auto-incrementing adds complexity without value for a bounded experiment.

### Loop Structure

- **D-10:** The loop structure is:
  1. Run pre-loop gate → exit on no-go
  2. Build metadata envelope
  3. Set `current_system_prompt = ITERATION_ZERO_SYSTEM_PROMPT`
  4. For `i in range(config.num_iterations)`:
     a. `agent_output = run_agent(current_system_prompt, nda_text)`
     b. `judge_result = run_judge(nda_text, agent_output, rubric, playbook)`
     c. Build `IterationResult` with scores, system_prompt, agent_output
     d. If `i < num_iterations - 1`: `opt_result = run_optimiser(current_system_prompt, judge_result)` and update `current_system_prompt = opt_result.new_system_prompt`. Populate `IterationResult.optimiser_feedback_seen`, `.prompt_diff`, `.prompt_word_count` from the `OptimiserResult`.
     e. Append `IterationResult` to iterations list
     f. Compute deltas, write `results/run_001.json`
     g. Print per-iteration progress line
  5. Print final summary banner

- **D-11:** LOOP-04 resilience: if `run_judge` returns sentinel `JudgeResult(scores=[])`, log the failure and continue. The `IterationResult` is still appended (with `scores=[]`, `total_score=0`). If `run_optimiser` returns `OptimiserResult(failed=True)`, `current_system_prompt` stays unchanged (the sentinel contract handles this automatically). The loop never crashes on a single iteration failure.

- **D-12:** The optimiser is NOT called after the last iteration (iteration N-1). The optimised prompt would never be used by the agent, so the LLM call would be wasted. The last iteration's `optimiser_feedback_seen`, `prompt_diff`, and `prompt_word_count` fields retain their defaults (`[]`, `""`, `0`).

### Claude's Discretion

The following are deliberately left for the planner/executor:

- **Exact progress line format.** D-07 gives the content requirements; exact formatting is planner's call.
- **Final summary banner design.** Whether to print a full trajectory table, a simple pass/fail summary, or just "Experiment complete — see results/run_001.json".
- **Ollama version fetch implementation.** D-08 says HTTP GET to `/api/version`; whether to use `urllib` (stdlib) or the existing `openai` client's underlying httpx is planner's call. Recommend `urllib.request` to avoid coupling to the SDK's internals.
- **`run_experiment()` return type.** Whether it returns `ExperimentRun | None` (None on no-go) or always returns `ExperimentRun` (with empty iterations on no-go). Given D-02 says no file on no-go, returning `None` is cleaner.
- **`ExperimentRun` model changes.** Whether to add a `deltas` field to the Pydantic model or compute and inject deltas into the JSON dict at serialisation time. The latter avoids model changes but loses type safety.
- **Unit test structure.** FakeClient-backed tests for the loop logic (happy path, judge sentinel mid-loop, optimiser failure mid-loop, no-go gate). Planner decides scope and coverage depth.
- **Live integration smoke test.** Optional `@pytest.mark.integration` test that runs 1-2 iterations against Ollama. Planner's call on whether to add this or rely on the actual experiment run.
- **Logging namespace.** Recommend `jitc.loop` following `jitc.agent`, `jitc.judge`, `jitc.preloop`, `jitc.optimiser` convention.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 4 Artifacts (directly consumed)
- `src/optimiser.py` — `run_optimiser(system_prompt, judge_result) -> OptimiserResult`. Called once per iteration except the last. NDA is NOT a parameter (OPTM-01).
- `src/models.py` — `OptimiserResult`, `IterationResult`, `ExperimentRun`, `JudgeResult`, `RubricScore`, `PreLoopTestResult`, `compute_category_scores()`, `BANNED_RUBRIC_VOCAB_TOKENS`. Phase 5 consumes all of these.
- `.planning/phases/04-optimiser/04-CONTEXT.md` — D-01..D-15 decisions, especially D-02 (OptimiserResult fields), D-11 (retry/sentinel contract), D-15 (vocab_warning semantics).

### Phase 3 Artifacts (directly consumed)
- `src/pre_loop_test.py` — `run_pre_loop_test() -> PreLoopTestResult`, `_print_banner(result)`. Phase 5 calls both at startup.
- `.planning/phases/03-pre-loop-validation-gate/03-CONTEXT.md` — D-05 (verdict representation), D-06 (sentinel hard-fail), D-09 (library function contract).

### Phase 2 Artifacts (directly consumed)
- `src/agent.py` — `run_agent(system_prompt, nda_text) -> str`, `ITERATION_ZERO_SYSTEM_PROMPT`. Phase 5 calls `run_agent` each iteration and seeds with the constant.
- `src/judge.py` — `run_judge(nda_text, agent_output, rubric, playbook) -> JudgeResult`. Phase 5 calls this each iteration. Sentinel: `JudgeResult(scores=[])`.
- `src/llm.py` — `get_client()` factory. Phase 5 does NOT create its own client — all LLM calls go through the component functions.
- `src/config.py` — `config.model`, `config.temperature`, `config.num_ctx`, `config.num_iterations`. Phase 5 reads all.

### Phase 1 Artifacts (static data consumed at runtime)
- `data/nda.md` — the NDA text passed to `run_agent` and `run_judge` each iteration
- `data/rubric.json` — passed as raw text to `run_judge`
- `data/playbook.md` — passed as raw text to `run_judge`

### Research
- `.planning/research/PITFALLS.md`:
  - **P5** (Goodhart's Law) — vocab_warning on OptimiserResult is the detection signal. Phase 5 should log it per iteration.
  - **P11** (prompt grows every iteration) — word count trend across iterations. Phase 5 should log prompt_word_count per iteration for post-hoc analysis.
  - **P8** (rubric vocab contamination) — Phase 4 handles detection; Phase 5 logs the result.

### Project-Level
- `.planning/PROJECT.md` — "Optimiser doesn't see NDA" key decision, "Same model for agent/judge/optimiser"
- `.planning/REQUIREMENTS.md` §Loop — LOOP-01, LOOP-02, LOOP-03, LOOP-04 acceptance text
- `.planning/ROADMAP.md` Phase 5 — the 5 success criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`src/agent.py::run_agent`** — thin wrapper, returns string. No error handling needed — always returns a string (empty on None content).
- **`src/judge.py::run_judge`** — retry loop with graceful failure. Returns `JudgeResult(scores=[])` on exhaustion. Phase 5 detects with `if not result.scores:`.
- **`src/optimiser.py::run_optimiser`** — retry loop with graceful failure. Returns `OptimiserResult(failed=True)` on exhaustion. `new_system_prompt` is safely the old prompt on failure.
- **`src/pre_loop_test.py::run_pre_loop_test`** — returns `PreLoopTestResult`. `_print_banner` prints the console banner.
- **`src/agent.py::ITERATION_ZERO_SYSTEM_PROMPT`** — the seed prompt for iteration 0.
- **`src/config.py::config`** — all configuration values. `config.num_iterations` defaults to 5.
- **`src/models.py::ExperimentRun`** — already has `iterations: list[IterationResult]`, `pre_loop_test: PreLoopTestResult | None`, `config: dict`.
- **`src/models.py::IterationResult`** — already has `optimiser_feedback_seen`, `prompt_diff`, `prompt_word_count` fields with defaults (Phase 4 additions).

### Established Patterns
- **`__main__` script + library function** — `src/pre_loop_test.py` does this. Phase 5 mirrors: `run_experiment()` + `if __name__ == "__main__":` block.
- **`sys.path` shim** — `src/pre_loop_test.py` uses `if __package__ in (None, ""):` guard. Phase 5 needs the same for `uv run python src/loop.py`.
- **stdlib `logging.getLogger("jitc.<component>")`** — extend with `jitc.loop`.
- **`Path("results").mkdir(exist_ok=True)`** — ensure results directory exists at runtime.
- **`model_dump_json(indent=2)`** — for human-readable results files.

### Integration Points
- **New file:** `src/loop.py` with `run_experiment()`, delta computation helper, progress printing, `__main__` block.
- **Possible edit:** `src/models.py` — may need to add a `deltas` field to `ExperimentRun` or leave it as a dict-level injection at serialisation time.
- **New file:** `tests/test_loop.py` with FakeClient-backed unit tests.
- **Does NOT touch:** `src/agent.py`, `src/judge.py`, `src/optimiser.py`, `src/pre_loop_test.py`, `src/llm.py`, `src/config.py`, `data/*`.

</code_context>

<specifics>
## Specific Ideas

- **Delta computation helper.** A function like `_compute_deltas(iterations: list[IterationResult]) -> list[dict[str, int] | None]` that walks the iteration list and produces the parallel deltas list. Handles sentinel failures (scores==[]) by returning `null` for that position and tracking the last valid scores for the next delta.

- **Per-iteration progress line example:**
  ```
  [iter 1/5] total=12 ext=7 jud=5 delta=+2 words=98
  [iter 2/5] total=14 ext=8 jud=6 delta=+2 words=112
  [iter 3/5] total=14 ext=8 jud=6 delta=0  words=115
  ```

- **Optimiser skip on last iteration.** D-12 saves one LLM call (~60s against gemma4:26b). The last iteration's `IterationResult` will have default values for the optimiser fields (`optimiser_feedback_seen=[]`, `prompt_diff=""`, `prompt_word_count=0`). This is unambiguous — iteration 0 also has these defaults because no optimiser ran before iteration 0.

- **ExperimentRun.experiment_id.** Use a simple format like `"run_001"` matching the filename. Or a UUID. Planner's call.

- **Ollama version fetch.** `urllib.request.urlopen("http://localhost:11434/api/version")` returns JSON like `{"version": "0.5.13"}`. Parse and store as string. Wrap in try/except to handle Ollama not running (store `"unknown"`).

- **Phase 4 deferred item: word-count trend.** The per-iteration progress line (D-07) already includes word count. Post-hoc analysis can detect monotonic growth from the stored `prompt_word_count` values. No additional code needed beyond what D-07 already provides.

</specifics>

<deferred>
## Deferred Ideas

- **Feedback deduplication across iterations.** Phase 4 deferred this. If iterations 2, 3, 4 all get similar feedback, the optimiser might keep adding the same instruction. Detection could be added as a post-hoc analysis step in v2 (ANAL requirements). Not in Phase 5 loop scope.

- **Auto-incrementing run numbers.** D-09 uses fixed `run_001.json`. If multiple runs become needed, auto-incrementing (`run_002.json`, etc.) can be added. Not needed for a single experiment.

- **Score trajectory analysis / plateau detection.** v2 requirements (ANAL-01, ANAL-02). The raw data for this is in `results/run_001.json`; analysis belongs in the Streamlit app or a separate script.

- **Prompt rollback on regression.** If total_score drops, revert to the previous prompt. Explicitly out of scope per REQUIREMENTS.md ("Changes experiment semantics from linear loop to search algorithm").

- **Token usage tracking.** Out of scope per REQUIREMENTS.md ("Irrelevant for local Ollama (free inference)").

- **Word-count trend warning.** Phase 4 deferred: detect monotonic word-count growth as P11 signal. The data is captured (D-07 progress line + stored `prompt_word_count`). Active detection/alerting is a v2 analysis concern.

</deferred>

---

*Phase: 05-main-loop*
*Context gathered: 2026-04-12*
