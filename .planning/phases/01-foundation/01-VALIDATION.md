---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (installed as dev dependency) |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | SETP-01 | — | N/A | integration | `uv sync && uv run python -c "from src.models import ExperimentRun"` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | MODL-01 | — | N/A | unit | `uv run pytest tests/test_models.py -v` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | CONF-01 | — | N/A | unit | `uv run pytest tests/test_config.py -v` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | DATA-01 | — | N/A | manual | Inspect data/nda.md for 4 issues + numbered sections | ❌ | ⬜ pending |
| 01-02-02 | 02 | 1 | DATA-02 | — | N/A | unit | `uv run pytest tests/test_rubric.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_models.py` — stubs for MODL-01, MODL-02
- [ ] `tests/test_config.py` — stubs for CONF-01, CONF-02
- [ ] `tests/test_rubric.py` — validates rubric.json has 8 items with correct schema
- [ ] `pytest` added as dev dependency in pyproject.toml

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| NDA has 4 embedded issues with numbered sections | DATA-01 | Legal content quality requires human review | Read data/nda.md, verify 4 issues present, clauses numbered |
| Playbook has precise extraction + vague judgment guidance | DATA-03 | Vagueness calibration is subjective | Read data/playbook.md, compare extraction vs judgment descriptions |
| Output A correctly identifies all 4 issues | DATA-04 | Legal judgment quality | Read data/output_a.md, verify all 4 issues + judgment calls present |
| Output B nails extraction but misses judgment | DATA-05 | Calibration between A and B is subjective | Read data/output_b.md, verify extraction correct + judgment missing |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
