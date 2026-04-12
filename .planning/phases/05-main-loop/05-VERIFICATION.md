---
phase: 05-main-loop
verified: 2026-04-12T13:00:00Z
status: human_needed
score: 5/6 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run `NUM_ITERATIONS=2 uv run python src/loop.py` with Ollama running (gemma4:26b loaded)"
    expected: "Pre-loop gate banner prints, 2 per-iteration progress lines appear, experiment completes without crash, results/run_001.json is created containing 2 iterations, 2 deltas entries (first null, second an 8-key dict), config with model/temperature/num_ctx/num_iterations/ollama_version, and pre_loop_test not null"
    why_human: "Requires live Ollama instance. The SUMMARY documents Task 3 (live run gate) was auto-approved without actual execution. Automated tests use FakeClient — they do not exercise the real Ollama API path."
---

# Phase 5: Main Loop Verification Report

**Phase Goal:** A complete experiment run executes N iterations of agent -> judge -> log -> optimiser and writes a single structured JSON artifact
**Verified:** 2026-04-12T13:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running `uv run python src/loop.py` executes the pre-loop gate then N iterations of agent->judge->optimiser and writes results/run_001.json | VERIFIED (unit) | `run_experiment()` calls `run_pre_loop_test()`, iterates N times, writes via `_write_results()`. 11/11 unit tests pass. Live run not yet executed. |
| 2 | Each iteration's scores, system prompt, agent output, and optimiser audit fields are captured in the JSON output | VERIFIED | `IterationResult` contains `system_prompt`, `agent_output`, `scores`, `extraction_score`, `judgment_score`, `optimiser_feedback_seen`, `prompt_diff`, `prompt_word_count`. `test_results_file_written_with_all_iterations` confirms JSON output structure. |
| 3 | Per-item deltas are present in the JSON output as a top-level 'deltas' key | VERIFIED | `_compute_deltas()` + `data["deltas"] = deltas` in `_write_results()`. `test_deltas_key_in_output_json` confirms deltas[0]=None, deltas[1..N] are 8-key dicts. |
| 4 | A judge sentinel failure mid-loop does not crash the process; the loop continues to the next iteration | VERIFIED | `if not judge_result.scores: logger.error(...)` then continues. `test_judge_sentinel_continues_loop` passes: 3 iterations produced with sentinel at iteration 1. |
| 5 | The results file is written after every iteration so a crash loses at most 1 iteration of work | VERIFIED | `_write_results(run, deltas, _RESULTS_FILE)` called inside loop body after each iteration (line 183). `test_results_file_written_with_all_iterations` confirms file exists and is valid after run. |
| 6 | The optimiser is NOT called after the last iteration | VERIFIED | `if i < config.num_iterations - 1:` guard at line 164. `test_optimiser_skipped_on_last_iteration` confirms 8 total LLM calls (3+3+2) for 3-iteration run. |

**Score:** 6/6 truths verified (automated)

### Note on ROADMAP Success Criteria Wording Deviations

Two ROADMAP SCs use wording that differs from the implementation — both are deliberate design decisions documented in the PLAN:

**ROADMAP SC #2** says "delta_from_prev values" inside each IterationResult. The implementation stores deltas as a top-level `data["deltas"]` array (parallel to `data["iterations"]`), not inside `IterationResult`. Design decision D-04 explicitly documents this: "Deltas are computed at write time, NOT stored on IterationResult. This avoids Pydantic model changes." The consumer intent (per-item deltas accessible in JSON) is satisfied.

