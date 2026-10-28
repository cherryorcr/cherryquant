from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence

from .models import Bar, ConditionResult, ConditionStatus


class Condition(Protocol):
    def evaluate(self, bars: Sequence[Bar], index: int) -> ConditionResult: ...

    def to_dict(self) -> dict[str, object]: ...


def _sma(bars: Sequence[Bar], index: int, period: int) -> Decimal | None:
    if index + 1 < period:
        return None
    closes = [bar.close for bar in bars[index + 1 - period : index + 1]]
    if any(close is None for close in closes):
        return None
    return sum((close for close in closes if close is not None), Decimal("0")) / Decimal(period)


def _unavailable(period: int, index: int, reason: str) -> ConditionResult:
    return ConditionResult(
        status=ConditionStatus.UNAVAILABLE,
        inputs={"index": index, "period": period},
        threshold=None,
        reason=reason,
    )


@dataclass(frozen=True)
class CloseAboveSMA:
    period: int

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("SMA period must be positive")

    def evaluate(self, bars: Sequence[Bar], index: int) -> ConditionResult:
        if index < 0 or index >= len(bars):
            return _unavailable(self.period, index, "INDEX_OUT_OF_RANGE")
        sma = _sma(bars, index, self.period)
        close = bars[index].close
        if sma is None or close is None:
            return _unavailable(self.period, index, "WARMUP_OR_MISSING_CLOSE")
        return ConditionResult(
            status=ConditionStatus.PASS if close > sma else ConditionStatus.FAIL,
            inputs={"close": close, "sma": sma, "period": self.period},
            threshold=f"close > SMA({self.period})",
            reason="CLOSE_ABOVE_SMA" if close > sma else "CLOSE_NOT_ABOVE_SMA",
        )

    def to_dict(self) -> dict[str, object]:
        return {"type": "close_above_sma", "period": self.period}


@dataclass(frozen=True)
class CloseBelowSMA:
    period: int

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("SMA period must be positive")

    def evaluate(self, bars: Sequence[Bar], index: int) -> ConditionResult:
        if index < 0 or index >= len(bars):
            return _unavailable(self.period, index, "INDEX_OUT_OF_RANGE")
        sma = _sma(bars, index, self.period)
        close = bars[index].close
        if sma is None or close is None:
            return _unavailable(self.period, index, "WARMUP_OR_MISSING_CLOSE")
        return ConditionResult(
            status=ConditionStatus.PASS if close < sma else ConditionStatus.FAIL,
            inputs={"close": close, "sma": sma, "period": self.period},
            threshold=f"close < SMA({self.period})",
            reason="CLOSE_BELOW_SMA" if close < sma else "CLOSE_NOT_BELOW_SMA",
        )

    def to_dict(self) -> dict[str, object]:
        return {"type": "close_below_sma", "period": self.period}


@dataclass(frozen=True)
class CloseCrossesAboveSMA:
    period: int

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("SMA period must be positive")

    def evaluate(self, bars: Sequence[Bar], index: int) -> ConditionResult:
        if index < 1:
            return _unavailable(self.period, index, "NEEDS_PREVIOUS_BAR")
        current = CloseAboveSMA(self.period).evaluate(bars, index)
        previous = CloseAboveSMA(self.period).evaluate(bars, index - 1)
        if current.status == ConditionStatus.UNAVAILABLE or previous.status == ConditionStatus.UNAVAILABLE:
            return _unavailable(self.period, index, "WARMUP_OR_MISSING_CLOSE")
        passed = current.status == ConditionStatus.PASS and previous.status == ConditionStatus.FAIL
        return ConditionResult(
            status=ConditionStatus.PASS if passed else ConditionStatus.FAIL,
            inputs={"current": current.inputs, "previous": previous.inputs, "period": self.period},
            threshold=f"crosses above SMA({self.period})",
            reason="CROSS_ABOVE" if passed else "NO_CROSS_ABOVE",
        )

    def to_dict(self) -> dict[str, object]:
        return {"type": "close_crosses_above_sma", "period": self.period}


@dataclass(frozen=True)
class CloseCrossesBelowSMA:
    period: int

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("SMA period must be positive")

    def evaluate(self, bars: Sequence[Bar], index: int) -> ConditionResult:
        if index < 1:
            return _unavailable(self.period, index, "NEEDS_PREVIOUS_BAR")
        current = CloseBelowSMA(self.period).evaluate(bars, index)
        previous = CloseBelowSMA(self.period).evaluate(bars, index - 1)
        if current.status == ConditionStatus.UNAVAILABLE or previous.status == ConditionStatus.UNAVAILABLE:
            return _unavailable(self.period, index, "WARMUP_OR_MISSING_CLOSE")
        passed = current.status == ConditionStatus.PASS and previous.status == ConditionStatus.FAIL
        return ConditionResult(
            status=ConditionStatus.PASS if passed else ConditionStatus.FAIL,
            inputs={"current": current.inputs, "previous": previous.inputs, "period": self.period},
            threshold=f"crosses below SMA({self.period})",
            reason="CROSS_BELOW" if passed else "NO_CROSS_BELOW",
        )

    def to_dict(self) -> dict[str, object]:
        return {"type": "close_crosses_below_sma", "period": self.period}


@dataclass(frozen=True)
class AllOf:
    conditions: tuple[Condition, ...]

    def __post_init__(self) -> None:
        if not self.conditions:
            raise ValueError("AllOf requires at least one condition")

    def evaluate(self, bars: Sequence[Bar], index: int) -> ConditionResult:
        results = [condition.evaluate(bars, index) for condition in self.conditions]
        if any(result.status == ConditionStatus.UNAVAILABLE for result in results):
            status = ConditionStatus.UNAVAILABLE
            reason = "ONE_OR_MORE_UNAVAILABLE"
        elif all(result.status == ConditionStatus.PASS for result in results):
            status = ConditionStatus.PASS
            reason = "ALL_CONDITIONS_PASS"
        else:
            status = ConditionStatus.FAIL
            reason = "ONE_OR_MORE_CONDITIONS_FAIL"
        return ConditionResult(
            status=status,
            inputs={"conditions": [result.to_dict() for result in results]},
            threshold="all",
            reason=reason,
        )

    def to_dict(self) -> dict[str, object]:
        return {"type": "all_of", "conditions": [condition.to_dict() for condition in self.conditions]}

