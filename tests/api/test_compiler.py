from __future__ import annotations

import pytest

from cherryquant_api.compiler import StrategyCompileError, compile_candidate
from cherryquant_api.strategy_ir import ConditionSpec, FactorSpec, StrategyCandidate, StrategyIR


def _candidate(
    *, metric: str = "close_vs_sma", factor_period: int = 20, condition_period: int = 20
) -> StrategyCandidate:
    factor = FactorSpec(
        id="trend",
        family="trend",
        metric=metric,
        params={"period": factor_period},
        explanation="trend factor",
    )
    ir = StrategyIR(
        objective="test",
        factors=[factor],
        entry=ConditionSpec(type="close_above_sma", period=condition_period, factor_id="trend"),
        exit=ConditionSpec(type="close_below_sma", period=condition_period, factor_id="trend"),
    )
    return StrategyCandidate(
        id="test",
        title="test",
        summary="test",
        form="condition_set",
        ir=ir,
    )


def test_compile_rejects_non_sma_metric_for_sma_condition() -> None:
    with pytest.raises(StrategyCompileError, match="不能用于 SMA 条件"):
        compile_candidate(_candidate(metric="rsi"))


def test_compile_rejects_factor_period_mismatch() -> None:
    with pytest.raises(StrategyCompileError, match="周期与条件周期不一致"):
        compile_candidate(_candidate(factor_period=60, condition_period=20))


def test_compile_rejects_partial_candidate_before_engine() -> None:
    candidate = _candidate()
    candidate = candidate.model_copy(update={"support": "partial"})
    with pytest.raises(StrategyCompileError, match="尚未支持"):
        compile_candidate(candidate)
