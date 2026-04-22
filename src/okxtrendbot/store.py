from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import TrendSignal


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

