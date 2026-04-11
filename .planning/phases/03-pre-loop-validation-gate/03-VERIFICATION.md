---
phase: 3
slug: pre-loop-validation-gate
verifier: gsd-verifier
date: 2026-04-11
status: passed
criteria_passed: 4/4
score: 5/5 must-haves verified
---

# Phase 3 Verification — Pre-Loop Validation Gate

## Goal Achievement

The ROADMAP goal for Phase 3 is "The judge demonstrably distinguishes the good review from the flawed review, confirming the experiment is worth running." Against live `gemma4:26b` (temperature 0.0, num_ctx 16384) the judge gave `output_a` a total of 16 and `output_b` a total of 11, producing a `gap` of 5.0 (2.5× the 2.0 threshold) with the entire delta coming from judgment items (`judgment_gap = 5`, extraction tied 8–8). The gate's `decision` field in `results/pre_loop_test.json` reads `"go"`, the rationale is self-explanatory, and all supporting code, schema, and integration test exist and pass. Phase 3's narrowest-of-phases scope was met in full: one plan, three tasks, one integration test, and a live artifact that structurally and evidentially confirms every success criterion.

## Success Criteria

### SC-1: `pre_loop_test.py` runs both outputs through `run_judge()` and writes `results/pre_loop_test.json` in the same schema as loop iteration results

- **Status: PASS**
- **Implementing code:**
  - `src/pre_loop_test.py:167-174` — `run_pre_loop_test` builds two lists of exactly two `IterationResult` entries via `_judge_one` (4 total `run_judge` calls)
  - `src/pre_loop_test.py:70` — `run_judge(nda, agent_output, rubric, playbook)` matches the Phase 2 contract
  - `src/pre_loop_test.py:208` — `_RESULTS_FILE.write_text(result.model_dump_json(indent=2))` writes the artifact
  - `src/models.py:73-168` — `PreLoopTestResult` holds `output_a_runs: list[IterationResult]` and `output_b_runs: list[IterationResult]`, guaranteed by `_compute_gate` to be exactly 2 entries each; each entry is a full `IterationResult` (same schema the loop iterations will use)
- **Test evidence:** `tests/test_pre_loop_gate.py:67-70` asserts `_RESULTS_FILE.exists()` after `run_pre_loop_test()` returns
- **Live evidence:** `/Users/houfu/Projects/judge-is-the-ceiling/results/pre_loop_test.json` parses as a valid `PreLoopTestResult`; top-level keys include `output_a_runs`, `output_b_runs`, `threshold`, `rationale`, `model`, `temperature`, `num_ctx`, `timestamp`, `gap`, `judgment_gap`, `passed`, `decision`, `variance_warning`. `output_a_runs` has 2 entries with `iteration=1,2`; `output_b_runs` has 2 entries with `iteration=1,2`. Each run carries the full `IterationResult` shape (`iteration`, `system_prompt`, `agent_output`, `scores`, `total_score`, `extraction_score`, `judgment_score`).
- **Verdict:** SC-1 met. The artifact exists, parses, contains exactly 2 `IterationResult` entries per output, and the schema is the same one the loop will use (same `IterationResult` class — not a parallel type).

### SC-2: Good review scores at least 2.0 points higher than the flawed review on average

- **Status: PASS**
- **Implementing code:**
  - `src/models.py:134` — `gap = float(a1.total_score - b1.total_score)` inside `_compute_gate`
  - `src/models.py:136` — `passed = (gap >= self.threshold) and (judgment_gap > 0)`
  - `src/models.py:98` — `threshold: float = 2.0` hard-coded per P10
- **Test evidence:** `tests/test_pre_loop_gate.py:52-56` asserts `result.gap >= result.threshold`
- **Live evidence:** `results/pre_loop_test.json` shows `"gap": 5.0`, `"threshold": 2.0`. Per-run totals (computed from the per-item `scores` arrays): `output_a` = 16/16, `output_b` = 11/11. Average totals are 16.0 vs 11.0, giving an average gap of 5.0. Run-1 gap (used by the gate) and average gap are identical here because run 1 and run 2 are bit-for-bit identical.
- **Verdict:** SC-2 met with 2.5× headroom. The criterion text says "at least 2.0 points higher than the flawed review on average across all 8 rubric items" — averaging across runs gives 5.0 points; per-run run-1 also gives 5.0 points; either interpretation clears the bar.

