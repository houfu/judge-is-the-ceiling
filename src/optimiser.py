"""Optimiser: rewrites the agent system prompt from judge feedback (OPTM-01..03).

Design notes:
- D-01: run_optimiser(system_prompt, judge_result) -> OptimiserResult.
  NDA is structurally unreachable — not a parameter.
- D-07/D-08: feedback extraction sorts by score ascending, strips item_id,
  formats as "N. [score=K] {feedback}". User-role message fences the old
  prompt in `---` and appends the rewrite instruction.
- D-09: OPTIMISER_SYSTEM_PROMPT enforces 300-word cap + banned vocabulary
  + no preamble + "describe what the reviewer does, not how scored".
- D-10/D-11: WORD_LIMIT=300 hard cap enforced via post-validation retry
  loop (MAX_RETRIES=3), mirroring src/judge.py. On exhaustion, returns
  sentinel OptimiserResult(failed=True, new_system_prompt=system_prompt,
  prompt_diff="") — non-raising, preserves old prompt.
- D-13: prompt_diff via difflib.unified_diff, stdlib only.
- D-14/D-15: post-hoc P8 scrub against BANNED_RUBRIC_VOCAB_TOKENS.
  On hit: log WARNING + set vocab_warning=True. DO NOT retry. DO NOT fail.
  Per PITFALLS P5: detection, not prevention.
- D-12: logger "jitc.optimiser" — INFO at entry, WARNING per overrun,
  ERROR on retry exhaustion.

Trust model: judge_result fields are structured (Pydantic-validated upstream
by run_judge). system_prompt is caller-provided and may contain anything
except NDA text (OPTM-01 enforced at Phase 5 call site). No tool access,
no file I/O, no network beyond the single chat.completions.create call.
"""

import difflib
import logging

from src.config import config
from src.llm import get_client
from src.models import BANNED_RUBRIC_VOCAB_TOKENS, JudgeResult, OptimiserResult

logger = logging.getLogger("jitc.optimiser")

MAX_RETRIES = 3
WORD_LIMIT = 300

# D-09: canonical optimiser meta-prompt. The banned-vocabulary list is
# interpolated from BANNED_RUBRIC_VOCAB_TOKENS at module load to guarantee
# the meta-prompt ban list and the post-hoc scrub list can NEVER drift
# apart (single source of truth — see P8 mitigation in 04-RESEARCH.md).
_BANNED_LIST_FORMATTED = ", ".join(f'"{t}"' for t in BANNED_RUBRIC_VOCAB_TOKENS)

OPTIMISER_SYSTEM_PROMPT = f"""\
You are a prompt optimiser. Your job is to rewrite an NDA-review agent's
system prompt based on feedback from an evaluator.

Hard constraints:
- The rewritten prompt MUST be {WORD_LIMIT} words or fewer. This is non-negotiable.
- Do NOT use words from the rubric or playbook. Banned vocabulary includes:
  {_BANNED_LIST_FORMATTED}.
- Rewrite the prompt in plain NDA-review terms only — describe what the
  reviewer should do, not how they will be scored.
- Do not mention feedback, evaluators, or the optimisation process itself.
- Do not include preamble, explanation, or commentary. Return ONLY the new
  system prompt text, nothing else.

You receive: the current agent system prompt, and a numbered list of
feedback strings with scores (0 = not addressed, 1 = partially, 2 = fully).
Rewrite the prompt to address the lowest-scoring items while preserving
what already works.
"""


def _count_words(text: str) -> int:
    """Plain-English word count via whitespace split (D-10 intent)."""
    return len(text.split())


def _build_feedback_block(judge_result: JudgeResult) -> list[str]:
    """D-07: sort 8 RubricScores by score ascending; strip item_id; format."""
    sorted_scores = sorted(judge_result.scores, key=lambda s: s.score)
    return [
        f"{idx}. [score={s.score}] {s.feedback}"
        for idx, s in enumerate(sorted_scores, start=1)
    ]


def _build_user_message(system_prompt: str, feedback_block: list[str]) -> str:
    """D-08: fenced old prompt + numbered feedback + rewrite instruction."""
    joined = "\n".join(feedback_block)
    return (
        "Current agent system prompt (to be rewritten):\n"
        "---\n"
        f"{system_prompt}\n"
        "---\n\n"
        "Judge feedback on the latest review "
        "(sorted by score ascending, worst first):\n"
        f"{joined}\n\n"
        "Rewrite the agent system prompt to address the lowest-scoring items "
        f"while preserving what already works. Hard limit: {WORD_LIMIT} words."
    )


