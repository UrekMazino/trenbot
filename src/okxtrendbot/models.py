from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SignalSide(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class TrendSignal:
    symbol: str
    side: SignalSide
    reason: str
    close: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None
    atr: float | None = None
    stop_price: float | None = None
    confidence: float = 0.0
    diagnostics: dict[str, float | str | int | bool | None] = field(default_factory=dict)

