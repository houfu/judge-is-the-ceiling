# Phase 3: Pre-Loop Validation Gate - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `src/pre_loop_test.py` — a non-negotiable validation gate that decides whether the main optimisation loop (Phases 4-5) is worth building. It runs the Phase 1 reference reviews (`data/output_a.md` — correct, `data/output_b.md` — plausible-but-flawed) through `run_judge()` from Phase 2 against the same rubric and playbook, measures the score gap, and emits a `go` or `no-go` verdict.

**In scope:** The library function, the `__main__` script wrapper (PRD compatibility), the pytest integration wrapper, the new `PreLoopTestResult` Pydantic model, and the `ExperimentRun.pre_loop_test` field type change.

**Out of scope:** The optimiser (Phase 4), the main loop (Phase 5), any score-comparison visualisation, any cross-model comparison, any deliberate-failure-mode sanity tests.

</domain>

<decisions>
## Implementation Decisions

### Schema (`src/models.py` extension)

- **D-01:** Add `PreLoopTestResult` as a Pydantic model in `src/models.py`. Fields:
  - `output_a_runs: list[IterationResult]` — exactly 2 entries (run 1, run 2) for `data/output_a.md`
  - `output_b_runs: list[IterationResult]` — exactly 2 entries for `data/output_b.md`
  - `gap: float` — `output_a_runs[0].total_score - output_b_runs[0].total_score` (computed on run 1 only per D-07)
  - `judgment_gap: int` — `output_a_runs[0].judgment_score - output_b_runs[0].judgment_score` (run 1)
  - `threshold: float = 2.0` — the fixed gate threshold
  - `passed: bool` — `gap >= threshold` AND `judgment_gap > 0` (per ROADMAP SC-2 + SC-3)
  - `decision: Literal["go", "no-go"]`
  - `rationale: str` — free-form, hand-written in code at test-authoring time (NOT auto-templated per discussion)
  - `variance_warning: bool` — True if any `RubricScore.score` differs by >1 between run 1 and run 2 for the same output+item_id pair (per D-07 aggregation rule)
  - `model: str` — snapshot of `config.model` at test time (reproducibility)
  - `temperature: float` — snapshot of `config.temperature`
  - `num_ctx: int` — snapshot of `config.num_ctx`
  - `timestamp: str` — ISO-8601 UTC, captured at test start

- **D-02:** Change `ExperimentRun.pre_loop_test: dict | None = None` to `pre_loop_test: PreLoopTestResult | None = None`. Type-safe; Phase 4/5 consumers get IDE completion and Pydantic validation on read.

- **D-03:** In each `IterationResult` entry, `system_prompt` is a sentinel string identifying the fixture: `"<pre-loop fixture: data/output_a.md>"` or `"<pre-loop fixture: data/output_b.md>"`. This makes pre-loop records unambiguously distinguishable from loop iterations when scanning results JSON. Do NOT use `ITERATION_ZERO_SYSTEM_PROMPT` here — it was not actually executed.

- **D-04:** In each `IterationResult` entry, `agent_output` is the full file contents of the corresponding fixture: `Path("data/output_a.md").read_text()`. This makes `results/pre_loop_test.json` self-contained — any future reader can reconstruct exactly what was judged without needing the repo at the right commit. Cost: ~2-4KB per entry; acceptable for a one-shot gate.

### Verdict representation

- **D-05:** The decision is observable in **both** the JSON file AND a stdout console banner. NOT via process exit code. NOT via exception. Rationale: the user chose structured-JSON + console; shell chaining for Phase 5 is a downstream caller's concern, not this phase's.
  - JSON: `PreLoopTestResult.decision`, `.gap`, `.passed`, `.rationale`, `.variance_warning`
  - Console banner: printed after results are written, loud formatted block showing gap / threshold / decision / any variance warning. Example shape:
    ```
    ═══════════════════════════════════════════
      PRE-LOOP VALIDATION GATE
    ═══════════════════════════════════════════
    Model:       gemma4:26b
    output_a:    total=14  ext=8  jud=6
    output_b:    total=6   ext=4  jud=2
    Gap:         8.00  (threshold: 2.00)
    Judgment:    output_a leads by 4
    Variance:    no warning
    Decision:    GO
    ═══════════════════════════════════════════
    ```

