# Requirements: Judge Is The Ceiling

**Defined:** 2026-04-11
**Core Value:** Produce a clean experiment run demonstrating whether the optimisation loop converges on extraction while plateauing on judgment

## v1 Requirements

### Static Data

- [ ] **DATA-01**: Synthetic NDA in markdown with 4 embedded issues (2 extraction, 2 judgment) and explicit clause numbering
- [ ] **DATA-02**: 8-item rubric JSON with metadata (item_id, type, issue_number, question, scoring guidance)
- [ ] **DATA-03**: Playbook with precise extraction descriptions and deliberately vague judgment descriptions
- [ ] **DATA-04**: Output A — model NDA review correctly identifying all 4 issues including judgment calls
- [ ] **DATA-05**: Output B — plausible-but-flawed review that nails extraction but misses judgment

### Data Models

- [ ] **MODL-01**: Pydantic models for RubricScore, JudgeResult, IterationResult, ExperimentRun
- [ ] **MODL-02**: Category-level score aggregation (extraction_score, judgment_score) computed at write time

### Configuration

- [ ] **CONF-01**: Configurable model name, base URL, API key, temperature, iteration count via environment variables with defaults
- [ ] **CONF-02**: Temperature enforced at 0 for all LLM calls

### Agent

- [ ] **AGNT-01**: Agent takes system prompt + NDA text, returns structured NDA review via OpenAI-compatible API
- [ ] **AGNT-02**: Agent system prompt does not reference rubric, playbook, or evaluation criteria

### Judge

- [ ] **JUDG-01**: Judge takes NDA + agent output + rubric + playbook, returns per-item scores as validated JSON
- [ ] **JUDG-02**: Pydantic validation with retry up to 3 attempts, sending error details back to model on failure
- [ ] **JUDG-03**: Markdown fence stripping before JSON parsing
- [ ] **JUDG-04**: Explicit Ollama num_ctx setting to prevent silent context truncation
- [ ] **JUDG-05**: Graceful failure handling — log raw output and continue on retry exhaustion, don't crash

### Pre-Loop Test

- [ ] **TEST-01**: Run Output A and Output B through judge with same rubric and playbook
- [ ] **TEST-02**: Results logged in same JSON schema as loop iterations for direct comparison

### Optimiser

- [ ] **OPTM-01**: Optimiser takes current system prompt + judge feedback only (not the NDA), returns rewritten prompt
- [ ] **OPTM-02**: Optimiser feedback pass-through logging — store what feedback was received
- [ ] **OPTM-03**: Prompt diff between iterations stored in results

### Loop

- [ ] **LOOP-01**: Main loop ties agent -> judge -> log -> optimiser for N iterations (default 5)
- [ ] **LOOP-02**: Per-iteration results written to structured JSON with iteration counter
- [ ] **LOOP-03**: Run metadata envelope (model, temperature, timestamp, iteration count, Ollama version)
- [ ] **LOOP-04**: Resilient to individual iteration failures — log error and continue

### Project Setup

- [ ] **SETP-01**: uv project with openai and pydantic dependencies, black for formatting
- [ ] **SETP-02**: results/ directory gitignored

## v2 Requirements

### Visualisation

- **VIZ-01**: Streamlit app reading from results/ directory
- **VIZ-02**: Score trajectory charts (extraction vs judgment over iterations)
- **VIZ-03**: Prompt evolution viewer

### Analysis

- **ANAL-01**: Plateau detection flag (extraction stable for N iterations, judgment not caught up)
- **ANAL-02**: Delta tracking (score change iteration-to-iteration)
- **ANAL-03**: Human review template and comparison tooling

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multiple model comparison | Confounds experiment variable; thesis is about judge ceiling, not model comparison |
| Agent SDK or tool use | PRD explicitly rules this out; prompt rewriting only |
| Streaming LLM output | Complicates Pydantic validation and retry; no latency benefit for batch experiment |
| Parallel iteration execution | Destroys sequential prompt versioning; iteration N+1 depends on N |
| Automatic prompt rollback | Changes experiment semantics from linear loop to search algorithm |
| External experiment tracking (MLflow, W&B) | Overkill for bounded single-run experiment; JSON files sufficient |
| Database storage | JSON files are grep-able and portable for this scale |
| Token usage tracking | Irrelevant for local Ollama (free inference) |
| Embedding-based similarity scoring | Outside rubric-anchored scoring model |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Pending |
| DATA-02 | Phase 1 | Pending |
| DATA-03 | Phase 1 | Pending |
| DATA-04 | Phase 1 | Pending |
| DATA-05 | Phase 1 | Pending |
| MODL-01 | Phase 1 | Pending |
| MODL-02 | Phase 1 | Pending |
| CONF-01 | Phase 1 | Pending |
| CONF-02 | Phase 1 | Pending |
| SETP-01 | Phase 1 | Pending |
| SETP-02 | Phase 1 | Pending |
| AGNT-01 | Phase 2 | Pending |
| AGNT-02 | Phase 2 | Pending |
| JUDG-01 | Phase 2 | Pending |
| JUDG-02 | Phase 2 | Pending |
| JUDG-03 | Phase 2 | Pending |
| JUDG-04 | Phase 2 | Pending |
| JUDG-05 | Phase 2 | Pending |
| TEST-01 | Phase 3 | Pending |
| TEST-02 | Phase 3 | Pending |
| OPTM-01 | Phase 4 | Pending |
| OPTM-02 | Phase 4 | Pending |
| OPTM-03 | Phase 4 | Pending |
| LOOP-01 | Phase 5 | Pending |
| LOOP-02 | Phase 5 | Pending |
| LOOP-03 | Phase 5 | Pending |
| LOOP-04 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0

---
*Requirements defined: 2026-04-11*
*Last updated: 2026-04-11 after roadmap creation*
