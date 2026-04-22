from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .candles import load_candles_csv, write_candles_csv
from .config import load_config
from .models import SignalSide
from .okx_market import OkxMarketDataClient
from .store import TrendStore
from .strategy import QuantTrendStrategy, TrendStrategyParams


def _strategy_from_config(symbol: str | None = None) -> QuantTrendStrategy:
    cfg = load_config()
    return QuantTrendStrategy(
        TrendStrategyParams(
            symbol=symbol or cfg.symbol,
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


def _signal_payload(signal) -> dict:
    payload = asdict(signal)
    payload["side"] = signal.side.value
    return payload


def cmd_evaluate(args: argparse.Namespace) -> int:
    cfg = load_config()
    candles = load_candles_csv(Path(args.csv))
    signal = _strategy_from_config().evaluate(candles)
    if args.record:
        signal_id = TrendStore(cfg.db_path).record_signal(signal)
        print(f"Recorded signal #{signal_id}")
    print(json.dumps(_signal_payload(signal), indent=2, sort_keys=True))
    return 0


def cmd_fetch_candles(args: argparse.Namespace) -> int:
    cfg = load_config()
    symbol = args.symbol or cfg.symbol
    timeframe = args.timeframe or cfg.timeframe
    limit = args.limit or cfg.candle_limit
    output = Path(args.output or f"data/{symbol}-{timeframe}.csv")
    client = OkxMarketDataClient(cfg.okx_base_url, cfg.request_timeout_seconds)
    candles = client.fetch_candles(symbol=symbol, bar=timeframe, limit=limit)
    write_candles_csv(output, candles)
    print(f"Fetched {len(candles)} candles for {symbol} {timeframe}: {output}")
    return 0


def cmd_paper_step(args: argparse.Namespace) -> int:
    cfg = load_config()
    symbol = args.symbol or cfg.symbol
    timeframe = args.timeframe or cfg.timeframe
    limit = args.limit or cfg.candle_limit
    output = Path(args.output or f"data/{symbol}-{timeframe}.csv")
    client = OkxMarketDataClient(cfg.okx_base_url, cfg.request_timeout_seconds)
    candles = client.fetch_candles(symbol=symbol, bar=timeframe, limit=limit)
    write_candles_csv(output, candles)
    signal = _strategy_from_config(symbol=symbol).evaluate(candles)
    signal_id = TrendStore(cfg.db_path).record_signal(signal)
    print(f"Fetched {len(candles)} candles and recorded signal #{signal_id}")
    print(json.dumps(_signal_payload(signal), indent=2, sort_keys=True))
    if signal.side == SignalSide.FLAT:
        print("No trade: flat is a normal paper-mode result.")
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

    fetch = sub.add_parser("fetch-candles", help="Fetch public OKX candles and save them to CSV")
    fetch.add_argument("--symbol", default=None, help="OKX instrument id, default from TREND_BOT_SYMBOL")
    fetch.add_argument("--timeframe", default=None, help="OKX candle bar, default from TREND_BOT_TIMEFRAME")
    fetch.add_argument("--limit", type=int, default=None, help="Candle limit, max 300 for OKX public candles")
    fetch.add_argument("--output", default=None, help="Output CSV path")
    fetch.set_defaults(func=cmd_fetch_candles)

    paper = sub.add_parser("paper-step", help="Fetch candles, evaluate the strategy, and record a paper signal")
    paper.add_argument("--symbol", default=None, help="OKX instrument id, default from TREND_BOT_SYMBOL")
    paper.add_argument("--timeframe", default=None, help="OKX candle bar, default from TREND_BOT_TIMEFRAME")
    paper.add_argument("--limit", type=int, default=None, help="Candle limit, max 300 for OKX public candles")
    paper.add_argument("--output", default=None, help="Optional candle CSV output path")
    paper.set_defaults(func=cmd_paper_step)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