- **D-06:** **Hard-fail the gate on judge sentinel failure.** If `run_judge(...)` returns `JudgeResult(scores=[])` (retry exhausted, per JUDG-05) for EITHER output on EITHER run:
  - Still write `results/pre_loop_test.json` with the partial data captured (the failing run becomes an `IterationResult` with `scores=[]` and `total_score=0`)
  - Set `decision="no-go"`, `passed=False`, `variance_warning=False`
  - Set `rationale="judge retry exhausted for <output_name> run <N>; see jitc.judge ERROR logs for raw output"`
  - Print the error banner variant (clearly distinguishable from a normal no-go)
  - Do NOT raise an exception
  - Rationale: if the judge can't even parse its own outputs on a clean test with Phase 1 reference fixtures, the loop is unsafe to build. The sentinel return is the judge telling us something is structurally wrong.

### Run count + aggregation

- **D-07:** **Two runs per output (4 live judge calls total).** Runtime ~2-4 min against gemma4:26b.
  - **Run 1 is authoritative** for the gate computation (`gap`, `judgment_gap`, `decision`, `passed`)
  - **Run 2 is a variance check only.** After both runs complete, compare run 1 and run 2 item-by-item via `item_id`. If ANY same-item score differs by more than 1 point between the two runs, set `variance_warning=True` and print a warning line in the console banner. Do NOT fail the gate on variance alone.
  - Both runs' `IterationResult` objects are stored in the respective `output_{a,b}_runs: list[IterationResult]` list so nothing is lost.

- **D-08:** Reproducibility metadata captured directly in `PreLoopTestResult`:
  - `model` — `config.model` at test start (probably `gemma4:26b`)
  - `temperature` — `config.temperature` (must be 0.0)
  - `num_ctx` — `config.num_ctx` (16384)
  - `timestamp` — ISO-8601 UTC string
  - **NOT captured:** Ollama version. The extra `/api/version` HTTP call was deemed not worth the complexity for this experiment — if drift becomes an issue, it can be added in Phase 5's run metadata envelope.

### Invocation surface

- **D-09:** `src/pre_loop_test.py` exposes a library function `run_pre_loop_test() -> PreLoopTestResult`. The function:
  - Reads `data/nda.md`, `data/output_a.md`, `data/output_b.md`, `data/rubric.json`, `data/playbook.md`
  - Calls `run_judge(nda_text, output_a, rubric, playbook)` twice (run 1 + run 2)
  - Calls `run_judge(nda_text, output_b, rubric, playbook)` twice (run 1 + run 2)
  - Builds 4 `IterationResult` entries, computes `gap`/`judgment_gap`/`variance_warning`/`passed`/`decision`
  - Writes `results/pre_loop_test.json` (the full `PreLoopTestResult` as JSON via `model_dump_json(indent=2)`)
  - Returns the `PreLoopTestResult` instance
  - Ensures `results/` directory exists (`Path("results").mkdir(exist_ok=True)`) — the directory itself is gitignored but must exist at runtime

- **D-10:** Module-level `if __name__ == "__main__":` block at the bottom of `src/pre_loop_test.py` calls `run_pre_loop_test()`, then calls a `_print_banner(result: PreLoopTestResult)` helper to print the console banner to stdout. This makes `uv run python src/pre_loop_test.py` work per the PRD.

- **D-11:** `tests/test_pre_loop_gate.py` with `@pytest.mark.integration` marker wraps the same library function:
  ```python
  import pytest
  pytestmark = pytest.mark.integration
  
  def test_pre_loop_gate_passes():
      from src.pre_loop_test import run_pre_loop_test
      result = run_pre_loop_test()
      assert result.decision == "go", f"Gate failed: {result.rationale}"
  ```
  Matches the Phase 2 pytest integration pattern (`tests/test_smoke_ollama.py`). Runs alongside the existing integration suite with `MODEL=gemma4:26b uv run pytest -q -m integration`.

### Claude's Discretion

The following are deliberately left to the planner/executor:

