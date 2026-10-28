from __future__ import annotations

from typing import Any

from cherryquant_engine import (
    AllOf,
    CloseAboveSMA,
    CloseBelowSMA,
    CloseCrossesAboveSMA,
    CloseCrossesBelowSMA,
    StrategySpec,
)

from .strategy_ir import ConditionSpec, FactorSpec, StrategyCandidate


class StrategyCompileError(ValueError):
    pass


def compile_candidate(candidate: StrategyCandidate) -> StrategySpec:
    if candidate.support != "supported":
        raise StrategyCompileError("这个候选方案包含当前引擎尚未支持的能力，请先选择可运行方案。")
    if candidate.ir.form != "condition_set":
        raise StrategyCompileError("当前版本只执行条件组合策略，加权评分候选暂时只能查看。")
    factors = {factor.id: factor for factor in candidate.ir.factors}
    entry = _compile_condition(candidate.ir.entry, factors)
    exit = _compile_condition(candidate.ir.exit, factors)
    return StrategySpec(
        version_id=candidate.id,
        entry_condition=entry,
        exit_condition=exit,
        position_fraction=candidate.ir.sizing.position_fraction,
        lot_size=candidate.ir.sizing.lot_size,
        observe_at=candidate.ir.execution.observe_at,
        execute_at=candidate.ir.execution.execute_at,
        confirmed=True,
        change_reason="由自然语言策略草稿确认并编译",
    )


def _compile_condition(condition: ConditionSpec, factors: dict[str, FactorSpec]) -> Any:
    factor = None
    if condition.factor_id and condition.factor_id not in factors:
        raise StrategyCompileError(f"条件引用了未知因子：{condition.factor_id}")
    if condition.factor_id:
        factor = factors[condition.factor_id]
    factories = {
        "close_above_sma": CloseAboveSMA,
        "close_below_sma": CloseBelowSMA,
        "close_crosses_above_sma": CloseCrossesAboveSMA,
        "close_crosses_below_sma": CloseCrossesBelowSMA,
    }
    if condition.type == "all_of":
        if not condition.conditions:
            raise StrategyCompileError("all_of 条件不能为空")
        return AllOf(tuple(_compile_condition(child, factors) for child in condition.conditions))
    factory = factories.get(condition.type)
    if factory is None or condition.period is None:
        raise StrategyCompileError(f"当前引擎不支持条件：{condition.type}")
    if factor is not None:
        if factor.metric != "close_vs_sma":
            raise StrategyCompileError(
                f"因子 {factor.id} 的指标 {factor.metric} 不能用于 SMA 条件"
            )
        configured_period = factor.params.get("period")
        if configured_period is not None:
            try:
                period_matches = int(configured_period) == condition.period
            except (TypeError, ValueError):
                period_matches = False
            if not period_matches:
                raise StrategyCompileError(f"因子 {factor.id} 的周期与条件周期不一致")
    return factory(condition.period)


def compiled_card(candidate: StrategyCandidate, strategy: StrategySpec) -> dict[str, Any]:
    return {
        "version_id": strategy.version_id,
        "entry_condition": strategy.entry_condition.to_dict(),
        "exit_condition": strategy.exit_condition.to_dict(),
        "position_fraction": str(strategy.position_fraction),
        "lot_size": strategy.lot_size,
        "confirmed": True,
        "change_reason": strategy.change_reason,
        "candidate_id": candidate.id,
    }
