# Phase 5: Main Loop - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-12
**Phase:** 05-main-loop
**Areas discussed:** Pre-loop gate integration, Delta tracking, Partial write strategy

---

## Pre-loop gate integration

| Option | Description | Selected |
|--------|-------------|----------|
| Run gate first (Recommended) | loop.py calls run_pre_loop_test() at the start. If decision='no-go', log the result, print banner, exit cleanly. Single command for full experiment. | ✓ |
| Assume gate passed | loop.py skips the gate entirely. User must run pre_loop_test.py separately first. Simpler code, two manual steps. | |
| Check results file | loop.py reads results/pre_loop_test.json and checks decision='go'. Doesn't re-run the gate. Middle ground. | |

**User's choice:** Run gate first
**Notes:** None

---

| Option | Description | Selected |
|--------|-------------|----------|
| Write partial file (Recommended) | Write results/run_001.json with pre_loop_test populated and iterations=[] so there's always a traceable artifact. | |
| No file on no-go | Only print the banner and exit. No run file created. Keeps results/ clean. | ✓ |

**User's choice:** No file on no-go
**Notes:** None

---

## Delta tracking

| Option | Description | Selected |
|--------|-------------|----------|
| Category deltas (Recommended) | Track delta_total, delta_extraction, delta_judgment as new fields on IterationResult. Directly shows thesis signal. | |
| Per-item deltas | Track per-rubric-item score change (8 deltas per iteration, by item_id). More granular. Can be computed post-hoc. | ✓ |
| Total delta only | Single delta_total field. Simpler, but loses extraction/judgment split. | |

**User's choice:** Per-item deltas
**Notes:** None

---

| Option | Description | Selected |
|--------|-------------|----------|
| Stored on IterationResult | New field delta_scores: dict[str, int] on IterationResult. Data self-contained in each record. | |
| Computed at write time (Recommended) | No new field on IterationResult. Loop computes deltas when assembling final JSON. Stored as top-level 'deltas' list. Keeps Pydantic model simpler. | ✓ |

**User's choice:** Computed at write time
**Notes:** None

---

## Partial write strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Write after each iteration (Recommended) | Overwrite results/run_001.json after every iteration. At most 1 iteration lost on crash. Maximally resilient. | ✓ |
| Buffer + finally block | Accumulate in memory, write once at end in try/finally. Less I/O, same resilience for completed iterations. | |
| Write to temp + rename | Write to .tmp after each iteration, atomic rename at end. More complex, ensures final file is always complete. | |

**User's choice:** Write after each iteration
**Notes:** None

---

| Option | Description | Selected |
|--------|-------------|----------|
| Per-iteration summary (Recommended) | Print short line after each iteration: number, scores, delta, word count. Real-time visibility during 30+ min run. | ✓ |
| Silent with final banner | No per-iteration output. Summary banner at end only. Cleaner logs, no real-time feedback. | |
| You decide | Claude picks the approach that fits with existing logging patterns. | |

**User's choice:** Per-iteration summary
**Notes:** None

---

## Claude's Discretion

- Exact progress line format
- Final summary banner design
- Ollama version fetch implementation (urllib vs httpx)
- run_experiment() return type (None on no-go vs always ExperimentRun)
- ExperimentRun model changes for deltas field
- Unit test structure and coverage depth
- Live integration smoke test (optional)
- Logging namespace (recommended: jitc.loop)

## Deferred Ideas

- Feedback deduplication across iterations (Phase 4 deferred)
- Auto-incrementing run numbers
- Score trajectory analysis / plateau detection (v2)
- Prompt rollback on regression (out of scope)
- Token usage tracking (out of scope)
- Word-count trend active warning (v2 analysis)
