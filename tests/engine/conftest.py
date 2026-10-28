from __future__ import annotations

from pathlib import Path

import pytest

from cherryquant_engine import DataSnapshot, bars_from_records, read_json_records


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def synthetic_snapshot() -> DataSnapshot:
    records = read_json_records(ROOT / "fixtures" / "synthetic_daily.json")
    return DataSnapshot(
        source="cherryquant.synthetic",
        frequency="1d",
        symbol="600000.SH",
        bars=bars_from_records(records),
        research_start="20260101",
        research_end="20260105",
        holdout_start="20260106",
        holdout_end="20260108",
    )