### SC-3: Score breakdown shows good review outscoring flawed review on judgment items specifically

- **Status: PASS**
- **Implementing code:**
  - `src/models.py:135` — `judgment_gap = a1.judgment_score - b1.judgment_score`
  - `src/models.py:136` — gate requires `judgment_gap > 0` alongside the total-gap check (decision flips to no-go if judgment_gap ≤ 0 even if total gap is ≥ 2.0)
  - `src/models.py:66-70` — `compute_category_scores` splits scores into extraction and judgment via `item_type`
- **Test evidence:** `tests/test_pre_loop_gate.py:59-64` asserts `result.judgment_gap > 0` as a separate assertion (ordered after gap so the failure message is diagnostic)
- **Live evidence:** `results/pre_loop_test.json` shows `"judgment_gap": 5`. Per-run judgment scores: `output_a` = 8/8, `output_b` = 3/3. Extraction scores are tied 8/8 — the entire total-score gap lives in the judgment category. This is the thesis-critical signal the roadmap demanded: the judge is discriminating on judgment items, not riding an extraction win.
- **Verdict:** SC-3 met. The judgment-category field is both present in the artifact and strongly positive (+5), and the assertion that enforces it is the third of four in the integration test.

### SC-4: Go/no-go decision is documented before the loop is built

- **Status: PASS**
- **Implementing code:**
  - `src/models.py:108` — `decision: Literal["go", "no-go"] = "no-go"` field on `PreLoopTestResult`
  - `src/models.py:137` — `decision = "go" if passed else "no-go"` computed by the validator
  - `src/pre_loop_test.py:221-290` — `_print_banner` prints an ASCII banner including `Decision:    GO/NO-GO` and a 140-char rationale snippet
  - `src/pre_loop_test.py:293-299` — `__main__` block calls `run_pre_loop_test()` then `_print_banner(_result)`, so `uv run python src/pre_loop_test.py` documents the decision to stdout
  - `src/pre_loop_test.py:85-131` — `_build_rationale` produces a go/no-go/sentinel-distinct natural-language rationale string stored on the artifact
- **Test evidence:** `tests/test_pre_loop_gate.py:44-49` asserts `result.decision == "go"` as the first (most diagnostic) assertion
- **Live evidence:** `results/pre_loop_test.json` contains `"decision": "go"`, `"passed": true`, and `"rationale": "output_a total_score=16 (extraction=8, judgment=8) outscored output_b total_score=11 (extraction=8, judgment=3) by gap=5.00 against threshold=2.00; judgment_gap=5 is positive. Gate passes — loop is worth building."` The rationale branch taken matches `_build_rationale`'s go-branch format (`src/pre_loop_test.py:111-120`), confirming the happy path executed end-to-end. `/tmp/phase3-integration.log` is only 2 lines (`.\n1 passed in 210.43s`) because pytest captures stdout by default — the banner printed at import time for the `__main__` block is not visible there, but SC-4 is satisfied by the JSON-documented decision (the roadmap phrasing is "in `results/pre_loop_test.json` OR console output").
- **Verdict:** SC-4 met. The go/no-go decision is structurally persisted in the JSON artifact, backed by a rationale string, and the `_print_banner` + `__main__` path is wired so direct CLI invocation also surfaces it. The SUMMARY's manual-only verification (Plan 03-VALIDATION.md) confirms the banner renders correctly when invoked interactively.

## Observable Truths (from PLAN must-haves)

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | `uv run python src/pre_loop_test.py` judges A+B through `run_judge` twice each and writes `results/pre_loop_test.json` in the loop iteration schema | VERIFIED | `run_pre_loop_test` at `src/pre_loop_test.py:134-218`; 4 `_judge_one` calls produce 4 `IterationResult`s; artifact exists on disk with 4 entries |
| 2 | `results/pre_loop_test.json` contains a `PreLoopTestResult` with `gap >= 2.0` between the good review and the flawed review on run 1 total_score | VERIFIED | `"gap": 5.0`, `"threshold": 2.0`; run 1 totals 16 vs 11 |
| 3 | `results/pre_loop_test.json` shows `judgment_gap > 0` — output_a outscores output_b on judgment items specifically | VERIFIED | `"judgment_gap": 5`; run-1 judgment 8 vs 3 |
| 4 | A go/no-go decision is observable in `results/pre_loop_test.json` (`decision` field + `rationale`) AND printed to stdout via a console banner | VERIFIED | `"decision": "go"`, rationale string intact; `_print_banner` + `__main__` wired at `src/pre_loop_test.py:293-299` |
| 5 | Existing Phase 1+2 unit tests still pass after `PreLoopTestResult` is added and `ExperimentRun.pre_loop_test` is retyped | VERIFIED | `uv run pytest -q -m "not integration"` → `21 passed, 3 deselected in 0.16s` (re-run during verification) |

