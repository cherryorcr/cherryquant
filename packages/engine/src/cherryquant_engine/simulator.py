from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .models import (
    Bar,
    ConditionStatus,
    DataSnapshot,
    DecisionTrace,
    ExperimentConfig,
    OrderAttempt,
    OrderStatus,
    RunResult,
    RunStatus,
    RunSummary,
    StrategySpec,
    Trade,
    floor_to_lot,
)


@dataclass
class _Position:
    quantity: int
    entry_price: Decimal
    entry_date: str
    entry_signal_date: str
    entry_fees: Decimal

    def snapshot(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity,
            "entry_price": format(self.entry_price, "f"),
            "entry_date": self.entry_date,
            "entry_signal_date": self.entry_signal_date,
        }


@dataclass(frozen=True)
class _PendingOrder:
    side: str
    signal_date: str
    execution_date: str
    quantity: int


def _fee(gross: Decimal, config: ExperimentConfig) -> Decimal:
    if gross <= 0:
        return Decimal("0")
    calculated = gross * config.commission_rate
    return max(calculated, config.min_commission)


def _position_snapshot(position: _Position | None) -> dict[str, Any]:
    return {} if position is None else position.snapshot()


def _equity(cash: Decimal, position: _Position | None, close: Decimal | None) -> Decimal | None:
    if position is None:
        return cash
    if close is None:
        return None
    return cash + Decimal(position.quantity) * close


def _failed_result(config: ExperimentConfig, reason: str) -> RunResult:
    summary = RunSummary(
        status=RunStatus.FAILED,
        reason=reason,
        initial_cash=config.initial_cash,
        final_cash=config.initial_cash,
        final_equity=config.initial_cash,
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        trade_count=0,
        filled_order_count=0,
        not_filled_order_count=0,
        total_return=None,
    )
    return RunResult(status=RunStatus.FAILED, summary=summary, errors=(reason,))


def _attempt_pending(
    pending: _PendingOrder,
    bar: Bar,
    cash: Decimal,
    position: _Position | None,
    config: ExperimentConfig,
) -> tuple[OrderAttempt, Decimal, _Position | None, Trade | None]:
    if pending.side == "buy":
        if position is not None:
            return (
                OrderAttempt("buy", pending.signal_date, bar.date, pending.quantity, OrderStatus.NOT_FILLED, reason="POSITION_ALREADY_OPEN"),
                cash,
                position,
                None,
            )
        if bar.suspended:
            return (
                OrderAttempt("buy", pending.signal_date, bar.date, pending.quantity, OrderStatus.NOT_FILLED, reason="SUSPENDED"),
                cash,
                position,
                None,
            )
        if bar.open is None:
            return (
                OrderAttempt("buy", pending.signal_date, bar.date, pending.quantity, OrderStatus.NOT_FILLED, reason="MISSING_OPEN"),
                cash,
                position,
                None,
            )
        if bar.limit_up is not None and bar.open >= bar.limit_up:
            return (
                OrderAttempt("buy", pending.signal_date, bar.date, pending.quantity, OrderStatus.NOT_FILLED, price=bar.open, reason="PRICE_LIMIT_UP"),
                cash,
                position,
                None,
            )
        gross = bar.open * Decimal(pending.quantity)
        commission = _fee(gross, config)
        if gross + commission > cash:
            return (
                OrderAttempt("buy", pending.signal_date, bar.date, pending.quantity, OrderStatus.NOT_FILLED, price=bar.open, reason="INSUFFICIENT_CASH"),
                cash,
                position,
                None,
            )
        next_cash = cash - gross - commission
        new_position = _Position(
            quantity=pending.quantity,
            entry_price=bar.open,
            entry_date=bar.date,
            entry_signal_date=pending.signal_date,
            entry_fees=commission,
        )
        return (
            OrderAttempt("buy", pending.signal_date, bar.date, pending.quantity, OrderStatus.FILLED, price=bar.open, commission=commission),
            next_cash,
            new_position,
            None,
        )

    if position is None:
        return (
            OrderAttempt("sell", pending.signal_date, bar.date, pending.quantity, OrderStatus.NOT_FILLED, reason="NO_POSITION"),
            cash,
            position,
            None,
        )
    if bar.suspended:
        return (
            OrderAttempt("sell", pending.signal_date, bar.date, pending.quantity, OrderStatus.NOT_FILLED, reason="SUSPENDED"),
            cash,
            position,
            None,
        )
    if bar.open is None:
        return (
            OrderAttempt("sell", pending.signal_date, bar.date, pending.quantity, OrderStatus.NOT_FILLED, reason="MISSING_OPEN"),
            cash,
            position,
            None,
        )
    if bar.limit_down is not None and bar.high is not None and bar.high <= bar.limit_down:
        return (
            OrderAttempt("sell", pending.signal_date, bar.date, pending.quantity, OrderStatus.NOT_FILLED, price=bar.open, reason="PRICE_LIMIT_DOWN"),
            cash,
            position,
            None,
        )
    gross = bar.open * Decimal(position.quantity)
    commission = _fee(gross, config)
    stamp_duty = gross * config.stamp_duty_rate
    next_cash = cash + gross - commission - stamp_duty
    trade = Trade(
        entry_signal_date=position.entry_signal_date,
        entry_date=position.entry_date,
        exit_signal_date=pending.signal_date,
        exit_date=bar.date,
        quantity=position.quantity,
        entry_price=position.entry_price,
        exit_price=bar.open,
        entry_fees=position.entry_fees,
        exit_fees=commission + stamp_duty,
        realized_pnl=(bar.open - position.entry_price) * Decimal(position.quantity) - position.entry_fees - commission - stamp_duty,
    )
    return (
        OrderAttempt(
            "sell",
            pending.signal_date,
            bar.date,
            pending.quantity,
            OrderStatus.FILLED,
            price=bar.open,
            commission=commission,
            stamp_duty=stamp_duty,
        ),
        next_cash,
        None,
        trade,
    )