- **Exact rationale wording.** D-07 says hand-written at test-authoring time. The planner should draft sentences like `"output_a total_score={a_total} with extraction={a_ext} and judgment={a_jud}; output_b total_score={b_total} with extraction={b_ext} and judgment={b_jud}; gap={gap:.2f} meets threshold={threshold}; judgment signal is positive"` but keep them readable.
- **Banner exact formatting.** The sketch in D-05 is indicative; planner decides the exact width, separator chars, colour (if any — probably none for stdout portability).
- **Variance check implementation details.** Whether it lives in `PreLoopTestResult.__init__` via a `@model_validator`, a separate helper function, or inline in `run_pre_loop_test`. Planner's call.
- **Logging shape.** Use stdlib `logging` at `"jitc.preloop"` namespace (matching Phase 2 convention). INFO at start+end, WARNING on variance, ERROR on judge sentinel.
- **Test fixtures vs real data for unit tests.** Since integration testing covers the real round-trip, any unit tests for `run_pre_loop_test` (if the planner wants them) should use `FakeClient` with deterministic VALID_JUDGE_JSON and test the aggregation/gap/variance logic without hitting Ollama. NOT required — the pytest integration wrapper alone is sufficient for SC-4. But if the planner wants fast unit tests for the aggregation math, they should reuse the existing Phase 2 `FakeClient` fixture.
- **Whether to add a `PreLoopTestResult.__str__` method** for pretty-printing. Nice-to-have, not required.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 2 Artifacts (directly consumed)
- `src/judge.py` — `run_judge(nda_text, agent_output, rubric, playbook) -> JudgeResult`. The function this phase calls 4 times.
- `src/models.py` — `JudgeResult`, `RubricScore`, `IterationResult`, `ExperimentRun`, `compute_category_scores()`. `IterationResult` auto-computes totals via `@model_validator`; do NOT duplicate that logic.
- `src/config.py` — `config.model`, `config.temperature`, `config.num_ctx` for metadata snapshot per D-08.
- `.planning/phases/02-agent-and-judge/02-CONTEXT.md` — D-01..D-10 from Phase 2 are still in effect
- `.planning/phases/02-agent-and-judge/02-SUMMARY.md` files for each plan — what was built
- `.planning/phases/02-agent-and-judge/02-VERIFICATION.md` — 5/5 criteria met, live evidence

### Phase 1 Artifacts (static data consumed)
- `data/nda.md` — the synthetic NDA passed as context for both judge calls
- `data/output_a.md` — reference CORRECT review (the "good" side of the gate)
- `data/output_b.md` — plausible-but-flawed review (the "flawed" side of the gate)
- `data/rubric.json` — 8-item rubric; passed as raw text per Phase 2 D-08
- `data/playbook.md` — playbook with precise extraction guidance and deliberately vague judgment guidance

### Research
- `.planning/research/PITFALLS.md` — especially:
  - **P3** (Ollama temperature=0 not deterministic across runs) — the reason we do 2 runs per output (D-07)
  - **P1** (judge grading its own output, self-reference collapse) — the reason this gate exists at all
  - **P10** (pre-loop test not actually diagnostic if gap is small) — justifies the hard 2.0 threshold
- `.planning/research/STACK.md` — Pydantic v2 patterns, retry loop pattern
- `.planning/research/FEATURES.md` — MVP scope

### Project-level
- `.planning/PROJECT.md` — Core value, "Pre-loop gate is non-negotiable" decision logged in STATE.md
- `.planning/REQUIREMENTS.md` — TEST-01, TEST-02 acceptance criteria
- `.planning/ROADMAP.md` Phase 3 section — the 4 success criteria (SC-1..SC-4)
- `prd.md` — The PRD may contain a specific pre_loop_test JSON shape example; if so, reconcile with D-01..D-04 or flag a conflict

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`run_judge`** — already handles retry, fence stripping, num_ctx, graceful failure. Phase 3 just calls it. Do NOT wrap it in additional error handling; rely on the sentinel contract.
- **`IterationResult`** — reuse as the per-run record. Its `@model_validator` auto-computes `total_score`/`extraction_score`/`judgment_score`. Phase 3 just passes `iteration`, `system_prompt`, `agent_output`, `scores` and lets the model fill totals.
- **`compute_category_scores()`** — exported from `src/models.py`. Useful for aggregation if the planner wants to compute category-level breakdowns outside of the model validator.
- **`config.model` / `config.temperature` / `config.num_ctx`** — readable snapshot for the metadata fields in `PreLoopTestResult`.
- **Phase 2 logging convention** — `jitc.agent` and `jitc.judge`. Follow with `jitc.preloop`.
- **Phase 2 pytest integration marker pattern** — `tests/test_smoke_ollama.py` uses `pytestmark = pytest.mark.integration` at module level. Mirror for `tests/test_pre_loop_gate.py`.