**Score:** 5/5 truths verified.

## Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/models.py` | Contains `class PreLoopTestResult` with `_compute_gate` validator; `ExperimentRun.pre_loop_test` retyped to `PreLoopTestResult \| None` | VERIFIED | 171 lines; `PreLoopTestResult` at lines 73-168; `ExperimentRun.model_rebuild()` at 171; forward-ref retype at line 62 |
| `src/pre_loop_test.py` | `run_pre_loop_test`, `_build_rationale`, `_print_banner`, `__main__` block; reads fixtures, calls `run_judge` 4×, writes JSON | VERIFIED | 299 lines (plan min_lines 150); all required symbols present; `run_judge(nda, agent_output, rubric, playbook)` at line 70; `_RESULTS_FILE.write_text` at line 208 |
| `tests/test_pre_loop_gate.py` | `@pytest.mark.integration`; `test_pre_loop_gate_passes` with 4 ordered assertions | VERIFIED | 70 lines; `pytestmark = pytest.mark.integration` at line 32; 4 asserts at lines 44, 52, 59, 67 (decision, gap, judgment_gap, file existence) |
| `results/pre_loop_test.json` | Contains `"decision": "go"` + 4 IterationResult entries + all derived fields | VERIFIED | File exists, parses, `decision=go`, `gap=5.0`, `judgment_gap=5`, `variance_warning=False`, `model=gemma4:26b`, `num_ctx=16384`, `timestamp=2026-04-11T12:28:09.231205+00:00` |

## Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `src/pre_loop_test.py` | `src.judge.run_judge` | Direct import + 4 calls (2 outputs × 2 runs) | WIRED | `from src.judge import run_judge` at line 38; 1 callsite inside `_judge_one` at line 70 invoked 4 times via `_judge_one` calls at lines 168-173 |
| `src/pre_loop_test.py` | `src.models.PreLoopTestResult` | Model instantiation with 4 IterationResults; validator fills derived fields | WIRED | `from src.models import IterationResult, PreLoopTestResult` at line 39; two instantiations (probe at 180, final at 198) feeding `output_a_runs`/`output_b_runs` |
| `tests/test_pre_loop_gate.py` | `src.pre_loop_test.run_pre_loop_test` | Import inside test function + single call | WIRED | Import at line 39; call at line 41; return value used in 4 subsequent asserts |
| `PreLoopTestResult` validator | `IterationResult.total_score / .judgment_score` | Arithmetic inside `@model_validator(mode="after")` | WIRED | `a1.total_score - b1.total_score` at `src/models.py:134`; `a1.judgment_score - b1.judgment_score` at line 135 |

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `results/pre_loop_test.json` | `output_a_runs[i].scores` | `run_judge(...)` on live Ollama → `_judge_one` → `IterationResult(scores=result.scores)` | Yes — 8 RubricScore entries per run, all `score` values in `{0,1,2}`, evidence/reasoning/feedback strings all non-empty | FLOWING |
| `results/pre_loop_test.json` | `output_b_runs[i].scores` | Same path with `data/output_b.md` as `agent_output` | Yes — 8 RubricScore entries per run, different values from output_a (extraction tied, judgment lower) | FLOWING |
| `results/pre_loop_test.json` | `gap`, `judgment_gap`, `passed`, `decision`, `variance_warning` | Computed in `PreLoopTestResult._compute_gate` from the above `scores` arrays via `IterationResult._check_totals` | Yes — values are consistent with hand-computed aggregates (gap=5.0, judgment_gap=5, variance_warning=False) | FLOWING |
| `rationale` field | Computed by `_build_rationale` on the go-branch | `src/pre_loop_test.py:111-120` — uses validator-computed gap/judgment_gap | Yes — rationale text contains the actual numeric values, not template placeholders | FLOWING |

