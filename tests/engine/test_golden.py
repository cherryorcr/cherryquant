from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from cherryquant_engine import CloseAboveSMA, CloseBelowSMA, DataSnapshot, ExperimentConfig, StrategySpec, run_experiment


def test_golden_run_is_deterministic(synthetic_snapshot: DataSnapshot) -> None:
    strategy = StrategySpec(
        version_id="golden-v1",
        entry_condition=CloseAboveSMA(2),
        exit_condition=CloseBelowSMA(2),
        position_fraction=Decimal("0.5"),
    )
    config = ExperimentConfig()
    first = run_experiment(synthetic_snapshot, strategy, config).to_dict()
    second = run_experiment(synthetic_snapshot, strategy, config).to_dict()
    assert first == second
    assert first["summary"]["trade_count"] == 1
    assert first["traces"][1]["signal"] == "entry"
    assert first["traces"][4]["order_attempt"]["price"] == "10.00"

    expected = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "golden_run.json").read_text())
    assert first["status"] == expected["status"]
    for key, value in expected["summary"].items():
        assert first["summary"][key] == value
    fills = [
        {
            "date": trace["date"],
            "side": trace["order_attempt"]["side"],
            "price": trace["order_attempt"]["price"],
            "quantity": trace["order_attempt"]["quantity"],
        }
        for trace in first["traces"]
        if trace["order_attempt"] and trace["order_attempt"]["status"] == "FILLED"
    ]
    assert fills == expected["fills"]

