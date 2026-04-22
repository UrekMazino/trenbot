from __future__ import annotations

from okxtrendbot.models import Candle, PaperTradingConfig, SignalSide, TrendSignal
from okxtrendbot.paper import PaperTrader
from okxtrendbot.store import TrendStore


def _store(tmp_path) -> TrendStore:
    return TrendStore(tmp_path / "paper.sqlite")


def _trader(store: TrendStore) -> PaperTrader:
    return PaperTrader(
        store,
        PaperTradingConfig(
            paper_equity_usdt=1000.0,
            risk_per_trade_pct=1.0,
            max_notional_usdt=100.0,
            stop_atr_mult=2.0,
        ),
    )


def _candle(close: float, *, low: float | None = None, high: float | None = None, ts: str = "1") -> Candle:
    return Candle(
        ts=ts,
        open=close,
        high=high if high is not None else close + 1.0,
        low=low if low is not None else close - 1.0,
        close=close,
        volume=1000.0,
    )


def _signal(side: SignalSide, close: float, *, stop: float | None = None, reason: str = "test") -> TrendSignal:
    return TrendSignal(
        symbol="BTC-USDT-SWAP",
        side=side,
        reason=reason,
        close=close,
        ema_fast=105.0 if side != SignalSide.SHORT else 95.0,
        ema_slow=100.0,
        atr=2.0,
        stop_price=stop,
        confidence=0.7,
    )


def test_paper_trader_opens_position_from_signal(tmp_path):
    store = _store(tmp_path)
    signal = _signal(SignalSide.LONG, 100.0, stop=95.0)
    signal_id = store.record_signal(signal)

    result = _trader(store).apply_signal(signal, _candle(100.0), signal_id)
    position = store.get_open_position("BTC-USDT-SWAP")

    assert result.action == "OPEN_POSITION"
    assert position is not None
    assert position["side"] == "LONG"
    assert float(position["entry_price"]) == 100.0
    assert float(position["quantity"]) > 0


def test_paper_trader_holds_and_raises_long_trailing_stop(tmp_path):
    store = _store(tmp_path)
    trader = _trader(store)
    open_signal = _signal(SignalSide.LONG, 100.0, stop=95.0)
    signal_id = store.record_signal(open_signal)
    trader.apply_signal(open_signal, _candle(100.0), signal_id)

    hold_signal = _signal(SignalSide.FLAT, 110.0, reason="no_confirmed_breakout")
    hold_signal = TrendSignal(
        **{
            **hold_signal.__dict__,
            "ema_fast": 108.0,
            "ema_slow": 100.0,
            "atr": 2.0,
        }
    )
    hold_id = store.record_signal(hold_signal)
    result = trader.apply_signal(hold_signal, _candle(110.0, low=109.0, high=111.0, ts="2"), hold_id)
    position = store.get_open_position("BTC-USDT-SWAP")

    assert result.action == "UPDATE_TRAILING_STOP"
    assert position is not None
    assert float(position["stop_price"]) == 106.0
    assert float(position["unrealized_pnl_usdt"]) > 0


def test_paper_trader_closes_on_stop_loss(tmp_path):
    store = _store(tmp_path)
    trader = _trader(store)
    open_signal = _signal(SignalSide.LONG, 100.0, stop=95.0)
    signal_id = store.record_signal(open_signal)
    trader.apply_signal(open_signal, _candle(100.0), signal_id)

    flat_signal = _signal(SignalSide.FLAT, 94.0, reason="no_confirmed_breakout")
    flat_id = store.record_signal(flat_signal)
    result = trader.apply_signal(flat_signal, _candle(94.0, low=94.0, high=96.0, ts="2"), flat_id)
    status = store.paper_status("BTC-USDT-SWAP")

    assert result.action == "CLOSE_POSITION"
    assert result.trade_id is not None
    assert result.realized_pnl_usdt is not None
    assert result.realized_pnl_usdt < 0
    assert status["open_position"] is None
    assert status["stats"]["trades"] == 1
    assert status["recent_trades"][0]["exit_reason"] == "stop_loss"


def test_paper_trader_closes_on_opposite_signal(tmp_path):
    store = _store(tmp_path)
    trader = _trader(store)
    open_signal = _signal(SignalSide.LONG, 100.0, stop=95.0)
    signal_id = store.record_signal(open_signal)
    trader.apply_signal(open_signal, _candle(100.0), signal_id)

    short_signal = _signal(SignalSide.SHORT, 101.0, stop=106.0)
    short_id = store.record_signal(short_signal)
    result = trader.apply_signal(short_signal, _candle(101.0, low=100.0, high=102.0, ts="2"), short_id)

    assert result.action == "CLOSE_POSITION"
    assert result.trade is not None
    assert result.trade["exit_reason"] == "opposite_signal"
