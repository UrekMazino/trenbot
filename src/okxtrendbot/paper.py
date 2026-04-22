from __future__ import annotations

from math import inf, isfinite

from .models import Candle, PaperStepResult, PaperTradingConfig, SignalSide, TrendSignal
from .store import TrendStore


class PaperTrader:
    def __init__(self, store: TrendStore, config: PaperTradingConfig):
        self.store = store
        self.config = config

    def apply_signal(self, signal: TrendSignal, latest_candle: Candle, signal_id: int) -> PaperStepResult:
        position = self.store.get_open_position(signal.symbol)
        if position is None:
            return self._maybe_open(signal, latest_candle, signal_id)
        return self._manage_open_position(position, signal, latest_candle, signal_id)

    def _maybe_open(self, signal: TrendSignal, latest_candle: Candle, signal_id: int) -> PaperStepResult:
        if signal.side == SignalSide.FLAT:
            return PaperStepResult(
                action="NO_POSITION",
                message=f"No paper position opened: {signal.reason}",
                signal_id=signal_id,
            )

        entry_price = _finite_or(signal.close, latest_candle.close)
        stop_price = signal.stop_price
        if stop_price is None and signal.atr is not None:
            stop_price = (
                entry_price - self.config.stop_atr_mult * signal.atr
                if signal.side == SignalSide.LONG
                else entry_price + self.config.stop_atr_mult * signal.atr
            )
        if stop_price is None or not isfinite(float(stop_price)):
            return PaperStepResult(
                action="OPEN_REJECTED",
                message="No paper position opened: missing stop price",
                signal_id=signal_id,
            )

        stop_distance = abs(entry_price - float(stop_price))
        if stop_distance <= 0:
            return PaperStepResult(
                action="OPEN_REJECTED",
                message="No paper position opened: invalid stop distance",
                signal_id=signal_id,
            )

        risk_usdt = self.config.paper_equity_usdt * (self.config.risk_per_trade_pct / 100.0)
        risk_quantity = risk_usdt / stop_distance if risk_usdt > 0 else inf
        notional_quantity = self.config.max_notional_usdt / entry_price if self.config.max_notional_usdt > 0 else inf
        quantity = min(risk_quantity, notional_quantity)
        if not isfinite(quantity) or quantity <= 0:
            return PaperStepResult(
                action="OPEN_REJECTED",
                message="No paper position opened: risk/notional settings produce zero size",
                signal_id=signal_id,
            )

        notional_usdt = quantity * entry_price
        position_id = self.store.open_position(
            symbol=signal.symbol,
            side=signal.side,
            entry_ts=latest_candle.ts,
            entry_price=entry_price,
            quantity=quantity,
            notional_usdt=notional_usdt,
            risk_usdt=risk_usdt,
            stop_price=float(stop_price),
            atr_at_entry=signal.atr,
            confidence=signal.confidence,
            entry_reason=signal.reason,
            entry_signal_id=signal_id,
        )
        position = self.store.get_open_position(signal.symbol)
        return PaperStepResult(
            action="OPEN_POSITION",
            message=f"Opened paper {signal.side.value} position",
            signal_id=signal_id,
            position_id=position_id,
            position=position,
        )

    def _manage_open_position(
        self,
        position: dict[str, object],
        signal: TrendSignal,
        latest_candle: Candle,
        signal_id: int,
    ) -> PaperStepResult:
        position_id = int(position["id"])
        side = str(position["side"])
        stop_price = _finite_or(position.get("trailing_stop_price"), position.get("stop_price"))
        close = float(latest_candle.close)

        stop_hit = (
            (side == SignalSide.LONG.value and float(latest_candle.low) <= stop_price)
            or (side == SignalSide.SHORT.value and float(latest_candle.high) >= stop_price)
        )
        if stop_hit:
            return self._close(position_id, signal_id, latest_candle.ts, stop_price, "stop_loss")

        if (
            (side == SignalSide.LONG.value and signal.side == SignalSide.SHORT)
            or (side == SignalSide.SHORT.value and signal.side == SignalSide.LONG)
        ):
            return self._close(position_id, signal_id, latest_candle.ts, close, "opposite_signal")

        trend_invalidated = False
        if signal.ema_fast is not None and signal.ema_slow is not None:
            if side == SignalSide.LONG.value and signal.ema_fast <= signal.ema_slow:
                trend_invalidated = True
            elif side == SignalSide.SHORT.value and signal.ema_fast >= signal.ema_slow:
                trend_invalidated = True
        if trend_invalidated:
            return self._close(position_id, signal_id, latest_candle.ts, close, "trend_invalidated")

        new_stop = self._trailing_stop(side, close, stop_price, signal)
        unrealized = _position_pnl(position, close)
        self.store.update_position(
            position_id,
            last_ts=latest_candle.ts,
            last_price=close,
            stop_price=new_stop,
            unrealized_pnl_usdt=unrealized,
        )
        refreshed = self.store.get_open_position(signal.symbol)
        action = "UPDATE_TRAILING_STOP" if abs(new_stop - stop_price) > 1e-9 else "HOLD_POSITION"
        return PaperStepResult(
            action=action,
            message="Paper position remains open",
            signal_id=signal_id,
            position_id=position_id,
            unrealized_pnl_usdt=unrealized,
            position=refreshed,
        )

    def _close(
        self,
        position_id: int,
        signal_id: int,
        exit_ts: str,
        exit_price: float,
        reason: str,
    ) -> PaperStepResult:
        trade_id, trade = self.store.close_position(
            position_id,
            exit_ts=exit_ts,
            exit_price=exit_price,
            exit_reason=reason,
            exit_signal_id=signal_id,
        )
        realized = float(trade.get("pnl_usdt") or 0.0)
        return PaperStepResult(
            action="CLOSE_POSITION",
            message=f"Closed paper position: {reason}",
            signal_id=signal_id,
            position_id=position_id,
            trade_id=trade_id,
            realized_pnl_usdt=realized,
            trade=trade,
        )

    def _trailing_stop(self, side: str, close: float, stop_price: float, signal: TrendSignal) -> float:
        if signal.atr is None or signal.atr <= 0:
            return stop_price
        if side == SignalSide.LONG.value:
            candidate = close - self.config.stop_atr_mult * signal.atr
            return max(stop_price, candidate)
        candidate = close + self.config.stop_atr_mult * signal.atr
        return min(stop_price, candidate)


def _position_pnl(position: dict[str, object], exit_price: float) -> float:
    side = str(position["side"])
    entry_price = float(position["entry_price"])
    quantity = float(position["quantity"])
    if side == SignalSide.LONG.value:
        return (exit_price - entry_price) * quantity
    return (entry_price - exit_price) * quantity


def _finite_or(value: object, fallback: object) -> float:
    try:
        parsed = float(value)
        if isfinite(parsed):
            return parsed
    except (TypeError, ValueError):
        pass
    return float(fallback)
