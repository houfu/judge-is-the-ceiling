# Phase 3: Pre-Loop Validation Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-11
**Phase:** 03-pre-loop-validation-gate
**Areas discussed:** Schema shape, Verdict representation, Run count, Invocation surface

---

## Gray Area Selection

Four gray areas offered; user selected all four.

---

## Schema shape of pre_loop_test.json

### Q1: Shape of `pre_loop_test` inside the JSON?

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated Pydantic model | New `PreLoopTestResult` class in src/models.py; typed fields. | ✓ |
| Two IterationResult entries + free-form dict | Reuse IterationResult twice; decision fields as untyped dict keys. | |
| Full ExperimentRun with pre_loop_test populated, no iterations | Canonical run envelope with iterations=[]. | |

**User's choice:** Dedicated Pydantic model (Recommended)

### Q2: `system_prompt` field for pre-loop IterationResult entries?

| Option | Description | Selected |
|--------|-------------|----------|
| Sentinel string identifying the fixture | `<pre-loop fixture: data/output_a.md>` | ✓ |
| Empty string | `""` | |
| ITERATION_ZERO_SYSTEM_PROMPT value | Use the real Phase 2 constant | |

**User's choice:** Sentinel string identifying the fixture (Recommended)

### Q3: `agent_output` field for pre-loop IterationResult entries?

| Option | Description | Selected |
|--------|-------------|----------|
| Full file contents | Read and embed data/output_{a,b}.md verbatim | ✓ |
| File path reference only | Just the path string | |
| Truncated head + path | Compromise head with path prefix | |

**User's choice:** Full file contents (Recommended)

---

## Go/no-go decision representation

### Q1: Where should the verdict be observable? (multi-select)

| Option | Description | Selected |
|--------|-------------|----------|
| JSON fields (decision + gap + passed) | Structured, machine-readable. | ✓ |
| Process exit code (non-zero on fail) | Enables shell chaining. | |
| Console banner on stdout | Human-readable interactive confirmation. | ✓ |
| Loud failure via exception | Custom PreLoopGateFailed exception. | |

**User's choices:** JSON fields + Console banner
**Notes:** User opted NOT to exit non-zero and NOT to raise an exception. Shell chaining for Phase 5 is a downstream caller's concern. The gate result lives in the JSON + banner; callers decide how to act on it.

### Q2: Judge sentinel failure (`JudgeResult(scores=[])`) handling?

| Option | Description | Selected |
|--------|-------------|----------|
| Hard fail the gate | Write partial results, decision=no-go, exit non-zero, error banner | ✓ |
| Raise exception and don't write results | Python traceback, lose partial capture | |
| Write results and continue | Weakest; breaks gatekeeping purpose | |

**User's choice:** Hard fail the gate (Recommended)

### Q3: Rationale text format?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-generated structured explanation | Template string with all numbers filled in | |
| Free-form string written at test time | Hand-written sentence, more readable | ✓ |
| Only fill rationale on no-go | Asymmetric; empty rationale on go | |

**User's choice:** Free-form string written at test time
**Notes:** Planner/executor will hand-draft rationale wording. Captured in CONTEXT.md "Claude's Discretion" with guidance toward readability + inclusion of key numbers.

---

## Single run vs multi-run (P3 reproducibility)

### Q1: How many runs per output?

| Option | Description | Selected |
|--------|-------------|----------|
| Single run per output | 2 calls total, fastest. Matches PRD literal wording. | |
| Dual run per output | 4 calls total, ~2-4 min; compare for variance. | ✓ |
| Triple run per output with median | 6 calls, most robust, slowest. | |

**User's choice:** Dual run per output
**Notes:** User chose reproducibility evidence over speed. Required a follow-up question on aggregation (see next).

### Q1.1 (Follow-up): Aggregation rule with 2 runs?

| Option | Description | Selected |
|--------|-------------|----------|
| Run 1 official, run 2 is variance check | Gate on run 1; warn if variance > 1, don't fail | ✓ |
| Minimum across runs (conservative) | Take min of run1/run2 per item | |
| Average across runs | Float scores; complicates schema | |
| Fail gate if any item diverges by >1 | Strictest reproducibility requirement | |

**User's choice:** Run 1 official, run 2 is variance check (Recommended)

### Q2: Reproducibility metadata captured?

| Option | Description | Selected |
|--------|-------------|----------|
| Model name + quantisation tag | config.model snapshot | ✓ |
| Ollama version | /api/version endpoint call | |
| Temperature + num_ctx | config.temperature + config.num_ctx snapshot | ✓ |
| Timestamp (ISO-8601) | When the test ran | ✓ |

**User's choices:** Model + temp/num_ctx + timestamp (not Ollama version)
**Notes:** Ollama version dropped as scope creep — can be added to Phase 5's ExperimentRun envelope without changing PreLoopTestResult.

---

## Invocation surface

### Q1: How should pre_loop_test be invoked?

| Option | Description | Selected |
|--------|-------------|----------|
| Library function + thin __main__ script | Importable + PRD-compatible script invocation | |
| Library function + __main__ + pytest integration wrapper | All three entry points, same library function | ✓ |
| Standalone script only, no library surface | Simplest; Phase 5 can't reuse | |

**User's choice:** Library function + __main__ + pytest integration wrapper
**Notes:** The pytest wrapper matches Phase 2's `tests/test_smoke_ollama.py` pattern exactly — same marker, same `MODEL=gemma4:26b uv run pytest -m integration` invocation style. Runs alongside the existing 2 Phase 2 integration tests.

---

## Claude's Discretion (deferred)

- Exact rationale string wording — hand-written at test-authoring time per D-07 decision
- Banner exact formatting (width, separators, line breaks)
- Variance check implementation location (validator vs helper vs inline)
- Logging shape (`jitc.preloop` logger naming)
- Whether to add a `PreLoopTestResult.__str__` pretty-print
- Whether to add FakeClient unit tests for aggregation math

## Deferred Ideas (future phases or not this milestone)

- Deliberate failure-mode sanity test (swap outputs) — scope creep
- Multi-model comparison — explicitly out of scope per PROJECT.md
- Judgment-specific threshold (stricter than "positive") — revisit after first real run
- Ollama version capture — Phase 5 ExperimentRun envelope if needed
- Banner colourisation — portability concern, plain ASCII only