No HOLLOW_PROP or STATIC_RETURN patterns detected. The entire pipeline from `run_judge` → `IterationResult` → `PreLoopTestResult` validator → artifact is live-data-backed.

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Non-integration pytest suite passes (no regressions from adding `PreLoopTestResult`) | `uv run pytest -q -m "not integration"` | `21 passed, 3 deselected in 0.16s` | PASS |
| Artifact exists and parses as JSON | `cat results/pre_loop_test.json \| python -m json.tool` | Parses; 61.8 KB | PASS |
| Artifact contains decision=go | `python3 -c "import json; d=json.load(open('results/pre_loop_test.json')); print(d['decision'])"` | `go` | PASS |
| Artifact contains gap=5.0 | Same via `d['gap']` | `5.0` | PASS |
| Artifact contains judgment_gap=5 | Same via `d['judgment_gap']` | `5` | PASS |
| 2 runs per output | `len(d['output_a_runs'])`, `len(d['output_b_runs'])` | `2, 2` | PASS |

Live integration test (`tests/test_pre_loop_gate.py`) not re-run during verification per instructions — trusting the `/tmp/phase3-integration.log` `1 passed in 210.43s` result.

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| TEST-01 | `03-01-PLAN.md` frontmatter | "Run Output A and Output B through judge with same rubric and playbook" | SATISFIED | `run_pre_loop_test` calls `run_judge` with the same `rubric` and `playbook` strings for both outputs (`src/pre_loop_test.py:163-174`); live artifact proves it executed. Marked `[x]` at `.planning/REQUIREMENTS.md:41` and `| Complete |` at line 112. |
| TEST-02 | `03-01-PLAN.md` frontmatter | "Results logged in same JSON schema as loop iterations for direct comparison" | SATISFIED | `PreLoopTestResult` uses the same `IterationResult` class the main loop will use (not a parallel schema); `src/models.py:96-97` declares `output_a_runs: list[IterationResult]`. Marked `[x]` at `.planning/REQUIREMENTS.md:42` and `| Complete |` at line 113. |

No orphaned requirements: `grep "Phase 3" .planning/REQUIREMENTS.md` returns only TEST-01 and TEST-02, both present in the plan's `requirements:` field.

## Anti-Patterns Found

None. Scanned `src/pre_loop_test.py`, `src/models.py`, and `tests/test_pre_loop_gate.py` for TODO/FIXME/placeholder/empty-return/hardcoded-empty patterns. Findings:

