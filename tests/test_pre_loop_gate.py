"""Live integration test for the Phase 3 pre-loop validation gate.

Gated behind @pytest.mark.integration (same pattern as
tests/test_smoke_ollama.py). Run with:

    uv run pytest -q -m integration tests/test_pre_loop_gate.py

Prerequisites:
- Ollama running on localhost:11434
- The configured model pulled (default: gemma4:26b; override with MODEL=...)

This test writes `results/pre_loop_test.json` as a real side effect. The
file is gitignored and each run overwrites the last — this is intentional
per CONTEXT.md D-09. Do NOT wrap run_pre_loop_test in tmp_path or mock
the target path; the test must prove the production artifact path works.

Asserts (in order of strictness):
1. result.decision == "go"             — SC-4 (the gate itself)
2. result.gap >= result.threshold      — SC-2 (at least 2.0 points)
3. result.judgment_gap > 0             — SC-3 (thesis-critical signal)
4. results/pre_loop_test.json exists   — SC-1 (artifact written)

The assertions are ordered so the first failure is the most informative:
decision tells the human "gate failed"; gap tells them "because total was
too close"; judgment_gap tells them "and the judgment signal was absent".
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RESULTS_FILE = _REPO_ROOT / "results" / "pre_loop_test.json"


def test_pre_loop_gate_passes():
    from src.pre_loop_test import run_pre_loop_test

    result = run_pre_loop_test()

    # Primary gate assertion — SC-4.
    assert result.decision == "go", (
        f"Pre-loop gate failed. Rationale: {result.rationale}\n"
        f"gap={result.gap:.2f} (threshold={result.threshold:.2f}), "
        f"judgment_gap={result.judgment_gap}, "
        f"variance_warning={result.variance_warning}"
    )

    # SC-2: gap must meet the hard-coded 2.0 threshold.
    assert result.gap >= result.threshold, (
        f"Gap {result.gap:.2f} below threshold {result.threshold:.2f} — "
        f"judge is not discriminating output_a from output_b. "
        f"See results/pre_loop_test.json for per-item scores."
    )

    # SC-3: judgment-category signal must be positive (thesis-critical).
    assert result.judgment_gap > 0, (
        f"judgment_gap={result.judgment_gap} — judge did not give output_a "
        f"a positive edge on judgment items specifically. The total-score "
        f"gap may be coming entirely from extraction wins, which does not "
        f"validate the thesis. Investigate playbook specificity."
    )

    # SC-1: artifact written in the canonical location.
    assert _RESULTS_FILE.exists(), (
        f"Expected {_RESULTS_FILE} to exist after run_pre_loop_test() — "
        f"check run_pre_loop_test's file-write path and results/ mkdir."
    )
