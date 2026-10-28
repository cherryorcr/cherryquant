from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from cherryquant_engine import normalize_bar_record, normalize_symbol, read_json_records


def test_quant_style_daily_bar_is_normalized() -> None:
    bar = normalize_bar_record(
        {
            "code": "sh.600000",
            "date": "2026-04-30",
            "open": "10.00",
            "high": "11.00",
            "low": "10.00",
            "close": "11.00",
            "preclose": "10.00",
        }
    )
    assert bar.symbol == "600000.SH"
    assert bar.date == "20260430"
    assert bar.close == Decimal("11.00")
    assert bar.pre_close == Decimal("10.00")


def test_symbol_normalization_supports_common_forms() -> None:
    assert normalize_symbol("600000") == "600000.SH"
    assert normalize_symbol("600000.SH") == "600000.SH"
    assert normalize_symbol("sh.600000") == "600000.SH"


def test_migrated_fixture_is_small_and_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    records = read_json_records(root / "fixtures" / "quant_daily_bar_sample.json")
    assert len(records) == 1
    assert records[0]["provenance"].startswith("small schema fixture")

