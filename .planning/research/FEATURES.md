# Feature Landscape: LLM Evaluation Experiment Systems

**Domain:** Auto-optimising LLM evaluation loop (agent -> judge -> optimiser)
**Project:** Judge Is The Ceiling
**Researched:** 2026-04-11
**Confidence note:** Web tools were unavailable. Analysis draws on training knowledge of DeepEval, promptfoo, LangSmith, DSPy, PromptLayer, Weights & Biases LLM tooling, and custom evaluation loop patterns. Confidence is MEDIUM — core patterns are stable and well-established, specific version details may drift.

---

## Table Stakes

Features that must exist or the experiment is unusable. Their absence makes results untrustworthy or the loop impossible to run.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Structured JSON output from every component | Without it you cannot compare scores across iterations or parse programmatically | Low | Pydantic models with field-level typing; the schema IS the experiment contract |
| Pydantic validation with retry (up to N attempts) | LLMs produce malformed JSON; a single bad parse crashes the run and loses data | Low | Standard pattern: parse -> validate -> retry on ValidationError; 3 attempts is the de facto community default |
| Per-iteration artifact persistence | If the loop crashes on iteration 8 of 10, you must not lose runs 1-7 | Low | Write one JSON file per iteration to results/ immediately after completion, not at loop end |
| Rubric-anchored scoring | Scores without an explicit rubric criterion are uninterpretable; you cannot distinguish extraction vs judgment plateau | Medium | Each rubric item must carry: criterion text, category (extraction/judgment), score (0/1 or 0-2), rationale string |
| Judge rationale capture | Scores alone do not reveal whether the judge is applying the rubric correctly | Low | Requires the judge to emit reasoning per criterion alongside the numeric score |
| Configurable model / endpoint | Experiment must work with Ollama locally and any OpenAI-compatible endpoint | Low | Single config object: base_url, model name, temperature, iteration count |
| Temperature = 0 enforcement | Non-zero temperature introduces variance that confounds whether score changes are signal or noise | Trivial | Hardcode or assert; document it as a reproducibility invariant |
| Pre-loop judge validation | Running a known-good and known-bad review through the judge before the loop confirms the judge is calibrated | Low | Two fixed synthetic reviews; expected score ranges documented; failure = experiment is invalid |
| Iteration counter in all artifacts | Without it you cannot plot convergence over time | Trivial | Include iteration: int in every output schema |
| Deterministic loop ordering | Agent -> Judge -> Log -> Optimiser must be a fixed sequence; side effects outside this order corrupt the experiment | Low | Single orchestrating function; no async branching |

---

## Differentiators

Features that make the experiment richer or the analysis more powerful. Not required for the loop to run, but valuable for the thesis.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Category-level score aggregation per iteration | Lets you see extraction vs judgment scores diverge across iterations in a single view without post-processing | Low | Compute at write time: sum(extraction_scores) / n_extraction_items per iteration; add to output JSON |
| Delta tracking (score change iteration-to-iteration) | Convergence detection — if delta < threshold for K consecutive iterations, the optimiser has plateaued | Low | Derive from persisted artifacts; add delta_from_prev field to iteration JSON |
| Prompt diff between iterations | Shows exactly what the optimiser changed, making it possible to reason about why scores moved | Medium | Store previous and new prompt text; optionally emit a unified diff string |
| Optimiser feedback pass-through logging | Records what feedback the optimiser received, not just the prompt it produced | Low | Store judge_feedback_to_optimiser as a field; the optimiser does not see the NDA, so this is the only signal |
| Run metadata envelope | Captures model name, temperature, iteration count, timestamp, and git commit hash at the start of each run | Low | Enables exact reproduction of any run; critical for a research experiment |
| Plateau detection flag | Automatically marks whether convergence has occurred (e.g., extraction score stable for 3 consecutive iterations and judgment score has not caught up) | Medium | Requires category-level aggregation and delta tracking as prerequisites |
| Rubric item-level score time series | Per-item score across all iterations, not just aggregate; reveals which items the optimiser struggles with | Low | Already implicit in per-iteration artifacts; requires consistent item IDs in the rubric schema |
| Pre-loop baseline capture in the same schema | The pre-loop judge test output stored in the same JSON schema as loop iterations enables direct comparison | Low | Minor schema discipline; high payoff for analysis |

