# Phase 5: Main Loop - Research

**Researched:** 2026-04-12
**Domain:** Python orchestration loop — sequential LLM pipeline, incremental JSON writes, resilient iteration failure handling
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `loop.py` calls `run_pre_loop_test()` at the start of `run_experiment()`. If `result.decision == "no-go"`, log the result, print the pre-loop banner via `_print_banner()`, and exit cleanly (return `None` or raise `SystemExit`).
- **D-02:** On no-go, **no results file is created**. Only the banner is printed and the process exits.
- **D-03:** Per-item deltas — 8 delta values per iteration, keyed by `item_id`. `delta = current_score - previous_score`. Iteration 0 has no deltas (no previous).
- **D-04:** Deltas are computed at write time, NOT stored on `IterationResult`. Stored as a top-level `"deltas"` key in the JSON output alongside `"iterations"`. First entry is `null`; subsequent entries are `dict[str, int]`.
- **D-05:** Delta computation must handle judge sentinel failure gracefully. If iteration N has `scores == []`, that iteration's delta entry is `null`; iteration N+1's delta is computed against the last iteration that had valid scores.
- **D-06:** Write `results/run_001.json` after every completed iteration. Overwrite the file each time with the full `ExperimentRun` (+ deltas). At most 1 iteration of work lost on crash.
- **D-07:** Per-iteration progress summary printed to stdout after each iteration completes: iteration number, total/extraction/judgment scores, delta from previous iteration's total, word count of new system prompt.
- **D-08:** `ExperimentRun.config` dict populated with: `model`, `temperature`, `num_ctx`, `num_iterations`, `ollama_version` (fetched via HTTP GET to `http://localhost:11434/api/version`; store `"unknown"` on failure).
- **D-09:** Run file naming: `results/run_001.json` (fixed). No auto-incrementing.
- **D-10:** Loop structure: (1) pre-loop gate → exit on no-go, (2) build metadata, (3) seed `ITERATION_ZERO_SYSTEM_PROMPT`, (4) iterate agent → judge → build IterationResult → [optimiser if not last] → append → compute deltas → write file → print progress line, (5) print final summary banner.
- **D-11:** LOOP-04 resilience: sentinel `JudgeResult(scores=[])` → log, append IterationResult anyway, continue. Sentinel `OptimiserResult(failed=True)` → `current_system_prompt` unchanged (sentinel contract handles this). Loop never crashes on single iteration failure.
- **D-12:** Optimiser is NOT called after the last iteration — the rewritten prompt would never be used.

### Claude's Discretion

