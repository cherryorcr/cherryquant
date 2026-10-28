from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from cherryquant_engine import (
    CloseAboveSMA,
    CloseBelowSMA,
    DataSnapshot,
    ExperimentConfig,
    StrategySpec,
    bars_from_records,
    read_json_records,
    run_experiment,
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    records = read_json_records(root / "fixtures" / "synthetic_daily.json")
    snapshot = DataSnapshot(
        source="cherryquant.synthetic",
        frequency="1d",
        symbol="600000.SH",
        bars=bars_from_records(records),
        research_start="20260101",
        research_end="20260105",
        holdout_start="20260106",
        holdout_end="20260108",
    )
    strategy = StrategySpec(
        version_id="demo-v1",
        entry_condition=CloseAboveSMA(2),
        exit_condition=CloseBelowSMA(2),
        position_fraction=Decimal("0.5"),
    )
    result = run_experiment(snapshot, strategy, ExperimentConfig())
    print(result.to_dict()["summary"])
    for trace in result.traces:
        if trace.signal or trace.order_attempt:
            print(trace.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