---

## Anti-Features

Features to explicitly NOT build in this milestone. Building them adds complexity without advancing the thesis.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Streamlit or any UI | Already out of scope; adds no experiment validity; analysis can be done from JSON | Leave for a separate milestone after the loop produces clean data |
| Multiple model comparison | Confounds the experiment variable; the thesis is about judge ceiling, not model comparison | Fix agent/judge/optimiser to a single model; make model configurable but not simultaneously varied |
| Human review tooling | Author fills in JSON manually; tooling is premature before the schema stabilises | Document the expected human-fill fields in the schema; leave them null in automated output |
| Streaming output from the LLM | Streaming complicates Pydantic validation and retry logic; no latency benefit for a batch experiment | Use non-streaming completions throughout |
| Parallel iteration execution | Parallelism destroys sequential prompt versioning; iteration N+1 must start from N's optimised prompt | Enforce sequential loop with no async parallelism |
| Automatic prompt rollback | Rolling back to a prior prompt when scores drop implies a search algorithm, not a linear loop; changes the experiment semantics | Log the plateau; let the researcher decide post-hoc |
| Embedding-based similarity scoring | Outside the rubric-anchored scoring model; adds a second incommensurable metric | Stick to rubric criterion scores only |
| External experiment tracking service (MLflow, W&B, Neptune) | Adds a dependency and account for a single-run experiment; JSON files are sufficient | Write to results/ directory; analysis done locally or in a notebook later |
| Database storage | Overkill for a bounded experiment; JSON files are grep-able and portable | Flat file per iteration in results/ |
| Token usage tracking per call | Useful for cost analysis, irrelevant for local Ollama (free); adds instrumentation complexity | Omit; note in run metadata that model is local |

---

## Feature Dependencies

```
temperature=0 enforcement
    -> reproducibility (required for any score comparison)

pre-loop judge validation
    -> rubric-anchored scoring (validation requires a rubric)
    -> judge rationale capture (validation requires readable rationale)

category-level score aggregation
    -> rubric item-level score time series (aggregation uses per-item scores)
    -> plateau detection flag (plateau requires aggregated category scores)
    -> delta tracking (delta requires aggregated scores per iteration)

prompt diff between iterations
    -> optimiser feedback pass-through logging (diff is meaningless without knowing what feedback drove it)

run metadata envelope
    -> per-iteration artifact persistence (metadata is the first artifact written)

pre-loop baseline capture in the same schema
    -> rubric-anchored scoring (same schema requires same rubric structure)
    -> per-iteration artifact persistence (baseline is artifact #0 in results/)
```

---

## MVP Recommendation

The loop is the MVP. Everything else is analysis enrichment.

**Prioritize (required for a valid experiment):**
1. Pydantic validation with retry — loop fails without it
2. Rubric-anchored scoring with rationale capture — thesis requires distinguishing extraction/judgment
3. Per-iteration artifact persistence — crash recovery and analysis require it
4. Temperature = 0 enforcement — reproducibility invariant
5. Pre-loop judge validation — confirms the judge is calibrated before spending compute on the loop
6. Configurable model / endpoint — Ollama portability

**Include in initial build (low complexity, high analytical value):**
7. Category-level score aggregation (extraction vs judgment) — this IS the thesis measurement
8. Run metadata envelope — enables exact reproduction
9. Iteration counter in all schemas — trivially cheap, enables time series

**Defer until loop produces clean data:**
- Plateau detection flag — implement if the loop produces enough iterations to need it
- Prompt diff between iterations — useful for analysis but not for running the experiment
- Delta tracking — can be derived from artifacts post-hoc

---

## Sources

- Training knowledge of DeepEval (deepeval.com), promptfoo, LangSmith, DSPy optimizer patterns, PromptLayer — MEDIUM confidence
- Project context: /Users/houfu/Projects/judge-is-the-ceiling/.planning/PROJECT.md
- Harvey auto-optimising agent approach (referenced in PROJECT.md) — source not directly verified; described as design inspiration
- Web tools unavailable during research session; ecosystem claims reflect patterns current as of mid-2025 training data
