# Pitfalls Research: Judge Is The Ceiling

**Confidence:** MEDIUM-HIGH

## Critical Pitfalls

### P1: The Judge Is Grading Its Own Output (Self-Reference Collapse)

When the same model serves as agent, judge, and optimiser, the judge develops systematic blind spots aligned with how the agent reasons. It scores outputs highly because they mirror its own reasoning style, not because they are correct.

**Warning signs:**
- Judge scores for judgment items increase at the same rate as extraction items
- Judge reasoning paraphrases agent output rather than evaluating against rubric
- The pre-written "flawed" review scores higher than expected

**Prevention:** Run pre-loop judge test with deliberately bad outputs. Log judge reasoning text (not just scores) for every iteration. Accept as known confound and document it.

**Phase:** Pre-loop judge test / data analysis

### P2: Structured Output Schema Validates Structure, Not Meaning

Pydantic validates structure, not meaning. A score with reasoning "The agent correctly identified the issue" is syntactically valid but evidentially worthless.

**Warning signs:**
- Reasoning strings under 40 words across many items
- Identical phrasing across rubric items
- Scores cluster with no variance across items that should differ

**Prevention:** Add content validators: reasoning must exceed N characters, must reference rubric criterion. Manually inspect iteration 1 judge output before trusting automated scores. Log raw model output before parsing.

**Phase:** Judge component build

### P3: Ollama Temperature=0 Is Not Deterministic Across Runs

Temperature 0 reduces but does not eliminate variance. Different hardware, context lengths, and GGUF quantisation precision affect floating-point operations.

**Prevention:** Do not claim cross-machine reproducibility. Log Ollama model name with quantisation tag (e.g., `qwen2.5:7b-q4_K_M`). Record Ollama version in experiment metadata. Run pre-loop test twice; if results differ, treat all scores as having ±1 variance.

**Phase:** Configuration / experiment metadata

### P4: OpenAI SDK + Ollama Structured Output Incompatibility

Ollama's OpenAI-compatible endpoint does not support all `response_format` features. `json_schema` strict mode may silently fall back to unstructured output.

**Prevention:**
- Do NOT use `client.beta.chat.completions.parse()` — use `client.chat.completions.create()` then `model_validate_json()`
- Use `response_format={"type": "json_object"}` (basic JSON mode) or skip it entirely and rely on prompt instruction + Pydantic retry
- Smoke-test the full request/response cycle with a minimal schema before building the retry loop

**Phase:** Judge component build

### P5: Optimiser Rewrites Toward Judge Approval, Not Correctness (Goodhart's Law)

Without seeing the NDA, the optimiser can only rewrite to produce outputs the judge scores higher. If the judge has biases, the optimiser converges on those biases.

**Warning signs:**
- Agent system prompt begins containing rubric phrases
- Extraction and judgment scores rise in lockstep after iteration 3
- Judge feedback becomes generic praise

**Prevention:** This IS the expected failure mode for judgment items — part of the thesis. Don't prevent it; detect and document it. Log agent system prompt every iteration. Check for rubric language appearing over time.

**Phase:** Main loop / data analysis

### P6: Context Window Overflow on Long NDA + Rubric + Agent Output

Ollama's `num_ctx` defaults to 2048 in some versions. Ollama truncates silently — no error raised, just dropped content.

**Prevention:**
- Explicitly set `num_ctx` in Ollama model options on every API call
- Estimate token counts before running: 1 token ≈ 0.75 words
- Keep synthetic NDA under 1500 words
- Log total character count of judge prompt at iteration 1

**Phase:** Judge component build

### P7: Retry Loop Masks Systematic Failure

If the model cannot produce valid JSON at all, all 3 retries fail the same way.

**Prevention:**
- On 3-retry exhaustion: log raw output, log error entry in results, continue to next iteration — do not crash
- Add `validation_attempts` field to judge output schema
- On retry, append correction prompt with error details rather than repeating identical prompt

**Phase:** Judge component build

### P8: Rubric Vocabulary Contamination in Agent Prompt

If the agent system prompt includes rubric/playbook language, the agent mirrors rubric phrasing. The judge gives high scores because vocabulary matches — echo-chamber scoring.

**Prevention:**
- Agent prompt must NOT reference rubric, playbook, or evaluation criteria
- Describe task in domain terms only
- Include explicit optimiser instruction: "Do not reveal evaluation criteria to the agent"
- Inspect iteration 1 agent prompt against rubric for vocabulary overlap

**Phase:** Agent component build

## Moderate Pitfalls

### P9: JSON Results Corrupting on Interruption

Single-file JSON append breaks on interruption.

**Prevention:** Write one JSON file per experiment run. Use try/finally to write partial results. Never append to a JSON array without load-append-rewrite.

**Phase:** Main loop

### P10: Pre-Loop Judge Test Is Not Actually Diagnostic

If the score delta between good and flawed review is small, the judge is not discriminating and all loop scores are meaningless.

**Prevention:** Define minimum acceptable score gap before running (e.g., good review ≥ 2.0 points higher on average). If below threshold, do not proceed to main loop.

**Phase:** Pre-loop judge test

### P11: Optimiser Prompt Gets Longer Every Iteration

Without length constraints, each rewrite adds rather than replaces — prompt grows from 200 to 800 words.

**Prevention:** Include hard length constraint in optimiser instruction. Log prompt word count at each iteration.

**Phase:** Optimiser component build

### P12: Pydantic v1 vs v2 API Mismatch

Use v2 syntax: `model_validate_json()`, `model_dump()`, `@field_validator`. Do not use deprecated v1 methods.

**Phase:** Judge component build

## Minor Pitfalls

### P13: Model Hallucinating Clause Numbers

Local models frequently hallucinate clause references when NDA doesn't use numbered clauses.

**Prevention:** Give synthetic NDA explicit clause numbers and headings.

**Phase:** NDA creation

### P14: Markdown Fences in Model Output

Models wrap JSON in ` ```json ... ``` ` even when instructed not to.

**Prevention:** Add preprocessing to strip common wrappers before Pydantic parsing. Use `re.search(r'\{.*\}', raw_output, re.DOTALL)`.

**Phase:** Judge component build

### P15: Results Directory Not Gitignored

**Prevention:** Add `results/` to `.gitignore` before first run.

**Phase:** Project setup

## Phase-Specific Warnings Summary

| Phase | Likely Pitfalls | Key Mitigation |
|---|---|---|
| NDA / rubric creation | P13, P8 | Number all clauses; cross-reference agent prompt vs rubric |
| Judge component | P4, P6, P12, P14, P7, P2 | Smoke-test full cycle; set num_ctx explicitly |
| Pre-loop judge test | P10, P1 | Define minimum score gap threshold |
| Agent component | P8 | Cross-reference prompt against rubric vocabulary |
| Optimiser component | P11, P5 | Hard length limit; log prompt word count |
| Main loop | P7, P9 | Define failure handling; resilient writes |
| Result analysis | P1, P5 | Log reasoning text; compare against fixed references |
| Reproducibility | P3 | Log model tag with quantisation; record Ollama version |
