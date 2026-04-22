from __future__ import annotations

import sqlite3

from okxtrendbot.config import BotConfig
from okxtrendbot.models import Candle
from okxtrendbot.runtime import PaperRunOptions, PaperRuntime
from okxtrendbot.store import TrendStore


def _cfg(tmp_path) -> BotConfig:
    return BotConfig(
        mode="paper",
        symbol="BTC-USDT-SWAP",
        timeframe="1H",
        db_path=tmp_path / "trend.sqlite",
        log_path=tmp_path / "logs" / "trend.log",
        state_path=tmp_path / "runtime_state.json",
        log_max_bytes=50_000,
        log_backups=1,
        candle_limit=90,
        okx_base_url="https://example.test",
        request_timeout_seconds=2.0,
        ema_fast=10,
        ema_slow=30,
        atr_period=10,
        breakout_lookback=12,
        min_ema_gap_atr=0.1,
        max_extension_atr=4.0,
        stop_atr_mult=2.0,
        paper_equity_usdt=1000.0,
        risk_per_trade_pct=1.0,
        max_notional_usdt=100.0,
    )


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


class _FakeClient:
    def fetch_candles(self, **_kwargs):
        return _candles_up()


def test_store_records_run_and_events(tmp_path):
    store = TrendStore(tmp_path / "trend.sqlite")
    run_id = store.start_run(run_key="paper_test", mode="paper", symbol="BTC-USDT-SWAP", timeframe="1H")
    event_id = store.record_event(run_id, event_type="heartbeat", message="ok", payload={"loop": 1})
    store.update_run_heartbeat(run_id, loop_count=1, signal_id=123, action="NO_POSITION")
    store.finish_run(run_id, status="stopped")

    latest = store.latest_run()
    assert latest is not None
    assert latest["id"] == run_id
    assert latest["loop_count"] == 1
    assert latest["last_signal_id"] == 123

    with sqlite3.connect(tmp_path / "trend.sqlite") as conn:
        count = conn.execute("SELECT COUNT(*) FROM run_events WHERE id = ?", (event_id,)).fetchone()[0]
    assert count == 1


def test_paper_runtime_runs_bounded_loop_with_state_and_events(tmp_path):
    cfg = _cfg(tmp_path)
    runtime = PaperRuntime(cfg, PaperRunOptions(interval_seconds=0.0, max_loops=1))
    runtime.client = _FakeClient()

    result = runtime.run()

    assert result["status"] == "stopped"
    assert result["loop_count"] == 1
    assert cfg.state_path.exists()
    assert cfg.log_path.exists()

    store = TrendStore(cfg.db_path)
    latest = store.latest_run()
    assert latest is not None
    assert latest["status"] == "stopped"
    assert latest["loop_count"] == 1

    with sqlite3.connect(cfg.db_path) as conn:
        events = conn.execute("SELECT event_type FROM run_events ORDER BY id").fetchall()
        event_types = [row[0] for row in events]
    assert "run_started" in event_types
    assert "paper_step" in event_types
    assert "run_finished" in event_types
