from pydantic import BaseModel, model_validator
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
    total_score: int = 0
    extraction_score: int = 0
    judgment_score: int = 0

    @model_validator(mode="after")
    def _check_totals(self) -> "IterationResult":
        extraction, judgment = compute_category_scores(self.scores)
        total = extraction + judgment
        # If caller left defaults, fill them in; otherwise enforce consistency.
        if (
            self.extraction_score == 0
            and self.judgment_score == 0
            and self.total_score == 0
        ):
            object.__setattr__(self, "extraction_score", extraction)
            object.__setattr__(self, "judgment_score", judgment)
            object.__setattr__(self, "total_score", total)
            return self
        if (
            self.extraction_score,
            self.judgment_score,
            self.total_score,
        ) != (extraction, judgment, total):
            raise ValueError(
                f"IterationResult totals inconsistent with scores: "
                f"got ({self.extraction_score}, {self.judgment_score}, {self.total_score}), "
                f"expected ({extraction}, {judgment}, {total})"
            )
        return self


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
