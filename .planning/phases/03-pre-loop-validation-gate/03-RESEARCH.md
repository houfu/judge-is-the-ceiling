# Phase 3: Pre-Loop Validation Gate - Research

**Researched:** 2026-04-11
**Domain:** Test-harness plumbing — calling Phase 2's `run_judge` twice against two fixture reviews, aggregating scores into a structured go/no-go verdict
**Confidence:** HIGH

## Summary

Phase 3 is a thin orchestration layer over the Phase 2 judge. It loads two fixture reviews (`data/output_a.md` and `data/output_b.md`) plus the shared NDA / rubric / playbook, calls `run_judge(...)` four times (2 outputs × 2 runs), aggregates the returned `JudgeResult` objects into a single `PreLoopTestResult` Pydantic model, writes that model to `results/pre_loop_test.json`, and prints a console banner summarising the go/no-go decision. Its purpose is to prove that the judge built in Phase 2 can actually distinguish a careful review from a plausible-but-flawed one before we spend engineering effort on the optimiser (Phase 4) and main loop (Phase 5).

This phase is the mitigation site for pitfalls **P1** (judge self-reference collapse) and **P10** (pre-loop test not diagnostic if gap is small). The 2.0-point gap threshold and the `judgment_gap > 0` sub-criterion together convert a soft "we think the judge works" feeling into a hard, falsifiable precondition for advancing the project.

Every load-bearing decision is already pinned by CONTEXT.md D-01..D-11, and every reusable asset already exists in Phase 2: `run_judge` has a stable sentinel contract, `IterationResult` has an auto-validating totals computation, `FakeClient` and `VALID_JUDGE_JSON` are available in `tests/conftest.py`, and `@pytest.mark.integration` is registered in `pyproject.toml`. No new dependencies are required.

**Primary recommendation:** Implement `src/models.py` additions first (one new class + one field retype), then `src/pre_loop_test.py` (library function + `__main__` + banner), then `tests/test_pre_loop_gate.py` (integration wrapper). Skip fast unit tests — the aggregation math is small enough to eyeball during code review, and the integration test covers the same code path against real data.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Schema (`src/models.py` extension)**

- **D-01:** Add `PreLoopTestResult` as a Pydantic model in `src/models.py`. Fields:
  - `output_a_runs: list[IterationResult]` — exactly 2 entries (run 1, run 2) for `data/output_a.md`
  - `output_b_runs: list[IterationResult]` — exactly 2 entries for `data/output_b.md`
  - `gap: float` — `output_a_runs[0].total_score - output_b_runs[0].total_score` (computed on run 1 only per D-07)
  - `judgment_gap: int` — `output_a_runs[0].judgment_score - output_b_runs[0].judgment_score` (run 1)
  - `threshold: float = 2.0` — the fixed gate threshold
  - `passed: bool` — `gap >= threshold` AND `judgment_gap > 0` (per ROADMAP SC-2 + SC-3)
  - `decision: Literal["go", "no-go"]`
  - `rationale: str` — free-form, hand-written in code at test-authoring time (NOT auto-templated)
  - `variance_warning: bool` — True if any `RubricScore.score` differs by >1 between run 1 and run 2 for the same output+item_id pair (per D-07 aggregation rule)
  - `model: str` — snapshot of `config.model` at test time
  - `temperature: float` — snapshot of `config.temperature`
  - `num_ctx: int` — snapshot of `config.num_ctx`
  - `timestamp: str` — ISO-8601 UTC, captured at test start

- **D-02:** Change `ExperimentRun.pre_loop_test: dict | None = None` to `pre_loop_test: PreLoopTestResult | None = None`.

- **D-03:** In each `IterationResult` entry, `system_prompt` is a sentinel string: `"<pre-loop fixture: data/output_a.md>"` or `"<pre-loop fixture: data/output_b.md>"`. Do NOT use `ITERATION_ZERO_SYSTEM_PROMPT` — it was not actually executed.

- **D-04:** In each `IterationResult` entry, `agent_output` is the full file contents of the corresponding fixture: `Path("data/output_a.md").read_text()`.

**Verdict representation**

- **D-05:** The decision is observable in **both** the JSON file AND a stdout console banner. NOT via process exit code. NOT via exception.
- **D-06:** Hard-fail the gate on judge sentinel failure (`result.scores == []`). Still write partial results, set `decision="no-go"`, `passed=False`, print error banner, do not raise.

**Run count + aggregation**

- **D-07:** Two runs per output (4 live judge calls total). Run 1 is authoritative for `gap`/`judgment_gap`/`decision`/`passed`. Run 2 drives `variance_warning` only (per-item score diff > 1 → warning, but do NOT fail gate on variance alone).
- **D-08:** Metadata captured: `model` + `temperature` + `num_ctx` + `timestamp`. NO Ollama version.

**Invocation surface**

- **D-09:** Library function `run_pre_loop_test() -> PreLoopTestResult` in `src/pre_loop_test.py`. Reads fixtures, calls `run_judge` 4 times, builds `PreLoopTestResult`, writes `results/pre_loop_test.json`, returns the instance. Ensures `results/` directory exists.
- **D-10:** `_print_banner(result)` helper — module-private, called only from `__main__`. Library API stays side-effect-free for Phase 4/5.
- **D-11:** `tests/test_pre_loop_gate.py` with `@pytest.mark.integration` marker asserts `result.decision == "go"`. Mirrors `tests/test_smoke_ollama.py` pattern.

### Claude's Discretion (resolved in this research)

The 8 items CONTEXT.md left to the planner have concrete recommended answers in `## Technical Approach — Discretion Resolutions` below. All 8 are marked **RESOLVED**.

### Deferred Ideas (OUT OF SCOPE)

- **Deliberate failure-mode sanity test** (swapping output_a as the "flawed" side). Scope creep — revisit only if the real gate emits `no-go`.
- **Fast FakeClient unit tests for the aggregation math.** Planner-discretion item #8 recommends **skip**. Rationale below.
- **Multi-model comparison.** Explicitly banned by PROJECT.md.
- **Stricter `judgment_gap` threshold** (e.g. `>= 2`). Revisit after first real run.
- **Ollama version capture.** Add to Phase 5's run envelope if drift becomes a concern.
- **Banner colourisation / terminal-width detection.** Plain ASCII only.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEST-01 | Run Output A and Output B through judge with same rubric and playbook | `run_pre_loop_test()` calls `run_judge(nda, output_a, rubric, playbook)` twice and `run_judge(nda, output_b, rubric, playbook)` twice. D-09 spells out the exact sequence; code skeleton in `## Code Skeletons` shows the four calls explicitly. |
| TEST-02 | Results logged in same JSON schema as loop iterations for direct comparison | Each of the 4 runs is wrapped in an `IterationResult` (the same model Phase 5 writes per iteration). Sentinel `system_prompt` (D-03) and full fixture contents as `agent_output` (D-04) keep the record self-contained. `PreLoopTestResult` embeds the 4 `IterationResult`s in `output_a_runs` / `output_b_runs` lists, so `results/pre_loop_test.json` is parseable by the same reader logic that will ingest `results/run_001.json`. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

| Directive | Source | Enforcement in Phase 3 |
|-----------|--------|------------------------|
| Python 3.11+ managed with `uv` | CLAUDE.md Tech Stack | `uv run python src/pre_loop_test.py`, `uv run pytest -m integration` |
| OpenAI Python SDK via `run_judge` from Phase 2 | CLAUDE.md Tech Stack | No direct `OpenAI(...)` construction in this phase — always go through `run_judge`. |
| Ollama local runtime; same model for agent/judge/optimiser | CLAUDE.md Tech Stack | `config.model` snapshotted into `PreLoopTestResult.model`; default `gemma4:26b`. |
| Pydantic v2 with retry (up to 3) | CLAUDE.md Tech Stack | Retry lives inside `run_judge` — Phase 3 does NOT add a second retry layer. |
| Black formatting | CLAUDE.md Tech Stack | `black src/pre_loop_test.py tests/test_pre_loop_gate.py` before commit. |
| Temperature = 0 (non-negotiable) | CLAUDE.md Key Design + CONF-02 | Pulled from `config.temperature`; also asserted via metadata snapshot in the banner (user sees `0.0` at every run). |
| No agent SDK, no tool use, prompt rewriting only | CLAUDE.md Key Design | Phase 3 adds no LLM call sites beyond the existing `run_judge`. |
| No `instructor`, `langchain`, `pydantic-settings`, `structlog`/`loguru` | STACK.md "What NOT to Use" | stdlib `logging` only, no new deps. |
| No `response_format` or `client.beta.chat.completions.parse` | STACK.md + P4 | Inherited — `run_judge` already respects this. |
| GSD workflow enforcement | CLAUDE.md | Plan → implement → verify via `/gsd-execute-phase`. |

