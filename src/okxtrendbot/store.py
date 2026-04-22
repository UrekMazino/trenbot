from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import SignalSide, TrendSignal


class TrendStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trend_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    close REAL,
                    ema_fast REAL,
                    ema_slow REAL,
                    atr REAL,
                    stop_price REAL,
                    confidence REAL NOT NULL,
                    diagnostics_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_trend_signals_symbol_created
                ON trend_signals(symbol, created_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    entry_ts TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    notional_usdt REAL NOT NULL,
                    risk_usdt REAL,
                    stop_price REAL,
                    trailing_stop_price REAL,
                    atr_at_entry REAL,
                    confidence REAL NOT NULL,
                    entry_reason TEXT NOT NULL,
                    entry_signal_id INTEGER,
                    last_ts TEXT,
                    last_price REAL,
                    unrealized_pnl_usdt REAL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_paper_positions_symbol_status
                ON paper_positions(symbol, status)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    position_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_ts TEXT NOT NULL,
                    exit_ts TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    notional_usdt REAL NOT NULL,
                    pnl_usdt REAL NOT NULL,
                    pnl_pct REAL NOT NULL,
                    exit_reason TEXT NOT NULL,
                    entry_reason TEXT NOT NULL,
                    entry_signal_id INTEGER,
                    exit_signal_id INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_paper_trades_symbol_created
                ON paper_trades(symbol, created_at)
                """
            )

    def record_signal(self, signal: TrendSignal) -> int:
        self.init_db()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO trend_signals (
                    symbol, side, reason, close, ema_fast, ema_slow, atr,
                    stop_price, confidence, diagnostics_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.symbol,
                    signal.side.value,
                    signal.reason,
                    signal.close,
                    signal.ema_fast,
                    signal.ema_slow,
                    signal.atr,
                    signal.stop_price,
                    signal.confidence,
                    json.dumps(signal.diagnostics, sort_keys=True),
                ),
            )
            return int(cur.lastrowid)

    def get_open_position(self, symbol: str) -> dict[str, object] | None:
        self.init_db()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM paper_positions
                WHERE symbol = ? AND status = 'OPEN'
                ORDER BY id DESC
                LIMIT 1
                """,
                (symbol,),
            ).fetchone()
        return _row_to_dict(row)

    def open_position(
        self,
        *,
        symbol: str,
        side: SignalSide,
        entry_ts: str,
        entry_price: float,
        quantity: float,
        notional_usdt: float,
        risk_usdt: float,
        stop_price: float,
        atr_at_entry: float | None,
        confidence: float,
        entry_reason: str,
        entry_signal_id: int,
    ) -> int:
        self.init_db()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO paper_positions (
                    symbol, side, status, entry_ts, entry_price, quantity,
                    notional_usdt, risk_usdt, stop_price, trailing_stop_price,
                    atr_at_entry, confidence, entry_reason, entry_signal_id,
                    last_ts, last_price, unrealized_pnl_usdt
                )
                VALUES (?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    side.value,
                    entry_ts,
                    entry_price,
                    quantity,
                    notional_usdt,
                    risk_usdt,
                    stop_price,
                    stop_price,
                    atr_at_entry,
                    confidence,
                    entry_reason,
                    entry_signal_id,
                    entry_ts,
                    entry_price,
                    0.0,
                ),
            )
            return int(cur.lastrowid)

    def update_position(
        self,
        position_id: int,
        *,
        last_ts: str,
        last_price: float,
        stop_price: float,
        unrealized_pnl_usdt: float,
    ) -> None:
        self.init_db()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE paper_positions
                SET updated_at = CURRENT_TIMESTAMP,
                    last_ts = ?,
                    last_price = ?,
                    stop_price = ?,
                    trailing_stop_price = ?,
                    unrealized_pnl_usdt = ?
                WHERE id = ? AND status = 'OPEN'
                """,
                (
                    last_ts,
                    last_price,
                    stop_price,
                    stop_price,
                    unrealized_pnl_usdt,
                    position_id,
                ),
            )

    def close_position(
        self,
        position_id: int,
        *,
        exit_ts: str,
        exit_price: float,
        exit_reason: str,
        exit_signal_id: int,
    ) -> tuple[int, dict[str, object]]:
        self.init_db()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM paper_positions WHERE id = ? AND status = 'OPEN'",
                (position_id,),
            ).fetchone()
            position = _row_to_dict(row)
            if position is None:
                raise ValueError(f"open paper position not found: {position_id}")

            side = str(position["side"])
            entry_price = float(position["entry_price"])
            quantity = float(position["quantity"])
            notional_usdt = float(position["notional_usdt"])
            if side == SignalSide.LONG.value:
                pnl_usdt = (exit_price - entry_price) * quantity
            else:
                pnl_usdt = (entry_price - exit_price) * quantity
            pnl_pct = (pnl_usdt / notional_usdt * 100.0) if notional_usdt else 0.0

            conn.execute(
                """
                UPDATE paper_positions
                SET status = 'CLOSED',
                    updated_at = CURRENT_TIMESTAMP,
                    last_ts = ?,
                    last_price = ?,
                    unrealized_pnl_usdt = ?
                WHERE id = ?
                """,
                (exit_ts, exit_price, pnl_usdt, position_id),
            )
            cur = conn.execute(
                """
                INSERT INTO paper_trades (
                    position_id, symbol, side, entry_ts, exit_ts, entry_price,
                    exit_price, quantity, notional_usdt, pnl_usdt, pnl_pct,
                    exit_reason, entry_reason, entry_signal_id, exit_signal_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position_id,
                    position["symbol"],
                    side,
                    position["entry_ts"],
                    exit_ts,
                    entry_price,
                    exit_price,
                    quantity,
                    notional_usdt,
                    pnl_usdt,
                    pnl_pct,
                    exit_reason,
                    position["entry_reason"],
                    position["entry_signal_id"],
                    exit_signal_id,
                ),
            )
            trade_id = int(cur.lastrowid)
            trade = _row_to_dict(
                conn.execute("SELECT * FROM paper_trades WHERE id = ?", (trade_id,)).fetchone()
            )
            return trade_id, trade or {}

    def paper_status(self, symbol: str) -> dict[str, object]:
        self.init_db()
        with self.connect() as conn:
            open_position = _row_to_dict(
                conn.execute(
                    """
                    SELECT * FROM paper_positions
                    WHERE symbol = ? AND status = 'OPEN'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (symbol,),
                ).fetchone()
            )
            stats = _row_to_dict(
                conn.execute(
                    """
                    SELECT
                        COUNT(*) AS trades,
                        COALESCE(SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END), 0) AS wins,
                        COALESCE(SUM(CASE WHEN pnl_usdt < 0 THEN 1 ELSE 0 END), 0) AS losses,
                        COALESCE(SUM(pnl_usdt), 0.0) AS pnl_usdt,
                        COALESCE(AVG(pnl_usdt), 0.0) AS avg_pnl_usdt
                    FROM paper_trades
                    WHERE symbol = ?
                    """,
                    (symbol,),
                ).fetchone()
            )
            recent_trades = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM paper_trades
                    WHERE symbol = ?
                    ORDER BY id DESC
                    LIMIT 10
                    """,
                    (symbol,),
                ).fetchall()
            ]
        trades = int((stats or {}).get("trades") or 0)
        wins = int((stats or {}).get("wins") or 0)
        win_rate_pct = (wins / trades * 100.0) if trades else None
        return {
            "symbol": symbol,
            "open_position": open_position,
            "stats": {
                **(stats or {}),
                "win_rate_pct": round(win_rate_pct, 2) if win_rate_pct is not None else None,
            },
            "recent_trades": recent_trades,
        }

    def reset_paper(self, symbol: str | None = None) -> dict[str, int]:
        self.init_db()
        with self.connect() as conn:
            if symbol:
                trades_deleted = conn.execute(
                    "DELETE FROM paper_trades WHERE symbol = ?",
                    (symbol,),
                ).rowcount
                positions_deleted = conn.execute(
                    "DELETE FROM paper_positions WHERE symbol = ?",
                    (symbol,),
                ).rowcount
            else:
                trades_deleted = conn.execute("DELETE FROM paper_trades").rowcount
                positions_deleted = conn.execute("DELETE FROM paper_positions").rowcount
        return {
            "deleted_positions": int(positions_deleted or 0),
            "deleted_trades": int(trades_deleted or 0),
        }


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, object] | None:
    if row is None:
        return None
    return dict(row)
