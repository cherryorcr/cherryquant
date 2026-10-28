from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from enum import Enum
from typing import Any, Mapping


class ConditionStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class RunStatus(str, Enum):
    COMPLETED = "COMPLETED"
    NO_TRADES = "NO_TRADES"
    FAILED = "FAILED"


class OrderStatus(str, Enum):
    FILLED = "FILLED"
    NOT_FILLED = "NOT_FILLED"


def decimal(value: Any, *, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid decimal value: {value!r}") from exc


def decimal_string(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def normalize_symbol(value: Any) -> str:
    raw = str(value).strip().upper()
    if not raw:
        raise ValueError("symbol must not be empty")
    if raw.startswith(("SH.", "SZ.", "BJ.")):
        exchange, code = raw.split(".", 1)
        return f"{code}.{exchange}"
    if raw.endswith((".SH", ".SZ", ".BJ")):
        code, exchange = raw.split(".", 1)
        return f"{code}.{exchange}"
    if re.fullmatch(r"\d{6}", raw):
        exchange = "SH" if raw.startswith(("5", "6", "9")) else "SZ"
        return f"{raw}.{exchange}"
    return raw


def _date(value: Any) -> str:
    raw = str(value).strip().replace("-", "").replace("/", "")
    if not re.fullmatch(r"\d{8}", raw):
        raise ValueError(f"date must be YYYYMMDD, got {value!r}")
    return raw


@dataclass(frozen=True)
class Bar:
    date: str
    symbol: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None = None
    pre_close: Decimal | None = None
    suspended: bool = False
    limit_up: Decimal | None = None
    limit_down: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "date", _date(self.date))
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        for name in ("open", "high", "low", "close", "pre_close", "limit_up", "limit_down"):
            object.__setattr__(self, name, decimal(getattr(self, name)))
        if self.volume is not None:
            volume = int(self.volume)
            if volume < 0:
                raise ValueError("volume must be non-negative")
            object.__setattr__(self, "volume", volume)
        prices = [self.open, self.high, self.low, self.close]
        if any(price is not None and price <= 0 for price in prices):
            raise ValueError("OHLC prices must be positive when present")
        if all(price is not None for price in prices):
            assert self.open is not None and self.high is not None
            assert self.low is not None and self.close is not None
            if self.low > self.high or not (self.low <= self.open <= self.high):
                raise ValueError(f"invalid OHLC relationship on {self.date}")
            if not (self.low <= self.close <= self.high):
                raise ValueError(f"close outside low/high range on {self.date}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "symbol": self.symbol,
            "open": decimal_string(self.open),
            "high": decimal_string(self.high),
            "low": decimal_string(self.low),
            "close": decimal_string(self.close),
            "volume": self.volume,
            "pre_close": decimal_string(self.pre_close),
            "suspended": self.suspended,
            "limit_up": decimal_string(self.limit_up),
            "limit_down": decimal_string(self.limit_down),
        }


@dataclass(frozen=True)
class DataSnapshot:
    source: str
    frequency: str
    symbol: str
    bars: tuple[Bar, ...]
    price_basis: str = "unadjusted"
    research_start: str | None = None
    research_end: str | None = None
    holdout_start: str | None = None
    holdout_end: str | None = None
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if self.frequency != "1d":
            raise ValueError("M1 only supports daily frequency '1d'")
        normalized_symbol = normalize_symbol(self.symbol)
        object.__setattr__(self, "symbol", normalized_symbol)
        bars = tuple(self.bars)
        if any(bar.symbol != normalized_symbol for bar in bars):
            raise ValueError("all bars must use the snapshot symbol")
        dates = [bar.date for bar in bars]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError("bars must be strictly increasing with unique dates")
        for name in ("research_start", "research_end", "holdout_start", "holdout_end"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _date(value))
        if self.research_start and self.research_end and self.research_start > self.research_end:
            raise ValueError("research_start must not be after research_end")
        if self.holdout_start and self.holdout_end and self.holdout_start > self.holdout_end:
            raise ValueError("holdout_start must not be after holdout_end")
        if self.research_end and self.holdout_start and self.research_end >= self.holdout_start:
            raise ValueError("holdout interval must start after research interval")
        object.__setattr__(self, "bars", bars)
        if not self.content_hash:
            payload = json.dumps([bar.to_dict() for bar in bars], sort_keys=True, separators=(",", ":"))
            object.__setattr__(self, "content_hash", hashlib.sha256(payload.encode("utf-8")).hexdigest())

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "frequency": self.frequency,
            "symbol": self.symbol,
            "price_basis": self.price_basis,
            "research_start": self.research_start,
            "research_end": self.research_end,
            "holdout_start": self.holdout_start,
            "holdout_end": self.holdout_end,
            "content_hash": self.content_hash,
            "bars": [bar.to_dict() for bar in self.bars],
        }

    def for_scope(self, scope: str) -> "DataSnapshot":
        """Return a snapshot restricted to an explicit research scope.

        The full snapshot may contain a later holdout interval, but callers can
        pass the research-scoped copy to the engine so results and explanations
        cannot accidentally expose values from a locked interval.
        """
        if scope == "full":
            return self
        if scope == "research":
            if self.research_end is None:
                raise ValueError("research scope is unavailable without research_end")
            bars = tuple(bar for bar in self.bars if bar.date <= self.research_end)
        elif scope == "holdout":
            if self.holdout_start is None:
                raise ValueError("holdout scope is unavailable without holdout_start")
            bars = tuple(bar for bar in self.bars if bar.date >= self.holdout_start)
        else:
            raise ValueError(f"unsupported snapshot scope: {scope}")
        return DataSnapshot(
            source=self.source,
            frequency=self.frequency,
            symbol=self.symbol,
            bars=bars,
            price_basis=self.price_basis,
            research_start=self.research_start,
            research_end=self.research_end,
            holdout_start=self.holdout_start,
            holdout_end=self.holdout_end,
        )


