# Project Research Summary

**Project:** Judge Is The Ceiling
**Domain:** LLM evaluation / auto-optimising prompt experiment
**Researched:** 2026-04-11
**Confidence:** HIGH (stack and architecture fully specified in PRD; feature and pitfall patterns well-established)

## Executive Summary

Judge Is The Ceiling is a closed-loop prompt optimisation experiment: an LLM agent reviews a synthetic NDA, a judge LLM scores the review against a rubric, an optimiser rewrites the agent's system prompt based on judge feedback, and the loop repeats. The core thesis is that because the same model family serves as all three roles, the judge's ceiling sets an upper bound on how well the optimiser can train the agent — judgment-type rubric items should plateau while extraction items improve. This is a focused, single-model, local-inference experiment, not a production system.

The recommended approach is deliberate minimalism: two runtime dependencies (openai SDK + pydantic), synchronous execution, flat JSON output files, and explicit retry logic instead of a framework. The architecture is fully specified in the PRD — five source files with thin, typed function signatures, no shared mutable state, and a hard build order enforced by a pre-loop judge validation gate. The only meaningful design choices left open are prompt content and rubric structure.

The dominant risk is self-reference collapse: the same model acting as agent, judge, and optimiser can converge on its own reasoning style rather than objective quality. This is not a bug to fix — it is the experiment's expected finding for judgment items. The mitigation is to log judge reasoning text alongside scores, run a pre-loop calibration test before the main loop, and treat score divergence between extraction and judgment categories as the primary analytical signal.

---

## Key Findings

### Recommended Stack

The stack is pre-decided and confirmed by research. Python 3.11+ with uv for dependency management, openai>=2.0 for the Ollama-compatible API client, and pydantic>=2.0 for structured output validation. No other runtime dependencies are needed or recommended.

The critical pattern is: use client.chat.completions.create() (not beta.parse()), prompt the model to return raw JSON, then model_validate_json() with a correction-prompt retry loop on failure. Ollama's structured output endpoint support is inconsistent across models; the prompt-plus-retry pattern is more reliable.

**Core technologies:**
- Python 3.11+ — required for Pydantic v2 performance and full type annotation support
- uv 0.7.x — uv sync / uv run for zero-activation dependency management
- openai>=2.0 (current: 2.31.0) — OpenAI SDK with base_url override for Ollama; api_key="ollama" is the community standard
- pydantic>=2.0 (current: 2.12.5) — structured output validation with model_validate_json() and ValidationError-based retry
- black>=26.0 (dev only) — formatting; no other dev tooling needed

**Explicitly skip:** instructor, LangChain, any agent SDK, pydantic-settings, async client, response_format json_schema strict mode.

### Expected Features

The MVP is the loop itself. All table-stakes features are low complexity and required before results are trustworthy.

**Must have (table stakes):**
- Pydantic validation with retry (3 attempts) — a single bad parse should not crash the run and lose data
- Rubric-anchored scoring with rationale capture — thesis requires distinguishing extraction vs judgment scores per criterion
- Per-iteration artifact persistence — crash recovery; write results/ JSON before loop exits
- Temperature = 0 enforcement — reproducibility invariant; document that cross-machine determinism is not guaranteed
- Pre-loop judge validation — two fixed synthetic reviews; confirms judge is calibrated before spending compute on the loop
- Configurable model / endpoint — Ollama portability via env vars
- Iteration counter in all artifacts — required for time-series analysis
- Deterministic loop ordering — Agent -> Judge -> Log -> Optimiser, no async branching

**Should have (high analytical value, low complexity):**
- Category-level score aggregation per iteration — extraction vs judgment scores ARE the thesis measurement; compute at write time
- Run metadata envelope — model name with quantisation tag, Ollama version, temperature, git commit hash
- Rubric item-level score time series — consistent item IDs in schema make this implicit; reveals per-criterion plateaus
- Optimiser feedback pass-through logging — records what feedback drove the prompt change
- Delta tracking (score change iteration-to-iteration) — can be derived post-hoc from artifacts; include delta_from_prev field

**Defer (v2+):**
- Plateau detection flag — implement only if run produces enough iterations to need automated detection
- Prompt diff between iterations — useful for analysis but not required for the loop to run
- Streamlit or any UI — out of scope for this experiment milestone
- External experiment tracking (MLflow, W&B) — JSON files are sufficient for a bounded local experiment
- Token usage tracking — irrelevant for local Ollama inference

### Architecture Approach

The system follows a closed-loop prompt optimisation pattern with five source files, each exposing exactly one typed function. loop.py is the sole orchestrator; it imports run_agent(), run_judge(), and run_optimiser() with no shared mutable state between components. config.py reads environment variables at import time and is imported by all components directly (singleton module pattern, no dependency injection). The optimiser deliberately does NOT receive the NDA — it sees only the current system prompt and JudgeResult.feedback strings, mirroring Harvey's approach and keeping the local model's context window smaller.

