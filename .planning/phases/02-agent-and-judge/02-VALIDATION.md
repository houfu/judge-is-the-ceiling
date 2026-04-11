---
phase: 2
slug: agent-and-judge
status: active
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-11
updated: 2026-04-11
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (Plan 02-01 Task 1 installs as dev dependency) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` (Plan 02-01 Task 1 creates) |
| **Quick run command** | `uv run pytest -q -m "not integration"` |
| **Full suite command** | `uv run pytest -q` (includes integration when Ollama is running) |
| **Estimated runtime** | ~5-15 seconds (unit only); ~30-90 seconds with integration (depends on local Ollama model) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m "not integration"` (unit tests only — no live Ollama dependency)
- **After every plan wave:** Run `uv run pytest -q -m "not integration"` (integration smoke gated behind `-m integration` and a local Ollama check)
- **Before `/gsd-verify-work`:** Full suite must be green, including `-m integration` if Ollama is running
- **Max feedback latency:** 15 seconds (unit only)

---

## Per-Task Verification Map

*Populated by the planner. Every task with a requirement ID maps to an automated verify command or a Wave 0 test stub.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-T1 | 02-01 | 0 | CONF-01 (num_ctx extension) | — | Config.num_ctx defaults to 16384, NUM_CTX env var overrides | config check | `uv run python -c "from src.config import config; assert config.num_ctx == 16384"` | ✅ (plan 02-01) | ⬜ pending |
| 02-01-T2 | 02-01 | 0 | JUDG-04 (A1 assumption) | T-02-01 | Live Ollama honours `extra_body={'options':{'num_ctx':16384}}` | live smoke | `uv run python -c "from src.llm import get_client; from src.config import config; get_client().chat.completions.create(model=config.model, messages=[{'role':'user','content':'pong'}], temperature=0, extra_body={'options':{'num_ctx':16384}})"` | ✅ (plan 02-01) | ⬜ pending |
| 02-01-T3 | 02-01 | 0 | (infra) | — | tests/ package + FakeClient fixture importable | unit | `uv run pytest tests/test_llm.py -q` | ✅ (plan 02-01) | ⬜ pending |
| 02-02-T1 | 02-02 | 1 | AGNT-01, AGNT-02 (RED) | — | Tests exist and fail on missing src/agent.py | unit | `uv run pytest tests/test_agent.py -q -m "not integration"` (non-zero exit expected) | ✅ (plan 02-02) | ⬜ pending |
| 02-02-T2 | 02-02 | 1 | AGNT-01 | T-02-A02 | run_agent returns content, calls create with correct messages/temperature/extra_body | unit (FakeClient) | `uv run pytest tests/test_agent.py::test_run_agent_returns_content tests/test_agent.py::test_run_agent_calls_create_with_two_messages tests/test_agent.py::test_run_agent_passes_num_ctx_and_temperature tests/test_agent.py::test_run_agent_handles_none_content -q` | ✅ (plan 02-02) | ⬜ pending |
| 02-02-T2 | 02-02 | 1 | AGNT-02 | T-02-A03 | ITERATION_ZERO_SYSTEM_PROMPT contains no banned rubric vocabulary | unit | `uv run pytest tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab -q` | ✅ (plan 02-02) | ⬜ pending |
| 02-03-T1 | 02-03 | 1 | JUDG-01..05 (RED) | — | All judge tests exist and fail on missing src/judge.py | unit | `uv run pytest tests/test_judge.py -q -m "not integration"` (non-zero exit expected) | ✅ (plan 02-03) | ⬜ pending |
| 02-03-T2 | 02-03 | 1 | JUDG-01 | T-02-J01 | run_judge happy path returns JudgeResult with 8 scores | unit (FakeClient, VALID_JUDGE_JSON) | `uv run pytest tests/test_judge.py::test_happy_path_returns_judge_result tests/test_judge.py::test_happy_path_returns_judge_result_from_fenced_json -q` | ✅ (plan 02-03) | ⬜ pending |
| 02-03-T2 | 02-03 | 1 | JUDG-02 | T-02-J01 | 3 retries with error feedback; messages grow by 2 per failed attempt | unit (FakeClient seq: bad, bad, good) | `uv run pytest tests/test_judge.py::test_retries_three_times_with_error_feedback tests/test_judge.py::test_retry_recovers_on_second_attempt -q` | ✅ (plan 02-03) | ⬜ pending |
| 02-03-T2 | 02-03 | 1 | JUDG-03 | — | _extract_json strips fences, handles nested objects, falls back on no braces | unit | `uv run pytest tests/test_judge.py::test_extract_json_strips_fences tests/test_judge.py::test_extract_json_strips_prose_preamble tests/test_judge.py::test_extract_json_handles_nested_objects tests/test_judge.py::test_extract_json_falls_back_to_raw_when_no_braces -q` | ✅ (plan 02-03) | ⬜ pending |
| 02-03-T2 | 02-03 | 1 | JUDG-04 | — | num_ctx in extra_body on every call including retries (D-04, P6) | unit (FakeClient, 3-call sequence) | `uv run pytest tests/test_judge.py::test_num_ctx_in_every_call -q` | ✅ (plan 02-03) | ⬜ pending |
| 02-03-T2 | 02-03 | 1 | JUDG-05 | T-02-J02 | Retry exhaustion returns JudgeResult(scores=[]), logs raw+error at ERROR, no raise | unit (caplog) | `uv run pytest tests/test_judge.py::test_graceful_failure_on_retry_exhaustion tests/test_judge.py::test_graceful_failure_logs_raw_output tests/test_judge.py::test_warning_logged_on_every_parse_failure -q` | ✅ (plan 02-03) | ⬜ pending |
| 02-03-T3 | 02-03 | 1 | (full sweep) | — | All 19+ unit tests pass together; no banned patterns; black clean | unit + lint | `uv run pytest -q -m "not integration" && uv run black --check src/ tests/` | ✅ (plan 02-03) | ⬜ pending |
| 02-04-T1 | 02-04 | 2 | AGNT-01 | T-02-S02 | Live Ollama returns non-empty agent review | integration | `uv run pytest -q -m integration tests/test_smoke_ollama.py::test_agent_smoke` | ✅ (plan 02-04) | ⬜ pending |
| 02-04-T1 | 02-04 | 2 | JUDG-01 | T-02-S02 | Live Ollama returns a valid JudgeResult (scores non-empty) | integration | `uv run pytest -q -m integration tests/test_smoke_ollama.py::test_judge_smoke` | ✅ (plan 02-04) | ⬜ pending |
| 02-04-T2 | 02-04 | 2 | JUDG-01 (P2) | — | Human confirms reasoning strings are specific and cite NDA | manual checkpoint | (human eyeball — see Plan 02-04 checkpoint task) | ✅ (plan 02-04) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements (owned by Plan 02-01)