@dataclass(frozen=True)
class StrategySpec:
    version_id: str
    entry_condition: Any
    exit_condition: Any
    position_fraction: Decimal = Decimal("1")
    lot_size: int = 100
    parent_version_id: str | None = None
    observe_at: str = "close"
    execute_at: str = "next_open"
    confirmed: bool = True
    change_reason: str = ""

    def __post_init__(self) -> None:
        if not self.version_id.strip():
            raise ValueError("version_id must not be empty")
        fraction = decimal(self.position_fraction)
        assert fraction is not None
        if not (Decimal("0") < fraction <= Decimal("1")):
            raise ValueError("position_fraction must be in (0, 1]")
        object.__setattr__(self, "position_fraction", fraction)
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if self.observe_at != "close" or self.execute_at != "next_open":
            raise ValueError("M1 only supports close observation and next-open execution")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "parent_version_id": self.parent_version_id,
            "entry_condition": self.entry_condition.to_dict(),
            "exit_condition": self.exit_condition.to_dict(),
            "position_fraction": decimal_string(self.position_fraction),
            "lot_size": self.lot_size,
            "observe_at": self.observe_at,
            "execute_at": self.execute_at,
            "confirmed": self.confirmed,
            "change_reason": self.change_reason,
        }


@dataclass(frozen=True)
class ExperimentConfig:
    initial_cash: Decimal = Decimal("100000")
    commission_rate: Decimal = Decimal("0.0003")
    min_commission: Decimal = Decimal("5")
    stamp_duty_rate: Decimal = Decimal("0.001")
    engine_version: str = "m1.0"
    order_expiry: str = "next_session"

    def __post_init__(self) -> None:
        for name in ("initial_cash", "commission_rate", "min_commission", "stamp_duty_rate"):
            value = decimal(getattr(self, name))
            assert value is not None
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.order_expiry != "next_session":
            raise ValueError("M1 only supports next_session order expiry")

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_cash": decimal_string(self.initial_cash),
            "commission_rate": decimal_string(self.commission_rate),
            "min_commission": decimal_string(self.min_commission),
            "stamp_duty_rate": decimal_string(self.stamp_duty_rate),
            "engine_version": self.engine_version,
            "order_expiry": self.order_expiry,
        }


