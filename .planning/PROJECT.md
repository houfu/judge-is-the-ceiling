# Judge Is The Ceiling

## What This Is

An experiment that runs an auto-optimising agent loop on an NDA review task to test whether an LLM judge can reliably distinguish extraction (finding information) from judgment (assessing significance). The loop captures all artifacts — prompts, outputs, scores, reasoning, feedback — as structured JSON for analysis.

## Core Value

Produce a clean experiment run that demonstrates whether the optimisation loop converges on extraction scores while plateauing on judgment scores, validating the thesis that the judge's ceiling is the playbook author's foresight.

## Requirements

### Validated

- ✓ Synthetic NDA with 4 embedded issues (2 extraction, 2 judgment) — Phase 1
- ✓ 8-item rubric with extraction/judgment pairs per issue — Phase 1
- ✓ Playbook with precise extraction guidance and deliberately vague judgment guidance — Phase 1
- ✓ Configurable model, base URL, temperature, iteration count — Phase 1
- ✓ Agent component: system prompt + NDA -> structured review via OpenAI-compatible API — Phase 2
- ✓ Judge component: NDA + agent output + rubric + playbook -> scored JSON with Pydantic validation and retry — Phase 2
- ✓ Pre-loop judge test running two pre-written reviews (good + flawed) through the judge — Phase 3
- ✓ Optimiser component: current prompt + judge feedback (no NDA) -> rewritten system prompt — Phase 4
- ✓ Main loop tying agent -> judge -> log -> optimiser for N iterations — Phase 5
- ✓ All results written as structured JSON to results/ directory — Phase 5

### Active

None — all v1 requirements validated. Ready for experiment run.

### Out of Scope

- Streamlit dashboard — separate task, not this milestone
- Human review tooling — author fills in JSON manually post-experiment
- Multiple model comparison — single model for agent/judge/optimiser
- Agent tooling or code generation — prompt rewriting only

## Context

- Author is a lawyer testing a thesis about LLM evaluation limits in legal work
- The experiment is inspired by Harvey's auto-optimising agent approach
- The playbook's vagueness on judgment items is a deliberate design choice that produces the predicted failure mode
- The optimiser deliberately does not receive the NDA — it works from feedback only, mirroring Harvey's setup
- Ollama is already set up locally for LLM inference
- Claude drafts NDA, rubric, playbook, and sample outputs; author edits for legal accuracy

## Constraints

- **Runtime**: Ollama (local) — no API costs, reproducible
- **SDK**: OpenAI Python SDK with configurable base_url — works with any OpenAI-compatible endpoint
- **Environment**: uv for Python project management
- **Code style**: Black
- **Temperature**: 0 for all calls — reproducibility
- **JSON parsing**: Pydantic validation with retry (up to 3 attempts)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Same model for agent, judge, and optimiser | Simplicity; isolates the evaluation variable | -- Pending |
| Optimiser doesn't see NDA | Mirrors Harvey's approach; smaller context window for local model | -- Pending |
| Vague playbook for judgment items | Realistic; produces the predicted failure mode the thesis tests | -- Pending |
| Loop only, no Streamlit | Focus on core experiment; viz is a separate task | -- Pending |
| Claude drafts legal content, author edits | Legal accuracy requires human judgment; Claude provides structure | -- Pending |
| Canonical experiment model is `gemma4:26b` | Installed on local host; verified working end-to-end in Phase 2 live integration smoke (run_agent + run_judge returning 8/8 scored rubric items); avoids ~19 GB pull of qwen2.5:32b | Confirmed 2026-04-11 post-Phase-2 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-12 after Phase 5 completion — all v1 phases complete*
