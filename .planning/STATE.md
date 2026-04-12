---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Completed 05-01-PLAN.md (all 3 tasks, Task 3 auto-approved)
last_updated: "2026-04-12T04:14:42.840Z"
last_activity: 2026-04-12
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 10
  completed_plans: 10
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-11)

**Core value:** Produce a clean experiment run demonstrating whether the optimisation loop converges on extraction scores while plateauing on judgment scores
**Current focus:** Phase 05 — Main Loop

## Current Position

Phase: 05 (Main Loop) — EXECUTING
Plan: 1 of 1
Status: Phase complete — ready for verification
Last activity: 2026-04-12

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 3
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 02-agent-and-judge P01 | 162 | 3 tasks | 10 files |
| Phase 02-agent-and-judge P02 | 95 | 2 tasks | 2 files |
| Phase 02-agent-and-judge P03 | 4 | 3 tasks | 4 files |
| Phase 02-agent-and-judge P04 | 180 | 2 tasks | 1 file |
| Phase 03-pre-loop-validation-gate P01 | 13 | 3 tasks | 3 files |
| Phase 04-optimiser P01 | 20 | 3 tasks | 4 files |
| Phase 05-main-loop P01 | 11 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Pre-loop gate is non-negotiable: if judge cannot discriminate good from flawed review by >=2.0 points, do not build the loop
- Optimiser must never receive NDA text — enforced at call site in loop.py
- Temperature = 0 on all LLM calls for reproducibility
- [Phase 02-agent-and-judge]: num_ctx default locked at 16384 (D-02) with NUM_CTX env var override (D-03)
- [Phase 02-agent-and-judge]: Assumption A1 verified: extra_body={'options':{'num_ctx':N}} is honoured by Ollama (qwen3.5:27b smoke returned 'pong')
- [Phase 02-agent-and-judge]: ITERATION_ZERO_SYSTEM_PROMPT copied verbatim from prd.md §3.4 with P8 banned-token regression gate in tests/test_agent.py (13 tokens)
- [Phase 02-agent-and-judge]: run_agent uses temperature=config.temperature (not hard-coded) and returns message.content or '' to absorb Ollama None-content quirk
- [Phase 02-agent-and-judge]: run_judge graceful failure returns JudgeResult(scores=[]) sentinel — callers detect with 'if not result.scores:' (JUDG-05)
- [Phase 02-agent-and-judge]: _extract_json uses single outermost-brace DOTALL regex (re.DOTALL) — handles json fences, prose preambles, and nested objects in one pass instead of separate fence-stripping step (P14)
- [Phase 02-agent-and-judge]: Judge retry loop uses single 'except ValidationError' — Pydantic v2 model_validate_json raises this for both JSON-decode and schema failures (P12), no JSONDecodeError catch needed
- [Phase 02-agent-and-judge]: FakeChatCompletions.create deep-copies kwargs at capture so multi-call retry tests can inspect per-call messages history without aliasing the caller's mutable list (Rule 1 deviation)
- [Phase 02-agent-and-judge P04]: Live Ollama integration verified end-to-end against gemma4:26b — run_agent + run_judge round-trip returned 8/8 rubric scores with specific, NDA-citing reasoning strings (126s pytest run)
- [Phase 02-agent-and-judge P04]: MODEL=gemma4:26b confirmed as the working local override; .env file created (gitignored) documenting MODEL/BASE_URL/API_KEY/NUM_CTX for developers — src/config.py default qwen2.5:32b left unchanged pending a user decision on canonical experiment model
- [Phase 03-pre-loop-validation-gate]: PreLoopTestResult schema with validator-owns-arithmetic pattern and probe-construction for rationale (D-01, Resolution #1)
- [Phase 03-pre-loop-validation-gate]: Threshold hard-coded at 2.0 on the Pydantic model, no env override (P10 mitigation)
- [Phase 03-pre-loop-validation-gate]: Script-mode sys.path shim guarded by __package__ sentinel enables uv run python src/pre_loop_test.py (D-10 PRD compat)
- [Phase 03-pre-loop-validation-gate]: jitc.preloop logger namespace established for Phase 3 (matches Phase 2 jitc.agent / jitc.judge convention)
- [Phase 03-pre-loop-validation-gate]: Live gemma4:26b gate: gap=5.0 judgment_gap=5 variance=False — entire gap from judgment category (extraction=8 for both reviews), cleanest possible P1 falsification
- [Phase 04-optimiser]: run_optimiser signature excludes NDA (structural OPTM-01), 3-retry word-limit loop with sentinel on exhaustion, post-hoc vocab scrub with vocab_warning flag but no retry (P5 detect-don't-prevent)
- [Phase 04-optimiser]: BANNED_RUBRIC_VOCAB_TOKENS lives in src/models.py as the single source of truth; imported by src/optimiser.py (meta-prompt + scrub) AND tests/test_agent.py (agent prompt gate) so P8 drift is impossible
- [Phase 05-main-loop]: Optimiser not called after last iteration (D-12): clean iteration boundary, no wasted LLM call
- [Phase 05-main-loop]: Deltas computed at write time via _compute_deltas, not stored in IterationResult: avoids Pydantic schema changes
- [Phase 05-main-loop]: model_dump() + dict injection pattern for top-level deltas key in results JSON

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3 requires a researcher decision before running: confirm the minimum acceptable score gap threshold (suggested >=2.0 points) and document rationale
- **RESOLVED 2026-04-11:** Canonical experiment model changed from `qwen2.5:32b` to `gemma4:26b` (Option B) — src/config.py default updated, PROJECT.md Key Decisions table updated. Live tests in Phase 3+ run against the default model with no env override needed.

## Session Continuity

Last session: 2026-04-12T04:14:42.837Z
Stopped at: Completed 05-01-PLAN.md (all 3 tasks, Task 3 auto-approved)
Resume file: None
