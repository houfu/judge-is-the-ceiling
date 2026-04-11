---
phase: 02-agent-and-judge
reviewer: gsd-code-fixer (Claude)
date: 2026-04-11
status: all_fixed
review_path: .planning/phases/02-agent-and-judge/02-REVIEW.md
findings_in_scope: 2
fixed: 2
skipped: 0
iteration: 1
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-04-11
**Source review:** `.planning/phases/02-agent-and-judge/02-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (medium+): 2
- Fixed: 2
- Skipped: 0

Scope was `critical_warning` — only medium-or-higher findings. The 4 LOW and
3 INFO findings in REVIEW.md were intentionally not touched. Post-fix
verification: `uv run pytest -q -m "not integration"` → **21 passed,
2 deselected**; `uv run black --check src/ tests/` → **12 files would be
left unchanged**.

## Fixed Issues

### M-01: `src/llm.py` module-level `_client` singleton leaks between tests

**Severity:** medium
**Files modified:** `tests/conftest.py`
**Commit:** `1a58e59`

**Original issue:** `test_get_client_returns_singleton` creates a real
`OpenAI` instance and never resets `src.llm._client`. The `fake_client`
fixture uses `monkeypatch.setattr(src.llm, "_client", client)`, which
restores to whatever value was present when the fixture ran. If
`test_llm.py` runs first and leaks a real client into the module global,
the restore target is that real client rather than `None`. No active
failure, but fragile against test-ordering changes in Phase 3+.

**Applied fix:** Added an `autouse=True` fixture `_reset_llm_singleton` in
`tests/conftest.py` that runs `monkeypatch.setattr(src.llm, "_client", None)`
before every test. Because the autouse fixture runs before the `fake_client`
fixture inside any given test, `_client` is always `None` when `fake_client`
captures its restore target. After teardown, `_client` is deterministically
back to `None`, matching the documented pre-test module state.

Verification:
- Tier 1: Re-read `tests/conftest.py` — fixture present, indentation correct.
- Tier 2: `python -c "import ast; ast.parse(...)"` — passes.
- Tier 2: `uv run pytest -q -m "not integration"` — 21 passed, 2 deselected.

### M-02: D-07 heading-collision mitigation is incomplete for NDA input

**Severity:** medium
**Files modified:** `src/judge.py`, `tests/test_judge.py`
**Commit:** `7fe3f67`

**Original issue:** `_build_user_message` used plain top-level markdown
headings (`# NDA`, `# AGENT OUTPUT`, `# RUBRIC`, `# PLAYBOOK`) as section
dividers. The D-07 rationale claimed this prevents collision "because the
agent uses `##` and below" — but `data/nda.md` itself starts with `# NDA`,
so any real NDA (benign or malicious) can contain literal `# AGENT OUTPUT`
or `# RUBRIC` lines that would confuse section boundaries. T-02-J01
documents prompt-injection as accepted residual risk, but D-07's
*prevention* claim was incorrect.

**Applied fix:** Switched the envelope to distinctive
`# === JITC_*_START ===` / `# === JITC_*_END ===` markers for each of the
four sections (NDA, AGENT_OUTPUT, RUBRIC, PLAYBOOK). These strings are
vanishingly unlikely to appear verbatim in a legitimate NDA or agent
output, so accidental collision is eliminated and intentional collision
requires deliberate effort (residual risk still accepted under T-02-J01 —
the judge has no tool access and outputs a Pydantic-validated `JudgeResult`,
so worst case is biased scoring, which the Phase 3 pre-loop test catches).

Changes:
1. `src/judge.py` module docstring: rewrote the D-07 bullet to describe the
   distinctive envelope and correctly state the threat model (collision
   prevention is robust for legitimate input; prompt-injection risk from
   crafted NDAs remains accepted under T-02-J01).
2. `src/judge.py::_build_user_message`: replaced all four `# NDA` /
   `# AGENT OUTPUT` / `# RUBRIC` / `# PLAYBOOK` headings with
   `# === JITC_{section}_START ===` … `# === JITC_{section}_END ===`
   envelopes. Fixed ordering preserved (D-06): NDA → Agent Output →
   Rubric → Playbook.
3. `tests/test_judge.py::test_build_user_message_uses_top_level_headings`:
   updated assertions to check the new START/END envelope markers, the
   payload body content, and (new) explicit ordering assertions via
   `result.index(...)`. Docstring reworded to match the envelope-based
   rationale. Test name left unchanged to preserve history; the "top-level
   headings" phrasing is still accurate (the envelope lines begin with
   `# `).

Other tests that touch the envelope (e.g. `test_retries_three_times_with_error_feedback`
inspecting `messages`) rely only on role/content, not envelope content,
so they remain green.

**Note on logic verification:** M-02 is partly a semantic/threat-model fix.
Tier 2 syntax checks and the existing unit suite confirm the code parses
and `_build_user_message` still concatenates in the correct order with the
correct payload bodies. The semantic property "no collision with NDA
content" is asserted by design (the JITC envelope is unique) rather than
by automated test. Human reviewer should confirm the D-07 docstring
accurately reflects the current threat model.

Verification:
- Tier 1: Re-read `src/judge.py` and `tests/test_judge.py` — changes present
  and correct.
- Tier 2: `python -c "import ast; ast.parse(...)"` — passes for both files.
- Tier 2: `uv run pytest -q -m "not integration"` — 21 passed, 2 deselected.
- Tier 2: `uv run black --check src/ tests/` — all 12 files unchanged.

## Skipped Issues

None — both in-scope findings fixed cleanly.

## Out-of-Scope Findings

The following LOW/INFO findings from REVIEW.md were intentionally not
addressed (scope = `critical_warning`):

- **L-01** `_extract_json` greedy regex edge case (retry loop compensates)
- **L-02** `test_retry_user_message_bounded` loose ceiling
- **L-03** `_client` type annotation without `from __future__ import annotations`
- **L-04** `list[dict]` should be `list[dict[str, str]]`
- **I-01** `test_get_client_returns_singleton` constructs real OpenAI client
  (partly mitigated by M-01's autouse reset fixture)
- **I-02** Tests read live `config` singleton
- **I-03** `data/nda.md` no size guard in smoke test

These can be picked up in a follow-up pass or deferred to Phase 3+ cleanup.

---

_Fixed: 2026-04-11_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
