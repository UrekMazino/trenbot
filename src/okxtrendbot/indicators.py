from __future__ import annotations

from collections.abc import Sequence

from .models import Candle


def ema_series(values: Sequence[float], period: int) -> list[float | None]:
    if period < 2:
        raise ValueError("period must be >= 2")
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output

    seed = sum(float(v) for v in values[:period]) / period
    output[period - 1] = seed
    alpha = 2.0 / (period + 1.0)
    prev = seed
    for idx in range(period, len(values)):
        current = float(values[idx]) * alpha + prev * (1.0 - alpha)
        output[idx] = current
        prev = current
    return output


def true_ranges(candles: Sequence[Candle]) -> list[float]:
    ranges: list[float] = []
    prev_close: float | None = None
    for candle in candles:
        high = float(candle.high)
        low = float(candle.low)
        if prev_close is None:
            ranges.append(high - low)
        else:
            ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        prev_close = float(candle.close)
    return ranges


def atr_series(candles: Sequence[Candle], period: int) -> list[float | None]:
    ranges = true_ranges(candles)
    return ema_series(ranges, period)

