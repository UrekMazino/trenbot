from __future__ import annotations

from okxtrendbot.models import Candle, SignalSide
from okxtrendbot.strategy import QuantTrendStrategy, TrendStrategyParams


def _candles_up(count: int = 90) -> list[Candle]:
    candles: list[Candle] = []
    price = 100.0
    for idx in range(count):
        price += 1.0
        candles.append(
            Candle(
                ts=str(idx),
                open=price - 0.4,
                high=price + 0.6,
                low=price - 0.8,
                close=price,
                volume=1000 + idx,
            )
        )
    candles[-1] = Candle(
        ts=str(count),
        open=price + 0.2,
        high=price + 4.0,
        low=price - 0.5,
        close=price + 3.0,
        volume=1400,
    )
    return candles


def _candles_down(count: int = 90) -> list[Candle]:
    candles: list[Candle] = []
    price = 200.0
    for idx in range(count):
        price -= 1.0
        candles.append(
            Candle(
                ts=str(idx),
                open=price + 0.4,
                high=price + 0.8,
                low=price - 0.6,
                close=price,
                volume=1000 + idx,
            )
        )
    candles[-1] = Candle(
        ts=str(count),
        open=price - 0.2,
        high=price + 0.5,
        low=price - 4.0,
        close=price - 3.0,
        volume=1400,
    )
    return candles


def _strategy() -> QuantTrendStrategy:
    return QuantTrendStrategy(
        TrendStrategyParams(
            ema_fast=10,
            ema_slow=30,
            atr_period=10,
            breakout_lookback=12,
            min_ema_gap_atr=0.1,
            max_extension_atr=4.0,
        )
    )


def test_strategy_stays_flat_with_insufficient_data():
    signal = _strategy().evaluate(_candles_up(10))

    assert signal.side == SignalSide.FLAT
    assert signal.reason == "insufficient_candles"


def test_strategy_detects_bullish_breakout():
    signal = _strategy().evaluate(_candles_up())

    assert signal.side == SignalSide.LONG
    assert signal.reason == "bullish_trend_breakout"
    assert signal.stop_price is not None
    assert signal.stop_price < signal.close


def test_strategy_detects_bearish_breakdown():
    signal = _strategy().evaluate(_candles_down())

    assert signal.side == SignalSide.SHORT
    assert signal.reason == "bearish_trend_breakdown"
    assert signal.stop_price is not None
    assert signal.stop_price > signal.close

