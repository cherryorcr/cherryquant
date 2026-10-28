"""CherryQuant's small, deterministic M1 experiment engine."""

from .conditions import (
    AllOf,
    CloseAboveSMA,
    CloseBelowSMA,
    CloseCrossesAboveSMA,
    CloseCrossesBelowSMA,
)
from .data_adapter import bars_from_records, normalize_bar_record, normalize_symbol, read_json_records
from .models import (
    Bar,
    ConditionResult,
    ConditionStatus,
    DataSnapshot,
    ExperimentConfig,
    RunResult,
    RunStatus,
    StrategySpec,
)
from .simulator import run_experiment

__all__ = [
    "AllOf",
    "Bar",
    "CloseAboveSMA",
    "CloseBelowSMA",
    "CloseCrossesAboveSMA",
    "CloseCrossesBelowSMA",
    "ConditionResult",
    "ConditionStatus",
    "DataSnapshot",
    "ExperimentConfig",
    "RunResult",
    "RunStatus",
    "StrategySpec",
    "normalize_bar_record",
    "normalize_symbol",
    "read_json_records",
    "bars_from_records",
    "run_experiment",
]