@dataclass(frozen=True)
class ConditionResult:
    status: ConditionStatus
    inputs: Mapping[str, Any] = field(default_factory=dict)
    threshold: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "inputs": {key: decimal_string(value) if isinstance(value, Decimal) else value for key, value in self.inputs.items()},
            "threshold": self.threshold,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OrderAttempt:
    side: str
    signal_date: str
    execution_date: str | None
    quantity: int
    status: OrderStatus
    price: Decimal | None = None
    commission: Decimal = Decimal("0")
    stamp_duty: Decimal = Decimal("0")
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "signal_date": self.signal_date,
            "execution_date": self.execution_date,
            "quantity": self.quantity,
            "status": self.status.value,
            "price": decimal_string(self.price),
            "commission": decimal_string(self.commission),
            "stamp_duty": decimal_string(self.stamp_duty),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Trade:
    entry_signal_date: str
    entry_date: str
    exit_signal_date: str
    exit_date: str
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    entry_fees: Decimal
    exit_fees: Decimal
    realized_pnl: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_signal_date": self.entry_signal_date,
            "entry_date": self.entry_date,
            "exit_signal_date": self.exit_signal_date,
            "exit_date": self.exit_date,
            "quantity": self.quantity,
            "entry_price": decimal_string(self.entry_price),
            "exit_price": decimal_string(self.exit_price),
            "entry_fees": decimal_string(self.entry_fees),
            "exit_fees": decimal_string(self.exit_fees),
            "realized_pnl": decimal_string(self.realized_pnl),
        }


@dataclass(frozen=True)
class DecisionTrace:
    date: str
    condition_results: Mapping[str, ConditionResult]
    signal: str | None
    order_attempt: OrderAttempt | None
    position_before: Mapping[str, Any]
    position_after: Mapping[str, Any]
    cash_before: Decimal
    cash_after: Decimal
    equity: Decimal | None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "condition_results": {key: value.to_dict() for key, value in self.condition_results.items()},
            "signal": self.signal,
            "order_attempt": self.order_attempt.to_dict() if self.order_attempt else None,
            "position_before": dict(self.position_before),
            "position_after": dict(self.position_after),
            "cash_before": decimal_string(self.cash_before),
            "cash_after": decimal_string(self.cash_after),
            "equity": decimal_string(self.equity),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RunSummary:
    status: RunStatus
    reason: str
    initial_cash: Decimal
    final_cash: Decimal
    final_equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    trade_count: int
    filled_order_count: int
    not_filled_order_count: int
    total_return: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "initial_cash": decimal_string(self.initial_cash),
            "final_cash": decimal_string(self.final_cash),
            "final_equity": decimal_string(self.final_equity),
            "realized_pnl": decimal_string(self.realized_pnl),
            "unrealized_pnl": decimal_string(self.unrealized_pnl),
            "trade_count": self.trade_count,
            "filled_order_count": self.filled_order_count,
            "not_filled_order_count": self.not_filled_order_count,
            "total_return": decimal_string(self.total_return),
        }


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    summary: RunSummary
    traces: tuple[DecisionTrace, ...] = ()
    trades: tuple[Trade, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "summary": self.summary.to_dict(),
            "traces": [trace.to_dict() for trace in self.traces],
            "trades": [trade.to_dict() for trade in self.trades],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def floor_to_lot(value: Decimal, lot_size: int) -> int:
    if value <= 0:
        return 0
    lots = (value / Decimal(lot_size)).to_integral_value(rounding=ROUND_DOWN)
    return int(lots) * lot_size