- `src/models.py:42-51` — consistency check in `IterationResult._check_totals` raises `ValueError` on inconsistency (defensive, not a stub)
- `src/models.py:124-131` — sentinel path in `_compute_gate` deliberately returns zero values; this is the documented D-06 "judge retry exhausted → force no-go" branch, not a stub
- `src/pre_loop_test.py:5,8,14,44,49,50,51` — sentinel strings and comments referencing "fixture" are intentional placeholders for the `system_prompt` slot of `IterationResult` (there's no real system prompt for a pre-written fixture); flagged in plan as D-03
- No `TODO`, `FIXME`, `XXX`, `HACK`, `PLACEHOLDER`, `not yet implemented`, `coming soon`, or `return null` markers found

## Human Verification Required

None. Per `03-VALIDATION.md`, the two manual-only items ("rationale string readable" and "banner legible when running the CLI directly") were both executed and documented as PASS in the SUMMARY (section "Manual-Only Verification Results"). The integration test provides automated coverage for the rest of the gate. There is no UI, no real-time behavior, no external service integration beyond Ollama (which is covered by the live integration run), and no visual rendering that requires human judgment beyond what has already been checked.

## P1 Falsification Analysis

**The thesis-critical claim of Phase 3 is that the judge's judgment-item scoring actually discriminates, not just its extraction scoring.** The live artifact is the cleanest possible outcome for this claim:

| Category | output_a (good) | output_b (flawed) | Delta |
| -------- | --------------- | ----------------- | ----- |
| Extraction total | 8 | 8 | **0** |
| Judgment total | 8 | 3 | **+5** |
| Overall total | 16 | 11 | **+5** |

**Interpretation:** Extraction scores are tied at the ceiling (8/8) for both reviews. The entire 5-point total-score gap lives in the judgment category. This is the best-case P1 falsification signal:

1. **The judge is not grading style.** Both reviews have similar structural shape; the extraction scores prove the judge sees both as covering the eight extraction items correctly. If the judge were riding style or length, extraction scores would diverge too.
2. **The judge is grading substance on judgment items specifically.** A 5/8 gap on judgment (62.5% of the judgment ceiling) when extraction is tied means the playbook's deliberately vague judgment guidance produces exactly the gap the thesis predicted — careful judgment > shallow judgment, with no confound from extraction quality.
3. **Phase 4 and Phase 5 are worth building.** The loop's optimiser has a real signal to chase: the agent can get to extraction=8 without breaking a sweat (Phase 5 will see this converge immediately), but pushing judgment_score from its starting point toward 8 is where the optimisation loop earns its keep. If the judge could not distinguish judgment quality, the loop would be optimising noise. It can, so the loop is meaningful.

**Bonus signal — extraction ceiling already hit.** Both reviews score 8/8 on extraction, which means Phase 5's plateau detection has a known-good upper bound for the extraction category from day one. Any Phase 5 iteration whose agent drops below 8 on extraction is a regression, not a plateau; any iteration that stays at 8 is at the ceiling. This gives the Phase 5 plateau detector a clean calibration point.

**This is the cleanest possible P1 falsification outcome:** identical extraction, divergent judgment. The judge works on the hard dimension. Proceed to Phase 4 with confidence.

## P3 Variance Analysis

**Temperature=0 is not guaranteed deterministic in Ollama.** Phase 3 ran each output twice to check for drift.

Run-by-run per-category scores:

| Run | output_a total | output_a ext | output_a judge | output_b total | output_b ext | output_b judge |
| --- | -------------- | ------------ | -------------- | -------------- | ------------ | -------------- |
| 1 | 16 | 8 | 8 | 11 | 8 | 3 |
| 2 | 16 | 8 | 8 | 11 | 8 | 3 |

**Findings:**

- Run 1 and Run 2 are bit-for-bit identical at the category level for both outputs.
- The per-item score variance check in `PreLoopTestResult._compute_gate` (src/models.py:143-161) scans all 8 rubric items across both runs and would flip `variance_warning=True` on any per-item diff greater than 1 or any missing item. The artifact shows `"variance_warning": false`, meaning per-item scores are also stable (not just the aggregates).
- **P3's "temperature=0 is not fully deterministic" concern did not manifest on this specific hardware/model combination (gemma4:26b on the local Ollama instance).** This is a positive data point for reproducibility of the Phase 5 loop runs: the judge component is behaving deterministically on this setup.
- **Caveat:** This is a two-sample check on a single model at a single point in time. It sets a high baseline but does not prove the judge will stay deterministic across Phase 5's 20+ iterations or across model upgrades. The variance tracking is now baked into `PreLoopTestResult.variance_warning`, and Phase 5's monitoring should continue to watch this field on re-runs.

**Conclusion:** P3 hedge validated but not burned — `variance_warning=False` today is a welcome surprise, not a guarantee for tomorrow. The infrastructure for catching drift exists; it just did not fire.

## Requirement Marks

- **TEST-01** in `.planning/REQUIREMENTS.md:41` → `[x] **TEST-01**: Run Output A and Output B through judge with same rubric and playbook`; also `| TEST-01 | Phase 3 | Complete |` at line 112 — **PASS**
- **TEST-02** in `.planning/REQUIREMENTS.md:42` → `[x] **TEST-02**: Results logged in same JSON schema as loop iterations for direct comparison`; also `| TEST-02 | Phase 3 | Complete |` at line 113 — **PASS**

## Gaps

None. All four success criteria, all five PLAN must-haves truths, all four required artifacts, all four key links, and both requirements are verified. No anti-patterns, no stubs, no orphaned code, no human verification pending.

## Recommendation

**Advance to Phase 4 (Optimiser).** The pre-loop validation gate has passed its live integration run with an unambiguous `decision=go`, a total-score gap of 5.0 that is 2.5× the hard-coded threshold, and — most importantly — a `judgment_gap` of 5 driven entirely by judgment-category discrimination (extraction tied 8–8). This is the cleanest P1 falsification outcome the thesis could hope for: the judge demonstrably distinguishes substantive judgment quality when extraction is held equal. Phase 4's optimiser has a real signal to chase.

The reusable infrastructure produced in Phase 3 (probe-construction pattern for Pydantic validators, `__package__`-guarded sys.path shim for `__main__` entry points, `jitc.preloop` logger convention, `PreLoopTestResult` type on `ExperimentRun`) is ready for Phase 4 and Phase 5 consumption.

---

*Verified: 2026-04-11*
*Verifier: Claude (gsd-verifier)*