**Major components:**
1. src/config.py — env var constants (model, base_url, temperature=0, num_iterations); imported by all
2. src/models.py — Pydantic classes (RubricScore, JudgeResult, IterationResult, ExperimentRun); no LLM calls
3. src/agent.py — run_agent(system_prompt, nda_text) -> str; one LLM call, no structured output required
4. src/judge.py — run_judge(nda_text, agent_output, rubric, playbook) -> JudgeResult; retry loop lives here
5. src/optimiser.py — run_optimiser(system_prompt, judge_result) -> str; one LLM call, receives feedback only
6. src/pre_loop_test.py — standalone entry point; runs judge on output_a.md + output_b.md before loop
7. src/loop.py — orchestrator; accumulates IterationResult objects, writes ExperimentRun JSON at end

**Key data files:** data/nda.md, data/rubric.json, data/playbook.md, data/output_a.md, data/output_b.md

### Critical Pitfalls

1. **Self-reference collapse (P1)** — Same model as agent + judge means the judge scores outputs that mirror its own reasoning style. Prevention: run pre-loop test with deliberately bad outputs; log full judge reasoning text every iteration, not just scores. Accept as documented confound for judgment items.

2. **Ollama structured output incompatibility (P4)** — response_format json_schema strict mode silently falls back to unstructured output on some models. Prevention: use client.chat.completions.create() + model_validate_json() + correction-prompt retry. Smoke-test the full request/response cycle with a minimal schema before building the retry loop.

3. **Context window silent truncation (P6)** — Ollama's num_ctx defaults to 2048 in some versions; truncation produces no error. Prevention: set num_ctx explicitly on every API call; keep synthetic NDA under 1500 words; log total character count of judge prompt at iteration 1.

4. **Rubric vocabulary contamination (P8)** — If the agent system prompt includes rubric/playbook language, the judge awards high scores for vocabulary matching rather than correct reasoning. Prevention: agent prompt must describe the task in domain terms only; the optimiser must be instructed not to leak evaluation criteria into the agent's system prompt.

5. **Goodhart's Law in the optimiser (P5)** — The optimiser rewrites toward rubric-approval, not correctness. Warning sign: rubric phrases appearing in the agent system prompt by iteration 3+. This is the expected failure mode for judgment items; detect and document it rather than trying to prevent it.

**Additional pitfalls to address per phase:**
- NDA creation: number all clauses explicitly to prevent clause hallucination (P13)
- Judge build: strip markdown fences before Pydantic parsing with re.search(r'\{.*\}', raw, re.DOTALL) (P14)
- Pre-loop test: define minimum score gap threshold (good >= 2.0 points above flawed average) before proceeding (P10)
- Optimiser build: enforce hard word-count limit in optimiser instruction to prevent prompt bloat (P11)
- Project setup: add results/ to .gitignore before first run (P15)
- Metadata: log model tag with quantisation suffix (e.g., qwen2.5:32b-q4_K_M) and Ollama version for reproducibility (P3)

---

## Implications for Roadmap

The build order is dictated by hard dependencies. Nothing here is ambiguous — the PRD fully specifies it.

### Phase 1: Foundation and Static Data
**Rationale:** models.py and config.py have no inter-module dependencies; everything else imports from them. Static data files must exist before any LLM component can be tested. NDA clause structure affects agent hallucination risk.
**Delivers:** Pydantic schemas, config constants, synthetic NDA with numbered clauses, rubric.json, playbook.md, output_a.md (good review), output_b.md (flawed review), .gitignore with results/ excluded
**Addresses:** Iteration counter in schemas, temperature enforcement in config, rubric-anchored scoring schema
**Avoids:** P13 (unnumbered NDA clauses), P15 (results not gitignored), P12 (Pydantic v1/v2 mismatch caught at schema definition)

### Phase 2: Agent and Judge Components
**Rationale:** Agent and judge can be built in parallel — they share only config and models. Judge is the more complex component (retry loop, structured output). Smoke-test with a direct call before wiring into the loop.
**Delivers:** Working run_agent() and run_judge() with full retry loop; JSON output verified against Pydantic schema
**Addresses:** Pydantic validation with retry (3 attempts), rubric-anchored scoring with rationale, configurable model/endpoint
**Avoids:** P4 (uses create() not parse()), P6 (num_ctx set explicitly), P14 (markdown fence stripping), P8 (agent prompt uses domain language only)

### Phase 3: Pre-Loop Judge Validation Gate
**Rationale:** The PRD specifies this as a hard decision point. If the judge cannot reliably distinguish the good review from the flawed review on judgment items, the thesis is invalid and the loop should not be built. This gate must be passed before the optimiser or loop are written.
**Delivers:** pre_loop_test.py producing results/pre_loop_test.json; score delta measured against minimum threshold (good review >= 2.0 points above flawed on average); go/no-go decision documented
**Addresses:** Pre-loop judge validation (table stakes), run metadata envelope (first artifact)
**Avoids:** P1 (calibration test uses fixed known-good/bad inputs), P10 (threshold defined before running)

