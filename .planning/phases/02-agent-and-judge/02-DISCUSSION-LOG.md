# Phase 2: Agent and Judge - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-11
**Phase:** 02-agent-and-judge
**Areas discussed:** Client wiring + num_ctx, Judge prompt layout

---

## Gray Area Selection

Four gray areas were offered. User selected 2:

| Option | Description | Selected |
|--------|-------------|----------|
| Client wiring + num_ctx | Shared `src/llm.py` client factory vs per-module instantiation; default num_ctx value; where num_ctx is passed | ✓ |
| Judge prompt layout | How to assemble the judge's messages: system+user split; block delimiters; rubric/schema format | ✓ |
| Graceful failure shape | What `run_judge()` returns after 3 retries exhaust | |
| Fence stripping + retry feedback | Exact fence-strip strategy; what error text is sent back on retries | |

**Note on unselected areas:** User deferred graceful failure shape and fence stripping / retry feedback to Claude's discretion. These are captured in CONTEXT.md §Claude's Discretion with references to the research + pitfalls that pin them down.

---

## Client wiring + num_ctx

### Q1: Where should the OpenAI/Ollama client live?

| Option | Description | Selected |
|--------|-------------|----------|
| Shared src/llm.py factory | `get_client()` function returning a configured OpenAI client. One place to set base_url/api_key/timeouts. | ✓ |
| Per-module instantiation | agent.py and judge.py each build their own `OpenAI(...)`. | |
| On Config dataclass | Add a `get_client()` method to `Config`. | |

**User's choice:** Shared src/llm.py factory (Recommended)

### Q2: What num_ctx value should the judge use?

Estimate shared with user: NDA ~1875 tok + rubric+playbook ~1500 tok + agent output ~800 tok + judge response ~1500 tok ≈ 5700 tok minimum.

| Option | Description | Selected |
|--------|-------------|----------|
| 8192 | ~2.4× the minimum estimate. Comfortable headroom. | |
| 16384 | 4.7× headroom. Safe for very long reasoning and future NDA growth. | ✓ |
| 4096 | Tight — risks silent truncation. | |

**User's choice:** 16384 (chose more headroom over the recommended default)

### Q3: How should num_ctx be configured — hard-coded or overridable?

| Option | Description | Selected |
|--------|-------------|----------|
| Env var with default | Add `num_ctx: int = 16384` to Config with `NUM_CTX` env var override. | ✓ |
| Module-level constant | `NUM_CTX = 16384` constant in src/llm.py. | |
| Hard-coded in each call site | Passed literal in each `extra_body`. | |

**User's choice:** Env var with default (Recommended)

### Q4: Should num_ctx apply to the agent call as well, or only the judge?

| Option | Description | Selected |
|--------|-------------|----------|
| Both agent and judge | Matches pitfall P6 'set explicitly on every API call'. Future-proofs Phase 5 where system prompts grow. | ✓ |
| Judge only | Only the judge context is really big enough to need it. Lighter touch. | |

**User's choice:** Both agent and judge (Recommended)

---

## Judge prompt layout

### Q1: How should the judge's messages be split between the `system` and `user` role?

| Option | Description | Selected |
|--------|-------------|----------|
| System=instructions, User=data | System holds task + schema + 'no preamble' rules; user holds NDA+output+rubric+playbook. | ✓ |
| Single user message, no system | Everything in one user message. | |
| System=instructions+rubric+playbook, User=NDA+agent output | Fixed evaluation criteria in system, case data in user. | |

**User's choice:** System=instructions, User=data (Recommended)

### Q2: How should the blocks inside the user message be delimited?

| Option | Description | Selected |
|--------|-------------|----------|
| XML-style tags | `<nda>...</nda>` etc. Strongest delimiter, won't collide. | |
| Markdown headings | `## NDA`, `## Agent Output`, etc. — readable, but agent output also contains `##` headings. | ✓ |
| Labelled plain-text dividers | `=== NDA ===` etc. Simple, unlikely to collide. | |

**User's choice:** Markdown headings
**Notes:** CONTEXT.md D-07 flags this as a mandatory collision-mitigation concern for the planner — the planner must choose a heading style that the agent markdown output cannot collide with (distinctive prefix like `## === NDA ===`, or top-level `#` headings that the agent never uses).

### Q3: The rubric is a JSON array with 8 items. How should it be serialised?

| Option | Description | Selected |
|--------|-------------|----------|
| Raw JSON, as-is | Paste `rubric.json` verbatim. | ✓ |
| Numbered prose list | Render each item as '1a (extraction, issue 1): ...'. | |
| Markdown table | Columns: item_id / item_type / issue_number / question. | |

**User's choice:** Raw JSON, as-is (Recommended)

### Q4: Should the judge receive the output schema as Pydantic text, a JSON example, or both?

| Option | Description | Selected |
|--------|-------------|----------|
| Concrete JSON example | One-item example showing expected shape. Local models imitate format-by-example well. | ✓ |
| Field list prose | Describe each field in prose, no example. | |
| Both example and field list | Belt-and-suspenders. More tokens, stronger signal. | |

**User's choice:** Concrete JSON example (Recommended)

---

## Claude's Discretion

Areas where the user explicitly deferred to Claude's discretion (left out of discuss-phase entirely; pinned by research + pitfalls):

- **Graceful failure shape (JUDG-05)** — exact return type on retry exhaustion
- **Markdown fence stripping approach** — regex vs explicit fence removal vs both
- **Retry error feedback format** — what ValidationError text is sent back to the model
- **Agent function signature details** — message structure, temperature sourcing
- **Logging** — stdlib logging level/naming, what to log on failure
- **Iteration-zero system prompt location** — introduced in Phase 2 or Phase 5

## Deferred Ideas

- **Judge reasoning content validators (P2)** — length minimums, rubric reference checks. Out of Phase 2 scope; revisit after Phase 3 pre-loop test.
- **Logging raw outputs to files** — may become necessary if stdlib logging is insufficient. Out of scope for now.
- **Per-call num_ctx values** (agent vs judge different) — not needed; one env var suffices.
