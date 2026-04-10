# Phase 1: Foundation - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Project skeleton (uv, dependencies), Pydantic data models, configuration module, and all 5 static data files (NDA, rubric, playbook, output A, output B). No LLM calls in this phase — everything here is consumed by Phase 2+.

</domain>

<decisions>
## Implementation Decisions

### NDA Design
- **D-01:** NDA length ~1500 words (medium). Enough for issues to feel natural among standard clauses while staying within context window headroom for local Ollama models.
- **D-02:** Issues are lightly hidden — standard clause headings, detectable by careful reading. Tests whether the agent reads thoroughly, not whether it can decode obfuscation.
- **D-03:** Numbered sections format (1. Definitions, 2. Obligations, etc.) — standard commercial NDA style. Prevents model hallucination of clause numbers.
- **D-04:** Governing law is Singapore. NDA content uses generic commercial language but governing law clause references Singapore.
- **D-05:** Neutral review perspective — agent identifies issues for either side, no stated party perspective.
- **D-06:** Boilerplate-realistic standard clauses — entire agreement, severability, notices, assignment, waiver. The NDA should feel like a real agreement so the 4 embedded issues don't stand out structurally.

### Rubric Calibration
- **D-07:** Playbook is minimally vague for judgment items — gives general direction but lacks specifics. E.g., "Score 2 if the agent provides a substantive assessment of the practical effect." Not maximally vague ("demonstrates good legal judgment") and not artificially imprecise.
- **D-08:** Partial credit (score=1) for judgment items is deliberately fuzzy — mirrors the judgment vagueness in the playbook. The 0/1/2 boundary for judgment items should be harder for the judge to apply than for extraction items.
- **D-09:** Rubric JSON is minimal: item_id, item_type (extraction/judgment), issue_number, question, max_score. Scoring guidance lives in the playbook only, not duplicated in rubric.json.

### Claude's Discretion
- Data model schema design (Pydantic field names, nesting, aggregation logic)
- Sample review content (Output A and Output B) — Claude drafts, author edits for legal accuracy
- Config module structure (dataclass vs dict, env var naming)
- Project layout (src/ package structure, __init__.py files)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Experiment Design
- `prd.md` — Full PRD with NDA issue table, rubric items, data model JSON shapes, sequence of work, and technical decisions

### Research
- `.planning/research/STACK.md` — Recommended stack, Pydantic patterns, pyproject.toml template
- `.planning/research/PITFALLS.md` — P13 (clause hallucination), P14 (markdown fences), P15 (results gitignore)
- `.planning/research/FEATURES.md` — Table stakes features, MVP recommendation

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code

### Established Patterns
- None — patterns will be established in this phase

### Integration Points
- None — this is the foundation phase

</code_context>

<specifics>
## Specific Ideas

- The PRD (section 5) contains exact JSON shapes for ExperimentRun, PreLoopTestResult, IterationResult, and HumanReview — use these as the starting point for Pydantic models
- The PRD (section 3.4) contains the iteration zero system prompt — include in data/ or as a constant
- Research STACK.md contains a complete pyproject.toml template with exact dependency versions
- Research STACK.md contains the Config dataclass pattern with os.getenv defaults

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-04-11*
