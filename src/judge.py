"""Judge: scores an agent review against a rubric (JUDG-01..05).

Design notes:
- D-04 / P6: every call passes extra_body={"options": {"num_ctx": N}}.
- D-05: two-message layout (system = stable rules + schema, user = case data).
- D-07: section dividers use distinctive `# === JITC_*_START/END ===` envelope
  markers rather than plain `# NDA` headings. This prevents collision with
  top-level `#` headings inside the NDA itself (data/nda.md starts with `# NDA`)
  and inside any markdown the agent might produce. Note: collision is not the
  same as prompt injection — a malicious NDA could still include a literal
  `# === JITC_AGENT_OUTPUT_START ===` string verbatim. The distinctive envelope
  makes accidental collision effectively impossible and raises the bar for
  intentional collision. Residual prompt-injection risk is accepted under
  T-02-J01 (no tool access, Pydantic-validated output, biased scoring is the
  worst case).
- D-09: exactly ONE JSON example in the system prompt (avoid multi-shot
  anchoring).
- D-10: the system prompt explicitly instructs "no preamble, no markdown fences".
- JUDG-02 / P7: on ValidationError, append (assistant raw, user error) turns
  and retry. Max 3 attempts.
- JUDG-03 / P14: _extract_json strips ```json fences and prose preambles via
  an outermost-brace regex before model_validate_json is called.
- JUDG-05 / P7: on retry exhaustion, log raw output at ERROR and return
  JudgeResult(scores=[]) — callers detect with `if not result.scores:`.
  NEVER raises out of run_judge.
- P12: Pydantic v2 model_validate_json raises ValidationError for both JSON
  decode and schema failures — a single except clause is sufficient.
- P4: no response_format, no stream, no client.beta.chat.completions.parse.

Trust model (T-02-J01): nda_text and agent_output are embedded verbatim in
the user-role message and may contain prompt-injection attempts. The judge
has no tool access; the only output channel is a Pydantic-validated
JudgeResult, so the worst case is biased scoring — the Phase 3 pre-loop
test catches systematic miscalibration. Logs may contain NDA text on retry
exhaustion (T-02-J02); run locally only.
"""

import logging
import re

from pydantic import ValidationError

from src.config import config
from src.llm import get_client
from src.models import JudgeResult

logger = logging.getLogger("jitc.judge")

MAX_RETRIES = 3
MAX_ERROR_CHARS = 800

JUDGE_SYSTEM_PROMPT = """\
You are a legal-review scoring judge. You will receive an NDA, an agent's
review of that NDA, a scoring rubric, and a scoring playbook. For each item
in the rubric you must return a score of 0, 1, or 2 with evidence, reasoning,
and feedback.

Return only valid JSON matching the schema below. No preamble. No markdown
code fences. No commentary before or after the JSON.

Output schema (one example shown; return one object per rubric item):
{
  "scores": [
    {
      "item_id": "1a",
      "item_type": "extraction",
      "issue_number": 1,
      "score": 2,
      "evidence": "Clause 4.1 states 'seven (7) years'.",
      "reasoning": "The review explicitly names the 7-year term and connects it to the confidentiality obligation.",
      "feedback": "Good identification. Could additionally cite clause 4.1 by number."
    }
  ]
}

item_type is either "extraction" or "judgment". issue_number is an integer
matching the rubric. score is 0, 1, or 2. All fields are required.
"""

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> str:
    """Strip common wrappers from a model response before Pydantic parsing.

    Matches the outermost {...} block, which naturally handles ```json fences,
    prose preambles, and XML wrappers in one pass. Falls back to the raw
    string if no brace pair is found (Pydantic will then raise a clean
    ValidationError the retry loop can surface).
    """
    match = _JSON_OBJECT_RE.search(raw)
    return match.group(0) if match else raw


