from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from cherryquant_engine import (
    AllOf,
    CloseAboveSMA,
    CloseBelowSMA,
    CloseCrossesAboveSMA,
    CloseCrossesBelowSMA,
    DataSnapshot,
    ExperimentConfig,
    StrategySpec,
    bars_from_records,
    read_json_records,
    run_experiment,
)
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .compiler import StrategyCompileError, compile_candidate, compiled_card
from .config import load_llm_config
from .llm_provider import LLMProviderError, get_strategy_provider
from .strategy_ir import DraftEnvelope


class ConditionCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    period: int | None = Field(default=None, gt=0)
    conditions: list["ConditionCard"] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ConditionCard":
        if self.type == "all_of":
            if not self.conditions:
                raise ValueError("all_of requires at least one condition")
            if self.period is not None:
                raise ValueError("all_of does not accept period")
        elif self.conditions is not None:
            raise ValueError(f"{self.type} does not accept nested conditions")
        elif self.period is None:
            raise ValueError(f"{self.type} requires period")
        return self


ConditionCard.model_rebuild()


class StrategyCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: str = Field(min_length=1, max_length=64)
    parent_version_id: str | None = Field(default=None, max_length=64)
    entry_condition: ConditionCard
    exit_condition: ConditionCard
    position_fraction: Decimal = Field(default=Decimal("1"), gt=0, le=1)
    lot_size: int = Field(default=100, gt=0)
    confirmed: bool = False
    change_reason: str = Field(default="", max_length=500)


class ExperimentConfigCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initial_cash: str = "100000"
    commission_rate: str = "0.0003"
    min_commission: str = "5"
    stamp_duty_rate: str = "0.001"
    engine_version: str = "m1.0"


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: Literal["demo-synthetic"] = "demo-synthetic"
    strategy: StrategyCard
    config: ExperimentConfigCard = Field(default_factory=ExperimentConfigCard)


class StrategyDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=8, max_length=4000)
    dataset_id: Literal["demo-synthetic"] = "demo-synthetic"
    symbol: str = "600000.SH"
    candidate_count: int = Field(default=3, ge=1, le=3)


class StrategyDraftConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=64)
    config: ExperimentConfigCard = Field(default_factory=ExperimentConfigCard)


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    dataset_id: str
    snapshot: DataSnapshot
    strategy: StrategySpec
    result: Any


@dataclass(frozen=True)
class StoredDraft:
    draft_id: str
    dataset_id: str
    prompt: str
    envelope: DraftEnvelope


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def load_demo_snapshot() -> DataSnapshot:
    records = read_json_records(_repo_root() / "fixtures" / "synthetic_daily.json")
    return DataSnapshot(
        source="cherryquant.synthetic",
        frequency="1d",
        symbol="600000.SH",
        bars=bars_from_records(records),
        research_start="20260101",
        research_end="20260107",
        holdout_start="20260108",
        holdout_end="20260108",
    )


def condition_from_card(card: ConditionCard) -> Any:
    factories = {
        "close_above_sma": CloseAboveSMA,
        "close_below_sma": CloseBelowSMA,
        "close_crosses_above_sma": CloseCrossesAboveSMA,
        "close_crosses_below_sma": CloseCrossesBelowSMA,
    }
    if card.type == "all_of":
        assert card.conditions is not None
        try:
            return AllOf(tuple(condition_from_card(child) for child in card.conditions))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    factory = factories.get(card.type)
    if factory is None:
        raise HTTPException(status_code=422, detail=f"unsupported condition type: {card.type}")
    assert card.period is not None
    return factory(card.period)


