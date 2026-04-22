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


@dataclass(frozen=True)
class PaperTradingConfig:
    paper_equity_usdt: float = 1000.0
    risk_per_trade_pct: float = 0.25
    max_notional_usdt: float = 100.0
    stop_atr_mult: float = 2.5


@dataclass(frozen=True)
class PaperStepResult:
    action: str
    message: str
    signal_id: int
    position_id: int | None = None
    trade_id: int | None = None
    realized_pnl_usdt: float | None = None
    unrealized_pnl_usdt: float | None = None
    position: dict[str, object] | None = None
    trade: dict[str, object] | None = None