def _build_user_message(
    nda_text: str, agent_output: str, rubric: str, playbook: str
) -> str:
    """Assemble the user-role message.

    D-06: markdown-heading delimited in fixed order NDA → Agent Output →
    Rubric → Playbook. D-07: distinctive `# === JITC_*_START/END ===` envelope
    markers rather than plain top-level headings, because `data/nda.md`
    itself starts with `# NDA` and any real NDA may contain arbitrary
    markdown headings. Plain `# NDA` / `# AGENT OUTPUT` dividers would be
    ambiguous against such input. The JITC envelope strings are unlikely
    to appear verbatim in a legitimate NDA, making accidental collision
    effectively impossible. Prompt-injection risk from a crafted NDA is
    accepted under T-02-J01.
    """
    return (
        "# === JITC_NDA_START ===\n"
        f"{nda_text}\n"
        "# === JITC_NDA_END ===\n\n"
        "# === JITC_AGENT_OUTPUT_START ===\n"
        f"{agent_output}\n"
        "# === JITC_AGENT_OUTPUT_END ===\n\n"
        "# === JITC_RUBRIC_START ===\n"
        f"{rubric}\n"
        "# === JITC_RUBRIC_END ===\n\n"
        "# === JITC_PLAYBOOK_START ===\n"
        f"{playbook}\n"
        "# === JITC_PLAYBOOK_END ===\n"
    )


def _retry_user_message(error: Exception) -> str:
    """Produce the correction prompt appended on retry.

    Bounded by MAX_ERROR_CHARS to prevent a pathological ValidationError
    from blowing the context window. Always includes the fixed reminder
    so the model sees the D-10 instruction repeated.
    """
    err_text = str(error)
    if len(err_text) > MAX_ERROR_CHARS:
        err_text = err_text[:MAX_ERROR_CHARS] + " …[truncated]"
    return (
        "Your previous response could not be parsed. Error:\n\n"
        f"{err_text}\n\n"
        "Return only valid JSON matching the schema. "
        "No preamble. No markdown code fences."
    )


def run_judge(
    nda_text: str, agent_output: str, rubric: str, playbook: str
) -> JudgeResult:
    """Score an agent's NDA review against the rubric.

    Retries up to MAX_RETRIES times on parse/validation failure, sending
    the error message back to the model between attempts (JUDG-02, P7).
    On retry exhaustion, logs raw output + final error at ERROR and
    returns an empty JudgeResult (JUDG-05) — caller must check
    `if not result.scores:` to detect failure.

    Args:
        nda_text: Raw NDA markdown.
        agent_output: The agent's review (raw text from run_agent).
        rubric: Raw JSON string of data/rubric.json (D-08).
        playbook: Raw markdown playbook text.

    Returns:
        JudgeResult with populated scores, OR JudgeResult(scores=[]) on
        retry exhaustion. Never raises.
    """
    client = get_client()
    user_content = _build_user_message(nda_text, agent_output, rubric, playbook)
    logger.info(
        "judge call: model=%s prompt_chars=%d num_ctx=%d",
        config.model,
        len(JUDGE_SYSTEM_PROMPT) + len(user_content),
        config.num_ctx,
    )

    messages: list[dict] = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    last_error: Exception | None = None
    raw: str = ""
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("judge attempt %d/%d", attempt, MAX_RETRIES)
        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            extra_body={"options": {"num_ctx": config.num_ctx}},  # D-04, P6
        )
        raw = response.choices[0].message.content or ""
        cleaned = _extract_json(raw)

        try:
            return JudgeResult.model_validate_json(cleaned)  # P12
        except ValidationError as err:
            last_error = err
            logger.warning("judge parse failed (attempt %d): %s", attempt, err)
            if attempt < MAX_RETRIES:
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": _retry_user_message(err)})

    # JUDG-05: retries exhausted — log raw + error, return sentinel.
    logger.error(
        "judge exhausted %d retries; returning empty result. raw=%r last_error=%s",
        MAX_RETRIES,
        raw,
        last_error,
    )
    # TODO(P2, Phase 3): add reasoning-length content validator
    # TODO(P7, Phase 5): track validation_attempts in IterationResult
    return JudgeResult(scores=[])
