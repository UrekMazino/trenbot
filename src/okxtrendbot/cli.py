from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from .config import load_config
from .models import Candle, SignalSide
from .store import TrendStore
from .strategy import QuantTrendStrategy, TrendStrategyParams


def _load_candles_csv(path: Path) -> list[Candle]:
    candles: list[Candle] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            candles.append(
                Candle(
                    ts=str(row.get("ts") or row.get("timestamp") or ""),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                )
            )
    return candles


def _strategy_from_config() -> QuantTrendStrategy:
    cfg = load_config()
    return QuantTrendStrategy(
        TrendStrategyParams(
            symbol=cfg.symbol,
            ema_fast=cfg.ema_fast,
            ema_slow=cfg.ema_slow,
            atr_period=cfg.atr_period,
            breakout_lookback=cfg.breakout_lookback,
            min_ema_gap_atr=cfg.min_ema_gap_atr,
            max_extension_atr=cfg.max_extension_atr,
            stop_atr_mult=cfg.stop_atr_mult,
        )
    )


def cmd_init_db(_args: argparse.Namespace) -> int:
    cfg = load_config()
    TrendStore(cfg.db_path).init_db()
    print(f"Initialized OKXTRENDBOT database: {cfg.db_path}")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    cfg = load_config()
    candles = _load_candles_csv(Path(args.csv))
    signal = _strategy_from_config().evaluate(candles)
    if args.record:
        signal_id = TrendStore(cfg.db_path).record_signal(signal)
        print(f"Recorded signal #{signal_id}")
    payload = asdict(signal)
    payload["side"] = signal.side.value
    print(json.dumps(payload, indent=2, sort_keys=True))
    if signal.side == SignalSide.FLAT:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="okxtrendbot")
    sub = parser.add_subparsers(dest="command", required=True)

    init_db = sub.add_parser("init-db", help="Initialize the independent trend bot database")
    init_db.set_defaults(func=cmd_init_db)

    evaluate = sub.add_parser("evaluate", help="Evaluate trend signal from a candle CSV")
    evaluate.add_argument("--csv", required=True, help="Path to candle CSV with ts,open,high,low,close,volume")
    evaluate.add_argument("--record", action="store_true", help="Record the signal in the trend bot database")
    evaluate.set_defaults(func=cmd_evaluate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

