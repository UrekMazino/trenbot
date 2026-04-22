from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .candles import load_candles_csv, write_candles_csv
from .config import load_config
from .models import PaperTradingConfig
from .okx_market import OkxMarketDataClient
from .paper import PaperTrader
from .runtime import PaperRunOptions, PaperRuntime
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


def _paper_config_from_config(cfg) -> PaperTradingConfig:
    return PaperTradingConfig(
        paper_equity_usdt=cfg.paper_equity_usdt,
        risk_per_trade_pct=cfg.risk_per_trade_pct,
        max_notional_usdt=cfg.max_notional_usdt,
        stop_atr_mult=cfg.stop_atr_mult,
    )


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
    store = TrendStore(cfg.db_path)
    signal_id = store.record_signal(signal)
    result = PaperTrader(store, _paper_config_from_config(cfg)).apply_signal(signal, candles[-1], signal_id)
    print(f"Fetched {len(candles)} candles and recorded signal #{signal_id}")
    print(
        json.dumps(
            {
                "signal": _signal_payload(signal),
                "paper": asdict(result),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if result.action in {"NO_POSITION", "HOLD_POSITION", "UPDATE_TRAILING_STOP"}:
        print(result.message)
    return 0


def cmd_paper_status(args: argparse.Namespace) -> int:
    cfg = load_config()
    symbol = args.symbol or cfg.symbol
    status = TrendStore(cfg.db_path).paper_status(symbol)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


def cmd_paper_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to reset paper lifecycle without --yes")
        return 2
    cfg = load_config()
    symbol = None if args.all else (args.symbol or cfg.symbol)
    result = TrendStore(cfg.db_path).reset_paper(symbol)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_paper_run(args: argparse.Namespace) -> int:
    cfg = load_config()
    options = PaperRunOptions(
        interval_seconds=float(args.interval),
        max_loops=int(args.max_loops or 0),
        symbol=args.symbol,
        timeframe=args.timeframe,
        limit=args.limit,
        output=args.output,
    )
    result = PaperRuntime(cfg, options).run()
    print(json.dumps(result, indent=2, sort_keys=True))
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

    paper_status = sub.add_parser("paper-status", help="Show open paper position and closed-trade stats")
    paper_status.add_argument("--symbol", default=None, help="OKX instrument id, default from TREND_BOT_SYMBOL")
    paper_status.set_defaults(func=cmd_paper_status)

    paper_reset = sub.add_parser("paper-reset", help="Clear paper positions/trades, preserving signals")
    paper_reset.add_argument("--symbol", default=None, help="OKX instrument id, default from TREND_BOT_SYMBOL")
    paper_reset.add_argument("--all", action="store_true", help="Reset all paper symbols")
    paper_reset.add_argument("--yes", action="store_true", help="Confirm reset")
    paper_reset.set_defaults(func=cmd_paper_reset)

    paper_run = sub.add_parser("paper-run", help="Run continuous paper trading loop")
    paper_run.add_argument("--symbol", default=None, help="OKX instrument id, default from TREND_BOT_SYMBOL")
    paper_run.add_argument("--timeframe", default=None, help="OKX candle bar, default from TREND_BOT_TIMEFRAME")
    paper_run.add_argument("--limit", type=int, default=None, help="Candle limit, max 300 for OKX public candles")
    paper_run.add_argument("--output", default=None, help="Optional candle CSV output path")
    paper_run.add_argument("--interval", type=float, default=300.0, help="Seconds between paper steps")
    paper_run.add_argument("--max-loops", type=int, default=0, help="Maximum loops before exit; 0 runs until stopped")
    paper_run.set_defaults(func=cmd_paper_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