def _build_retry_message(actual_words: int) -> str:
    """D-11: correction prompt appended on word-overrun retry."""
    return (
        f"Your rewrite is {actual_words} words; the hard limit is {WORD_LIMIT}. "
        f"Rewrite again staying strictly under {WORD_LIMIT} words. "
        "Return ONLY the new system prompt, no preamble, no commentary."
    )


def _compute_prompt_diff(old: str, new: str) -> str:
    """D-13: stdlib unified diff, single joined string.

    Uses splitlines() (no keepends) with lineterm="" and "\n".join so that
    single-line inputs without trailing newlines still produce a readable
    multi-line unified diff. With keepends=True + lineterm="", difflib
    concatenates all headers and body lines into a single run (no inter-line
    separators), which breaks grep / splitlines-based consumers downstream.
    """
    diff_lines = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile="old_system_prompt",
        tofile="new_system_prompt",
        lineterm="",
        n=3,
    )
    return "\n".join(diff_lines)


def _check_banned_vocab(prompt: str) -> list[str]:
    """D-14: case-insensitive substring check against BANNED_RUBRIC_VOCAB_TOKENS.

    Returns the list of banned tokens that appeared in the prompt. Empty
    list means clean. Non-empty list triggers vocab_warning=True (D-15)
    but NOT retry and NOT failure — per PITFALLS P5, this is the expected
    drift signal and must be surfaced, not suppressed.
    """
    lowered = prompt.lower()
    return [tok for tok in BANNED_RUBRIC_VOCAB_TOKENS if tok in lowered]


def run_optimiser(system_prompt: str, judge_result: JudgeResult) -> OptimiserResult:
    """Rewrite the agent system prompt based on judge feedback.

    Structural contract:
    - NDA is NOT a parameter (OPTM-01 enforced by type signature).
    - Retries up to MAX_RETRIES on word-count overrun (P11 mitigation).
    - On retry exhaustion: returns sentinel OptimiserResult(failed=True,
      new_system_prompt=system_prompt). Non-raising — mirrors JUDG-05.
    - Post-hoc P8 scrub sets vocab_warning=True but never retries (D-15).

    Args:
        system_prompt: The agent system prompt to rewrite.
        judge_result: Structured judge feedback (8 RubricScore entries).

    Returns:
        OptimiserResult carrying the new prompt, feedback trace, diff,
        word counts, vocab_warning, and retry metadata. Never raises.
    """
    client = get_client()
    feedback_block = _build_feedback_block(judge_result)
    user_content = _build_user_message(system_prompt, feedback_block)
    old_word_count = _count_words(system_prompt)

    logger.info(
        "optimiser call: model=%s old_words=%d num_ctx=%d",
        config.model,
        old_word_count,
        config.num_ctx,
    )

    messages: list[dict] = [
        {"role": "system", "content": OPTIMISER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    raw: str = ""
    last_word_count: int = 0
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("optimiser attempt %d/%d", attempt, MAX_RETRIES)
        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            extra_body={"options": {"num_ctx": config.num_ctx}},  # P6
        )
        raw = response.choices[0].message.content or ""
        last_word_count = _count_words(raw)

        if last_word_count <= WORD_LIMIT:
            # Success path — compute diff, run P8 scrub, build result.
            prompt_diff = _compute_prompt_diff(system_prompt, raw)
            hits = _check_banned_vocab(raw)
            if hits:
                logger.warning(
                    "optimiser output contains banned vocab tokens: %s", hits
                )
            logger.info(
                "optimiser success: new_words=%d retries=%d vocab_warning=%s",
                last_word_count,
                attempt - 1,
                bool(hits),
            )
            return OptimiserResult(
                new_system_prompt=raw,
                feedback_seen=feedback_block,
                prompt_diff=prompt_diff,
                prompt_word_count=last_word_count,
                old_word_count=old_word_count,
                vocab_warning=bool(hits),
                retry_count=attempt - 1,
                failed=False,
            )

        # Overrun — log and append retry correction turn.
        logger.warning(
            "optimiser overrun attempt %d: %d words (limit %d)",
            attempt,
            last_word_count,
            WORD_LIMIT,
        )
        if attempt < MAX_RETRIES:
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {"role": "user", "content": _build_retry_message(last_word_count)}
            )

    # All retries exhausted — sentinel. Keep old prompt byte-identical (D-11).
    logger.error(
        "optimiser retry exhausted; keeping old prompt unchanged "
        "(last attempt: %d words, limit %d)",
        last_word_count,
        WORD_LIMIT,
    )
    return OptimiserResult(
        new_system_prompt=system_prompt,
        feedback_seen=feedback_block,
        prompt_diff="",
        prompt_word_count=old_word_count,
        old_word_count=old_word_count,
        vocab_warning=False,
        retry_count=MAX_RETRIES,
        failed=True,
    )
