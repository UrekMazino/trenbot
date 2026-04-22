from __future__ import annotations

import json
import logging
import signal
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .candles import write_candles_csv
from .config import BotConfig
from .models import PaperTradingConfig
from .okx_market import OkxMarketDataClient
from .paper import PaperTrader
from .store import TrendStore
from .strategy import QuantTrendStrategy, TrendStrategyParams


@dataclass(frozen=True)
class PaperRunOptions:
    interval_seconds: float = 300.0
    max_loops: int = 0
    symbol: str | None = None
    timeframe: str | None = None
    limit: int | None = None
    output: str | None = None


def setup_logger(log_path: Path, max_bytes: int, backups: int) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("okxtrendbot.runtime")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max(int(max_bytes), 1024),
        backupCount=max(int(backups), 0),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger


class PaperRuntime:
    def __init__(self, cfg: BotConfig, options: PaperRunOptions):
        self.cfg = cfg
        self.options = options
        self.symbol = options.symbol or cfg.symbol
        self.timeframe = options.timeframe or cfg.timeframe
        self.limit = options.limit or cfg.candle_limit
        self.output = Path(options.output or f"data/{self.symbol}-{self.timeframe}.csv")
        self.store = TrendStore(cfg.db_path)
        self.client = OkxMarketDataClient(cfg.okx_base_url, cfg.request_timeout_seconds)
        self.strategy = QuantTrendStrategy(
            TrendStrategyParams(
                symbol=self.symbol,
                ema_fast=cfg.ema_fast,
                ema_slow=cfg.ema_slow,
                atr_period=cfg.atr_period,
                breakout_lookback=cfg.breakout_lookback,
                min_ema_gap_atr=cfg.min_ema_gap_atr,
                max_extension_atr=cfg.max_extension_atr,
                stop_atr_mult=cfg.stop_atr_mult,
            )
        )
        self.paper_trader = PaperTrader(
            self.store,
            PaperTradingConfig(
                paper_equity_usdt=cfg.paper_equity_usdt,
                risk_per_trade_pct=cfg.risk_per_trade_pct,
                max_notional_usdt=cfg.max_notional_usdt,
                stop_atr_mult=cfg.stop_atr_mult,
            ),
        )
        self.logger = setup_logger(cfg.log_path, cfg.log_max_bytes, cfg.log_backups)
        self._stop_requested = False

    def run(self) -> dict[str, object]:
        run_key = self._run_key()
        run_id = self.store.start_run(
            run_key=run_key,
            mode=self.cfg.mode,
            symbol=self.symbol,
            timeframe=self.timeframe,
        )
        self.store.record_event(
            run_id,
            event_type="run_started",
            message="paper runtime started",
            payload=self._runtime_payload(run_key=run_key),
        )
        self._write_state(
            {
                "run_id": run_id,
                "run_key": run_key,
                "status": "running",
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "loop_count": 0,
            }
        )
        self._install_signal_handlers()
        self.logger.info("Paper runtime started run_key=%s symbol=%s timeframe=%s", run_key, self.symbol, self.timeframe)

        loop_count = 0
        status = "stopped"
        last_error = None
        try:
            while not self._stop_requested:
                loop_count += 1
                step = self.step(run_id, loop_count)
                self._write_state(
                    {
                        "run_id": run_id,
                        "run_key": run_key,
                        "status": "running",
                        "symbol": self.symbol,
                        "timeframe": self.timeframe,
                        "loop_count": loop_count,
                        "last_step": step,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                if self.options.max_loops and loop_count >= self.options.max_loops:
                    break
                self._sleep_interval()
        except Exception as exc:
            status = "error"
            last_error = str(exc)
            self.logger.exception("Paper runtime crashed: %s", exc)
            self.store.record_event(
                run_id,
                event_type="runtime_error",
                severity="error",
                message=str(exc),
                payload={"loop_count": loop_count},
            )
            raise
        finally:
            self.store.finish_run(run_id, status=status, last_error=last_error)
            self.store.record_event(
                run_id,
                event_type="run_finished",
                message=f"paper runtime {status}",
                payload={"loop_count": loop_count, "status": status, "last_error": last_error},
            )
            self._write_state(
                {
                    "run_id": run_id,
                    "run_key": run_key,
                    "status": status,
                    "symbol": self.symbol,
                    "timeframe": self.timeframe,
                    "loop_count": loop_count,
                    "last_error": last_error,
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            self.logger.info("Paper runtime finished run_key=%s status=%s loops=%d", run_key, status, loop_count)
        return {"run_id": run_id, "run_key": run_key, "status": status, "loop_count": loop_count}

    def step(self, run_id: str, loop_count: int) -> dict[str, object]:
        candles = self.client.fetch_candles(symbol=self.symbol, bar=self.timeframe, limit=self.limit)
        write_candles_csv(self.output, candles)
        signal_result = self.strategy.evaluate(candles)
        signal_id = self.store.record_signal(signal_result)
        paper_result = self.paper_trader.apply_signal(signal_result, candles[-1], signal_id)
        step_payload = {
            "loop_count": loop_count,
            "signal_id": signal_id,
            "signal": _signal_payload(signal_result),
            "paper": asdict(paper_result),
        }
        self.store.update_run_heartbeat(
            run_id,
            loop_count=loop_count,
            signal_id=signal_id,
            action=paper_result.action,
        )
        self.store.record_event(
            run_id,
            event_type="paper_step",
            message=paper_result.message,
            payload=step_payload,
        )
        self.logger.info(
            "paper_step loop=%d signal=%s reason=%s action=%s close=%s",
            loop_count,
            signal_result.side.value,
            signal_result.reason,
            paper_result.action,
            signal_result.close,
        )
        return step_payload

    def _sleep_interval(self) -> None:
        deadline = time.time() + max(float(self.options.interval_seconds), 0.0)
        while not self._stop_requested and time.time() < deadline:
            time.sleep(min(1.0, max(deadline - time.time(), 0.0)))

    def _install_signal_handlers(self) -> None:
        def _request_stop(_signum, _frame):
            self._stop_requested = True
            self.logger.info("Stop requested")

        try:
            signal.signal(signal.SIGINT, _request_stop)
            signal.signal(signal.SIGTERM, _request_stop)
        except (ValueError, AttributeError):
            pass

    def _write_state(self, payload: dict[str, object]) -> None:
        self.cfg.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _runtime_payload(self, *, run_key: str) -> dict[str, object]:
        return {
            "run_key": run_key,
            "mode": self.cfg.mode,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "interval_seconds": self.options.interval_seconds,
            "max_loops": self.options.max_loops,
        }

    @staticmethod
    def _run_key() -> str:
        return f"paper_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


def _signal_payload(signal) -> dict:
    payload = asdict(signal)
    payload["side"] = signal.side.value
    return payload
