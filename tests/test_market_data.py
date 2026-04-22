from __future__ import annotations

from okxtrendbot.candles import load_candles_csv, write_candles_csv
from okxtrendbot.okx_market import parse_okx_candles


def test_parse_okx_candles_returns_chronological_candles():
    payload = {
        "code": "0",
        "msg": "",
        "data": [
            ["1713787200000", "102", "106", "101", "105", "12", "0", "0", "1"],
            ["1713783600000", "100", "103", "99", "102", "10", "0", "0", "1"],
        ],
    }

    candles = parse_okx_candles(payload)

    assert [candle.ts for candle in candles] == ["2024-04-22T11:00:00Z", "2024-04-22T12:00:00Z"]
    assert candles[0].open == 100.0
    assert candles[1].close == 105.0


def test_candle_csv_roundtrip(tmp_path):
    payload = {
        "code": "0",
        "msg": "",
        "data": [["1713783600000", "100", "103", "99", "102", "10", "0", "0", "1"]],
    }
    candles = parse_okx_candles(payload)
    path = tmp_path / "candles.csv"

    write_candles_csv(path, candles)
    loaded = load_candles_csv(path)

    assert loaded == candles
