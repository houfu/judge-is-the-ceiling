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
    pre_loop_test: "PreLoopTestResult | None" = None
    iterations: list[IterationResult] = []


def compute_category_scores(scores: list[RubricScore]) -> tuple[int, int]:
    """Return (extraction_score, judgment_score) from a list of RubricScore."""
    extraction = sum(s.score for s in scores if s.item_type == "extraction")
    judgment = sum(s.score for s in scores if s.item_type == "judgment")
    return extraction, judgment


class PreLoopTestResult(BaseModel):
    """Structured result of the Phase 3 pre-loop validation gate.

    Exactly two runs per reference output. Run 1 is authoritative for the
    gate computation (gap, judgment_gap, passed, decision). Run 2 is a
    variance check only — it drives variance_warning but never fails the
    gate (D-07).

    Construction contract: callers pass `output_a_runs`, `output_b_runs`,
    `rationale`, `model`, `temperature`, `num_ctx`, `timestamp`. The
    @model_validator(mode="after") computes `gap`, `judgment_gap`,
    `passed`, `decision`, and `variance_warning` from the 4 runs. Do NOT
    pass those derived fields at construction — they will be overwritten.

    Sentinel path (D-06): if either output_a_runs[0] or output_b_runs[0]
    has scores == [], the gate forces decision="no-go", passed=False,
    variance_warning=False regardless of the arithmetic. Never raises.

    P10 mitigation: threshold is hard-coded at 2.0. Do NOT make this an
    env var — the whole point of the gate is that weakening the bar at
    runtime defeats falsifiability.
    """

    output_a_runs: list[IterationResult]
    output_b_runs: list[IterationResult]
    threshold: float = 2.0  # P10 mitigation — hard-coded
    rationale: str  # hand-written per resolution #4
    model: str
    temperature: float
    num_ctx: int
    timestamp: str
    # Derived fields — the validator overwrites these; defaults are placeholders.
    gap: float = 0.0
    judgment_gap: int = 0
    passed: bool = False
    decision: Literal["go", "no-go"] = "no-go"
    variance_warning: bool = False

    @model_validator(mode="after")
    def _compute_gate(self) -> "PreLoopTestResult":
        # D-01: exactly 2 runs per output.
        if len(self.output_a_runs) != 2 or len(self.output_b_runs) != 2:
            raise ValueError(
                f"PreLoopTestResult requires exactly 2 runs per output; "
                f"got output_a_runs={len(self.output_a_runs)}, "
                f"output_b_runs={len(self.output_b_runs)}"
            )

        a1 = self.output_a_runs[0]
        b1 = self.output_b_runs[0]

        # D-06: sentinel path — if either run 1 failed, force no-go and return.
        if not a1.scores or not b1.scores:
            object.__setattr__(self, "gap", 0.0)
            object.__setattr__(self, "judgment_gap", 0)
            object.__setattr__(self, "passed", False)
            object.__setattr__(self, "decision", "no-go")
            object.__setattr__(self, "variance_warning", False)
            return self

        # Happy path: compute gap from run 1.
        gap = float(a1.total_score - b1.total_score)
        judgment_gap = a1.judgment_score - b1.judgment_score
        passed = (gap >= self.threshold) and (judgment_gap > 0)
        decision = "go" if passed else "no-go"

        # Variance check — Resolution #3. Per-item diff > 1 (0↔2 flip) or a
        # missing item in one run flags variance_warning. Variance NEVER fails
        # the gate (D-07); it is a Phase 5 signal only. Run-2 sentinel also
        # counts as variance.
        variance_warning = False
        for runs in (self.output_a_runs, self.output_b_runs):
            if not runs[0].scores or not runs[1].scores:
                variance_warning = True
                continue
            r1_by_id = {s.item_id: s.score for s in runs[0].scores}
            r2_by_id = {s.item_id: s.score for s in runs[1].scores}
            all_ids = set(r1_by_id) | set(r2_by_id)
            for item_id in all_ids:
                s1 = r1_by_id.get(item_id)
                s2 = r2_by_id.get(item_id)
                if s1 is None or s2 is None:
                    variance_warning = True
                    break
                if abs(s1 - s2) > 1:
                    variance_warning = True
                    break
            if variance_warning:
                break

        object.__setattr__(self, "gap", gap)
        object.__setattr__(self, "judgment_gap", judgment_gap)
        object.__setattr__(self, "passed", passed)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "variance_warning", variance_warning)
        return self


ExperimentRun.model_rebuild()