- Exact progress line format (content requirements given by D-07; exact formatting is planner's call)
- Final summary banner design (table, summary, or simple "Experiment complete — see results/run_001.json")
- Ollama version fetch implementation (recommend `urllib.request` to avoid coupling to SDK internals)
- `run_experiment()` return type: `ExperimentRun | None` (None on no-go) — returning None is cleaner given D-02
- `ExperimentRun` model changes: whether to add a `deltas` field to the Pydantic model or inject into the JSON dict at serialisation time (latter avoids model changes but loses type safety)
- Unit test structure: FakeClient-backed tests for happy path, judge sentinel mid-loop, optimiser failure mid-loop, no-go gate
- Live integration smoke test: optional `@pytest.mark.integration` test for 1-2 iterations against Ollama
- Logging namespace: `jitc.loop` following `jitc.agent`, `jitc.judge`, `jitc.preloop`, `jitc.optimiser` convention

### Deferred Ideas (OUT OF SCOPE)

- Feedback deduplication across iterations (Phase 4 deferred; v2 ANAL requirement)
- Auto-incrementing run numbers
- Score trajectory analysis / plateau detection (v2 VIZ/ANAL requirements)
- Prompt rollback on regression (changes experiment semantics from linear loop to search algorithm)
- Token usage tracking (irrelevant for local Ollama)
- Word-count trend warning / active detection (data is captured; alerting is v2)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LOOP-01 | Main loop ties agent -> judge -> log -> optimiser for N iterations (default 5) | D-10 loop structure; `run_agent`, `run_judge`, `run_optimiser` all implemented and ready to import |
| LOOP-02 | Per-iteration results written to structured JSON with iteration counter | D-06 incremental write strategy; `ExperimentRun.model_dump_json(indent=2)` pattern already established |
| LOOP-03 | Run metadata envelope (model, temperature, timestamp, iteration count, Ollama version) | D-08 config dict; Ollama `/api/version` fetch via `urllib.request` |
| LOOP-04 | Resilient to individual iteration failures — log error and continue | D-11; sentinel contracts on `JudgeResult` and `OptimiserResult` already implemented upstream |
</phase_requirements>

---

## Summary

Phase 5 is the final integration layer. All the component functions (`run_agent`, `run_judge`, `run_optimiser`, `run_pre_loop_test`) exist, are tested, and expose clean sentinel-based failure contracts. Phase 5's job is to wire them together in `src/loop.py` with the correct orchestration logic, resilient write strategy, and diagnostic output.

The phase introduces no new LLM patterns, no new Pydantic models beyond a potential `deltas` serialisation choice, and no new dependencies. The only external call that is new to this phase is the Ollama version fetch via `urllib.request` (stdlib) — all other patterns are inherited from Phase 2-4.

The primary implementation complexity is in delta computation logic (tracking last valid scores across sentinel failures), the incremental JSON write strategy (computing and re-serialising deltas at each write), and the test harness (sequencing FakeClient responses across a multi-iteration loop). The tests for Phase 4 (`tests/test_optimiser.py`) demonstrate the exact fake-client multi-call pattern the loop tests should follow.

**Primary recommendation:** Build `src/loop.py` as a library function `run_experiment() -> ExperimentRun | None` with a `_compute_deltas()` helper and a `__main__` block, mirroring `src/pre_loop_test.py` exactly. Inject deltas into the JSON dict at serialisation time (not into the Pydantic model) to avoid backward-compatibility concerns.

---

## Standard Stack

### Core (all already installed)
[VERIFIED: pyproject.toml in codebase]

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `openai` | >=2.0 (2.31.0 installed) | LLM client — NOT used directly in loop.py | All LLM calls go through component functions; loop.py never calls get_client() |
| `pydantic` | >=2.0 (2.12.5 installed) | Structured output validation | `ExperimentRun.model_dump_json(indent=2)` for results file |
| `urllib.request` | stdlib | Ollama version fetch | No additional dependency; decoupled from openai SDK internals |
| `difflib` | stdlib | Already used in optimiser.py | No new usage in loop.py |
| `pathlib.Path` | stdlib | File I/O patterns | `Path("results").mkdir(exist_ok=True)` established in pre_loop_test.py |
| `datetime` | stdlib | UTC timestamps | `datetime.now(timezone.utc).isoformat()` — same as pre_loop_test.py |
| `logging` | stdlib | `jitc.loop` namespace | Follows `jitc.agent`, `jitc.judge`, `jitc.preloop`, `jitc.optimiser` convention |

### No New Dependencies
Phase 5 requires zero new packages. [VERIFIED: all capabilities available via established imports in Phase 2-4 code]

---

## Architecture Patterns

### Recommended Project Structure (additions only)
```
src/
└── loop.py              # run_experiment() + _compute_deltas() + __main__

tests/
└── test_loop.py         # FakeClient-backed unit tests for loop logic
```

### Pattern 1: Library Function + `__main__` Block
**What:** `run_experiment()` is a pure library function returning `ExperimentRun | None`. The `__main__` block handles logging setup and invocation.
**When to use:** Required — mirrors pre_loop_test.py exactly so `uv run python src/loop.py` works without module import issues.
**Example:**
```python
# Source: src/pre_loop_test.py (VERIFIED in codebase)
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config
from src.agent import run_agent, ITERATION_ZERO_SYSTEM_PROMPT
from src.judge import run_judge
from src.optimiser import run_optimiser
from src.pre_loop_test import run_pre_loop_test, _print_banner
from src.models import ExperimentRun, IterationResult

logger = logging.getLogger("jitc.loop")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    result = run_experiment()
    if result is not None:
        print("Experiment complete — see results/run_001.json")
```

### Pattern 2: Incremental Write with Delta Injection
**What:** After each iteration, compute deltas from the full iterations list, serialise ExperimentRun to dict, inject `"deltas"` key, then write JSON.
**When to use:** Required by D-04 and D-06.
**Example:**
```python
# Source: design decisions D-04, D-06 (VERIFIED in CONTEXT.md)
def _write_results(
    run: ExperimentRun,
    deltas: list[dict[str, int] | None],
    path: Path,
) -> None:
    data = run.model_dump()
    data["deltas"] = deltas
    path.write_text(json.dumps(data, indent=2))
```

### Pattern 3: Delta Computation with Sentinel Awareness
**What:** Walk the iterations list, tracking the last iteration with valid scores. Produce a parallel list: `None` for iteration 0, `None` for iterations with `scores == []`, `dict[str, int]` otherwise.
**When to use:** Required by D-03, D-04, D-05.
**Example:**
```python
# Source: design decisions D-03..D-05 (VERIFIED in CONTEXT.md)
def _compute_deltas(
    iterations: list[IterationResult],
) -> list[dict[str, int] | None]:
    result: list[dict[str, int] | None] = []
    last_valid_scores: dict[str, int] | None = None
    for i, it in enumerate(iterations):
        if i == 0 or last_valid_scores is None or not it.scores:
            result.append(None)
        else:
            current = {s.item_id: s.score for s in it.scores}
            result.append({k: current.get(k, 0) - last_valid_scores.get(k, 0)
                           for k in current})
        if it.scores:
            last_valid_scores = {s.item_id: s.score for s in it.scores}
    return result
```

### Pattern 4: Ollama Version Fetch
**What:** HTTP GET to `http://localhost:11434/api/version` via `urllib.request`. Returns `{"version": "0.5.13"}`. Wrap in try/except for cases where Ollama is not running.
**When to use:** Required by D-08 for run metadata envelope.
**Example:**
```python
# Source: design decision D-08, specific ideas section (VERIFIED in CONTEXT.md)
import json
import urllib.request

def _get_ollama_version() -> str:
    try:
        with urllib.request.urlopen(
            "http://localhost:11434/api/version", timeout=5
        ) as resp:
            data = json.loads(resp.read())
            return data.get("version", "unknown")
    except Exception:
        return "unknown"
```

### Pattern 5: IterationResult Population from OptimiserResult
**What:** After a successful optimiser call, populate the `IterationResult`'s optimiser fields from the `OptimiserResult`. Fields have defaults on `IterationResult` (Phase 4 D-04).
**When to use:** Required by D-10 step 4d.
**Example:**
```python
# Source: src/models.py IterationResult (VERIFIED in codebase)
# IterationResult already has these fields with defaults:
#   optimiser_feedback_seen: list[str] = []
#   prompt_diff: str = ""
#   prompt_word_count: int = 0
iter_result = IterationResult(
    iteration=i,
    system_prompt=current_system_prompt,
    agent_output=agent_output,
    scores=judge_result.scores,
    # scores=[] if sentinel; model_validator computes totals as 0
    optimiser_feedback_seen=opt_result.feedback_seen,
    prompt_diff=opt_result.prompt_diff,
    prompt_word_count=opt_result.prompt_word_count,
)
```

### Anti-Patterns to Avoid

- **Writing the file once at the end only:** Violates D-06; a crash in iteration 3 of 5 loses everything. Write after every iteration.
- **Calling `run_optimiser` after the last iteration:** Violates D-12; wastes one ~60s LLM call.
- **Crashing on judge sentinel:** Violates D-11 and LOOP-04. Detect with `if not judge_result.scores:`, log ERROR, build `IterationResult` with `scores=[]`, continue.
- **Raising `SystemExit` without printing the banner:** D-01 requires calling `_print_banner()` before exiting on no-go.
- **Using `model_dump_json()` for the results file:** This would lose the `deltas` key. Use `model_dump()` then inject `"deltas"` then `json.dumps(..., indent=2)` instead.
- **Creating a new LLM client in loop.py:** All LLM calls go through component functions (`run_agent`, `run_judge`, `run_optimiser`). `loop.py` does NOT call `get_client()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Word count tracking | Custom tokeniser | `len(text.split())` | Already used in `optimiser.py`; consistent |
| Unified diff | Custom diff | `difflib.unified_diff` (stdlib) | Already in `_compute_prompt_diff` in optimiser.py |
| JSON serialisation | Custom encoder | `model_dump()` + `json.dumps()` | Pydantic handles nested model serialisation; handles datetime, etc. |
| Retry logic | Another retry loop | Already in `run_judge` and `run_optimiser` | Loop.py just checks sentinels; does NOT add a second retry layer |
| HTTP fetch | requests/httpx | `urllib.request` (stdlib) | No new dependency needed for a single GET |

**Key insight:** Phase 5 is an orchestration layer. Every complex sub-problem (retries, parsing, diffs, validation) is already solved in the component modules. Loop.py's job is sequencing, accumulation, and file I/O only.

---

## Common Pitfalls

### Pitfall 1: Delta Keys Missing for Sentinel Iterations (P9 variant)
**What goes wrong:** If `_compute_deltas` doesn't track the last valid scores across a sentinel failure, iteration N+1's delta is computed against iteration N's empty scores instead of iteration N-1's valid scores — producing nonsense deltas.
**Why it happens:** Naively iterating pairs `(iter[i-1], iter[i])` without checking for sentinels.
**How to avoid:** Track `last_valid_scores` as a running variable; only update it when `it.scores` is non-empty.
**Warning signs:** All delta values = 0 for iterations after a sentinel failure.

### Pitfall 2: Optimiser Fields Not Populated on Iteration 0
**What goes wrong:** Iteration 0 has no predecessor optimiser call. `IterationResult` fields `optimiser_feedback_seen`, `prompt_diff`, `prompt_word_count` are `[]`, `""`, `0` — which is correct and intended, but must not be confused with a sentinel failure.
**Why it happens:** Treating default values as error indicators.
**How to avoid:** Document: defaults on iteration 0 are correct, not a failure. The last iteration also has these defaults (D-12). This is by design.
**Warning signs:** Test assertions that `prompt_word_count > 0` for all iterations would incorrectly fail on iterations 0 and N-1.

### Pitfall 3: JSON File Written with Wrong Keys After Delta Injection
**What goes wrong:** `model_dump_json()` does not accept extra keys at call time. If you try to call `run.model_dump_json(extra={"deltas": ...})`, it silently ignores the extra.
**Why it happens:** Pydantic's `model_dump_json()` only serialises defined model fields.
**How to avoid:** Use `model_dump()` → `data["deltas"] = deltas` → `json.dumps(data, indent=2)`. See Pattern 2.
**Warning signs:** The output JSON file has no `"deltas"` key.

### Pitfall 4: Pre-Loop Gate Called But Banner Not Printed on No-Go
**What goes wrong:** `run_pre_loop_test()` does NOT print the banner (D-10 from Phase 3). `_print_banner()` must be called explicitly in `loop.py` on no-go exit.
**Why it happens:** Assuming `run_pre_loop_test()` handles its own console output.
**How to avoid:** Check Phase 3's `pre_loop_test.py` docstring: "Does NOT print to stdout (D-10)." Call `_print_banner(result)` explicitly before exit.
**Warning signs:** No-go run produces no human-readable output to stdout.

### Pitfall 5: P5/P8 Signals Not Logged Per Iteration
**What goes wrong:** `OptimiserResult.vocab_warning` is computed by the optimiser but never surfaced in the loop's per-iteration progress line or logs.
**Why it happens:** Only logging scores, not the optimiser audit fields.
**How to avoid:** After each `run_optimiser` call, log `opt_result.vocab_warning` at WARNING level if True (mirrors PITFALLS.md P5 detection guidance). Include it in the iteration progress line or at least the logger output.
**Warning signs:** A vocab_warning=True iteration is invisible in the experiment output.

### Pitfall 6: Results Directory Not Created Before Write (P9)
**What goes wrong:** First write to `results/run_001.json` fails with `FileNotFoundError` if `results/` doesn't exist.
**Why it happens:** Directory existence not checked.
**How to avoid:** Call `Path("results").mkdir(exist_ok=True)` at the start of `run_experiment()`, before the first write attempt. Same pattern as `pre_loop_test.py`.

---

## Code Examples

Verified patterns from the existing codebase:

### ExperimentRun Construction
```python
# Source: src/models.py (VERIFIED in codebase)
# ExperimentRun already has these fields:
#   experiment_id: str
#   timestamp: str
#   config: dict
#   nda_file: str
#   rubric_file: str
#   playbook_file: str
#   pre_loop_test: PreLoopTestResult | None = None
#   iterations: list[IterationResult] = []

run = ExperimentRun(
    experiment_id="run_001",
    timestamp=datetime.now(timezone.utc).isoformat(),
    config={
        "model": config.model,
        "temperature": config.temperature,
        "num_ctx": config.num_ctx,
        "num_iterations": config.num_iterations,
        "ollama_version": _get_ollama_version(),
    },
    nda_file="data/nda.md",
    rubric_file="data/rubric.json",
    playbook_file="data/playbook.md",
    pre_loop_test=pre_loop_result,
)
```

### Sentinel Detection Patterns
```python
# Source: src/pre_loop_test.py (VERIFIED in codebase) — same pattern for loop.py
if not judge_result.scores:
    logger.error("judge sentinel at iteration %d — continuing", i)
    # still build IterationResult; model_validator computes total_score=0 correctly

# Source: src/models.py OptimiserResult docstring (VERIFIED)
# OptimiserResult.failed=True means new_system_prompt == old system_prompt
# So: current_system_prompt = opt_result.new_system_prompt
# works correctly for both success and failure — no special-case needed
```

### FakeClient Test Pattern (for test_loop.py)
```python
# Source: tests/conftest.py + tests/test_optimiser.py (VERIFIED in codebase)
def test_happy_path_five_iterations(fake_client, valid_judge_json):
    # agent: 5 responses; judge: 5 responses; optimiser: 4 responses (not last iter)
    responses = []
    for i in range(5):
        responses.append("Agent review text")        # run_agent
        responses.append(valid_judge_json)           # run_judge
        if i < 4:
            responses.append("New rewritten prompt " + "word " * 60)  # run_optimiser
    client = fake_client(responses)
    result = run_experiment()
    assert result is not None
    assert len(result.iterations) == 5
```

### Logging Convention
```python
# Source: src/optimiser.py (VERIFIED in codebase)
logger = logging.getLogger("jitc.loop")  # extend established namespace

logger.info("loop start: model=%s iterations=%d", config.model, config.num_iterations)
logger.info("[iter %d/%d] agent call", i + 1, config.num_iterations)
logger.error("judge sentinel at iter %d — continuing", i + 1)
logger.warning("vocab_warning at iter %d — P5 signal", i + 1)
```

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_loop.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOOP-01 | Agent -> judge -> log -> optimiser runs N=5 times | unit (FakeClient) | `uv run pytest tests/test_loop.py::test_happy_path_five_iterations -x` | ❌ Wave 0 |
| LOOP-01 | Optimiser NOT called after last iteration | unit (FakeClient) | `uv run pytest tests/test_loop.py::test_optimiser_skipped_on_last_iteration -x` | ❌ Wave 0 |
| LOOP-02 | results/run_001.json written with all IterationResults | unit (FakeClient + tmp_path) | `uv run pytest tests/test_loop.py::test_results_file_written_with_all_iterations -x` | ❌ Wave 0 |
| LOOP-02 | Deltas key present in output JSON | unit (FakeClient + tmp_path) | `uv run pytest tests/test_loop.py::test_deltas_key_in_output_json -x` | ❌ Wave 0 |
| LOOP-03 | config dict includes model, temperature, num_ctx, num_iterations, ollama_version | unit (mock urllib) | `uv run pytest tests/test_loop.py::test_run_metadata_envelope -x` | ❌ Wave 0 |
| LOOP-04 | Judge sentinel mid-loop: loop continues, IterationResult appended | unit (FakeClient) | `uv run pytest tests/test_loop.py::test_judge_sentinel_continues_loop -x` | ❌ Wave 0 |
| LOOP-04 | Optimiser sentinel mid-loop: old prompt preserved, loop continues | unit (FakeClient) | `uv run pytest tests/test_loop.py::test_optimiser_sentinel_continues_loop -x` | ❌ Wave 0 |
| LOOP-01 | No-go gate: returns None, no file written | unit (FakeClient) | `uv run pytest tests/test_loop.py::test_nogo_returns_none_no_file_written -x` | ❌ Wave 0 |
| LOOP-01 | Integration: 1 iteration against live Ollama | integration | `uv run pytest tests/test_loop.py -m integration -x` | ❌ optional Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_loop.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_loop.py` — covers LOOP-01, LOOP-02, LOOP-03, LOOP-04
- [ ] `src/loop.py` — the implementation itself (no infrastructure gaps; conftest.py already has FakeClient)

*(Existing conftest.py with `FakeClient`, `fake_client` fixture, and `valid_judge_json` fixture covers all test infrastructure needs — no new fixtures required.)*

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | ✓ | 3.11+ (uv managed) | — |
| uv | All | ✓ | 0.7.x | — |
| Ollama | Live experiment run | ✓ (verified Phase 3/4) | gemma4:26b confirmed | — |
| `urllib.request` | Ollama version fetch | ✓ | stdlib | Store `"unknown"` on exception |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:**
- Ollama `/api/version` endpoint — if the call fails (network error, Ollama not running), store `"unknown"` in config dict. Does not block experiment.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ExperimentRun.model_dump()` correctly serialises nested `IterationResult` and `PreLoopTestResult` objects | Code Examples | JSON output would be malformed; use `model_dump(mode='json')` if datetime/enum values don't serialise correctly |
| A2 | `_print_banner` from `src/pre_loop_test.py` is importable as a module-private function (leading underscore) | Architecture Patterns | If import fails, banner must be reimplemented in loop.py; low risk — Python allows importing `_` names |

**All other claims in this document are VERIFIED against the codebase or CONTEXT.md.**

---

## Open Questions

1. **Delta injection: `model_dump()` vs `model_dump_json()` serialisation of datetime/enum fields**
   - What we know: `model_dump()` returns Python objects (datetime stays as datetime); `json.dumps()` would fail on datetime unless `default=str` is added.
   - What's unclear: Whether `ExperimentRun` actually contains datetime fields (it uses `timestamp: str`, so it's already a string — no issue).
   - Recommendation: Use `model_dump()` + `json.dumps(data, indent=2)`. The timestamp field is `str`, not `datetime`, so no custom serialiser needed. Confirm by checking actual `ExperimentRun` fields (all primitive types in the model).

2. **`ExperimentRun` model: add `deltas` field or inject at serialisation time?**
   - What we know: D-04 says "stored as a top-level key in the JSON output." The Pydantic model does NOT currently have a `deltas` field (verified in models.py).
   - Recommendation: Inject at serialisation time (dict injection pattern). Avoids a model change, avoids backward-compat concerns. The planner should document this choice explicitly — if the model gets a `deltas` field later, the injection approach becomes dead code.

---

## Sources

### Primary (HIGH confidence)
- `src/models.py` — ExperimentRun, IterationResult, OptimiserResult, PreLoopTestResult schemas. All fields verified.
- `src/pre_loop_test.py` — Library function + `__main__` pattern, sys.path shim, `_print_banner` contract, `_RESULTS_DIR.mkdir(exist_ok=True)` pattern.
- `src/optimiser.py` — Sentinel contract, retry pattern, `difflib.unified_diff` usage, `jitc.*` logger convention.
- `src/config.py` — All config fields: model, base_url, api_key, temperature, num_iterations, num_ctx.
- `src/agent.py` — `ITERATION_ZERO_SYSTEM_PROMPT` constant, `run_agent` signature.
- `tests/conftest.py` — FakeClient, `fake_client` fixture, `valid_judge_json` fixture, `_reset_llm_singleton` autouse.
- `tests/test_optimiser.py` — Multi-call FakeClient test patterns, retry sequence construction.
- `.planning/phases/05-main-loop/05-CONTEXT.md` — All locked decisions D-01..D-12, specific ideas, delta format.
- `.planning/research/PITFALLS.md` — P5, P8, P9, P11 phase-specific warnings for main loop.

### Secondary (MEDIUM confidence)
- `pyproject.toml` — Confirmed dependency versions (openai>=2.0, pydantic>=2.0, pytest>=8.0, black>=26.0).

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies already installed and in use; no new libraries
- Architecture patterns: HIGH — verified against existing Phase 2-4 source code; patterns are direct extensions of established code
- Pitfalls: HIGH — verified against PITFALLS.md and existing test patterns in the codebase
- Test map: HIGH — existing conftest.py provides all required fixtures

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable domain; only risk is Ollama version API changing, which is low)
