from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_VERSION = "strategy-ir.v1"
SUPPORTED_CONDITION_TYPES = {
    "close_above_sma",
    "close_below_sma",
    "close_crosses_above_sma",
    "close_crosses_below_sma",
    "all_of",
}


class FactorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    family: Literal["trend", "volume", "volatility", "regime", "fundamental", "risk"]
    kind: Literal["indicator", "event", "constant"] = "indicator"
    metric: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)
    operator: str | None = Field(default=None, max_length=32)
    direction: Literal["positive", "negative", "neutral"] = "neutral"
    weight: Decimal | None = None
    warmup_period: int = Field(default=0, ge=0, le=1000)
    explanation: str = Field(min_length=1, max_length=500)


class ConditionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    period: int | None = Field(default=None, gt=0, le=1000)
    factor_id: str | None = None
    threshold: Decimal | None = None
    conditions: list["ConditionSpec"] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ConditionSpec":
        if self.type == "all_of":
            if not self.conditions or len(self.conditions) > 8:
                raise ValueError("all_of requires 1-8 conditions")
            if self.period is not None or self.factor_id is not None:
                raise ValueError("all_of cannot have period or factor_id")
        elif self.type not in SUPPORTED_CONDITION_TYPES:
            # Weighted-score and future nodes are allowed in the IR but are not
            # executable by the current compiler. This lets the UI show them
            # as partial candidates instead of silently changing their meaning.
            if self.conditions is not None:
                raise ValueError(f"{self.type} cannot have nested conditions")
        elif self.period is None:
            raise ValueError(f"{self.type} requires period")
        elif self.conditions is not None:
            raise ValueError(f"{self.type} cannot have nested conditions")
        return self
ConditionSpec.model_rebuild()


class SizingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_fraction: Decimal = Field(default=Decimal("0.5"), gt=0, le=1)
    lot_size: int = Field(default=100, gt=0, le=100000)


class ExecutionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observe_at: Literal["close"] = "close"
    execute_at: Literal["next_open"] = "next_open"
    order_expiry: Literal["next_session"] = "next_session"


class EvaluationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    research_scope: Literal["research"] = "research"
    holdout_scope: Literal["locked"] = "locked"


class StrategyIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    form: Literal["condition_set", "weighted_score"] = "condition_set"
    objective: str = Field(min_length=1, max_length=500)
    universe: dict[str, Any] = Field(default_factory=lambda: {"scope": "single_symbol"})
    factors: list[FactorSpec] = Field(min_length=1, max_length=8)
    entry: ConditionSpec
    exit: ConditionSpec
    sizing: SizingSpec = Field(default_factory=SizingSpec)
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    evaluation: EvaluationSpec = Field(default_factory=EvaluationSpec)

    @model_validator(mode="after")
    def validate_factor_references(self) -> "StrategyIR":
        """Keep the IR self-contained before it reaches the compiler.

        The language model is allowed to suggest a factor in natural language,
        but it must reference an explicitly declared factor in the structured
        result.  Failing here gives the API a safe, deterministic error instead
        of allowing a dangling reference to reach a later execution step.
        """
        factor_ids = [factor.id for factor in self.factors]
        if len(factor_ids) != len(set(factor_ids)):
            raise ValueError("factors must have unique ids")

        def visit(condition: ConditionSpec) -> None:
            if condition.factor_id and condition.factor_id not in factor_ids:
                raise ValueError(f"condition references unknown factor: {condition.factor_id}")
            for child in condition.conditions or []:
                visit(child)

        visit(self.entry)
        visit(self.exit)
        return self


class StrategyCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=500)
    form: Literal["condition_set", "weighted_score"]
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    data_requirements: list[str] = Field(default_factory=list, max_length=8)
    risk_notes: list[str] = Field(default_factory=list, max_length=8)
    support: Literal["supported", "partial", "unsupported"] = "supported"
    ir: StrategyIR

    @model_validator(mode="after")
    def validate_candidate_consistency(self) -> "StrategyCandidate":
        if self.form != self.ir.form:
            raise ValueError("candidate form must match ir.form")
        if self.form == "weighted_score" and self.support == "supported":
            raise ValueError("weighted_score candidates must be marked partial or unsupported")
        return self


class DraftEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The server replaces both values after model validation. Defaults let an
    # OpenAI-compatible model return only the semantic draft fields without
    # having to invent an ID or echo the user's prompt.
    request_id: str = "model-draft"
    user_intent: str = Field(default="model request", min_length=1, max_length=2000)
    candidates: list[StrategyCandidate] = Field(min_length=1, max_length=3)
    clarifications: list[str] = Field(default_factory=list, max_length=8)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_candidate_ids(self) -> "DraftEnvelope":
        ids = [candidate.id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate ids must be unique")
        return self