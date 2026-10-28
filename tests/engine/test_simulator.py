from __future__ import annotations

from decimal import Decimal

from cherryquant_engine import (
    CloseAboveSMA,
    CloseBelowSMA,
    DataSnapshot,
    ExperimentConfig,
    RunStatus,
    StrategySpec,
    bars_from_records,
    run_experiment,
)


def test_signal_is_observed_at_close_and_filled_next_open(synthetic_snapshot: DataSnapshot) -> None:
    strategy = StrategySpec(
        version_id="v1",
        entry_condition=CloseAboveSMA(2),
        exit_condition=CloseBelowSMA(2),
        position_fraction=Decimal("0.5"),
    )
    result = run_experiment(synthetic_snapshot, strategy, ExperimentConfig())
    assert result.status == RunStatus.COMPLETED
    assert result.summary.trade_count == 1
    assert result.summary.filled_order_count == 2
    assert result.traces[1].signal == "entry"
    assert result.traces[1].order_attempt is None
    assert result.traces[2].order_attempt is not None
    assert result.traces[2].order_attempt.execution_date == "20260105"
    assert result.traces[2].order_attempt.price == Decimal("10.60")
    assert result.traces[3].signal == "exit"
    assert result.traces[4].order_attempt is not None
    assert result.traces[4].order_attempt.price == Decimal("10.00")


def test_no_trade_is_not_failure() -> None:
    bars = bars_from_records(
        [
            {"date": "20260101", "symbol": "600000.SH", "open": 10, "high": 10, "low": 10, "close": 10},
            {"date": "20260102", "symbol": "600000.SH", "open": 10, "high": 10, "low": 10, "close": 10},
        ]
    )
    snapshot = DataSnapshot(source="test", frequency="1d", symbol="600000.SH", bars=bars)
    strategy = StrategySpec("never", CloseAboveSMA(2), CloseBelowSMA(2))
    result = run_experiment(snapshot, strategy, ExperimentConfig())
    assert result.status == RunStatus.NO_TRADES
    assert result.summary.reason == "NO_FILLED_ORDERS"


def test_last_day_signal_is_not_filled() -> None:
    bars = bars_from_records(
        [
            {"date": "20260101", "symbol": "600000.SH", "open": 10, "high": 10, "low": 10, "close": 10},
            {"date": "20260102", "symbol": "600000.SH", "open": 10, "high": 12, "low": 10, "close": 12},
        ]
    )
    snapshot = DataSnapshot(source="test", frequency="1d", symbol="600000.SH", bars=bars)
    strategy = StrategySpec("last-day", CloseAboveSMA(2), CloseBelowSMA(2))
    result = run_experiment(snapshot, strategy, ExperimentConfig())
    assert result.status == RunStatus.NO_TRADES
    assert result.traces[-1].order_attempt is not None
    assert result.traces[-1].order_attempt.reason == "NO_NEXT_BAR"


def test_limit_up_buy_is_recorded_as_not_filled() -> None:
    bars = bars_from_records(
        [
            {"date": "20260101", "symbol": "600000.SH", "open": 10, "high": 10, "low": 10, "close": 10},
            {"date": "20260102", "symbol": "600000.SH", "open": 11, "high": 11, "low": 10, "close": 11},
            {"date": "20260105", "symbol": "600000.SH", "open": 11, "high": 11, "low": 11, "close": 11, "limit_up": 11},
        ]
    )
    snapshot = DataSnapshot(source="test", frequency="1d", symbol="600000.SH", bars=bars)
    strategy = StrategySpec("limit-up", CloseAboveSMA(2), CloseBelowSMA(2))
    result = run_experiment(snapshot, strategy, ExperimentConfig())
    assert result.status == RunStatus.NO_TRADES
    assert result.traces[-1].order_attempt is not None
    assert result.traces[-1].order_attempt.reason == "PRICE_LIMIT_UP"


def test_exit_fill_does_not_reenter_on_the_same_bar() -> None:
    bars = bars_from_records(
        [
            {"date": "20260101", "symbol": "600000.SH", "open": 10, "high": 10, "low": 10, "close": 10},
            {"date": "20260102", "symbol": "600000.SH", "open": 10, "high": 12, "low": 10, "close": 12},
            {"date": "20260105", "symbol": "600000.SH", "open": 11, "high": 12, "low": 10, "close": 11},
            {"date": "20260106", "symbol": "600000.SH", "open": 11, "high": 11, "low": 10, "close": 10},
        ]
    )
    snapshot = DataSnapshot(source="test", frequency="1d", symbol="600000.SH", bars=bars)
    strategy = StrategySpec("no-reentry", CloseAboveSMA(2), CloseBelowSMA(2))
    result = run_experiment(snapshot, strategy, ExperimentConfig())
    # The exit for the position opened on 20260105 fills on 20260106. It must
    # not create a second entry signal from the same bar after that fill.
    assert result.traces[-1].signal != "entry"