- [ ] Install pytest as dev dependency: `uv add --dev pytest` (Task 1)
- [ ] Create `pyproject.toml [tool.pytest.ini_options]` block with `markers = ["integration: requires live Ollama endpoint"]` (Task 1)
- [ ] Add `num_ctx: int = 16384` to Config dataclass with NUM_CTX env var override (Task 1)
- [ ] Create `src/llm.py` with `get_client()` factory (Task 2)
- [ ] Verify assumption A1 with a live Ollama smoke call passing `extra_body={"options": {"num_ctx": 16384}}` — STOP phase if it fails (Task 2)
- [ ] Create `tests/__init__.py` (Task 3)
- [ ] Create `tests/conftest.py` with `FakeClient` + `fake_client` fixture + `VALID_JUDGE_JSON` (Task 3)
- [ ] Create `tests/test_llm.py` with `test_get_client_returns_singleton` (Task 3)
- [ ] Create stub files `tests/test_agent.py`, `tests/test_judge.py`, `tests/test_smoke_ollama.py` for Wave 1 and Wave 2 to fill in (Task 3)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Qualitative review of iteration-zero agent prompt against rubric/playbook vocabulary | AGNT-02 / P8 | Automated vocab-collision test can only catch exact tokens — human eyeballs catch paraphrases | After Wave 1, read `ITERATION_ZERO_SYSTEM_PROMPT` in `src/agent.py` side-by-side with `data/rubric.json` and `data/playbook.md`; confirm no concepts leak. Handled informally by the executor during Plan 02-02. |
| Judge reasoning strings are "real", not formulaic (P2) | JUDG-01 | Structure-valid but meaningless reasoning is a semantic concern Pydantic can't detect | Plan 02-04 Task 2 is a blocking checkpoint. Human reads 3 `reasoning` strings from `data/output_a.md` smoke test and confirms they cite the NDA, not the rubric. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (FakeClient, pytest install, markers config, num_ctx field, get_client factory)
- [x] No watch-mode flags (pytest runs are one-shot)
- [x] Feedback latency < 15s (unit suite only)
- [x] `nyquist_compliant: true` set in frontmatter (populated after task map above)

**Approval:** approved by planner 2026-04-11