def strategy_from_card(card: StrategyCard) -> StrategySpec:
    try:
        return StrategySpec(
            version_id=card.version_id,
            parent_version_id=card.parent_version_id,
            entry_condition=condition_from_card(card.entry_condition),
            exit_condition=condition_from_card(card.exit_condition),
            position_fraction=str(card.position_fraction),
            lot_size=card.lot_size,
            confirmed=card.confirmed,
            change_reason=card.change_reason,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def config_from_card(card: ExperimentConfigCard) -> ExperimentConfig:
    try:
        return ExperimentConfig(
            initial_cash=card.initial_cash,
            commission_rate=card.commission_rate,
            min_commission=card.min_commission,
            stamp_duty_rate=card.stamp_duty_rate,
            engine_version=card.engine_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def dataset_metadata(snapshot: DataSnapshot) -> dict[str, Any]:
    research_snapshot = snapshot.for_scope("research")
    return {
        "dataset_id": "demo-synthetic",
        "source": snapshot.source,
        "frequency": snapshot.frequency,
        "symbol": snapshot.symbol,
        "bar_count": len(research_snapshot.bars),
        "start": research_snapshot.bars[0].date if research_snapshot.bars else None,
        "end": research_snapshot.bars[-1].date if research_snapshot.bars else None,
        "research_start": snapshot.research_start,
        "research_end": snapshot.research_end,
        "holdout_start": snapshot.holdout_start,
        "holdout_end": snapshot.holdout_end,
        "price_basis": snapshot.price_basis,
        "content_hash": snapshot.content_hash,
        "holdout_locked": True,
        "note": "演示合成数据，不代表真实市场表现。",
    }


def create_app() -> FastAPI:
    api = FastAPI(title="CherryQuant Natural Language Strategy API", version="0.3.0")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    runs: dict[str, StoredRun] = {}
    drafts: dict[str, StoredDraft] = {}
    snapshot = load_demo_snapshot()

    @api.get("/health")
    def health() -> dict[str, Any]:
        config = load_llm_config()
        return {
            "status": "ok",
            "engine": "m1.0",
            "api": "m3-natural-language",
            "llm_provider": get_strategy_provider().name,
            "llm": config.public_summary(),
        }

    @api.get("/v1/datasets/demo")
    def demo_dataset() -> dict[str, Any]:
        return dataset_metadata(snapshot)

    @api.get("/v1/datasets/demo/bars")
    def demo_bars() -> dict[str, Any]:
        research_snapshot = snapshot.for_scope("research")
        return {
            "dataset_id": "demo-synthetic",
            "holdout_locked": True,
            "bars": [bar.to_dict() for bar in research_snapshot.bars],
        }

    @api.post("/v1/strategies/validate")
    def validate_strategy(card: StrategyCard) -> dict[str, Any]:
        strategy = strategy_from_card(card)
        return {
            "valid": True,
            "confirmed": strategy.confirmed,
            "confirmation_required": not strategy.confirmed,
            "strategy": strategy.to_dict(),
            "readable": {
                "entry": _readable_condition(card.entry_condition),
                "exit": _readable_condition(card.exit_condition),
                "position_fraction": str(card.position_fraction),
                "lot_size": card.lot_size,
                "observe": "日线收盘后观察",
                "execute": "下一交易日开盘尝试成交",
            },
        }

    @api.post("/v1/strategy-drafts")
    def create_strategy_draft(request: StrategyDraftRequest) -> dict[str, Any]:
        provider = get_strategy_provider()
        context = {
            "dataset_id": request.dataset_id,
            "symbol": request.symbol,
            "frequency": "1d",
            "visible_range": [snapshot.research_start, snapshot.research_end],
            "candidate_count": request.candidate_count,
        }
        try:
            envelope = provider.generate(request.prompt, context)
        except LLMProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        candidates = envelope.candidates[: request.candidate_count]
        envelope = envelope.model_copy(update={"candidates": candidates})
        draft_id = envelope.request_id
        drafts[draft_id] = StoredDraft(draft_id, request.dataset_id, request.prompt, envelope)
        return {"draft_id": draft_id, "source": provider.name, "draft": envelope.model_dump(mode="json")}

    @api.get("/v1/strategy-drafts/{draft_id}")
    def get_strategy_draft(draft_id: str) -> dict[str, Any]:
        stored = _get_draft(drafts, draft_id)
        return {"draft_id": stored.draft_id, "dataset_id": stored.dataset_id, "draft": stored.envelope.model_dump(mode="json")}

    @api.post("/v1/strategy-drafts/{draft_id}/confirm")
    def confirm_strategy_draft(draft_id: str, request: StrategyDraftConfirmRequest) -> dict[str, Any]:
        stored = _get_draft(drafts, draft_id)
        candidate = next((item for item in stored.envelope.candidates if item.id == request.candidate_id), None)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"unknown candidate: {request.candidate_id}")
        try:
            strategy = compile_candidate(candidate)
        except StrategyCompileError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        config = config_from_card(request.config)
        run_snapshot = snapshot.for_scope("research")
        result = run_experiment(run_snapshot, strategy, config)
        run_id = uuid4().hex
        runs[run_id] = StoredRun(run_id, stored.dataset_id, run_snapshot, strategy, result)
        return {
            "draft_id": draft_id,
            "candidate": candidate.model_dump(mode="json"),
            "compiled_strategy": compiled_card(candidate, strategy),
            "run_id": run_id,
            "result": result.to_dict(),
        }

    @api.post("/v1/runs")
    def create_run(request: RunRequest) -> dict[str, Any]:
        if not request.strategy.confirmed:
            raise HTTPException(status_code=409, detail="strategy must be confirmed before running")
        strategy = strategy_from_card(request.strategy)
        config = config_from_card(request.config)
        run_snapshot = snapshot.for_scope("research")
        result = run_experiment(run_snapshot, strategy, config)
        run_id = uuid4().hex
        runs[run_id] = StoredRun(run_id, request.dataset_id, run_snapshot, strategy, result)
        return {"run_id": run_id, "dataset_id": request.dataset_id, "result": result.to_dict()}

    @api.get("/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        stored = _get_run(runs, run_id)
        return {
            "run_id": stored.run_id,
            "dataset_id": stored.dataset_id,
            "strategy": stored.strategy.to_dict(),
            "result": stored.result.to_dict(),
        }

    @api.get("/v1/runs/{run_id}/traces")
    def get_traces(run_id: str, date: str | None = Query(default=None, pattern=r"^\d{8}$")) -> dict[str, Any]:
        stored = _get_run(runs, run_id)
        traces = [trace.to_dict() for trace in stored.result.traces if date is None or trace.date == date]
        return {"run_id": run_id, "date": date, "traces": traces}

    @api.get("/v1/runs/{run_id}/candles")
    def get_candles(run_id: str) -> dict[str, Any]:
        stored = _get_run(runs, run_id)
        return {"run_id": run_id, "dataset_id": stored.dataset_id, "bars": [bar.to_dict() for bar in stored.snapshot.bars]}

    return api


def _get_run(runs: dict[str, StoredRun], run_id: str) -> StoredRun:
    stored = runs.get(run_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    return stored


def _get_draft(drafts: dict[str, StoredDraft], draft_id: str) -> StoredDraft:
    stored = drafts.get(draft_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"unknown strategy draft: {draft_id}")
    return stored


def _readable_condition(card: ConditionCard) -> str:
    if card.type == "all_of" and card.conditions:
        return " 且 ".join(_readable_condition(child) for child in card.conditions)
    labels = {
        "close_above_sma": "收盘价高于均线",
        "close_below_sma": "收盘价低于均线",
        "close_crosses_above_sma": "收盘价上穿均线",
        "close_crosses_below_sma": "收盘价下穿均线",
    }
    label = labels.get(card.type, card.type)
    return f"{label} SMA({card.period})"


app = create_app()

