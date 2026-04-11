# Roadmap: Judge Is The Ceiling

## Overview

The build follows hard dependency order dictated by the experiment architecture: schemas and static data must exist before any LLM component can run; the agent and judge are built next; the pre-loop judge test acts as a non-negotiable go/no-go gate before the optimiser is written; and the main loop is the last component assembled, integrating all prior pieces into a single experiment run.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Project setup, Pydantic schemas, config, and all static data files
- [ ] **Phase 2: Agent and Judge** - Working run_agent() and run_judge() with retry loop, verified against schemas
- [ ] **Phase 3: Pre-Loop Validation Gate** - Judge calibration test producing a go/no-go decision before proceeding
- [ ] **Phase 4: Optimiser** - Working run_optimiser() with feedback pass-through and prompt length enforcement
- [ ] **Phase 5: Main Loop** - Complete experiment run producing structured JSON results

## Phase Details

### Phase 1: Foundation
**Goal**: The project is runnable and all static content exists for the experiment
**Depends on**: Nothing (first phase)
**Requirements**: SETP-01, SETP-02, CONF-01, CONF-02, MODL-01, MODL-02, DATA-01, DATA-02, DATA-03, DATA-04, DATA-05
**Success Criteria** (what must be TRUE):
  1. `uv sync` installs all dependencies without errors and `uv run python -c "from src.models import ExperimentRun"` succeeds
  2. All four Pydantic model classes (RubricScore, JudgeResult, IterationResult, ExperimentRun) can be instantiated and serialised to JSON
  3. Config constants (model, base_url, temperature, iteration count) are readable from environment variables with documented defaults
  4. data/nda.md, data/rubric.json, data/playbook.md, data/output_a.md, and data/output_b.md all exist with correct structure (rubric has 8 items, NDA has numbered clauses, playbook covers all 4 issues)
  5. results/ directory is listed in .gitignore
**Plans**: 3 plans
Plans:
- [x] 01-01-PLAN.md — Project skeleton (uv, dependencies, gitignore) + Config dataclass + Pydantic models
- [x] 01-02-PLAN.md — Synthetic NDA, rubric JSON, and judge playbook
- [x] 01-03-PLAN.md — Output A (model review) and Output B (flawed review)

### Phase 2: Agent and Judge
**Goal**: The agent can review an NDA and the judge can score any review with structured, validated output
**Depends on**: Phase 1
**Requirements**: AGNT-01, AGNT-02, JUDG-01, JUDG-02, JUDG-03, JUDG-04, JUDG-05
**Success Criteria** (what must be TRUE):
  1. run_agent(system_prompt, nda_text) returns a non-empty string review when called against the local Ollama endpoint
  2. run_judge(nda_text, agent_output, rubric, playbook) returns a validated JudgeResult Pydantic object with all 8 rubric items scored
  3. Judge retries up to 3 times on invalid JSON and sends the ValidationError message back to the model on each retry; a deliberately malformed call demonstrates this behaviour
  4. Markdown fences are stripped before Pydantic parsing and num_ctx is set explicitly on every judge API call
  5. If all 3 retries are exhausted the judge logs the raw output and returns a graceful failure result rather than raising an exception
**Plans**: TBD

### Phase 3: Pre-Loop Validation Gate
**Goal**: The judge demonstrably distinguishes the good review from the flawed review, confirming the experiment is worth running
**Depends on**: Phase 2
**Requirements**: TEST-01, TEST-02
**Success Criteria** (what must be TRUE):
  1. pre_loop_test.py runs output_a.md and output_b.md through run_judge() and writes results/pre_loop_test.json in the same schema as loop iteration results
  2. The good review (output_a) scores at least 2.0 points higher than the flawed review (output_b) on average across all 8 rubric items
  3. Score breakdown in results/pre_loop_test.json shows the good review outscoring the flawed review on judgment items specifically (the thesis-critical signal)
  4. A go/no-go decision is documented (in results/pre_loop_test.json or console output) before the loop is built
**Plans**: TBD

### Phase 4: Optimiser
**Goal**: The optimiser can rewrite an agent system prompt based solely on judge feedback, without access to the NDA
**Depends on**: Phase 3
**Requirements**: OPTM-01, OPTM-02, OPTM-03
**Success Criteria** (what must be TRUE):
  1. run_optimiser(system_prompt, judge_result) returns a new system prompt string; the NDA text is never passed as an argument (enforced at call site)
  2. The optimiser meta-prompt enforces a hard word-count limit and the returned prompt demonstrably stays within that limit
  3. The feedback strings that were passed to the optimiser are stored alongside the new prompt (pass-through logging)
  4. A prompt diff between the input and output system prompt is captured and stored
**Plans**: TBD

### Phase 5: Main Loop
**Goal**: A complete experiment run executes N iterations of agent -> judge -> log -> optimiser and writes a single structured JSON artifact
**Depends on**: Phase 4
**Requirements**: LOOP-01, LOOP-02, LOOP-03, LOOP-04
**Success Criteria** (what must be TRUE):
  1. Running loop.py produces results/run_001.json containing an ExperimentRun with all IterationResult objects for N iterations (default 5)
  2. Each IterationResult includes the system prompt used, agent output, full JudgeResult with per-item scores, extraction_score and judgment_score category aggregates, and delta_from_prev values
  3. The run metadata envelope in results/run_001.json includes model name (with quantisation tag), Ollama version, temperature, and timestamp
  4. If a single iteration fails (e.g., judge retry exhaustion) the error is logged and the loop continues to the next iteration without crashing
  5. results/run_001.json is written via try/finally so a partial run is preserved even if the process is interrupted
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/3 | Planning complete | - |
| 2. Agent and Judge | 0/TBD | Not started | - |
| 3. Pre-Loop Validation Gate | 0/TBD | Not started | - |
| 4. Optimiser | 0/TBD | Not started | - |
| 5. Main Loop | 0/TBD | Not started | - |
