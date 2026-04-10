from pydantic import BaseModel
from typing import Literal


class RubricScore(BaseModel):
    item_id: str  # e.g. "1a", "3b"
    item_type: Literal["extraction", "judgment"]
    issue_number: int
    score: Literal[0, 1, 2]
    evidence: str
    reasoning: str
    feedback: str


class JudgeResult(BaseModel):
    scores: list[RubricScore]


class IterationResult(BaseModel):
    iteration: int
    system_prompt: str
    agent_output: str
    scores: list[RubricScore]
    total_score: int
    extraction_score: int
    judgment_score: int


class ExperimentRun(BaseModel):
    experiment_id: str
    timestamp: str
    config: dict
    nda_file: str
    rubric_file: str
    playbook_file: str
    pre_loop_test: dict | None = None
    iterations: list[IterationResult] = []


def compute_category_scores(scores: list[RubricScore]) -> tuple[int, int]:
    """Return (extraction_score, judgment_score) from a list of RubricScore."""
    extraction = sum(s.score for s in scores if s.item_type == "extraction")
    judgment = sum(s.score for s in scores if s.item_type == "judgment")
    return extraction, judgment
