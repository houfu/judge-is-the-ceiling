---
phase: 5
slug: main-loop
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `uv run pytest -q -m "not integration" tests/test_loop.py` |
| **Full suite command** | `uv run pytest -q -m "not integration"` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m "not integration" tests/test_loop.py`
- **After every plan wave:** Run `uv run pytest -q -m "not integration"`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | LOOP-01 | — | N/A | unit | `uv run pytest -q tests/test_loop.py -k "test_happy_path"` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | LOOP-02 | — | N/A | unit | `uv run pytest -q tests/test_loop.py -k "test_iteration_result"` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | LOOP-03 | — | N/A | unit | `uv run pytest -q tests/test_loop.py -k "test_metadata"` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | LOOP-04 | — | N/A | unit | `uv run pytest -q tests/test_loop.py -k "test_resilience"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_loop.py` — stubs for LOOP-01, LOOP-02, LOOP-03, LOOP-04
- [ ] Reuse existing `tests/conftest.py` — FakeClient fixture already available

*Existing test infrastructure (pytest, conftest.py, FakeClient) covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full experiment run against Ollama | LOOP-01 | Requires local Ollama with gemma4:26b | `uv run python src/loop.py` — verify results/run_001.json written with N iterations |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
