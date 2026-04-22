from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import mean

from .indicators import atr_series, ema_series
from .models import Candle, SignalSide, TrendSignal


@dataclass(frozen=True)
class TrendStrategyParams:
    symbol: str = "BTC-USDT-SWAP"
    ema_fast: int = 20
    ema_slow: int = 60
    atr_period: int = 14
    breakout_lookback: int = 20
    min_ema_gap_atr: float = 0.20
    max_extension_atr: float = 3.00
    stop_atr_mult: float = 2.50


class QuantTrendStrategy:
    """BTC-first single-symbol trend continuation model.

    The strategy stays flat unless trend strength, breakout direction, and
    overextension checks agree. This is deliberately not a statarb validator.
    """

    def __init__(self, params: TrendStrategyParams):
        self.params = params

    @property
    def min_candles(self) -> int:
        return max(
            self.params.ema_slow + 2,
            self.params.atr_period + 2,
            self.params.breakout_lookback + 2,
        )

    def evaluate(self, candles: list[Candle]) -> TrendSignal:
        if len(candles) < self.min_candles:
            return TrendSignal(
                symbol=self.params.symbol,
                side=SignalSide.FLAT,
                reason="insufficient_candles",
                diagnostics={"required": self.min_candles, "actual": len(candles)},
            )

        closes = [float(c.close) for c in candles]
        latest = candles[-1]
        prev_window = candles[-self.params.breakout_lookback - 1 : -1]
        prev_high = max(float(c.high) for c in prev_window)
        prev_low = min(float(c.low) for c in prev_window)

        fast = ema_series(closes, self.params.ema_fast)
        slow = ema_series(closes, self.params.ema_slow)
        atr = atr_series(candles, self.params.atr_period)
        fast_now = fast[-1]
        slow_now = slow[-1]
        fast_prev = fast[-2]
        atr_now = atr[-1]
        close = float(latest.close)

        if not self._all_finite(fast_now, slow_now, fast_prev, atr_now) or float(atr_now or 0.0) <= 0:
            return TrendSignal(
                symbol=self.params.symbol,
                side=SignalSide.FLAT,
                reason="indicator_not_ready",
                close=close,
            )

        fast_now = float(fast_now)
        slow_now = float(slow_now)
        fast_prev = float(fast_prev)
        atr_now = float(atr_now)
        ema_gap_atr = abs(fast_now - slow_now) / atr_now
        extension_atr = abs(close - fast_now) / atr_now
        breakout_up_atr = (close - prev_high) / atr_now
        breakout_down_atr = (prev_low - close) / atr_now

        diagnostics = {
            "prev_high": prev_high,
            "prev_low": prev_low,
            "ema_gap_atr": ema_gap_atr,
            "extension_atr": extension_atr,
            "breakout_up_atr": breakout_up_atr,
            "breakout_down_atr": breakout_down_atr,
        }

        if ema_gap_atr < self.params.min_ema_gap_atr:
            return self._flat("weak_trend_strength", close, fast_now, slow_now, atr_now, diagnostics)

        if extension_atr > self.params.max_extension_atr:
            return self._flat("overextended_move", close, fast_now, slow_now, atr_now, diagnostics)

        bullish = fast_now > slow_now and fast_now > fast_prev and close > prev_high
        bearish = fast_now < slow_now and fast_now < fast_prev and close < prev_low

        if bullish:
            confidence = self._confidence(ema_gap_atr, max(breakout_up_atr, 0.0), candles)
            return TrendSignal(
                symbol=self.params.symbol,
                side=SignalSide.LONG,
                reason="bullish_trend_breakout",
                close=close,
                ema_fast=fast_now,
                ema_slow=slow_now,
                atr=atr_now,
                stop_price=close - self.params.stop_atr_mult * atr_now,
                confidence=confidence,
                diagnostics=diagnostics,
            )

        if bearish:
            confidence = self._confidence(ema_gap_atr, max(breakout_down_atr, 0.0), candles)
            return TrendSignal(
                symbol=self.params.symbol,
                side=SignalSide.SHORT,
                reason="bearish_trend_breakdown",
                close=close,
                ema_fast=fast_now,
                ema_slow=slow_now,
                atr=atr_now,
                stop_price=close + self.params.stop_atr_mult * atr_now,
                confidence=confidence,
                diagnostics=diagnostics,
            )

        return self._flat("no_confirmed_breakout", close, fast_now, slow_now, atr_now, diagnostics)

    @staticmethod
    def _all_finite(*values: float | None) -> bool:
        return all(value is not None and isfinite(float(value)) for value in values)

    def _flat(
        self,
        reason: str,
        close: float,
        ema_fast: float,
        ema_slow: float,
        atr: float,
        diagnostics: dict[str, float | str | int | bool | None],
    ) -> TrendSignal:
        return TrendSignal(
            symbol=self.params.symbol,
            side=SignalSide.FLAT,
            reason=reason,
            close=close,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            atr=atr,
            confidence=0.0,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _confidence(ema_gap_atr: float, breakout_atr: float, candles: list[Candle]) -> float:
        recent_volumes = [float(c.volume) for c in candles[-20:] if float(c.volume) >= 0]
        volume_bonus = 0.0
        if len(recent_volumes) >= 10 and recent_volumes[-1] > mean(recent_volumes) * 1.10:
            volume_bonus = 0.08
        raw = 0.45 + min(ema_gap_atr, 2.0) * 0.18 + min(breakout_atr, 2.0) * 0.08 + volume_bonus
        return round(min(max(raw, 0.0), 1.0), 4)