### Phase 4: Optimiser Component
**Rationale:** Optimiser depends on JudgeResult output from Phase 2 and cannot be meaningfully tested until the judge is confirmed calibrated in Phase 3.
**Delivers:** Working run_optimiser() that accepts system_prompt + JudgeResult and returns a new system_prompt; hard word-count limit enforced in optimiser prompt; prompt word count logged
**Addresses:** Configurable endpoint (same config), optimiser feedback pass-through logging
**Avoids:** P5 (NDA not passed to optimiser — enforced at call site), P11 (prompt length constraint)

### Phase 5: Main Loop and Experiment Run
**Rationale:** loop.py is the integration point for all prior components. It is the last thing to build, not the first.
**Delivers:** src/loop.py producing results/run_001.json with full ExperimentRun including all IterationResult objects, category-level aggregation, delta tracking, and run metadata envelope
**Addresses:** Per-iteration artifact persistence (try/finally write), deterministic loop ordering, iteration counter, category-level score aggregation, delta tracking
**Avoids:** P7 (failure handling on judge retry exhaustion: log + skip, not crash), P9 (try/finally write on interruption)

### Phase Ordering Rationale

- **Schemas before code:** models.py defines the experiment contract. Every other file imports from it. Writing it first prevents schema drift between components.
- **Pre-loop gate is non-negotiable:** The thesis depends on judge calibration. If the gate is skipped and the judge turns out to be non-discriminating, all loop results are meaningless. The build order enforces the gate structurally.
- **Optimiser last (before loop):** The optimiser's prompt strategy depends on understanding what kinds of feedback the judge actually produces, which only becomes clear after the judge is built and tested.
- **Loop last:** The orchestrator is the thinnest layer — it calls three functions and writes a JSON file. Building it last means each call is already verified.

### Research Flags

Phases with standard, well-documented patterns (no additional research needed):
- **Phase 1:** Pydantic v2 schema definition — canonical API, no ambiguity
- **Phase 2:** OpenAI SDK create() + Pydantic retry — fully specified in STACK.md with working code
- **Phase 4:** String-returning LLM call with length enforcement — trivial pattern
- **Phase 5:** Synchronous orchestration with try/finally — standard Python

Phases requiring human judgment (not researchable):
- **Phase 3:** The minimum acceptable score gap threshold (suggested: >=2.0 points) is a research design decision, not a software pattern. The researcher must set and document this before running the pre-loop test.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Live PyPI versions verified 2026-04-11; Ollama base_url pattern is stable and community-standard |
| Features | MEDIUM | Web tools unavailable during research; patterns drawn from training knowledge of DeepEval, promptfoo, DSPy — core patterns stable |
| Architecture | HIGH | Fully specified in PRD and CLAUDE.md; research confirms patterns, adds no ambiguity |
| Pitfalls | MEDIUM-HIGH | Self-reference collapse and Goodhart's Law pitfalls are well-established ML patterns; Ollama-specific pitfalls confirmed by community |

**Overall confidence:** HIGH for build decisions; MEDIUM for analytical predictions about experiment outcomes (appropriate — the outcome is the research question).

### Gaps to Address

- **Ollama num_ctx default:** Exact default varies by Ollama version. Mitigation: always set explicitly; smoke-test at Phase 2.
- **Judge discrimination threshold:** The >=2.0 point gap for the pre-loop gate is a suggested heuristic, not a validated standard. The researcher must document their chosen threshold and rationale before Phase 3.
- **Quantisation effects on determinism:** Temperature=0 variance from GGUF quantisation cannot be eliminated. Mitigation: log quantisation tag and run pre-loop test twice to measure baseline variance before trusting score deltas.
- **Optimiser prompt strategy:** The research specifies what the optimiser receives (system_prompt + feedback strings) but does not prescribe the optimiser's meta-prompt. This is a design decision to make during Phase 4.

---

## Sources

### Primary (HIGH confidence)
- PRD (prd.md) — component signatures, data models, sequence of work, all design decisions
- CLAUDE.md — confirms architecture, data flow, file structure
- PyPI JSON API (2026-04-11) — live package versions for openai, pydantic, black

### Secondary (MEDIUM confidence)
- Training knowledge: DeepEval, promptfoo, LangSmith, DSPy optimizer patterns, PromptLayer — feature landscape and evaluation loop patterns
- Community standard: Ollama api_key="ollama" pattern; response_format instability on Ollama — widely documented
- Harvey auto-optimising agent approach (referenced in PROJECT.md) — design inspiration, not directly verified

### Tertiary (LOW confidence)
- Cross-machine temperature=0 determinism claims — inferred from floating-point precision theory; not experimentally verified for this specific model/hardware combination

---
*Research completed: 2026-04-11*
*Ready for roadmap: yes*
