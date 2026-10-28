from __future__ import annotations

import pytest

from cherryquant_engine import DataSnapshot, bars_from_records


def test_snapshot_rejects_overlapping_holdout() -> None:
    bars = bars_from_records(
        [
            {"date": "20260101", "symbol": "600000.SH", "open": 10, "high": 10, "low": 10, "close": 10},
            {"date": "20260102", "symbol": "600000.SH", "open": 10, "high": 10, "low": 10, "close": 10},
        ]
    )
    with pytest.raises(ValueError, match="holdout interval"):
        DataSnapshot(
            source="test",
            frequency="1d",
            symbol="600000.SH",
            bars=bars,
            research_start="20260101",
            research_end="20260102",
            holdout_start="20260102",
            holdout_end="20260102",
        )


def test_snapshot_content_hash_is_stable(synthetic_snapshot: DataSnapshot) -> None:
    assert len(synthetic_snapshot.content_hash) == 64
    assert synthetic_snapshot.content_hash == DataSnapshot(
        source="other-source",
        frequency="1d",
        symbol="600000.SH",
        bars=synthetic_snapshot.bars,
    ).content_hash

