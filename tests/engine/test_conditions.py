from __future__ import annotations

from cherryquant_engine import (
    CloseAboveSMA,
    CloseCrossesAboveSMA,
    ConditionStatus,
    DataSnapshot,
)


def test_sma_warmup_is_unavailable(synthetic_snapshot: DataSnapshot) -> None:
    condition = CloseAboveSMA(2)
    result = condition.evaluate(synthetic_snapshot.bars, 0)
    assert result.status == ConditionStatus.UNAVAILABLE
    assert result.reason == "WARMUP_OR_MISSING_CLOSE"


def test_sma_condition_records_inputs(synthetic_snapshot: DataSnapshot) -> None:
    result = CloseAboveSMA(2).evaluate(synthetic_snapshot.bars, 1)
    assert result.status == ConditionStatus.PASS
    assert result.inputs["close"] == 10.5
    assert str(result.inputs["sma"]) == "10.25"


def test_cross_condition_requires_previous_observation(synthetic_snapshot: DataSnapshot) -> None:
    result = CloseCrossesAboveSMA(2).evaluate(synthetic_snapshot.bars, 0)
    assert result.status == ConditionStatus.UNAVAILABLE
    assert result.reason == "NEEDS_PREVIOUS_BAR"

