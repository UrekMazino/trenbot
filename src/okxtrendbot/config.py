from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - package dependency in normal install
    load_dotenv = None


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = str(raw).strip()
    return value or default


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(float(raw)) if raw is not None and str(raw).strip() else int(default)
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None:
        value = max(value, minimum)
    return value


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw is not None and str(raw).strip() else float(default)
    except (TypeError, ValueError):
        value = float(default)
    if minimum is not None:
        value = max(value, minimum)
    return value


@dataclass(frozen=True)
class BotConfig:
    mode: str
    symbol: str
    timeframe: str
    db_path: Path
    log_path: Path
    ema_fast: int
    ema_slow: int
    atr_period: int
    breakout_lookback: int
    min_ema_gap_atr: float
    max_extension_atr: float
    stop_atr_mult: float
    risk_per_trade_pct: float
    max_notional_usdt: float


def load_config(env_file: str | Path = ".env") -> BotConfig:
    env_path = Path(env_file)
    if load_dotenv is not None and env_path.exists():
        load_dotenv(env_path)

    mode = _env_str("TREND_BOT_MODE", "paper").lower()
    if mode not in {"paper", "shadow", "live"}:
        mode = "paper"

    ema_fast = _env_int("TREND_BOT_EMA_FAST", 20, minimum=2)
    ema_slow = _env_int("TREND_BOT_EMA_SLOW", 60, minimum=ema_fast + 1)

    return BotConfig(
        mode=mode,
        symbol=_env_str("TREND_BOT_SYMBOL", "BTC-USDT-SWAP").upper(),
        timeframe=_env_str("TREND_BOT_TIMEFRAME", "1H"),
        db_path=Path(_env_str("TREND_BOT_DB_PATH", "data/okxtrendbot.sqlite")),
        log_path=Path(_env_str("TREND_BOT_LOG_PATH", "logs/okxtrendbot.log")),
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        atr_period=_env_int("TREND_BOT_ATR_PERIOD", 14, minimum=2),
        breakout_lookback=_env_int("TREND_BOT_BREAKOUT_LOOKBACK", 20, minimum=2),
        min_ema_gap_atr=_env_float("TREND_BOT_MIN_EMA_GAP_ATR", 0.20, minimum=0.0),
        max_extension_atr=_env_float("TREND_BOT_MAX_EXTENSION_ATR", 3.00, minimum=0.1),
        stop_atr_mult=_env_float("TREND_BOT_STOP_ATR_MULT", 2.50, minimum=0.1),
        risk_per_trade_pct=_env_float("TREND_BOT_RISK_PER_TRADE_PCT", 0.25, minimum=0.0),
        max_notional_usdt=_env_float("TREND_BOT_MAX_NOTIONAL_USDT", 100.0, minimum=0.0),
    )

