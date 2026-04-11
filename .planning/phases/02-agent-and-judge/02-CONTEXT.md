# Phase 2: Agent and Judge - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Build two library functions (no loop, no CLI):

- `run_agent(system_prompt, nda_text) -> str` — calls Ollama via the OpenAI SDK, returns the agent's free-text NDA review.
- `run_judge(nda_text, agent_output, rubric, playbook) -> JudgeResult` — calls Ollama, parses the response into a validated `JudgeResult`, retries on `ValidationError` / `JSONDecodeError` up to 3 times, strips markdown fences, sets `num_ctx` explicitly, and returns a graceful failure result on retry exhaustion instead of raising.

Out of scope for this phase: the pre-loop test driver (Phase 3), the optimiser (Phase 4), and the main loop that sequences agent → judge → log → optimiser (Phase 5). This phase delivers the two building blocks that those later phases will import and call.

</domain>

<decisions>
## Implementation Decisions

### Client Wiring
- **D-01:** A shared client factory lives at `src/llm.py` exposing `get_client() -> OpenAI`. Both `agent.py` and `judge.py` import from it. Rationale: one place to set `base_url` / `api_key` / timeouts, and one place to pass Ollama-specific options like `num_ctx`.
- **D-02:** `num_ctx` default is **16384** — roughly 4.7× the ~5700-token minimum estimate (NDA ~1875 + rubric+playbook ~1500 + agent output ~800 + judge response ~1500). Chosen for headroom over long judge reasoning and growing agent system prompts in Phase 5 iterations.
- **D-03:** `num_ctx` is configurable via the `NUM_CTX` env var on `Config` with a default of 16384. Add `num_ctx: int = 16384` to the `Config` dataclass in `src/config.py` and read `NUM_CTX` in `Config.from_env()`.
- **D-04:** `num_ctx` is applied to **every** LLM call — agent and judge — by passing `extra_body={"options": {"num_ctx": config.num_ctx}}` on `client.chat.completions.create(...)`. Matches pitfall P6 guidance ("set num_ctx explicitly on every API call") and future-proofs Phase 5 where system prompts grow across iterations.

### Judge Prompt Layout
- **D-05:** Two-message request: `system` role holds the task description, the JSON output schema, the concrete example, and the "no preamble, no markdown fences" instruction. `user` role holds the case data (NDA, agent output, rubric, playbook). Rationale: the task rules stay stable across retries; only the data varies between runs.
- **D-06:** Data blocks inside the `user` message are delimited with **markdown headings**: `## NDA`, `## Agent Output`, `## Rubric`, `## Playbook`, in that order.
- **D-07:** ⚠️ **Heading-collision mitigation (MANDATORY for planner/executor):** The agent's free-text review is itself markdown and will very likely contain `##` headings. The planner MUST choose a heading style for the judge prompt that the agent output cannot collide with. Two acceptable approaches:
  - Use a distinctive prefix like `## === NDA ===` / `## === AGENT OUTPUT ===` / etc.
  - Use top-level `#` headings for the judge's section dividers and rely on the fact that the agent never generates `#` (only `##` and below).
  Either is fine, but the chosen approach must be consistent and documented in a comment in `judge.py`.
- **D-08:** The rubric is serialised into the prompt as **raw JSON, verbatim** — read `data/rubric.json` and paste the contents into the `## Rubric` section. No transformation, no table, no prose rendering. Keeps `item_id` and `issue_number` identical between input and expected output.
- **D-09:** The output schema is communicated via **one concrete JSON example** of a single-item `JudgeResult` response (plus a short field-list sentence for the unused fields). Exactly one example — avoid multi-shot examples that could contaminate the judge's scoring behaviour with anchoring effects.
- **D-10:** The system message explicitly instructs: "Return only valid JSON. No preamble. No markdown code fences. No commentary before or after the JSON."