### Established Patterns
- **Module-level singletons for shared state** — `src/config.py` ends with `config = Config.from_env()`. Phase 3 does not need a new singleton; just imports `config`.
- **Top-level `__main__` blocks are acceptable for scripts** — `src/pre_loop_test.py` gets one per D-10. No prior Phase 2 module has a `__main__` block, so this is a new pattern but a small one.
- **Pydantic v2 `model_validate_json` / `model_dump_json`** — used throughout Phase 2. Use `model_dump_json(indent=2)` for human-readable results files.

### Integration Points
- **Writes to:** `src/models.py` (add `PreLoopTestResult`, change `ExperimentRun.pre_loop_test` type), `src/pre_loop_test.py` (new), `tests/test_pre_loop_gate.py` (new), `results/pre_loop_test.json` (runtime output — gitignored per Phase 1 SETP-02)
- **Reads from:** `src/judge.py`, `src/config.py`, `data/*.md`, `data/rubric.json`
- **Does NOT touch:** `src/loop.py` (doesn't exist yet), `src/optimiser.py` (Phase 4), `src/agent.py` (not called by pre_loop_test)

</code_context>

<specifics>
## Specific Ideas

- **PreLoopTestResult validator.** A `@model_validator(mode="after")` on `PreLoopTestResult` is the cleanest place to enforce invariants:
  - `len(output_a_runs) == 2` AND `len(output_b_runs) == 2`
  - `decision == "go"` iff `passed == True`
  - `passed == True` iff `gap >= threshold` AND `judgment_gap > 0` (SC-2 + SC-3 combined)
  - If any run has `scores == []`, then `decision == "no-go"` and `passed == False` (sentinel contract)

- **Variance check algorithm.** For each `item_id` in run 1 and run 2 of the same output, compare `score` values. If any differ by more than 1, set `variance_warning=True`. Since scores are `Literal[0,1,2]`, diff > 1 means 0→2 or 2→0 — a meaningful flip.

- **Console banner helper.** Keep `_print_banner(result)` as a module-private function so the library API (`run_pre_loop_test()`) returns only the structured result and the banner is purely a side effect of the `__main__` path. Phase 4/5 importing the library shouldn't see stdout spam.

- **Results file naming.** PRD says `results/pre_loop_test.json`. Do not introduce a timestamp suffix — this is a one-shot gate, not an append-only log. If a second run is needed, it overwrites the first. Phase 5 loop files will use `results/run_001.json` etc. (different naming).

</specifics>

<deferred>
## Deferred Ideas

- **Deliberate failure-mode sanity test.** Swapping outputs (output_a as the "flawed" side) and confirming the gate would fail — discussed but flagged as scope creep. If the real gate emits `no-go` on the first attempt, we can revisit. Not in Phase 3 scope.

- **Unit tests against FakeClient for the aggregation math.** Not required (pytest integration wrapper + live smoke cover SC-1..SC-4). If drift or flakiness becomes a concern in Phase 5 integration testing, add fast FakeClient unit tests then.

- **Multi-model comparison.** Running the gate against 2+ models to see which is most discriminating. Explicitly out of scope per PROJECT.md "Out of Scope" table (Multiple model comparison confounds the experiment variable).

- **Judgment-specific threshold.** SC-3 currently just requires `judgment_gap > 0`. A stricter gate (e.g., `judgment_gap >= 1` or `>= 2`) might be warranted if early runs show the judgment signal is weak. Revisit after first real run.

- **Ollama version capture.** Not in Phase 3 metadata. Can be added to Phase 5's `ExperimentRun` envelope without touching the `PreLoopTestResult` schema.

- **Banner colourisation / terminal width detection.** Plain ASCII only for portability; no `rich`/`colorama` dependencies.

</deferred>

---

*Phase: 03-pre-loop-validation-gate*
*Context gathered: 2026-04-11*
