"""Agent: takes a system prompt + NDA text, returns a free-text review.

Implements AGNT-01 and AGNT-02:
- AGNT-01: thin wrapper over chat.completions.create. Returns the raw
  response string (no parsing, no trimming).
- AGNT-02: ITERATION_ZERO_SYSTEM_PROMPT contains no rubric, playbook,
  or evaluation vocabulary. Verified by tests/test_agent.py::
  test_prompt_scrubbed_of_rubric_vocab.

Every call applies num_ctx via extra_body.options (D-04, P6) and reads
temperature from config (CONF-02: config.temperature defaults to 0.0).

Security note: nda_text is treated as untrusted input (it may contain
prompt-injection attempts), but the agent has no tool access, no file
write, and no network capability beyond this single completion call,
so the worst case is a weird-looking review — no security boundary is
crossed. See threat T-02-A01 in 02-02-PLAN.md.
"""

import logging

from src.config import config
from src.llm import get_client

logger = logging.getLogger("jitc.agent")

# Verbatim from prd.md §3.4.
# MUST NOT contain rubric / playbook / evaluation vocabulary (P8, AGNT-02).
# This is enforced by tests/test_agent.py::test_prompt_scrubbed_of_rubric_vocab.
# Phase 5's optimiser will rewrite this constant per iteration; the vocab
# scrub test is a permanent regression gate.
ITERATION_ZERO_SYSTEM_PROMPT = """\
You are reviewing a Non-Disclosure Agreement. Identify all issues
and assess their significance. Output your findings as a structured
list. For each issue provide: the clause reference, a description
of the issue, and your risk assessment.
"""


def run_agent(system_prompt: str, nda_text: str) -> str:
    """Run the agent against an NDA and return its review as a string.

    Args:
        system_prompt: The agent's instructions. Starts as
            ITERATION_ZERO_SYSTEM_PROMPT; Phase 5's optimiser rewrites
            it per iteration.
        nda_text: Raw markdown NDA text.

    Returns:
        The agent's review — whatever the model produced, unmodified.
        If the model returns None content (rare but possible on some
        Ollama versions), an empty string is returned.
    """
    client = get_client()
    logger.info("agent call: model=%s chars=%d", config.model, len(nda_text))
    response = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": nda_text},
        ],
        temperature=config.temperature,
        extra_body={"options": {"num_ctx": config.num_ctx}},  # D-04, P6
    )
    return response.choices[0].message.content or ""
