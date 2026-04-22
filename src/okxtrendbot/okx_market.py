from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Candle


class OkxMarketDataError(RuntimeError):
    pass


class OkxMarketDataClient:
    def __init__(self, base_url: str = "https://www.okx.com", timeout_seconds: float = 10.0):
        self.base_url = str(base_url or "https://www.okx.com").rstrip("/")
        self.timeout_seconds = float(timeout_seconds or 10.0)

    def fetch_candles(self, symbol: str, bar: str = "1H", limit: int = 300) -> list[Candle]:
        params = urlencode(
            {
                "instId": symbol,
                "bar": bar,
                "limit": max(min(int(limit), 300), 1),
            }
        )
        url = f"{self.base_url}/api/v5/market/candles?{params}"
        request = Request(url, headers={"User-Agent": "OKXTRENDBOT/0.1"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except Exception as exc:  # pragma: no cover - network dependent
            raise OkxMarketDataError(f"OKX candle request failed: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OkxMarketDataError("OKX candle response was not valid JSON") from exc
        return parse_okx_candles(payload)


def parse_okx_candles(payload: dict[str, Any]) -> list[Candle]:
    if str(payload.get("code")) != "0":
        message = payload.get("msg") or "unknown OKX error"
        raise OkxMarketDataError(f"OKX candle response error: {message}")

    rows = payload.get("data")
    if not isinstance(rows, list):
        raise OkxMarketDataError("OKX candle response missing data rows")

    candles: list[Candle] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        ts_raw, open_raw, high_raw, low_raw, close_raw, volume_raw = row[:6]
        candles.append(
            Candle(
                ts=_format_okx_ts(ts_raw),
                open=float(open_raw),
                high=float(high_raw),
                low=float(low_raw),
                close=float(close_raw),
                volume=float(volume_raw),
            )
        )

    candles.sort(key=lambda item: item.ts)
    return candles


def _format_okx_ts(value: object) -> str:
    try:
        timestamp_ms = int(float(value))
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp_ms / 1000.0))
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value or "")