**ROADMAP SC #5** says "written via try/finally so a partial run is preserved". The implementation achieves crash resilience through D-06 (per-iteration file overwrite inside the loop body), not a try/finally wrapper. The PLAN's must_have reframes this as "written after every iteration so a crash loses at most 1 iteration of work" — which is satisfied. The only scenario try/finally would catch (mid-write crash) leaves a partially-written file, which both approaches handle identically.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/loop.py` | run_experiment() + _compute_deltas() + _get_ollama_version() + _write_results() + __main__, min 100 lines | VERIFIED | 216 lines. All 4 functions + __main__ present. Black-clean. |
| `tests/test_loop.py` | FakeClient-backed unit tests for happy path, sentinel resilience, no-go gate, metadata; min 80 lines | VERIFIED | 491 lines. 11 tests (plan called for 10; one split for clarity per SUMMARY). All 11 pass. |
| `results/run_001.json` | Complete experiment run artifact (created at runtime) | MISSING — runtime only | Not present. Requires live Ollama. SUMMARY acknowledges Task 3 (live run) was auto-approved without execution. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| src/loop.py | src/agent.py::run_agent | direct import call per iteration | VERIFIED | Line 20: `from src.agent import ... run_agent`. Line 150: `agent_output = run_agent(current_system_prompt, nda)` |
| src/loop.py | src/judge.py::run_judge | direct import call per iteration | VERIFIED | Line 22: `from src.judge import run_judge`. Line 152: `judge_result = run_judge(nda, agent_output, rubric, playbook)` |
| src/loop.py | src/optimiser.py::run_optimiser | direct import call per iteration (except last) | VERIFIED | Line 24: `from src.optimiser import run_optimiser`. Line 165: `opt_result = run_optimiser(current_system_prompt, judge_result)` inside `if i < config.num_iterations - 1:` |
| src/loop.py | src/pre_loop_test.py::run_pre_loop_test | called once at start of run_experiment | VERIFIED | Line 25: `from src.pre_loop_test import _print_banner, run_pre_loop_test`. Line 113: `pre_loop_result = run_pre_loop_test()` |
| src/loop.py | results/run_001.json | _write_results after each iteration | VERIFIED | Line 183: `_write_results(run, deltas, _RESULTS_FILE)` inside loop body. `_RESULTS_FILE = _RESULTS_DIR / "run_001.json"` at module level. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| src/loop.py::run_experiment | agent_output | run_agent() -> OpenAI-compatible API | Yes (real API call, FakeClient in tests) | FLOWING |
| src/loop.py::run_experiment | judge_result.scores | run_judge() -> Pydantic-validated JSON | Yes (validated, retry on failure) | FLOWING |
| src/loop.py::run_experiment | opt_result.new_system_prompt | run_optimiser() -> Pydantic-validated text | Yes (validated, sentinel on exhaustion) | FLOWING |
| src/loop.py::_write_results | data (JSON) | run.model_dump() + deltas injection | Yes (ExperimentRun + computed deltas) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| src/loop.py importable | `.venv/bin/python -c "import src.loop"` | Import succeeds | PASS |
| All key functions defined | `grep -c "^def " src/loop.py` | 4 functions | PASS |
| 11 unit tests pass | `.venv/bin/python -m pytest tests/test_loop.py -q` | 11/11 passed (0.15s) | PASS |
| Full suite passes (no regression) | `uv run pytest tests/ --ignore=tests/test_smoke_ollama.py` | 45/45 passed | PASS |
| Black formatting clean | `uv run black --check src/loop.py tests/test_loop.py` | All files unchanged | PASS |
| Live experiment run | `NUM_ITERATIONS=2 uv run python src/loop.py` | Not executed (requires Ollama) | SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LOOP-01 | 05-01-PLAN.md | Main loop ties agent -> judge -> log -> optimiser for N iterations (default 5) | SATISFIED | `run_experiment()` iterates `range(config.num_iterations)`, calling agent, judge, then optimiser (except last). Default from `config.num_iterations = 5`. |
| LOOP-02 | 05-01-PLAN.md | Per-iteration results written to structured JSON with iteration counter | SATISFIED | `IterationResult(iteration=i, ...)` appended to `run.iterations`, serialized via `_write_results()` after each iteration. `iteration` field is the counter. |
| LOOP-03 | 05-01-PLAN.md | Run metadata envelope (model, temperature, timestamp, iteration count, Ollama version) | SATISFIED | `ExperimentRun.config` dict populated with `model`, `temperature`, `num_ctx`, `num_iterations`, `ollama_version`. `timestamp` set via `datetime.now(timezone.utc).isoformat()`. `test_run_metadata_envelope` confirms all 5 keys. |
| LOOP-04 | 05-01-PLAN.md | Resilient to individual iteration failures — log error and continue | SATISFIED | Judge sentinel: `if not judge_result.scores: logger.error(...)` then loop continues. Optimiser sentinel: `current_system_prompt = opt_result.new_system_prompt` works for both `failed=True` and success. `test_judge_sentinel_continues_loop` and `test_optimiser_sentinel_continues_loop` both pass. |

### Anti-Patterns Found

No anti-patterns detected in `src/loop.py` or `tests/test_loop.py`. No TODO/FIXME/placeholder comments. No stub implementations. No hardcoded empty returns in production code paths. No disconnected state.

One notable item in `tests/test_loop.py` (line 237-238): `test_optimiser_skipped_on_last_iteration` has a dead code line (`last_iter = loop.run_experiment.__module__`) that appears to be a leftover comment scaffold. It does not affect test correctness — the assertion on line 235 (`assert len(client.calls) == 8`) is valid and the test passes. Severity: Info (not a blocker).

### Human Verification Required

#### 1. Live Experiment Run

**Test:** With Ollama running and `gemma4:26b` loaded, execute:
```bash
NUM_ITERATIONS=2 uv run python src/loop.py
```
Then verify:
```bash
python -c "import json; d=json.load(open('results/run_001.json')); print('iterations:', len(d['iterations'])); print('deltas:', len(d['deltas'])); print('config keys:', list(d['config'].keys())); print('ollama_version:', d['config']['ollama_version']); print('pre_loop_test:', d['pre_loop_test'] is not None)"
```

**Expected:**
- Pre-loop gate banner prints showing GO decision
- 2 per-iteration progress lines in format: `[iter N/2] total=X ext=Y jud=Z delta=+W words=V`
- Process exits 0 (no crash)
- `results/run_001.json` exists and is valid JSON
- `iterations` count = 2
- `deltas` count = 2, first entry is `null`, second is an 8-key dict
- `config` contains all 5 keys: `model`, `temperature`, `num_ctx`, `num_iterations`, `ollama_version`
- `pre_loop_test` is not null

**Why human:** Requires live Ollama running locally. The SUMMARY documents that Task 3 (the live run gate in the plan) was auto-approved without actual execution. All automated verification uses FakeClient injection and cannot substitute for real end-to-end validation.

### Gaps Summary

No hard gaps blocking goal achievement at the unit test level. The single unverified item is the runtime artifact (`results/run_001.json`) which requires live Ollama execution. This is categorized as human_needed rather than gaps_found because the code is substantive, wired, and tested — the runtime artifact simply cannot exist until the experiment is run against a live model.

---

_Verified: 2026-04-12T13:00:00Z_
_Verifier: Claude (gsd-verifier)_