### Claude's Discretion
The following were deliberately left for the planner to decide based on RESEARCH.md and PITFALLS.md, not asked during discuss-phase:

- **Graceful failure shape (JUDG-05):** what exactly `run_judge()` returns after 3 retries exhaust — sentinel `JudgeResult` with all-zero `RubricScore` entries, `JudgeResult | None`, or a dedicated failure wrapper. Planner should pick whatever is simplest for Phase 3 (`pre_loop_test.py`) and Phase 5 (main loop) to consume, and MUST ensure the raw output is logged before the return per P7.
- **Markdown fence stripping helper:** regex approach (`re.search(r'\{.*\}', raw, re.DOTALL)` per P14), explicit `` ```json `` fence removal, or both — planner's choice. The helper should live in a small utility function (e.g. `_extract_json(raw: str) -> str`) in `judge.py`, not in `models.py`.
- **Retry error feedback format:** what error text is sent back to the model on validation failure. Must include enough of the `ValidationError` / `JSONDecodeError` message for the model to self-correct (per P7), plus the fixed reminder "Return only valid JSON. No preamble. No markdown fences." Planner decides verbosity and truncation.
- **Agent function signature details:** `run_agent` message construction (single user message vs system+user), temperature sourcing (hard-coded 0 vs `config.temperature`), and whether the agent call also passes `response_format`. Research says don't use `response_format` — follow that.
- **Logging:** use stdlib `logging` at INFO level (no `structlog` / `loguru` per STACK.md "What NOT to Use"). On retry-exhaustion in `run_judge`, log the raw response body and the final `ValidationError` message. Logger name convention: `jitc.agent` and `jitc.judge`.
- **Where iteration-zero system prompt lives:** Phase 1 CONTEXT.md §Specific Ideas notes the PRD §3.4 contains an iteration-zero agent system prompt. The planner should decide whether it's introduced in Phase 2 (as a constant in `src/agent.py` or a file in `data/`) or left entirely to Phase 5. Recommendation: introduce as `ITERATION_ZERO_SYSTEM_PROMPT` constant in `src/agent.py` so Phase 3's `pre_loop_test.py` has something to import if needed, but do not build any optimiser or loop wiring.
- **Test vectors for Phase 2 deliverable check:** Success criterion 3 ("a deliberately malformed call demonstrates retry behaviour") implies some kind of smoke test / demonstration. Planner decides whether that's a standalone script, a module `__main__` block, or a documented manual test.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Research (locks most of the how)
- `.planning/research/STACK.md` — Ollama client config, sync vs async choice, retry pattern skeleton, `response_format` avoidance, "What NOT to Use" table
- `.planning/research/PITFALLS.md` — P2 (structure≠meaning), P4 (SDK+Ollama compat), P6 (num_ctx), P7 (retry masking), P8 (rubric vocab contamination), P12 (Pydantic v2 API), P14 (markdown fences)
- `.planning/research/FEATURES.md` — MVP feature scope for this phase

### Data Contracts (from Phase 1)
- `src/models.py` — `RubricScore`, `JudgeResult`, `IterationResult`, `ExperimentRun` Pydantic models (already built)
- `src/config.py` — `Config` dataclass with env-var loading (already built; planner will ADD `num_ctx` field per D-03)
- `data/rubric.json` — The 8-item rubric, to be pasted verbatim into the judge prompt (per D-08)
- `data/playbook.md` — Playbook text, pasted into judge prompt
- `data/nda.md` — Default NDA fixture (the agent and judge both read it at call time; Phase 2 functions take the text as a parameter, not a path)

### Project-Level
- `.planning/PROJECT.md` — Core value and constraints; Temperature=0 and Ollama-local are non-negotiable
- `.planning/REQUIREMENTS.md` §Agent, §Judge — AGNT-01/02, JUDG-01..05 acceptance criteria
- `prd.md` — Full PRD (Phase 1 context flagged this as having iteration-zero system prompt text in §3.4)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/config.py` — `Config` dataclass already has `model`, `base_url`, `api_key`, `temperature`, `num_iterations` with env-var loading. Phase 2 adds `num_ctx` here (D-03).
- `src/models.py` — `JudgeResult` and `RubricScore` are already defined; `run_judge` returns these as-is. The judge prompt's "one concrete example" (D-09) should mirror the actual field set of `RubricScore`: `item_id`, `item_type`, `issue_number`, `score`, `evidence`, `reasoning`, `feedback`.
- `data/rubric.json` — Contents are already in the exact shape that will be pasted into the judge prompt (D-08). No transformation needed.

