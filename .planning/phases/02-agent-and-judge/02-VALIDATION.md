---
phase: 2
slug: agent-and-judge
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (Wave 0 installs as dev dependency) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` (Wave 0 creates) |
| **Quick run command** | `uv run pytest -q -m "not integration"` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~5-15 seconds (unit only); ~30-90 seconds with integration (depends on local Ollama model) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m "not integration"` (unit tests only — no live Ollama dependency)
- **After every plan wave:** Run `uv run pytest -q -m "not integration"` (integration smoke gated behind `-m integration` and a local Ollama check)
- **Before `/gsd-verify-work`:** Full suite must be green, including `-m integration` if Ollama is running
- **Max feedback latency:** 15 seconds (unit only)

---

## Per-Task Verification Map

*Populated by the planner during plan authoring. Every task with a requirement ID must map to an automated verify command or a Wave 0 test stub.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD by planner | | | AGNT-01 | — | Agent returns non-empty str against live Ollama | integration | `uv run pytest -q -m integration tests/test_agent.py::test_live_round_trip` | ❌ W0 | ⬜ pending |
| TBD by planner | | | AGNT-02 | — | Iteration-zero prompt has zero rubric vocabulary | unit | `uv run pytest -q tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab` | ❌ W0 | ⬜ pending |
| TBD by planner | | | JUDG-01 | — | run_judge returns JudgeResult with 8 scored items | unit | `uv run pytest -q tests/test_judge.py::test_happy_path_returns_judge_result` | ❌ W0 | ⬜ pending |
| TBD by planner | | | JUDG-02 | — | 3 retries on ValidationError, error text fed back each retry | unit | `uv run pytest -q tests/test_judge.py::test_retries_three_times_with_error_feedback` | ❌ W0 | ⬜ pending |
| TBD by planner | | | JUDG-03 | — | Markdown fences stripped before parse | unit | `uv run pytest -q tests/test_judge.py::test_strips_markdown_fences` | ❌ W0 | ⬜ pending |
| TBD by planner | | | JUDG-04 | — | num_ctx appears in every OpenAI call's extra_body | unit | `uv run pytest -q tests/test_judge.py::test_num_ctx_in_every_call` | ❌ W0 | ⬜ pending |
| TBD by planner | | | JUDG-05 | — | Retry exhaustion returns sentinel JudgeResult (scores=[]), logs raw output, doesn't raise | unit | `uv run pytest -q tests/test_judge.py::test_graceful_failure_on_retry_exhaustion` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Install pytest as dev dependency: `uv add --dev pytest pytest-mock` (or just `pytest`; `pytest-mock` is optional)
- [ ] Create `pyproject.toml [tool.pytest.ini_options]` block with `markers = ["integration: requires live Ollama endpoint"]`
- [ ] Create `tests/__init__.py` (empty) and `tests/conftest.py` with:
  - `FakeClient` fixture that captures all `chat.completions.create(...)` calls and returns scripted responses
  - `fake_config` fixture overriding `src.config.config` with deterministic values
- [ ] Create `tests/test_llm.py` stubs — at minimum one test asserting `get_client()` returns a cached singleton
- [ ] Create `tests/test_agent.py` stubs — at minimum one unit test for `run_agent` happy path with `FakeClient`, plus one stub marked `@pytest.mark.integration` for live Ollama
- [ ] Create `tests/test_judge.py` stubs — happy path, fence strip, retry-with-feedback, graceful-failure, num_ctx-in-extra_body (5 unit tests), plus one `@pytest.mark.integration` live round-trip
- [ ] **Wave 0 preflight verification task:** run one live `client.chat.completions.create(model=config.model, messages=[...], extra_body={"options": {"num_ctx": 16384}})` against local Ollama to confirm the `extra_body.options.num_ctx` path is honoured by the Ollama OpenAI adapter (flagged as assumption A1 in RESEARCH.md). If it fails, STOP — the whole plan rests on this.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Qualitative review of iteration-zero agent prompt against rubric/playbook vocabulary | AGNT-02 / P8 | Automated vocab-collision test can only catch exact tokens — human eyeballs catch paraphrases | After Wave 1, read `ITERATION_ZERO_SYSTEM_PROMPT` in `src/agent.py` side-by-side with `data/rubric.json` and `data/playbook.md`; confirm no concepts leak. |
| Judge reasoning strings are "real", not formulaic (P2) | JUDG-01 | Structure-valid but meaningless reasoning is a semantic concern Pydantic can't detect | After integration smoke test runs, manually inspect 2-3 returned `RubricScore.reasoning` strings to confirm they cite the NDA, not the rubric. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (FakeClient, pytest install, markers config)
- [ ] No watch-mode flags (pytest runs are one-shot)
- [ ] Feedback latency < 15s (unit suite only)
- [ ] `nyquist_compliant: true` set in frontmatter — set by planner after task map is populated

**Approval:** pending