## Standard Stack

### Core (all existing — no new deps)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic` | `>=2.0` (2.12.5 as of 2026-04-11) [CITED: STACK.md] | Define `PreLoopTestResult`, serialise to JSON | Already used by `src/models.py`; `@model_validator` is the v2 canonical invariant-enforcement path [CITED: P12] |
| `pytest` | `>=8.0` [VERIFIED: pyproject.toml `[tool.uv] dev-dependencies`] | Integration wrapper gates CI on `result.decision == "go"` | Already installed in Phase 2 Wave 0; `@pytest.mark.integration` marker already registered [VERIFIED: pyproject.toml `[tool.pytest.ini_options]`] |
| `logging` (stdlib) | — | Phase 3 start/end + judge-sentinel ERROR + variance WARNING | `jitc.preloop` logger namespace — matches Phase 2 `jitc.agent` / `jitc.judge` convention [CITED: CONTEXT.md §Claude's Discretion] |
| `datetime` (stdlib) | — | Capture ISO-8601 UTC timestamp | `datetime.now(timezone.utc).isoformat()` |
| `pathlib` (stdlib) | — | Read fixtures; mkdir `results/`; write `pre_loop_test.json` | Already used elsewhere in tests |
| `json` (stdlib) | — | Only for `model_dump_json` output — Pydantic handles it | — |

### Phase 2 Assets (reused as-is — no modification)
| Asset | Purpose |
|-------|---------|
| `src.judge.run_judge` | The function under test; called 4 times |
| `src.config.config` | `.model`, `.temperature`, `.num_ctx` metadata snapshot |
| `src.models.IterationResult` | Per-run record wrapper; auto-validator computes `total_score` / `extraction_score` / `judgment_score` — do NOT duplicate that logic [CITED: CONTEXT.md §Existing Code Insights] |
| `src.models.JudgeResult` | Return type of `run_judge`; sentinel check is `if not result.scores:` [CITED: Phase 2 D-05] |
| `tests/conftest.py` `FakeClient` + `VALID_JUDGE_JSON` | Available if planner decides to write unit tests (not recommended — see resolution #8) |
| `pyproject.toml` `integration` marker | Already registered; no Wave 0 pytest setup needed [VERIFIED: pyproject.toml] |

**Installation:** No new dependencies. Planner should NOT run `uv add` in Phase 3.

**Version verification:** Not applicable — all stack components are already locked by Phase 1/2.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pydantic `PreLoopTestResult` | Plain `dict` serialised with `json.dump` | Loses IDE completion, loses D-02 type safety, loses automatic invariant enforcement via `@model_validator` [CITED: CONTEXT.md §Specific Ideas] |
| Reusing `IterationResult` | Inventing a new `PreLoopRun` type | Breaks TEST-02 ("same schema as loop iterations"); `IterationResult` already does what we need [CITED: CONTEXT.md D-01, TEST-02] |
| Integration test as the only test | Fast FakeClient unit tests for aggregation | Addressed in resolution #8 below — recommend skip |
| Exit code for go/no-go | Stdout banner + JSON field | Deliberately rejected by user in D-05 — shell chaining is Phase 5's concern |

## Architecture Patterns

### Recommended File Additions
```
src/
├── models.py          # MODIFY — add PreLoopTestResult, retype ExperimentRun.pre_loop_test
├── pre_loop_test.py   # NEW — run_pre_loop_test() + _print_banner + __main__
tests/
└── test_pre_loop_gate.py  # NEW — @pytest.mark.integration wrapper
results/
└── pre_loop_test.json     # RUNTIME OUTPUT — gitignored
```

### Pattern 1: Pydantic Aggregate Model with `@model_validator(mode="after")` (D-01 + resolution #1)
**What:** Put gap/judgment_gap/variance computation inside a `@model_validator(mode="after")` on `PreLoopTestResult`, so constructing the model from 4 raw `IterationResult` inputs automatically fills in the derived fields and enforces invariants.
**When to use:** When the derived fields are a pure function of the stored fields — exactly this case.
**Why this is the right shape:**
- Mirrors the existing `IterationResult._check_totals` pattern in `src/models.py:28-52` — same project idiom [CITED: src/models.py line 28].
- Construction-time enforcement means bad states cannot be written to disk: if `len(output_a_runs) != 2`, `ValidationError` fires before `model_dump_json` runs.
- The planner can construct a `PreLoopTestResult` by passing only the 4 `IterationResult`s, `threshold`, metadata, and `rationale` — everything else is derived.

**Example:** See Code Skeleton 1 below.

### Pattern 2: Library Function + `__main__` Split (D-09 / D-10)
**What:** `run_pre_loop_test()` returns the result and is side-effect-free *for stdout* (it still writes `results/pre_loop_test.json` because that is part of the contract per TEST-02). `_print_banner(result)` is module-private and called only from the `if __name__ == "__main__":` block.
**When to use:** Any time the same function is consumed both by scripts and by libraries (Phase 4/5 may import `run_pre_loop_test`; they must not get stdout spam).
**Rationale:** Matches the Phase 2 convention where `run_agent` and `run_judge` return structured data and never print. Phase 3 is allowed one exception (the banner) because D-05 requires it, but that exception is isolated behind `_print_banner` + `__main__`.

### Pattern 3: pytest Integration Marker (D-11 / mirrors `tests/test_smoke_ollama.py`)
**What:** Module-level `pytestmark = pytest.mark.integration`. Default `uv run pytest -q -m "not integration"` skips it; `uv run pytest -m integration` runs it. Matches the Phase 2 convention exactly.
**When to use:** Any test that requires live Ollama. Phase 3 is one test (`test_pre_loop_gate_passes`) — nothing else needs the marker.

### Pattern 4: stdlib Logger Namespacing (`jitc.preloop`)
**What:** `logging.getLogger("jitc.preloop")` — matches `jitc.agent` and `jitc.judge` from Phase 2.
**When to log:**
- INFO at entry: `"pre-loop gate start: model=%s num_ctx=%d"` with metadata snapshot
- INFO before each run: `"judging %s run %d/2"` with fixture name and run number
- WARNING on variance: `"variance warning: item %s diff=%d between run 1 and run 2"` for each offending item
- ERROR on sentinel failure (D-06): `"judge sentinel failure for %s run %d — gate decision forced to no-go"`
- INFO at exit: `"pre-loop gate complete: decision=%s gap=%.2f"` (INFO for go, WARNING for no-go)

### Anti-Patterns to Avoid
- **Calling `run_judge` inside a `try/except` block:** Phase 2 D-05 / JUDG-05 guarantees no exception — the sentinel `JudgeResult(scores=[])` is the contract. Wrapping it in try/except masks real bugs and adds zero safety.
- **Mutating `results/pre_loop_test.json` on partial failures:** if a sentinel is detected in run 2 of output_a, we still want runs 1 of both outputs written, the offending `IterationResult` preserved with `scores=[]`, and a clear `rationale` string. One atomic write at the end — not incremental appends.
- **Computing `gap` outside the model validator:** leads to a possible desync between `passed` and the underlying data (e.g. someone edits `output_a_runs` after construction). Putting it inside `@model_validator(mode="after")` makes drift impossible.
- **Adding a timestamp suffix to the results filename:** CONTEXT.md §Specific Ideas explicitly says the PRD names `results/pre_loop_test.json` as fixed. A second run overwrites the first.
- **Printing from `run_pre_loop_test`:** breaks the library API contract (D-10). Printing only from `_print_banner`, only from `__main__`.
- **Passing rubric as `list[dict]` to `run_judge`:** Phase 2 D-08 says "raw JSON, verbatim". Read `data/rubric.json` as text and pass the text.
- **Re-reading files inside `run_judge`:** Phase 2 established that `run_judge` takes strings, not paths. Read once in `run_pre_loop_test`, pass to all 4 calls.
- **Using `ITERATION_ZERO_SYSTEM_PROMPT` as the `system_prompt` value:** explicitly banned by D-03. The reference reviews were hand-written; no prompt was executed.
- **Writing `pre_loop_test.json` inside the pytest wrapper:** the wrapper just calls `run_pre_loop_test()`. The library function writes the file. Double-writing creates race confusion.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Judge retry / fence stripping / graceful failure | A second retry loop in `pre_loop_test.py` | Rely on Phase 2 `run_judge` sentinel contract | Already tested (SC-3, SC-5 of Phase 2); adding a wrapper duplicates the retry accounting |
| Score aggregation | Manual `sum(s.score for s in ...)` in `run_pre_loop_test` | `IterationResult._check_totals` auto-computes on construction | Already exists in `src/models.py:28-52` — pass `scores=...` and read `.total_score` / `.extraction_score` / `.judgment_score` back |
| Category aggregation | Recomputing extraction/judgment splits | `compute_category_scores(scores)` in `src/models.py:66-70` | Already exported for exactly this use case |
| Go/no-go invariant enforcement | Hand-written `if result.gap >= 2 ...` checks scattered across code | `@model_validator(mode="after")` on `PreLoopTestResult` | One place, enforced at construction, unbypassable |
| Timestamp capture | `str(datetime.now())` | `datetime.now(timezone.utc).isoformat()` | ISO-8601 UTC is the project standard (matches what Phase 5's run envelope will emit) |
| Results file write | Custom JSON encoder | `Path.write_text(result.model_dump_json(indent=2))` | Pydantic v2 handles `Literal` / nested models / ordering correctly |
| Env-var overrides for threshold | `os.getenv("THRESHOLD", "2.0")` | Hard-coded `threshold: float = 2.0` field default | Tuning the threshold at runtime would let operators weaken the gate — that defeats P10 mitigation. If the threshold ever needs to change, the change should be a code edit reviewed in a PR. |

**Key insight:** Phase 3 is the thinnest possible layer on top of Phase 2. Every opportunity to "add a little something" (a second retry, a custom aggregator, a configurable threshold) is either already solved upstream or actively hostile to the thesis. The value is in getting 4 line items right, not in writing cleverness.

## Runtime State Inventory

*(Not a rename/migration phase — skipped per research protocol.)*

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Project | ✓ (Phase 2 verified) | — | — |
| `uv` | Project management | ✓ (Phase 2 verified) | — | — |
| `openai` | Transitively via `run_judge` | ✓ | `>=2.0` | — |
| `pydantic` | `PreLoopTestResult` | ✓ | `>=2.0` | — |
| `pytest` | Integration wrapper | ✓ (installed Phase 2 Wave 0) | `>=8.0` | — |
| `@pytest.mark.integration` marker | Integration wrapper | ✓ registered in `pyproject.toml` | — | — |
| Ollama on `localhost:11434` | `test_pre_loop_gate_passes` | verify at run time with `curl http://localhost:11434/api/tags` | — | Integration test is skipped unless `-m integration`. No unit-test path is proposed (see resolution #8). |
| `gemma4:26b` model pulled | `test_pre_loop_gate_passes` | verify with `ollama list` | — | Override with `MODEL=<other-model>` env var |
| `data/nda.md`, `data/output_a.md`, `data/output_b.md`, `data/rubric.json`, `data/playbook.md` | Fixtures | ✓ (Phase 1 shipped) | — | — |

**Missing dependencies with no fallback:** None — Phase 2 Wave 0 already installed everything Phase 3 needs.

**Missing dependencies with fallback:** Live Ollama is only required for the integration wrapper. Since the plan does not include unit tests (resolution #8), there is no "fast path" — but the phase can still be implemented, committed, and code-reviewed without Ollama. The integration run is a separate gate.

## Technical Approach — Discretion Resolutions

### 1. `PreLoopTestResult` validator placement — **RESOLVED: `@model_validator(mode="after")` on the model itself**

**Options considered:**
1. **`@model_validator(mode="after")` on `PreLoopTestResult`** ← **RECOMMEND**
2. Standalone helper function `_compute_gate_result(a_runs, b_runs, threshold, ...)` that builds and returns the model
3. Computing fields inline in `run_pre_loop_test` and passing them all to the constructor

**Reasoning:**
- **Matches the existing project idiom:** `IterationResult._check_totals` (src/models.py:28-52) already uses `@model_validator(mode="after")` for the same shape — derive fields from one input, store them on the instance, enforce consistency. Phase 3 picks up the same pattern instead of introducing a second one.
- **Unbypassable:** Anyone constructing a `PreLoopTestResult` (Phase 3 code today, Phase 5 reading back the JSON tomorrow, any future test) goes through the validator. There is no path where `gap` can desync from `output_a_runs[0].total_score - output_b_runs[0].total_score`.
- **Makes `run_pre_loop_test` tiny:** the orchestration function shrinks to "read files → call run_judge 4 times → build 4 IterationResults → instantiate PreLoopTestResult(...) → write JSON". The validator does the arithmetic.
- **Against Option 2 (helper function):** scatters the derivation logic across two modules; a future reader has to hunt for where `gap` came from.
- **Against Option 3 (inline in run_pre_loop_test):** duplicates effort between the library function and any test that constructs a `PreLoopTestResult` directly from in-memory `IterationResult`s. The whole point of Pydantic is to put this kind of logic on the model.

**Consequence for the planner:** the model has fields declared with placeholder defaults (`gap: float = 0.0`, `judgment_gap: int = 0`, `passed: bool = False`, `decision: Literal["go", "no-go"] = "no-go"`, `variance_warning: bool = False`) that the validator overwrites. Callers pass only the 4 runs, the threshold (default 2.0), the rationale, and the metadata — the rest populates automatically.

### 2. Exact `passed` computation rule — **RESOLVED: Validator enforces the invariant**

**Rule:** `passed = (gap >= threshold) AND (judgment_gap > 0) AND (no sentinel failures in run 1 of either output)`

**Where the check lives:** inside the same `@model_validator(mode="after")` as resolution #1. The validator:
1. Computes `gap` and `judgment_gap` from run 1 of both outputs.
2. Sentinel check: if either `output_a_runs[0].scores == []` or `output_b_runs[0].scores == []`, force `passed=False`, `decision="no-go"`, `variance_warning=False` (per D-06).
3. Otherwise: `passed = (gap >= threshold) and (judgment_gap > 0)`.
4. Set `decision = "go" if passed else "no-go"`.
5. Run the variance check (resolution #3) across run 1 vs run 2.

**Why the validator (not the test-authoring code):** D-01 pins the formula. Making the formula data rather than code means every future reader of `pre_loop_test.json` can trust that the stored `passed` field reflects the stored scores. If `run_pre_loop_test` computed `passed` in a separate step, a bug there could persist a `passed=True` + `gap=1.5` combination into JSON and silently poison downstream analysis.

**Caller's only responsibility:** pass the four runs and the rationale. Do NOT pass `passed` or `decision` as constructor args — the validator owns them.

### 3. Variance check algorithm — **RESOLVED: Per-item diff > 1, missing item = warning**

**Algorithm (pseudocode — use in the validator after the `passed` computation):**

```
variance_warning = False
for output_runs in (output_a_runs, output_b_runs):
    run1_by_id = {s.item_id: s.score for s in output_runs[0].scores}
    run2_by_id = {s.item_id: s.score for s in output_runs[1].scores}
    all_ids = set(run1_by_id) | set(run2_by_id)
    for item_id in all_ids:
        s1 = run1_by_id.get(item_id)
        s2 = run2_by_id.get(item_id)
        if s1 is None or s2 is None:
            variance_warning = True      # missing item in one run
            continue
        if abs(s1 - s2) > 1:
            variance_warning = True      # 0→2 or 2→0 flip
```

**Key decisions:**
- **Missing item in one run → warning.** This is the recommended strict interpretation: if the judge returned 8 items on run 1 and 7 items on run 2, the rubric coverage itself is unstable and we want to flag that. A missing item is a *larger* instability signal than a score flip, not a smaller one.
- **Sentinel-only output (scores == [])** doesn't count as "missing items" — it's already caught by the D-06 sentinel path above, which sets `decision="no-go"` and skips the variance check. The variance check runs only when both runs of the given output returned scores.
- **`abs(s1 - s2) > 1` means a 0↔2 flip.** Since `score: Literal[0,1,2]`, the only diffs possible are 0, 1, or 2. `> 1` selects exactly the 0↔2 case — a meaningful disagreement, not a 1↔2 nudge that could be ordinary temperature-0 noise per P3.
- **Variance does NOT fail the gate.** D-07 is explicit: warning only, not a blocker. The variance field is a Phase 5 signal that the loop will need ±1 tolerance in its plateau detection.

### 4. Rationale string template — **RESOLVED: Three example sentences for the planner to adapt**

D-05 is clear that the rationale is hand-written (not f-string-interpolated from a template) — the planner writes three concrete strings at test-authoring time and picks one based on branch. The three cases below cover every path the validator can take. Each is 1-2 sentences and the planner should interpolate the actual numbers at construction time using a standard f-string *inside the call site*, not inside the model.

**Case 1 — Gate passes (decision="go"):**
> `f"output_a total_score={a_total} (extraction={a_ext}, judgment={a_jud}) outscored output_b total_score={b_total} (extraction={b_ext}, judgment={b_jud}) by gap={gap:.2f} against threshold={threshold:.2f}; judgment_gap={judgment_gap} is positive. Gate passes — loop is worth building."`

**Case 2 — Gate fails on gap or judgment (decision="no-go", no sentinel):**
> `f"output_a total_score={a_total} (extraction={a_ext}, judgment={a_jud}); output_b total_score={b_total} (extraction={b_ext}, judgment={b_jud}); gap={gap:.2f} vs threshold={threshold:.2f}; judgment_gap={judgment_gap}. Gate fails — the judge is not reliably distinguishing the good review from the flawed one, so the loop is not worth building. Investigate playbook specificity for judgment items and re-run."`

**Case 3 — Gate fails on sentinel (decision="no-go", judge returned empty scores):**
> `f"judge retry exhausted for {failing_fixture} run {failing_run_number} — see jitc.judge ERROR logs for raw output. Gate forced to no-go. Investigate prompt construction or num_ctx before re-running."`

**Implementation note:** since the f-strings depend on whether there is a sentinel failure, compute them in `run_pre_loop_test` *after* you've built the 4 `IterationResult`s but *before* constructing `PreLoopTestResult`. Pass the chosen string in as `rationale=...`. The validator does not rewrite it.

### 5. Banner format — **RESOLVED: Plain-ASCII template**

Use ASCII `=` separators and no Unicode box-drawing. Two variants needed: normal (go or no-go) and error (sentinel). Banner prints after the results file is written.

**Normal banner (used for both go and no-go):**
```
===========================================
  PRE-LOOP VALIDATION GATE
===========================================
Model:       gemma4:26b
Temperature: 0.0
num_ctx:     16384
Timestamp:   2026-04-11T14:32:05+00:00

output_a:    total=14  extraction=8  judgment=6
output_b:    total=6   extraction=4  judgment=2

Gap:         8.00  (threshold: 2.00)
Judgment:    output_a leads by 4
Variance:    no warning
Decision:    GO
Rationale:   output_a total_score=14 ... (truncate at ~140 chars)
===========================================
```

**Error banner (sentinel path — D-06):**
```
===========================================
  PRE-LOOP VALIDATION GATE — ERROR
===========================================
Model:       gemma4:26b
Timestamp:   2026-04-11T14:32:05+00:00

Judge sentinel failure detected:
  - output_a run 2: scores=[] (retry exhausted)

Decision:    NO-GO
Rationale:   judge retry exhausted for data/output_a.md run 2 ...
See jitc.judge ERROR logs above for the raw model output.
===========================================
```

**Format rules (all enforceable in a small helper):**
- ASCII only — no `═`, `╔`, `╗`, `║`, no ANSI colours. `=` and `-` and spaces.
- Fixed width 43 characters (`"=" * 43`). Works in 80-column terminals, log files, pipes, and CI output.
- `Decision:` uses the literal strings `GO` and `NO-GO` (not `go` / `no-go`) — matches the visual weight a human reader expects.
- `Variance:` reads `"no warning"` when `variance_warning=False`, or `"WARNING — per-item scores diverged between runs"` when True.
- Rationale is truncated to ~140 chars with `...` to keep the banner scannable. Full rationale lives in the JSON file.

### 6. Where to compute `gap` and `judgment_gap` — **RESOLVED: Inside the `@model_validator`**

Already decided in resolution #1, called out here for completeness. The validator is the only place arithmetic happens. `run_pre_loop_test` does orchestration only (read files → call run_judge → build 4 IterationResults → choose rationale string → instantiate model → dump JSON).

### 7. Test isolation for the pytest integration wrapper — **RESOLVED: Accept the overwrite; document it**

**The question:** `run_pre_loop_test()` writes `results/pre_loop_test.json`. Running pytest twice overwrites. Is that a problem?

**Answer: No. Accept overwrites, do not add cleanup.**

**Reasoning:**
- `results/pre_loop_test.json` is a **single-latest-run artifact**, not an append log. D-09 / CONTEXT.md §Specific Ideas explicitly states: *"Do not introduce a timestamp suffix — this is a one-shot gate... If a second run is needed, it overwrites the first."*
- `results/` is gitignored (`results/*` in `.gitignore`), so overwrites never affect the repo.
- A temp-dir fixture would mask a real bug: if Phase 4/5 consumers depend on `results/pre_loop_test.json` existing at the canonical path, writing to a temp dir in tests means the test proves nothing about the real path behaviour.
- The developer's mental model is simple: *"I ran the gate; here's the latest result in `results/pre_loop_test.json`."* Keeping one artifact instead of a history is the whole point of the convention.

**What to add to the docstring of `test_pre_loop_gate_passes`:**
> `"""Integration test: runs the live pre-loop gate against Ollama. Note: this test writes `results/pre_loop_test.json` as a real side effect. The file is gitignored and each run overwrites the last — this is intentional per CONTEXT.md D-09."""`

**What NOT to do:**
- Do NOT add a `tmp_path` fixture — changes the behaviour under test.
- Do NOT delete the file after the test — a developer running `pytest -m integration` should be able to `cat results/pre_loop_test.json` afterward.
- Do NOT add a teardown — the file is a deliberate artifact, not test pollution.

### 8. Fast FakeClient unit tests for aggregation math — **RESOLVED: SKIP. Rely on the integration wrapper.**

**The question:** CONTEXT.md §Deferred says unit tests are NOT required. Re-confirm: are they worth adding anyway?

**Answer: Skip. The integration wrapper is sufficient.**

**Reasoning (concrete pros and cons):**

*Pro add:* Aggregation math is load-bearing — a bug that silently sets `passed=True` when `gap=1.9` would poison the gate with no visible symptom. Unit tests would catch that in < 100ms without Ollama.

*Con add:*
1. The aggregation is not hand-rolled — the validator is ~15 lines and most of the heavy lifting is done by Pydantic's `@model_validator` pattern and the existing `IterationResult._check_totals`. The planner will write at most two arithmetic lines (`gap = a_total - b_total`, `judgment_gap = a_jud - b_jud`) and a boolean composition. Bugs in two lines are better caught by eyeballing during code review than by a unit test.
2. The integration test exercises exactly the same validator code path against real `IterationResult` objects built from real `JudgeResult`s. If the arithmetic is wrong, the integration test fails on its `assert result.decision == "go"` assertion.
3. Writing FakeClient unit tests means constructing synthetic `RubricScore` lists with carefully-chosen totals, running them through `run_pre_loop_test` with a monkeypatched `run_judge` (not a monkeypatched client — a second mock layer). That's another 100 lines of fixture code and it would *duplicate* the logic it's testing.
4. The pre-loop gate is run deliberately by a human operator, not by CI on every commit. It is not in the hot path that a unit suite is supposed to protect. The speed advantage of fast unit tests is less important here than it is for a framework.
5. Phase 5 will exercise this data structure continuously as part of the main loop's artifact reader. Any arithmetic bug that sneaks through Phase 3 will surface at Phase 5 with the first real run, long before anyone ships results.

**Revisit conditions (when the planner should override this):**
- If Phase 4 or Phase 5 integration shows the aggregation flake in unexpected ways.
- If the validator grows beyond ~20 lines because additional invariants are added.
- If someone proposes an env-var knob for the threshold (and gets overruled, per the Don't Hand-Roll table).

**Net:** 0 unit tests, 1 integration test. The `tests/test_pre_loop_unit.py` file is NOT created in Phase 3.

## Pitfall Cross-References

### P1 — Judge grading its own output (self-reference collapse)

**Mitigation site:** This entire phase IS the P1 mitigation. P1 warns that a judge built from the same model as the agent will develop blind spots aligned with the agent's reasoning style — scoring by mirror, not by rubric. Phase 3 makes that warning concrete and falsifiable: if the judge cannot tell a deliberately-flawed hand-written review apart from a deliberately-correct hand-written review (by at least 2.0 points total *and* by a positive margin on judgment items specifically), the self-reference failure is already present and no amount of optimiser tuning in Phase 4 will fix it.

**What the planner must ensure:**
- The `rationale` string written to `results/pre_loop_test.json` must contain the three category splits (`extraction_score` for both outputs, `judgment_score` for both outputs, and the gap on each). Without that, a human reviewing the result cannot tell whether the gate passed on total-score luck but failed the thesis-critical judgment signal. The resolution #4 templates include all three splits.
- The judge must score all 8 rubric items. If either run 1 returns fewer than 8 items, the variance check (resolution #3) flags it, and the integration test's `assert result.decision == "go"` still passes if the gap is large enough — but the `variance_warning=True` field in the JSON is the signal that the Phase 5 loop will need to treat missing items as a real failure mode, not just temperature-0 noise.

**Verification step in the plan:** the integration test MUST assert `result.judgment_gap > 0` as a separate assertion, not bundled into `result.decision == "go"`. This surfaces the judgment-specific signal in the test output, making P1-style failure visible in a pytest report rather than hidden inside a conjunction.

### P3 — Ollama temperature=0 not fully deterministic across runs

**Mitigation site:** D-07's dual-run design. P3 is explicit that temperature 0 reduces but does not eliminate variance — hardware differences, context padding, and GGUF quantisation can cause run-to-run drift even with identical inputs. Phase 3's two-run design per output is the lightest-weight way to detect this in advance of Phase 5.

**What the planner must ensure:**
- Both runs for each output use literally identical input — same NDA text, same rubric text, same playbook text, same `system_prompt` sentinel, same fixture file contents. The only thing varying between run 1 and run 2 is Ollama's internal non-determinism. If the planner accidentally rebuilds the rubric string between runs, they're testing the wrong thing.
- The metadata snapshot (`model`, `temperature`, `num_ctx`, `timestamp`) is captured **once, at the start of run_pre_loop_test**, not per-run. All 4 runs share the same metadata. P3's concern is drift across runs that share all inputs; recording per-run metadata would imply you intended them to differ.
- Timestamp is captured **before the first judge call**, not after. If a run takes 2 minutes and the timestamp is captured after all 4 calls, the file's "time of gate" is off by up to 8 minutes from the actual decision boundary.
- `variance_warning=True` in the JSON **does not fail the gate** (per D-07). It is a signal for Phase 5's plateau detection, not a Phase 3 blocker. The integration test asserts `result.decision == "go"` — which depends only on the run-1 gap — and NOT on `variance_warning == False`.

**Future drift detection:** P3 recommends "record Ollama version". D-08 deliberately skips this. The compensating control is that the metadata snapshot in `PreLoopTestResult` gives future readers enough to re-run (`MODEL=... TEMPERATURE=... NUM_CTX=... uv run python src/pre_loop_test.py`) and compare results. If it turns out the gate flakes across days or machines, the Phase 5 run envelope can add Ollama version without touching `PreLoopTestResult`'s schema.

### P10 — Pre-loop test not actually diagnostic if gap is small

**Mitigation site:** The 2.0-point threshold is the P10 mitigation. P10 is explicit that a small score delta means the judge is not discriminating and all loop scores are meaningless — so the minimum gap must be defined *before* running and enforced as a hard gate.

**Why 2.0 is load-bearing (and not arbitrary):**
- **Scoring range:** each rubric item scores 0, 1, or 2. With 8 items, `total_score` ranges from 0 to 16. A 2.0-point gap is 12.5% of the range.
- **Single-item discrimination:** 2.0 points could come from a single item flipping from `0` (not addressed) to `2` (fully addressed), or from two items going from `1` (partially addressed) to `2`. Either way, it represents *at least one unambiguous scoring difference*, not a noise-level 0.1 drift.
- **Variance floor from P3:** even under ordinary temperature-0 non-determinism, individual scores can drift by ±1 point per item on repeated runs. With 8 items, the expected RMS drift on `total_score` is roughly `√8 ≈ 2.8` for a worst-case item-by-item random walk. A 2.0-point gap is *below* this worst-case drift — but the `judgment_gap > 0` sub-criterion is what saves it: the gate demands that the gap show up *structurally* in the judgment category, not just numerically in the total. A random temperature-0 drift of `total_score` is unlikely to consistently align with the judgment/extraction partition.
- **Against lower thresholds:** 0.1 is noise; 1.0 is indistinguishable from a single per-item drift in either direction; 2.0 is the smallest threshold that guarantees *at least one full-grade disagreement* on at least one item between the two outputs.
- **Against higher thresholds:** 4.0 would make the gate unnecessarily strict and risk false negatives against real-but-modest judge discrimination. 2.0 is the point where the signal is unambiguous but not unreachable.

**What the planner must ensure:**
- The threshold is **hard-coded as a field default** (`threshold: float = 2.0`) — not an env var, not a config knob, not a plan parameter. CONTEXT.md §Don't Hand-Roll and Phase 3 deferred ideas both reject tuning at runtime. If the threshold ever needs to change, the change is a code edit reviewed in a PR and documented in STATE.md, not a `THRESHOLD=1.5 uv run ...` invocation.
- The threshold is captured in the persisted `PreLoopTestResult.threshold` field, so future readers can see what bar this specific run was graded against. If a later Phase 5 run fails with a gap of 1.5, the researcher can look at this file and know that the bar was 2.0.
- The `passed` computation is a logical AND of gap-vs-threshold *and* `judgment_gap > 0`. A gap of 2.0 with `judgment_gap == 0` is a fail — the total-score win could have come entirely from extraction items, which does not vindicate P1. Both conditions must hold.

## Code Skeletons

The skeletons below are reference implementations. The planner should adapt (variable names, docstring length, comment density) but the structure and logic are load-bearing.

### Skeleton 1: `src/models.py` additions

```python
# Add to imports at the top of src/models.py:
from datetime import datetime, timezone
# Keep existing: from pydantic import BaseModel, model_validator
# Keep existing: from typing import Literal

# Add at the bottom of src/models.py, AFTER IterationResult and AFTER
# compute_category_scores (PreLoopTestResult references IterationResult).

class PreLoopTestResult(BaseModel):
    """Structured result of the Phase 3 pre-loop validation gate.

    Exactly two runs per reference output. Run 1 is authoritative for the
    gate computation (gap, judgment_gap, passed, decision). Run 2 is a
    variance check only — it drives variance_warning but never fails the
    gate (D-07).

    Construction contract: callers pass `output_a_runs`, `output_b_runs`,
    `rationale`, `model`, `temperature`, `num_ctx`, `timestamp`. The
    @model_validator(mode="after") computes `gap`, `judgment_gap`,
    `passed`, `decision`, and `variance_warning` from the 4 runs. Do NOT
    pass those derived fields at construction — they will be overwritten.

    The sentinel path (D-06): if either output_a_runs[0] or
    output_b_runs[0] has scores == [], the gate forces decision="no-go",
    passed=False, variance_warning=False regardless of the arithmetic.
    """

    output_a_runs: list[IterationResult]
    output_b_runs: list[IterationResult]
    threshold: float = 2.0                  # P10 mitigation — hard-coded
    rationale: str                          # hand-written per resolution #4
    model: str
    temperature: float
    num_ctx: int
    timestamp: str
    # Derived fields (validator overwrites these; defaults are placeholders)
    gap: float = 0.0
    judgment_gap: int = 0
    passed: bool = False
    decision: Literal["go", "no-go"] = "no-go"
    variance_warning: bool = False

    @model_validator(mode="after")
    def _compute_gate(self) -> "PreLoopTestResult":
        # D-01: exactly 2 runs per output.
        if len(self.output_a_runs) != 2 or len(self.output_b_runs) != 2:
            raise ValueError(
                f"PreLoopTestResult requires exactly 2 runs per output; "
                f"got output_a_runs={len(self.output_a_runs)}, "
                f"output_b_runs={len(self.output_b_runs)}"
            )

        a1 = self.output_a_runs[0]
        b1 = self.output_b_runs[0]

        # D-06: sentinel path — if either run 1 failed, force no-go.
        if not a1.scores or not b1.scores:
            object.__setattr__(self, "gap", 0.0)
            object.__setattr__(self, "judgment_gap", 0)
            object.__setattr__(self, "passed", False)
            object.__setattr__(self, "decision", "no-go")
            object.__setattr__(self, "variance_warning", False)
            return self

        # Happy path: compute gap from run 1.
        gap = float(a1.total_score - b1.total_score)
        judgment_gap = a1.judgment_score - b1.judgment_score
        passed = (gap >= self.threshold) and (judgment_gap > 0)
        decision = "go" if passed else "no-go"

        # Variance check: per-item diff > 1 between run 1 and run 2
        # for the same output. Missing item in one run also counts.
        variance_warning = False
        for runs in (self.output_a_runs, self.output_b_runs):
            if not runs[0].scores or not runs[1].scores:
                # Run-2 sentinel is variance by definition.
                variance_warning = True
                continue
            r1_by_id = {s.item_id: s.score for s in runs[0].scores}
            r2_by_id = {s.item_id: s.score for s in runs[1].scores}
            all_ids = set(r1_by_id) | set(r2_by_id)
            for item_id in all_ids:
                s1 = r1_by_id.get(item_id)
                s2 = r2_by_id.get(item_id)
                if s1 is None or s2 is None:
                    variance_warning = True
                    break
                if abs(s1 - s2) > 1:
                    variance_warning = True
                    break
            if variance_warning:
                break

        object.__setattr__(self, "gap", gap)
        object.__setattr__(self, "judgment_gap", judgment_gap)
        object.__setattr__(self, "passed", passed)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "variance_warning", variance_warning)
        return self


# Also UPDATE ExperimentRun — change pre_loop_test field type (D-02):
class ExperimentRun(BaseModel):
    experiment_id: str
    timestamp: str
    config: dict
    nda_file: str
    rubric_file: str
    playbook_file: str
    pre_loop_test: PreLoopTestResult | None = None   # D-02 — was `dict | None`
    iterations: list[IterationResult] = []
```

**Note on `object.__setattr__`:** mirrors the existing `IterationResult._check_totals` pattern (src/models.py:38-40). Pydantic v2 models are frozen-by-default at the `@model_validator(mode="after")` stage; `object.__setattr__` is how the existing code bypasses that to write derived fields. Use the same technique in the new validator so the idiom is consistent across the module.

### Skeleton 2: `src/pre_loop_test.py`

```python
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
_SENTINEL_A = f"<pre-loop fixture: data/output_a.md>"   # D-03
_SENTINEL_B = f"<pre-loop fixture: data/output_b.md>"


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
            fixture_label, iteration,
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
        model, temperature, num_ctx,
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

    # First pass: compute gap/judgment_gap/decision without a rationale so
    # we can build a matching rationale string, then construct the real
    # PreLoopTestResult with the rationale filled in.
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
        output_a_runs, output_b_runs,
        probe.gap, probe.judgment_gap, probe.threshold, probe.decision,
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
        result.decision, result.gap, result.judgment_gap, result.variance_warning,
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
        # Also flag run-2 sentinels since they count against variance.
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
    print(
        f"Variance:    "
        f"{'WARNING — per-item scores diverged between runs' if result.variance_warning else 'no warning'}"
    )
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
```

**Implementation note on the "probe" pattern:** Constructing `PreLoopTestResult` twice (once with a `"<probe>"` rationale to compute the arithmetic, then again with the real rationale) is a small inefficiency that keeps the rationale logic cleanly separated from the model validator. The alternative — computing `gap`/`judgment_gap` in `run_pre_loop_test` and then duplicating it in the validator — violates resolution #1. Two Pydantic constructions are cheap (no LLM calls), and the second overwrites the first's JSON output.

**Optional simplification (planner's call):** if the probe/rebuild feels ugly, the planner can add a `classmethod` like `PreLoopTestResult.build(output_a_runs, output_b_runs, rationale_fn, ...)` that calls `rationale_fn(gap, judgment_gap, decision)` to produce the string between the validator run and the final store. This centralises the pattern on the model. Not required — the probe is fine for a one-shot gate.

### Skeleton 3: `tests/test_pre_loop_gate.py`

```python
"""Live integration test for the Phase 3 pre-loop validation gate.

Gated behind @pytest.mark.integration (same pattern as
tests/test_smoke_ollama.py). Run with:

    uv run pytest -q -m integration tests/test_pre_loop_gate.py

Prerequisites:
- Ollama running on localhost:11434
- The configured model pulled (default: gemma4:26b; override with MODEL=...)

This test writes `results/pre_loop_test.json` as a real side effect. The
file is gitignored and each run overwrites the last — this is intentional
per CONTEXT.md D-09. Do NOT wrap run_pre_loop_test in tmp_path or mock
the target path; the test must prove the production artifact path works.

Asserts (in order of strictness):
1. result.decision == "go"             — SC-4 (the gate itself)
2. result.gap >= result.threshold      — SC-2 (at least 2.0 points)
3. result.judgment_gap > 0             — SC-3 (thesis-critical signal)
4. results/pre_loop_test.json exists   — SC-1 (artifact written)

The assertions are ordered so the first failure is the most informative:
decision tells the human "gate failed"; gap tells them "because total was
too close"; judgment_gap tells them "and the judgment signal was absent".
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RESULTS_FILE = _REPO_ROOT / "results" / "pre_loop_test.json"


def test_pre_loop_gate_passes():
    from src.pre_loop_test import run_pre_loop_test

    result = run_pre_loop_test()

    # Primary gate assertion — SC-4.
    assert result.decision == "go", (
        f"Pre-loop gate failed. Rationale: {result.rationale}\n"
        f"gap={result.gap:.2f} (threshold={result.threshold:.2f}), "
        f"judgment_gap={result.judgment_gap}, "
        f"variance_warning={result.variance_warning}"
    )

    # SC-2: gap must meet the hard-coded 2.0 threshold.
    assert result.gap >= result.threshold, (
        f"Gap {result.gap:.2f} below threshold {result.threshold:.2f} — "
        f"judge is not discriminating output_a from output_b. "
        f"See results/pre_loop_test.json for per-item scores."
    )

    # SC-3: judgment-category signal must be positive (thesis-critical).
    assert result.judgment_gap > 0, (
        f"judgment_gap={result.judgment_gap} — judge did not give output_a "
        f"a positive edge on judgment items specifically. The total-score "
        f"gap may be coming entirely from extraction wins, which does not "
        f"validate the thesis. Investigate playbook specificity."
    )

    # SC-1: artifact written in the canonical location.
    assert _RESULTS_FILE.exists(), (
        f"Expected {_RESULTS_FILE} to exist after run_pre_loop_test() — "
        f"check run_pre_loop_test's file-write path and results/ mkdir."
    )
```

### Skeleton 4: Unit tests file — **NOT CREATED**

Per resolution #8, no `tests/test_pre_loop_unit.py` is created in Phase 3. If the planner overrides this decision, the fixture is available: `tests/conftest.py` exports `fake_client` and `VALID_JUDGE_JSON`, and the tests would monkeypatch `src.pre_loop_test.run_judge` (not the client, because `run_judge` is what this phase consumes, not `chat.completions.create`). But the planner should not override — see resolution #8.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `ExperimentRun.pre_loop_test: dict | None = None` | `PreLoopTestResult | None = None` | Phase 3 (D-02) | Phase 4/5 consumers get type-safe access instead of raw dict lookups. No migration needed — the field is currently None. |
| Pre-loop test output as free-form dict (prd.md §Output Schema sketch shows `"pre_loop_test": { ... }`) | Structured Pydantic model with enforced invariants | Phase 3 (D-01) | JSON schema is now formally defined by `PreLoopTestResult`. Schema is guaranteed to be a strict superset of the loop-iteration schema (embeds `IterationResult` verbatim), satisfying TEST-02. |

**Deprecated/outdated:** None — this is a greenfield addition. The only existing code that touches this area is the `dict | None` field on `ExperimentRun`, which is retyped in place.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `IterationResult._check_totals` (src/models.py:28-52) still correctly fills in `extraction_score`/`judgment_score`/`total_score` when callers pass only `iteration`/`system_prompt`/`agent_output`/`scores`. | Skeleton 2 `_judge_one` | If the validator's defaulting logic changes, `_judge_one` would need to compute totals manually. **VERIFIED by reading src/models.py:28-52 in this research session** — the logic triggers when all three totals equal 0, which is the default case. [VERIFIED: src/models.py lines 28-52] |
| A2 | The `abs(s1 - s2) > 1` variance rule (resolution #3) correctly captures P3's "±1 per-item temperature-0 drift" expected noise without false-flagging legitimate variance. | Resolution #3, Skeleton 1 validator | If real Phase 3 runs show `variance_warning=True` on every invocation even with a passing gate, the rule is too tight and should be loosened to `>= 2` (which is the same as `> 1` for integer scores in 0..2 — but documented differently). Integration test does NOT assert on `variance_warning`, so a wrong rule does not break the gate — it just makes the signal noisier. Revisit in Phase 5. |
| A3 | 2.0 points is the correct threshold for a 0..16 total-score range with 8 items at 0..2 each. | P10 section, D-01 | Too low → false pass (P10 failure mode). Too high → false fail (no real runs). Rationale in the P10 section defends 2.0 specifically. If early runs cluster at 1.5-1.9, the user should discuss loosening; if they cluster at 5+, the threshold is irrelevant. This is the strongest candidate for user confirmation if any Phase 3 run produces a borderline result. |
| A4 | Ollama's `gemma4:26b` (the default model in src/config.py) will actually produce a ≥ 2.0-point gap between the hand-written output_a and output_b. | Integration test `assert result.decision == "go"` | If false, the gate fails on first run — which is exactly what it's supposed to do. But it would mean Phase 1's reference reviews need to be re-authored to be more distinguishable, OR the judge prompt in Phase 2 needs refinement, OR the experiment's thesis is wrong. This is the load-bearing empirical risk of the entire project; the gate is *designed* to make it visible rather than hide it. |
| A5 | Running `run_pre_loop_test()` writes to `results/pre_loop_test.json` at the repo root, not at the CWD of the Python invocation. | Skeleton 2 `_RESULTS_FILE` path | Verified by using `Path(__file__).resolve().parent.parent / "results" / "pre_loop_test.json"` — CWD-independent. The existing `tests/test_smoke_ollama.py` uses the same pattern (`Path(__file__).parent.parent / "data"`). [VERIFIED: tests/test_smoke_ollama.py line 29] |

**Assumptions needing user confirmation before execution:** A3 (threshold) is the only one that could benefit from user acknowledgement, but D-01 already pins it at 2.0, so we treat it as locked. A4 is an empirical risk that only shows up at integration time — no amount of pre-confirmation helps. **Net: no blocking assumptions.**

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 (verified in `pyproject.toml` `[tool.uv] dev-dependencies`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, `markers = ["integration: ..."]` |
| Quick run command | `uv run pytest -q -m "not integration"` (skips Phase 3's one new test) |
| Full suite command | `uv run pytest -q` (runs everything) |
| Integration-only | `uv run pytest -q -m integration tests/test_pre_loop_gate.py` (just Phase 3's test) |

### Phase Requirements → Test Map
| Req / SC | Behaviour | Test Type | Automated Command | File Exists? |
|----------|-----------|-----------|-------------------|-------------|
| TEST-01 / SC-1 | Runs output_a.md and output_b.md through run_judge; produces `results/pre_loop_test.json` | integration (live) | `uv run pytest -q -m integration tests/test_pre_loop_gate.py::test_pre_loop_gate_passes` | ❌ Phase 3 creates |
| TEST-02 / SC-1 | Results logged in same JSON schema as loop iterations (embeds 4 `IterationResult`s) | integration (live) — asserts `_RESULTS_FILE.exists()` after run | same as above | ❌ Phase 3 creates |
| SC-2 | good review ≥ 2.0 pts higher on average across 8 items | integration (live) — asserts `result.gap >= result.threshold` | same as above | ❌ Phase 3 creates |
| SC-3 | good review outscores flawed on judgment items specifically | integration (live) — asserts `result.judgment_gap > 0` | same as above | ❌ Phase 3 creates |
| SC-4 | go/no-go decision documented | integration (live) — asserts `result.decision == "go"`, banner printed via `_print_banner` | same as above | ❌ Phase 3 creates |
| (sentinel path / D-06) | Judge sentinel failure produces no-go without raising | manual — intentionally hard to trigger against a working model; covered by code review + Phase 2's own sentinel tests (`tests/test_judge.py::test_graceful_failure_on_retry_exhaustion`) | — | ✓ Phase 2 already has `test_graceful_failure_on_retry_exhaustion` |

### Sampling Rate
- **Per task commit:** `uv run pytest -q -m "not integration"` — runs the Phase 2 unit suite (21 tests) in <1s. Phase 3 adds 0 unit tests per resolution #8, so this command's result is unchanged. Use during implementation to catch regressions in `src/models.py` (the `PreLoopTestResult` addition must not break existing `IterationResult` / `ExperimentRun` behaviour).
- **Per wave merge:** same quick command + one integration invocation: `uv run pytest -q -m integration tests/test_pre_loop_gate.py`. This is the actual phase gate.
- **Phase gate:** full suite green (`uv run pytest -q`) before `/gsd-verify-work`. The integration test run should be captured to `/tmp/phase3-*.log` following the Phase 2 convention, so the verifier can cite evidence without re-running 2+ minutes of live calls.

### Wave 0 Gaps

**None.** Phase 2 Wave 0 already installed pytest, registered the `integration` marker in `pyproject.toml`, created `tests/conftest.py` with the autouse `_reset_llm_singleton` fixture and `FakeClient`/`VALID_JUDGE_JSON` helpers, and established the `tests/test_smoke_ollama.py` integration-test pattern. Phase 3 reuses all of this infrastructure and adds exactly two new things:

1. `src/models.py` — new `PreLoopTestResult` class + `ExperimentRun.pre_loop_test` retype (no test file changes).
2. `tests/test_pre_loop_gate.py` — one new file, one new test, ~25 lines.

No `conftest.py` changes. No pyproject changes. No new dependencies. **Wave 0 is empty for Phase 3.**

### Test-Evidence Capture Convention

Mirror Phase 2's `/tmp/phase2-04-integration.log` capture pattern:
```
MODEL=gemma4:26b uv run pytest -q -m integration tests/test_pre_loop_gate.py 2>&1 | tee /tmp/phase3-integration.log
```
Commit the log hash (not the log itself) to the phase summary. The verifier reads the log to confirm `1 passed` and verifies `results/pre_loop_test.json` matches.

## Security Domain

> `security_enforcement` is not explicitly set in `.planning/config.json`, which per protocol means "enabled". This is a local-only test harness with no new network surface beyond what Phase 2 already established, so the threat surface is minimal. ASVS categories that apply:

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth boundary crossed by this phase. Ollama `api_key="ollama"` is a client-library placeholder, not a real credential. |
| V3 Session Management | no | No sessions. Stateless script invocation. |
| V4 Access Control | no | No access control surface. `results/` is already gitignored and lives locally. |
| V5 Input Validation | yes | `PreLoopTestResult` has a `@model_validator` that enforces the "exactly 2 runs per output" invariant and the sentinel contract. Bad inputs cannot persist to JSON. |
| V6 Cryptography | no | No new crypto. Files are plain JSON / markdown. |

### Known Threat Patterns for this phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious NDA content in `data/nda.md` reaching the judge via `run_pre_loop_test` | Tampering | Inherited from Phase 2 threat model T-02-J01: judge has no tool access, Pydantic-validated output, worst case is biased scoring. Phase 3 inherits this — no new surface. |
| Rogue fixture swap (`data/output_a.md` replaced with a flawed review and vice versa) | Tampering | File integrity is git's job, not Phase 3's. A swap would surface immediately as a failing gate. |
| Stale `results/pre_loop_test.json` from an unrelated run misleading a reader | Repudiation | Mitigated by `timestamp` field in `PreLoopTestResult`. Every run overwrites with a fresh ISO-8601 UTC string. A reader checking the timestamp field can verify freshness. |
| Secrets leaking into `results/pre_loop_test.json` via `agent_output` (D-04 stores full file contents) | Information disclosure | `data/output_a.md` and `data/output_b.md` are hand-written reference reviews with no secret material. `data/nda.md` is synthetic. `results/` is gitignored. No secret has ever touched this path. |
| Log spam from `_print_banner` in a CI context leaking the rationale string | Information disclosure | Rationale strings are bounded-length (Case 1-3 templates in resolution #4) and contain only score integers, not fixture contents. The 140-char banner truncation is an extra hedge. |
| Writing outside `results/` because of path manipulation | Tampering | `_RESULTS_FILE` is constructed from `Path(__file__).resolve().parent.parent / "results" / "pre_loop_test.json"` — CWD-independent, no user input, no traversal surface. |

**Net:** Phase 3 introduces no new security-relevant surface. All mitigations are inherited from Phase 2 (`run_judge` contract, gitignored results, local-only operation).

## Open Questions (RESOLVED)

This is the Dimension 11 gate: every open question from the discretion list has a concrete recommendation. Marking them RESOLVED upfront so the code reviewer does not flag them as unresolved ambiguity during Phase 3 review.

1. **`PreLoopTestResult` validator placement** — **RESOLVED:** `@model_validator(mode="after")` on the model itself. Mirrors existing `IterationResult._check_totals`. See Resolution #1.

2. **Exact `passed` computation rule** — **RESOLVED:** `passed = (gap >= threshold) AND (judgment_gap > 0)`, enforced inside the same validator. Sentinel path (D-06) short-circuits to `passed=False`. See Resolution #2.

3. **Variance check algorithm details (missing-item handling)** — **RESOLVED:** Per-item `abs(s1 - s2) > 1` flags variance; missing item in either run also flags variance (strict interpretation — missing item is a larger instability signal than a score flip). Variance never fails the gate. See Resolution #3.

4. **Rationale string template** — **RESOLVED:** Three hand-written f-string templates (Case 1: go, Case 2: no-go non-sentinel, Case 3: sentinel), computed in `_build_rationale` inside `run_pre_loop_test`. See Resolution #4 + Skeleton 2.

5. **Banner format** — **RESOLVED:** Plain-ASCII, 43-char width, `=` separators, no Unicode, no colour. Two variants (normal + error). See Resolution #5 + Skeleton 2.

6. **Where to compute `gap` and `judgment_gap`** — **RESOLVED:** Inside the `@model_validator(mode="after")`. `run_pre_loop_test` never does arithmetic. See Resolution #6.

7. **Test isolation for the pytest integration wrapper** — **RESOLVED:** Accept overwrites; do not add cleanup. `results/pre_loop_test.json` is gitignored, is a single-latest-run artifact by design, and a temp-dir fixture would mask real behaviour. Document in test docstring. See Resolution #7.

8. **Whether to add fast FakeClient unit tests for aggregation math** — **RESOLVED:** Skip. Integration test covers the same validator code path with real data; aggregation is 2 lines of arithmetic; unit tests would duplicate logic they're testing. 0 unit tests, 1 integration test. See Resolution #8.

**Net: 8/8 discretion items resolved with concrete recommendations. Planner can proceed without returning to discuss-phase.**

## Sources

### Primary (HIGH confidence — verified in this session)
- `src/models.py` lines 1-70 — `IterationResult._check_totals` pattern, `compute_category_scores`, `ExperimentRun` schema [VERIFIED]
- `src/judge.py` lines 125-210 — `run_judge` sentinel return contract, retry accounting [VERIFIED]
- `src/config.py` lines 1-44 — `config.model`, `config.temperature`, `config.num_ctx` attributes [VERIFIED]
- `src/llm.py` lines 1-23 — `get_client()` factory for cross-reference only (Phase 3 does not call directly) [VERIFIED]
- `src/agent.py` lines 1-65 — convention reference for module header style and `ITERATION_ZERO_SYSTEM_PROMPT` (Phase 3 does NOT import this per D-03) [VERIFIED]
- `tests/conftest.py` lines 1-115 — `fake_client`, `VALID_JUDGE_JSON`, autouse `_reset_llm_singleton` [VERIFIED]
- `tests/test_smoke_ollama.py` lines 1-88 — integration marker pattern, `_load` helper, CWD-independent path resolution [VERIFIED]
- `data/output_a.md`, `data/output_b.md`, `data/rubric.json` — fixture content; confirmed output_a is substantively stronger on judgment items (sees market-norm context, clause-placement anomaly, functionally-unusable exception) while output_b is factual-only [VERIFIED]
- `pyproject.toml` — `[tool.pytest.ini_options]` registers `integration` marker; `[tool.uv] dev-dependencies` lists `pytest>=8.0` [VERIFIED]
- `.gitignore` — `results/*` already present [VERIFIED]
- `.planning/config.json` — `workflow.nyquist_validation: true`, `security_enforcement` absent (= enabled) [VERIFIED]
- `.planning/phases/03-pre-loop-validation-gate/03-CONTEXT.md` — D-01..D-11 locked decisions [VERIFIED]
- `.planning/phases/02-agent-and-judge/02-VERIFICATION.md` — Phase 2 5/5 SC met, live evidence in `/tmp/phase2-04-integration.log` [VERIFIED]
- `.planning/REQUIREMENTS.md` — TEST-01, TEST-02 [VERIFIED]
- `.planning/ROADMAP.md` — Phase 3 SC-1..SC-4 [VERIFIED]
- `.planning/research/PITFALLS.md` — P1, P3, P10 [VERIFIED]
- `.planning/research/STACK.md` — Pydantic v2 patterns, "what not to use" table [VERIFIED]
- `prd.md` lines 162-166, 249-257, 291-296 — PRD only sketches `"pre_loop_test": { ... }` as a placeholder; D-01..D-04 is the authoritative shape [VERIFIED: no schema conflict]

### Secondary (MEDIUM confidence)
- None needed — Phase 3 is a thin orchestration layer and every technical claim is verifiable from in-repo sources.

### Tertiary (LOW confidence / ASSUMED)
- P3 RMS drift estimate `√8 ≈ 2.8` in the P10 section — informal heuristic based on random-walk argument, not a measured property of Ollama. [ASSUMED — does not affect plan correctness; the 2.0 threshold is defended by multiple independent arguments in the P10 section.]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every dependency is already installed and verified by Phase 2 live evidence.
- Architecture patterns: HIGH — two of the four patterns (`@model_validator`, `integration` marker) are literally copied from existing code in the same repo.
- Code skeletons: HIGH — cross-checked against `src/models.py`, `src/judge.py`, `src/config.py`, `tests/test_smoke_ollama.py`, `tests/conftest.py` in this session.
- Pitfalls: HIGH — P1, P3, P10 are all concrete file-level mitigations with explicit enforcement sites.
- Validation architecture: HIGH — reuses Phase 2 Wave 0 infrastructure 1:1; no gaps.
- Security: HIGH — no new surface beyond Phase 2.

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (30 days — stack and data are stable, only the live Ollama model behaviour could drift)