def run_experiment(snapshot: DataSnapshot, strategy: StrategySpec, config: ExperimentConfig) -> RunResult:
    """Run one deterministic single-symbol daily experiment.

    Signals are observed at today's close. A signal creates at most one order
    attempt for the next bar's open. All explanations are emitted into traces;
    callers should read those records rather than recomputing conditions.
    """
    if not snapshot.bars:
        return _failed_result(config, "EMPTY_DATASET")
    if not strategy.confirmed:
        return _failed_result(config, "STRATEGY_NOT_CONFIRMED")
    bars = snapshot.bars
    cash = config.initial_cash
    position: _Position | None = None
    pending: _PendingOrder | None = None
    traces: list[DecisionTrace] = []
    trades: list[Trade] = []
    warnings: list[str] = []
    filled_orders = 0
    not_filled_orders = 0
    realized_pnl = Decimal("0")

    for index, bar in enumerate(bars):
        cash_before = cash
        position_before = _position_snapshot(position)
        position_at_bar_start = position
        order_attempt: OrderAttempt | None = None
        if pending is not None:
            order_attempt, cash, position, trade = _attempt_pending(pending, bar, cash, position, config)
            pending = None
            if order_attempt.status == OrderStatus.FILLED:
                filled_orders += 1
            else:
                not_filled_orders += 1
            if trade is not None:
                trades.append(trade)
                realized_pnl += trade.realized_pnl

        entry_result = strategy.entry_condition.evaluate(bars, index)
        exit_result = strategy.exit_condition.evaluate(bars, index)
        condition_results = {"entry": entry_result, "exit": exit_result}
        signal: str | None = None

        if position is not None:
            if exit_result.status == ConditionStatus.PASS:
                signal = "exit"
                if index + 1 < len(bars):
                    pending = _PendingOrder("sell", bar.date, bars[index + 1].date, position.quantity)
                else:
                    not_filled_orders += 1
                    order_attempt = OrderAttempt("sell", bar.date, None, position.quantity, OrderStatus.NOT_FILLED, reason="NO_NEXT_BAR")
        elif position is None and position_at_bar_start is None and entry_result.status == ConditionStatus.PASS:
            signal = "entry"
            if index + 1 < len(bars):
                assert bars[index].close is not None
                target_cash = cash * strategy.position_fraction
                quantity = floor_to_lot(target_cash / bars[index].close, strategy.lot_size)
                if quantity <= 0:
                    not_filled_orders += 1
                    order_attempt = OrderAttempt("buy", bar.date, bars[index + 1].date, quantity, OrderStatus.NOT_FILLED, reason="INSUFFICIENT_LOT")
                else:
                    pending = _PendingOrder("buy", bar.date, bars[index + 1].date, quantity)
            else:
                not_filled_orders += 1
                order_attempt = OrderAttempt("buy", bar.date, None, 0, OrderStatus.NOT_FILLED, reason="NO_NEXT_BAR")

        if entry_result.status == ConditionStatus.UNAVAILABLE or exit_result.status == ConditionStatus.UNAVAILABLE:
            warnings.append(f"{bar.date}: condition unavailable during warmup or missing data")
        equity = _equity(cash, position, bar.close)
        traces.append(
            DecisionTrace(
                date=bar.date,
                condition_results=condition_results,
                signal=signal,
                order_attempt=order_attempt,
                position_before=position_before,
                position_after=_position_snapshot(position),
                cash_before=cash_before,
                cash_after=cash,
                equity=equity,
                warnings=("CONDITION_UNAVAILABLE",) if entry_result.status == ConditionStatus.UNAVAILABLE or exit_result.status == ConditionStatus.UNAVAILABLE else (),
            )
        )

    last_close = bars[-1].close
    unrealized_pnl = Decimal("0")
    if position is not None and last_close is not None:
        unrealized_pnl = (last_close - position.entry_price) * Decimal(position.quantity) - position.entry_fees
    final_equity = _equity(cash, position, last_close)
    if final_equity is None:
        final_equity = cash
    status = RunStatus.COMPLETED if trades or filled_orders else RunStatus.NO_TRADES
    reason = "COMPLETED" if status == RunStatus.COMPLETED else "NO_FILLED_ORDERS"
    total_return = (final_equity - config.initial_cash) / config.initial_cash
    summary = RunSummary(
        status=status,
        reason=reason,
        initial_cash=config.initial_cash,
        final_cash=cash,
        final_equity=final_equity,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        trade_count=len(trades),
        filled_order_count=filled_orders,
        not_filled_order_count=not_filled_orders,
        total_return=total_return,
    )
    return RunResult(
        status=status,
        summary=summary,
        traces=tuple(traces),
        trades=tuple(trades),
        warnings=tuple(dict.fromkeys(warnings)),
    )

