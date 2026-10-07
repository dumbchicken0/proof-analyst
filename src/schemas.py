"""Shared contract between agent, verifier, API and UI."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError, model_validator

Scalar = Union[int, float, str]


class Verdict(str, Enum):
    ANSWERED = "ANSWERED"
    ANSWERED_WITH_ASSUMPTIONS = "ANSWERED_WITH_ASSUMPTIONS"
    AMBIGUOUS = "AMBIGUOUS"
    REFUSED = "REFUSED"


class Value(BaseModel):
    label: str
    value: Scalar
    unit: Optional[str] = None


class Assumption(BaseModel):
    id: str
    type: Literal["dedupe", "currency", "date", "missing", "unit", "join", "category", "other"]
    detail: str
    evidence: str


class Interpretation(BaseModel):
    label: str
    value: Scalar


class CrossCheck(BaseModel):
    path_b_value: Optional[Scalar] = None
    agree: bool


class Proof(BaseModel):
    code: str
    language: Literal["python"] = "python"
    data_hash: str
    rerun_value: Optional[dict[str, Scalar]] = None
    reproduced: bool
    cross_check: Optional[CrossCheck] = None


class Refusal(BaseModel):
    reason: str
    missing: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)


class TraceStep(BaseModel):
    step: int
    thought: str = ""
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    observation: str = ""


class Answer(BaseModel):
    question: str
    verdict: Verdict
    text: str
    values: list[Value] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    interpretations: list[Interpretation] = Field(default_factory=list)
    proof: Optional[Proof] = None
    refusal: Optional[Refusal] = None
    trace: list[TraceStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> "Answer":
        answered = (Verdict.ANSWERED, Verdict.ANSWERED_WITH_ASSUMPTIONS)
        if self.verdict in answered and (self.proof is None or not self.values):
            raise ValueError("answered verdicts require proof and values")
        if self.verdict == Verdict.ANSWERED_WITH_ASSUMPTIONS and not self.assumptions:
            raise ValueError("ANSWERED_WITH_ASSUMPTIONS requires at least one assumption")
        if self.verdict == Verdict.REFUSED and self.refusal is None:
            raise ValueError("REFUSED requires a refusal reason")
        return self


# ---- Agent actions -------------------------------------------------------

ToolName = Literal[
    "inspect_schema", "sample_rows", "profile_column",
    "run_code", "cross_check", "ask_clarification", "finish",
]


class Action(BaseModel):
    thought: str = ""
    tool: ToolName
    args: dict[str, Any] = Field(default_factory=dict)


class EmptyArgs(BaseModel):
    pass


class SampleRowsArgs(BaseModel):
    table: str
    n: int = Field(5, ge=1, le=20)


class ProfileColumnArgs(BaseModel):
    table: str
    column: str


class RunCodeArgs(BaseModel):
    code: str


class CrossCheckArgs(BaseModel):  # stretch: SQL path B
    sql: str


class AskClarificationArgs(BaseModel):
    question: str
    options: list[str] = Field(default_factory=list)


class FinishArgs(BaseModel):
    verdict: Verdict
    answer_text: str
    values: list[Value] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    interpretations: list[Interpretation] = Field(default_factory=list)
    refusal: Optional[Refusal] = None


ARGS_MODELS: dict[str, type[BaseModel]] = {
    "inspect_schema": EmptyArgs,
    "sample_rows": SampleRowsArgs,
    "profile_column": ProfileColumnArgs,
    "run_code": RunCodeArgs,
    "cross_check": CrossCheckArgs,
    "ask_clarification": AskClarificationArgs,
    "finish": FinishArgs,
}


def parse_action(raw: str) -> Action:
    """Parse raw model output into a validated Action.

    Raises ValueError with a message that can be fed straight back to the model.
    """
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found. Reply with exactly one JSON object.")
    try:
        action = Action.model_validate_json(raw[start : end + 1])
        args = ARGS_MODELS[action.tool].model_validate(action.args)
    except ValidationError as exc:
        raise ValueError(f"Invalid action: {exc.errors(include_url=False)}") from exc
    action.args = args.model_dump(mode="json")
    return action
