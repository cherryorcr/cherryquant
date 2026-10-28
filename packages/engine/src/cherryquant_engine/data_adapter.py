from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import Bar, normalize_symbol


def read_json_records(path: str | Path) -> list[dict[str, Any]]:
    """Read a small JSON list of daily-bar records.

    M1 intentionally uses JSON fixtures so the engine has no pandas/Parquet or
    network dependency. A future data layer can add Parquet readers around the
    same normalized record shape.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError("daily-bar JSON must contain a list of objects")
    return [dict(row) for row in payload]


def normalize_bar_record(record: Mapping[str, Any], *, default_symbol: str | None = None) -> Bar:
    """Convert common Baostock/quant daily-bar fields into a CherryQuant Bar.

    The mapping is a clean-room rewrite of the field normalization idea used by
    ``quant/limitup_ai``. It does not import that project's runtime or copy its
    provider/backtest implementation.
    """
    symbol = record.get("symbol", record.get("ts_code", record.get("code", default_symbol)))
    if symbol is None:
        raise ValueError("daily-bar record is missing code/symbol")
    date = record.get("date", record.get("trade_date"))
    if date is None:
        raise ValueError("daily-bar record is missing date/trade_date")
    return Bar(
        date=str(date),
        symbol=normalize_symbol(symbol),
        open=record.get("open"),
        high=record.get("high"),
        low=record.get("low"),
        close=record.get("close"),
        volume=record.get("volume", record.get("vol")),
        pre_close=record.get("pre_close", record.get("preclose")),
        suspended=bool(record.get("suspended", False)),
        limit_up=record.get("limit_up", record.get("up_limit")),
        limit_down=record.get("limit_down", record.get("down_limit")),
    )


def bars_from_records(records: Iterable[Mapping[str, Any]], *, default_symbol: str | None = None) -> tuple[Bar, ...]:
    return tuple(sorted((normalize_bar_record(row, default_symbol=default_symbol) for row in records), key=lambda bar: bar.date))

