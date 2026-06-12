"""Guarded paper stepper with CATCH-UP — WORK_ITEM_PAPER_TRIAL.md v1.1.

Processes EVERY unprocessed completed 4H bar in chronological order through
the bot's own classes (QuantTrendStrategy.evaluate -> store.record_signal ->
PaperTrader.apply_signal — the exact paper-step sequence, once per bar).
A normal scheduled run processes 1 new bar; a run after machine downtime
catches up N bars. Idempotent: bars <= last_bar.json are skipped. No
lookahead: each bar's decision uses only candles through that bar.

Kill-switches enforced AFTER stepping (work item v1.0, unchanged):
  drawdown >= 15% of paper equity        -> KILL (marker file)
  profile divergence (>=8 trades)        -> KILL
  stale DATA (newest bar > 2 bars old)   -> flagged (source anomaly)
  catch-up runs                          -> flagged caught_up=N (uptime record)

Run (scheduler or manual):  python research/paper_trial/paper_step_guarded.py
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import certifi
import httpx

HERE = Path(__file__).resolve().parent
BOT_ROOT = HERE.parents[1]
sys.path.insert(0, str(BOT_ROOT / "src"))

from okxtrendbot.config import load_config                      # noqa: E402
from okxtrendbot.models import Candle, PaperTradingConfig        # noqa: E402
from okxtrendbot.paper import PaperTrader                        # noqa: E402
from okxtrendbot.store import TrendStore                         # noqa: E402
from okxtrendbot.strategy import QuantTrendStrategy, TrendStrategyParams  # noqa: E402

DB = BOT_ROOT / "data" / "okxtrendbot.sqlite"
KILL_MARKER = HERE / "KILL_SWITCH.txt"
STATUS_CSV = HERE / "trial_status.csv"
STATE_FILE = HERE / "last_bar.json"

PAPER_EQUITY = 1000.0
DD_KILL = 0.15
PROFILE_MIN_TRADES = 8
PROFILE_WIN_MIN = 0.15
PROFILE_PAYOFF_MIN = 1.0
BAR_HOURS = 4
BAR_MS = BAR_HOURS * 3_600_000
WINDOW = 300
SYMBOL = "BTC-USDT-SWAP"


def fetch_bars(since_ms: int) -> list[dict]:
    """Confirmed 4H bars from since_ms to now (public endpoint, paginated)."""
    client = httpx.Client(verify=certifi.where(), timeout=20)
    rows, after = [], None
    while True:
        params = {"instId": SYMBOL, "bar": "4H", "limit": "100"}
        if after:
            params["after"] = str(after)
        d = client.get("https://www.okx.com/api/v5/market/history-candles",
                       params=params).json()
        if d.get("code") != "0" or not d.get("data"):
            break
        page = d["data"]
        rows.extend(r for r in page if r[8] == "1")
        oldest = min(int(r[0]) for r in page)
        if oldest <= since_ms or len(page) < 100:
            break
        after = oldest
        time.sleep(0.12)
    rows = [r for r in rows if int(r[0]) >= since_ms]
    rows.sort(key=lambda r: int(r[0]))
    return [{"ts": int(r[0]), "open": float(r[1]), "high": float(r[2]),
             "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
            for r in rows]


def to_candle(b: dict) -> Candle:
    iso = datetime.fromtimestamp(b["ts"] / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Candle(ts=iso, open=b["open"], high=b["high"], low=b["low"],
                  close=b["close"], volume=b["volume"])


def log_status(row: dict) -> None:
    new = not STATUS_CSV.exists()
    with STATUS_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ts_utc", "action", "closed_trades",
                                          "realized_usdt", "unrealized_usdt",
                                          "equity", "peak", "dd_pct", "flags"])
        if new:
            w.writeheader()
        w.writerow(row)


def kill(reason: str, row: dict) -> int:
    KILL_MARKER.write_text(
        f"KILL tripped {datetime.now(timezone.utc).isoformat()}\nreason: {reason}\n"
        f"Per WORK_ITEM_PAPER_TRIAL.md the trial is HALTED for operator review.\n"
        f"Delete this file only after the review is recorded.\n", encoding="utf-8")
    row["action"] = "KILL"
    row["flags"] = reason
    log_status(row)
    print(f"KILL: {reason} — marker written; trial halted.")
    return 2


def main() -> int:
    now = datetime.now(timezone.utc)
    row = {"ts_utc": now.isoformat(timespec="seconds"), "action": "", "closed_trades": 0,
           "realized_usdt": 0.0, "unrealized_usdt": 0.0, "equity": PAPER_EQUITY,
           "peak": PAPER_EQUITY, "dd_pct": 0.0, "flags": ""}
    flags = []

    if KILL_MARKER.exists():
        row["action"] = "REFUSED_KILLED"
        row["flags"] = "kill marker present"
        log_status(row)
        print("REFUSED: kill marker present — operator review required.")
        return 2

    # last processed bar (wrapper-owned state)
    last_bar = None
    if STATE_FILE.exists():
        try:
            last_bar = int(json.loads(STATE_FILE.read_text(encoding="utf-8"))["last_bar_ts"])
        except Exception:
            last_bar = None

    # fetch enough history for full evaluation windows on every unprocessed bar
    fetch_from = (last_bar - WINDOW * BAR_MS) if last_bar else int(now.timestamp() * 1000) - (WINDOW + 2) * BAR_MS
    bars = fetch_bars(fetch_from)
    if not bars:
        row["action"] = "STEP_ERROR"
        row["flags"] = "no bars fetched"
        log_status(row)
        return 1

    # stale-DATA guard: newest available bar too old = source anomaly
    newest = bars[-1]["ts"]
    age_h = (now.timestamp() * 1000 - newest) / 3_600_000
    if age_h > 2 * BAR_HOURS:
        flags.append(f"stale_data={age_h:.1f}h")

    if last_bar is None:
        last_bar = bars[-2]["ts"] if len(bars) >= 2 else bars[-1]["ts"] - BAR_MS

    todo = [b for b in bars if b["ts"] > last_bar]

    # the bot's own configuration + classes (paper-step sequence, per bar)
    cfg = load_config(BOT_ROOT / ".env")
    strat = QuantTrendStrategy(TrendStrategyParams(
        symbol=SYMBOL, ema_fast=cfg.ema_fast, ema_slow=cfg.ema_slow,
        atr_period=cfg.atr_period, breakout_lookback=cfg.breakout_lookback,
        min_ema_gap_atr=cfg.min_ema_gap_atr, max_extension_atr=cfg.max_extension_atr,
        stop_atr_mult=cfg.stop_atr_mult))
    store = TrendStore(DB)
    trader = PaperTrader(store, PaperTradingConfig(
        paper_equity_usdt=cfg.paper_equity_usdt,
        risk_per_trade_pct=cfg.risk_per_trade_pct,
        max_notional_usdt=cfg.max_notional_usdt,
        stop_atr_mult=cfg.stop_atr_mult))

    actions = []
    for b in todo:
        idx = next(i for i, x in enumerate(bars) if x["ts"] == b["ts"])
        window = bars[max(0, idx - WINDOW + 1): idx + 1]
        candles = [to_candle(x) for x in window]
        if len(candles) < strat.min_candles:
            continue
        signal = strat.evaluate(candles)
        signal_id = store.record_signal(signal)
        result = trader.apply_signal(signal, candles[-1], signal_id)
        actions.append(result.action)
        last_bar = b["ts"]

    STATE_FILE.write_text(json.dumps({"last_bar_ts": last_bar}), encoding="utf-8")
    if len(todo) > 1:
        flags.append(f"caught_up={len(todo)}")
    if not todo:
        flags.append("no_new_bar")

    # ---- kill-switch audit (unchanged from v1.0) ----
    db = sqlite3.connect(DB)
    pnls = [float(p[0] or 0) for p in db.execute(
        "SELECT pnl_usdt FROM paper_trades WHERE symbol=? ORDER BY id", (SYMBOL,))]
    open_pos = db.execute(
        "SELECT unrealized_pnl_usdt FROM paper_positions WHERE symbol=? AND status='open'",
        (SYMBOL,)).fetchone()
    unrealized = float(open_pos[0] or 0) if open_pos else 0.0
    db.close()

    realized = sum(pnls)
    eq, peak, worst_dd = PAPER_EQUITY, PAPER_EQUITY, 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        worst_dd = max(worst_dd, (peak - eq) / peak)
    eq_now = PAPER_EQUITY + realized + unrealized
    peak = max(peak, eq_now)
    worst_dd = max(worst_dd, (peak - eq_now) / peak)

    row.update(closed_trades=len(pnls), realized_usdt=round(realized, 2),
               unrealized_usdt=round(unrealized, 2), equity=round(eq_now, 2),
               peak=round(peak, 2), dd_pct=round(worst_dd * 100, 2))

    if worst_dd >= DD_KILL:
        return kill(f"drawdown {worst_dd*100:.1f}% >= {DD_KILL*100:.0f}%", row)
    if len(pnls) >= PROFILE_MIN_TRADES:
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls)
        payoff = ((sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
                  if wins and losses and sum(losses) != 0 else 99.0)
        if win_rate < PROFILE_WIN_MIN or payoff < PROFILE_PAYOFF_MIN:
            return kill(f"profile divergence win={win_rate:.0%} payoff={payoff:.2f}", row)

    summary = ",".join(f"{a}" for a in actions) if actions else "none"
    row["action"] = "STEP_OK"
    row["flags"] = ";".join(flags)
    log_status(row)
    print(f"STEP_OK bars_processed={len(todo)} actions=[{summary}] "
          f"trades={row['closed_trades']} equity=${row['equity']} "
          f"dd={row['dd_pct']}% flags=[{row['flags']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
