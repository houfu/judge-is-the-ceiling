"""Live Ollama smoke tests — filled in by Plan 02-04."""

import pytest

pytestmark = pytest.mark.integration

# test_agent_smoke: run_agent against real Ollama, assert non-empty output
# test_judge_smoke: run_judge against real Ollama with output_a.md, assert scores populated
