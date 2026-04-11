# Phase 4: Optimiser - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-12
**Phase:** 04-optimiser
**Areas discussed:** Function signature + return shape + schema, Meta-prompt + word limit, Feedback extraction, Word-count enforcement + diff format + P8 scrub

---

## Gray Area Selection

Four gray areas offered; user selected all four.

---

## Function signature + return shape + schema

### Q1: Input parameter shape for `run_optimiser`?

| Option | Description | Selected |
|--------|-------------|----------|
| `(system_prompt: str, judge_result: JudgeResult)` | Full Phase 2 JudgeResult; function extracts feedback internally | ✓ |
| `(system_prompt: str, feedback: list[str])` | Only feedback strings, maximally minimal | |
| `(system_prompt: str, feedback_bundles: list[FeedbackBundle])` | New custom model for structured context | |

**User's choice:** JudgeResult (Recommended)

### Q2: Return shape?

| Option | Description | Selected |
|--------|-------------|----------|
| Richer `OptimiserResult` | new_system_prompt + feedback_seen + prompt_diff + prompt_word_count + old_word_count | ✓ |
| Plain `str` | Just the new prompt; caller computes diff/log separately | |
| `tuple[str, OptimiserLog]` | Split what from how | |

**User's choice:** Richer `OptimiserResult` (Recommended)

### Q3: Where `feedback_seen` / `prompt_diff` / `prompt_word_count` live in results schema?

| Option | Description | Selected |
|--------|-------------|----------|
| Extend IterationResult | Add 3 new fields with defaults | ✓ |
| New `OptimiserLog` nested under IterationResult | Cleaner separation; more model classes | |
| Separate top-level list in ExperimentRun | Parallel to iterations; drift risk | |

**User's choice:** Extend IterationResult (Recommended)

---

## Meta-prompt + word-count value

### Q1: Hard word-count limit?

| Option | Description | Selected |
|--------|-------------|----------|
| 200 words | Matches PITFALLS P11 example | |
| 150 words | Tighter, more aggressive editing | |
| 300 words | Looser; more room; weaker P11 mitigation | ✓ |

**User's choice:** 300 words
**Notes:** Tradeoff acknowledged. CONTEXT.md D-10 flags Phase 5 must monitor word-count trend across iterations as an additional P11 signal.

### Q2: Explicit anti-P8/P5 instructions in optimiser meta-prompt?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — explicit instructions | Ban rubric/judge/score/evaluation/criteria vocabulary in the rewrite | ✓ |
| No — rely on post-hoc scrub | Cleaner separation; gives up prevention leverage | |

**User's choice:** Yes — explicit instructions (Recommended)

### Q3: Item IDs (1a, 1b, etc.) in feedback passed to optimiser?

| Option | Description | Selected |
|--------|-------------|----------|
| Strip item IDs, free-form feedback only | IDs are rubric vocabulary (P8) | ✓ |
| Keep item IDs as-is | Easier cross-reference; P8 violation risk | |
| Use issue numbers only (1-4), drop a/b | Middle ground | |

**User's choice:** Strip item IDs (Recommended)

### Q4: Scores visible to optimiser?

| Option | Description | Selected |
|--------|-------------|----------|
| Scores + feedback together | Lets optimiser prioritise by severity | ✓ |
| Feedback only, no scores | Cannot weight by failure severity | |
| Only items scoring < 2 (actionable) | Focus on failures; lose 'what works' signal | |

**User's choice:** Scores + feedback together (Recommended)

---

## Feedback extraction strategy

### Q1: Transformation format?

| Option | Description | Selected |
|--------|-------------|----------|
| Numbered failure list sorted by score ascending | Worst failures first; drops item_ids | ✓ |
| Grouped by score bucket | Clearer priority grouping but headers leak rubric-y language | |
| Flat list, no sorting, scores inline | Simplest | |

**User's choice:** Numbered failure list sorted by score ascending (Recommended)

### Q2: Items scoring 2 (already satisfied)?

| Option | Description | Selected |
|--------|-------------|----------|
| Include them so optimiser doesn't regress wins | Preserve what works | ✓ |
| Drop fully-satisfied items entirely | Smaller input; regression risk | |

**User's choice:** Include them (Recommended)

---

## Word-count enforcement + diff format + P8 scrub

### Q1: Word-count enforcement strategy?

| Option | Description | Selected |
|--------|-------------|----------|
| Post-validate + retry with stricter reminder, max 3 | Mirror Phase 2 judge retry pattern; graceful sentinel on exhaustion | ✓ |
| Post-validate + truncate silently | Risks cutting mid-sentence | |
| Post-validate + raise ValueError | Harshest, least graceful | |
| Trust LLM; log overruns but don't enforce | Weakest P11 mitigation | |

**User's choice:** Post-validate + retry (Recommended)

### Q2: Prompt diff storage format?

| Option | Description | Selected |
|--------|-------------|----------|
| Plain unified diff string via difflib | Human-readable; stdlib only | ✓ |
| Structured dict with added/removed lines | Machine-friendly; harder to eyeball | |
| Store both prompts; compute diff at read time | Scattered diff logic | |

**User's choice:** Plain unified diff (Recommended)

### Q3: P8 post-hoc vocab scrub behaviour?

| Option | Description | Selected |
|--------|-------------|----------|
| Scrub + WARN + flag, don't retry | Detect/document per PITFALLS P5 guidance | ✓ |
| Scrub + retry on contamination | Masks P5 signal; strongest prevention | |
| No — leave to Phase 5 analysis | Loses per-iteration observability | |

**User's choice:** Scrub + WARN but don't fail (Recommended)

---

## Claude's Discretion (deferred)

- Exact meta-prompt wording (template provided in D-09; planner may polish)
- Retry error message exact wording (template provided in D-11)
- MAX_RETRIES and WORD_LIMIT constant placement (module-level recommended)
- Unit test structure and coverage depth (mirror Phase 2 test_judge.py)
- Whether to add a live Ollama integration smoke test in Phase 4 or defer to Phase 5
- Runtime NDA-leakage assertion — deferred (call-site enforcement per OPTM-01)
- Whether `run_optimiser` accepts optional `model` override parameter (recommend no)

## Deferred Ideas

- Cross-iteration word-count trend analysis — Phase 5 scope
- Optimiser self-critique / reflection pass — out of scope per PROJECT.md
- Feedback deduplication across iterations — Phase 5 scope
- Adaptive word limit — out of scope
- Alternative diff formats — out of scope
- Optimiser meta-prompt evolution — out of scope (would convert to multi-variable search)
- Runtime NDA-substring assertion — out of scope (Phase 5 call-site concern)