### Established Patterns
- **Module-level singletons:** `src/config.py` ends with `config = Config.from_env()` — a module-level singleton. `src/llm.py` should follow the same pattern if a shared client instance is wanted, though a `get_client()` factory function is what D-01 commits to.
- **Dataclass + `from_env()` classmethod:** used by `Config`. Not directly reused by Phase 2 but worth matching if new configurable state appears.
- **`typing.Literal` for enums in Pydantic:** `RubricScore.item_type: Literal["extraction", "judgment"]` — use the same style if any new literals appear in Phase 2.

### Integration Points
- `src/llm.py` (new) — imported by `src/agent.py` (new) and `src/judge.py` (new).
- `src/agent.py` imports `get_client` from `src/llm.py` and `config` from `src/config.py`. Exposes `run_agent(system_prompt: str, nda_text: str) -> str`.
- `src/judge.py` imports `get_client`, `config`, `JudgeResult` from `src/models.py`. Exposes `run_judge(nda_text, agent_output, rubric, playbook) -> JudgeResult`. Rubric is passed as raw text (read from `data/rubric.json`) or as a list of dicts — planner's choice; the prompt embedding is raw JSON either way (D-08).
- No `src/loop.py` yet — do not create it in Phase 2.

</code_context>

<specifics>
## Specific Ideas

- The PRD §3.4 contains the iteration-zero agent system prompt text — if introducing it in Phase 2, put it in `src/agent.py` as `ITERATION_ZERO_SYSTEM_PROMPT` per the discretion note above. This prompt must NOT contain rubric or playbook vocabulary (AGNT-02 / pitfall P8).
- The retry pattern skeleton in `.planning/research/STACK.md` "Retry Pattern (3 attempts)" is the reference implementation — adapt it rather than reinventing. Note it currently `raise`s on final attempt; Phase 2 JUDG-05 requires replacing that `raise` with "log raw output + return graceful failure".
- When building the "deliberately malformed call demonstrates retry behaviour" check for success criterion 3, the simplest path is to monkeypatch the client to return invalid JSON on the first 1-2 attempts and valid JSON on the third, then assert that the retry path was exercised. Planner decides whether this is a pytest test, a `__main__` smoke script, or manual.
- Temperature 0 is non-negotiable (CONF-02 / project constraint) — do not allow any call site to override it.

</specifics>

<deferred>
## Deferred Ideas

- **Graceful failure shape, fence stripping strategy, retry feedback verbosity** — intentionally left to the planner (see "Claude's Discretion" in decisions). User chose not to discuss these explicitly; they are fully pinned by research + pitfalls.
- **Judge reasoning content validators** (P2): length minimums, rubric-reference checks. Noted in PITFALLS.md as a future mitigation; NOT in scope for Phase 2. Revisit if the pre-loop test in Phase 3 shows the judge returning empty/formulaic reasoning.
- **Logging raw outputs to files** (vs stdlib logging only) — may become necessary if Phase 3 pre-loop test diagnostics are insufficient. Not in Phase 2 scope.
- **Alternative num_ctx values per call** — some future hardware-constrained setup may want 8192 for agent, 16384 for judge. Not needed now; one env var is enough.

</deferred>

---

*Phase: 02-agent-and-judge*
*Context gathered: 2026-04-11*
