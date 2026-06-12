"""TRENDBOT offline gate backtest — per WORK_ITEM_GATE.md (locked 0af2f90).

Imports the bot's own QuantTrendStrategy for signals (zero transcription
drift). Portfolio loop per paper.py semantics with the two locked
no-lookahead corrections: next-bar-open fills for entries/signal-exits;
stop active during bar t is the stop as of end of bar t-1 (intrabar fill
at stop, gap-aware). 300-bar sliding window (the bot's candle_limit mode).

Costs (locked): 0.12% RT (taker 0.05% + slip 0.01% per side) +
0.005%/8h funding charged both sides. Primary sizing: $1000 notional.

Run:  python gate_backtest.py          (fetches/caches data on first run)
      python gate_backtest.py --fetch-only
"""

from __future__ import annotations

import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import certifi
import httpx
import numpy as np

HERE = Path(__file__).resolve().parent
BOT_ROOT = HERE.parents[1]
sys.path.insert(0, str(BOT_ROOT / "src"))

from okxtrendbot.models import Candle, SignalSide          # noqa: E402
from okxtrendbot.strategy import QuantTrendStrategy, TrendStrategyParams  # noqa: E402

DATA_DIR = HERE / "data"
DATA_DIR.mkdir(exist_ok=True)
CACHE = DATA_DIR / "BTC-USDT-SWAP-1H-real.csv"
OUT_DIR = HERE / "analysis"
OUT_DIR.mkdir(exist_ok=True)

WINDOW = 300                 # bot's candle_limit operating mode
NOTIONAL = 1000.0            # locked primary sizing
EQUITY0 = 1000.0
FEE_SLIP_PER_SIDE = 0.0006   # 0.05% taker + 0.01% slip
FUNDING_PER_8H = 0.00005     # 0.005%/8h, charged both sides (locked)
STOP_MULT = 2.5
MAX_PAGES = 500


def fetch_1h() -> int:
    if CACHE.exists():
        return sum(1 for _ in CACHE.open()) - 1
    client = httpx.Client(verify=certifi.where(), timeout=20)
    rows, after, pages = [], None, 0
    while pages < MAX_PAGES:
        params = {"instId": "BTC-USDT-SWAP", "bar": "1H", "limit": "100"}
        if after:
            params["after"] = str(after)
        d = client.get("https://www.okx.com/api/v5/market/history-candles",
                       params=params).json()
        if d.get("code") != "0" or not d.get("data"):
            break
        page = d["data"]
        rows.extend(r for r in page if r[8] == "1")
        after = int(page[-1][0])
        pages += 1
        if len(page) < 100:
            break
        time.sleep(0.12)
    rows.sort(key=lambda r: int(r[0]))
    with CACHE.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts_ms", "open", "high", "low", "close", "volume"])
        for r in rows:
            w.writerow([r[0], r[1], r[2], r[3], r[4], r[5]])
    return len(rows)


def load_candles() -> list[dict]:
    out = []
    with CACHE.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append({"ts": int(row["ts_ms"]), "open": float(row["open"]),
                        "high": float(row["high"]), "low": float(row["low"]),
                        "close": float(row["close"]), "volume": float(row["volume"])})
    return out


def simulate(bars: list[dict], params: TrendStrategyParams,
             fill_at_signal_close: bool = False, bar_hours: float = 1.0) -> dict:
    """One full simulation. Returns trades + equity curve + metrics.

    bar_hours: real hours per bar (1.0 for 1H, 4.0 for 4H, 24.0 for 1D) —
    per WORK_ITEM_MTF_GATE.md this is a unit-handling extension only:
    funding is charged on real hours held and Sharpe annualizes by actual
    periods/year. 1H results are unchanged at the default.
    """
    strat = QuantTrendStrategy(params)
    candle_objs = [Candle(ts=str(b["ts"]), open=b["open"], high=b["high"],
                          low=b["low"], close=b["close"], volume=b["volume"])
                   for b in bars]
    n = len(bars)
    pos = None              # {side, entry_px, stop, entry_i, atr0}
    pending = None          # ("enter", side, atr) | ("exit", reason)
    trades = []
    equity = [EQUITY0]
    eq = EQUITY0

    def close_pos(i: int, px: float, reason: str):
        nonlocal pos, eq
        sgn = 1.0 if pos["side"] == "long" else -1.0
        gross = sgn * (px - pos["entry_px"]) / pos["entry_px"] * NOTIONAL
        hold_h = (i - pos["entry_i"]) * bar_hours
        cost = 2 * FEE_SLIP_PER_SIDE * NOTIONAL + FUNDING_PER_8H * NOTIONAL * (hold_h / 8)
        net = gross - cost
        eq += net
        trades.append({"side": pos["side"], "entry_i": pos["entry_i"], "exit_i": i,
                       "entry_px": pos["entry_px"], "exit_px": px, "hold_h": hold_h,
                       "reason": reason, "gross": gross, "cost": cost, "net": net,
                       "exit_ts": bars[i]["ts"]})
        pos = None

    start = max(strat.min_candles, WINDOW)
    for i in range(start, n):
        b = bars[i]
        # 1) fill pending action from bar i-1's signal at bar i open
        if pending:
            kind = pending[0]
            if kind == "exit" and pos:
                close_pos(i, b["open"], pending[1])
            elif kind == "enter" and pos is None:
                side, atr0 = pending[1], pending[2]
                px = b["open"]
                stop = px - STOP_MULT * atr0 if side == "long" else px + STOP_MULT * atr0
                pos = {"side": side, "entry_px": px, "stop": stop, "entry_i": i, "atr0": atr0}
            pending = None
        # 2) intrabar stop check (stop as of end of bar i-1; gap-aware fill)
        if pos:
            if pos["side"] == "long" and b["low"] <= pos["stop"]:
                close_pos(i, min(b["open"], pos["stop"]), "stop_loss")
            elif pos["side"] == "short" and b["high"] >= pos["stop"]:
                close_pos(i, max(b["open"], pos["stop"]), "stop_loss")
        # 3) evaluate the bot's own signal on the 300-bar window ending at i
        sig = strat.evaluate(candle_objs[i - WINDOW + 1: i + 1])
        # 4) decisions (fill next bar open, unless peek-variant)
        if pos:
            opposite = ((pos["side"] == "long" and sig.side == SignalSide.SHORT)
                        or (pos["side"] == "short" and sig.side == SignalSide.LONG))
            invalidated = False
            if sig.ema_fast is not None and sig.ema_slow is not None:
                if pos["side"] == "long" and sig.ema_fast <= sig.ema_slow:
                    invalidated = True
                elif pos["side"] == "short" and sig.ema_fast >= sig.ema_slow:
                    invalidated = True
            if opposite or invalidated:
                reason = "opposite_signal" if opposite else "trend_invalidated"
                if fill_at_signal_close:
                    close_pos(i, b["close"], reason)
                else:
                    pending = ("exit", reason)
            elif sig.atr and sig.atr > 0:
                # trailing ratchet (effective next bar)
                cand = (b["close"] - STOP_MULT * sig.atr if pos["side"] == "long"
                        else b["close"] + STOP_MULT * sig.atr)
                pos["stop"] = (max(pos["stop"], cand) if pos["side"] == "long"
                               else min(pos["stop"], cand))
        elif sig.side in (SignalSide.LONG, SignalSide.SHORT) and sig.atr and sig.atr > 0:
            if fill_at_signal_close:
                px = b["close"]
                stop = (px - STOP_MULT * sig.atr if sig.side == SignalSide.LONG
                        else px + STOP_MULT * sig.atr)
                pos = {"side": "long" if sig.side == SignalSide.LONG else "short",
                       "entry_px": px, "stop": stop, "entry_i": i, "atr0": sig.atr}
            else:
                pending = ("enter",
                           "long" if sig.side == SignalSide.LONG else "short", sig.atr)
        # 5) mark equity (MTM)
        mtm = 0.0
        if pos:
            sgn = 1.0 if pos["side"] == "long" else -1.0
            mtm = sgn * (b["close"] - pos["entry_px"]) / pos["entry_px"] * NOTIONAL
        equity.append(eq + mtm)

    if pos:
        close_pos(n - 1, bars[n - 1]["close"], "data_end")
        equity[-1] = eq

    eq_arr = np.array(equity)
    rets = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = float(rets.mean() / rets.std() * np.sqrt(8760 / bar_hours)) if rets.std() > 0 else 0.0
    peak = np.maximum.accumulate(eq_arr)
    mdd = float(((peak - eq_arr) / peak).max())
    net = sum(t["net"] for t in trades)
    return {"trades": trades, "equity": eq_arr, "net": net, "sharpe": sharpe,
            "mdd": mdd, "n": len(trades)}


def main() -> int:
    n_bars = fetch_1h()
    bars = load_candles()
    span_d = (bars[-1]["ts"] - bars[0]["ts"]) / 86_400_000
    t0 = datetime.fromtimestamp(bars[0]["ts"] / 1000, timezone.utc).date()
    t1 = datetime.fromtimestamp(bars[-1]["ts"] / 1000, timezone.utc).date()
    print(f"Data: {n_bars} confirmed 1H bars, {t0} -> {t1} ({span_d:.0f} days)")
    if "--fetch-only" in sys.argv:
        return 0

    base_params = TrendStrategyParams()
    print("\nBASE run (bot defaults, $1000 notional, locked costs)...")
    base = simulate(bars, base_params)
    tr = base["trades"]
    print(f"  trades={base['n']}  net=${base['net']:+.2f}  "
          f"sharpe={base['sharpe']:.2f}  maxDD={base['mdd']*100:.1f}%")

    # exit-reason breakdown (sign audit input)
    from collections import defaultdict
    by_r = defaultdict(lambda: [0, 0, 0.0])
    for t in tr:
        d = by_r[t["reason"]]
        d[0] += 1; d[1] += t["net"] > 0; d[2] += t["net"]
    print(f"  {'reason':<18} {'n':>5} {'%net>0':>7} {'avg_net':>9}")
    for k, (cnt, wins, s) in sorted(by_r.items()):
        print(f"  {k:<18} {cnt:>5} {wins/cnt:>7.1%} {s/cnt:>+9.3f}")

    # sub-periods (4 equal quarters of span)
    qs = np.array_split(np.arange(len(tr)), 1)  # placeholder, use exit_ts instead
    bounds = [bars[0]["ts"] + k * (bars[-1]["ts"] - bars[0]["ts"]) / 4 for k in range(5)]
    sub_nets = []
    for k in range(4):
        s = sum(t["net"] for t in tr if bounds[k] <= t["exit_ts"] < bounds[k + 1] + 1)
        sub_nets.append(s)
    print(f"  sub-period nets: {[f'{s:+.2f}' for s in sub_nets]}  "
          f"positive: {sum(1 for s in sub_nets if s > 0)}/4")

    gross_profit = sum(t["net"] for t in tr if t["net"] > 0)
    top_share = (max((t["net"] for t in tr), default=0) / gross_profit) if gross_profit > 0 else float("nan")
    print(f"  top trade share of gross profit: {top_share:.2f}" if gross_profit > 0
          else "  no gross profit")

    # parameter perturbations (six single-param +/-20%)
    perturb = []
    for name, base_v in [("ema_fast", 20), ("ema_slow", 60), ("breakout_lookback", 20)]:
        for mult in (0.8, 1.2):
            v = max(2, round(base_v * mult))
            kwargs = {name: v}
            if name == "ema_fast" and v >= 60:
                continue
            p = TrendStrategyParams(**kwargs)
            r = simulate(bars, p)
            perturb.append((f"{name}={v}", r["net"], r["n"]))
    print("\n  perturbations (+/-20%):")
    for label, net, cnt in perturb:
        print(f"    {label:<24} net=${net:+9.2f}  trades={cnt}")
    all_perturb_pos = all(net > 0 for _, net, _ in perturb)

    # persist trades
    with (OUT_DIR / "gate_trades.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(tr[0].keys()) if tr else ["none"])
        w.writeheader()
        w.writerows(tr)

    # ---- verdict per locked gates ----
    print("\n" + "=" * 78)
    print("VERDICT (per WORK_ITEM_GATE.md, locked at 0af2f90)")
    print("=" * 78)
    pos_subs = sum(1 for s in sub_nets if s > 0)
    concentration_dead = (gross_profit > 0 and top_share >= 0.50)
    if base["net"] <= 0 or concentration_dead:
        print("TREND-DEAD")
        print(f"  net ${base['net']:+.2f} after costs"
              + (f"; top-trade share {top_share:.0%} >= 50%" if concentration_dead else ""))
        print("  Routes to: TRENDBOT shelved before further effort.")
        verdict = "TREND-DEAD"
    elif base["n"] < 30:
        print(f"TREND-AMBIGUOUS (UNDERPOWERED) — only {base['n']} closed trades")
        verdict = "AMBIGUOUS-UNDERPOWERED"
    elif (base["sharpe"] >= 0.8 and base["mdd"] < 0.25 and pos_subs >= 3
          and top_share < 0.30 and all_perturb_pos):
        print("TREND-VIABLE (pending skeptical audit: peek test + sign audit)")
        peek = simulate(bars, base_params, fill_at_signal_close=True)
        print(f"  peek-test (fill at signal close): net ${peek['net']:+.2f} "
              f"vs base ${base['net']:+.2f}")
        verdict = "TREND-VIABLE-PENDING-AUDIT"
    else:
        causes = []
        if base["sharpe"] < 0.8 or base["mdd"] >= 0.25:
            causes.append("MARGINAL-NET")
        if pos_subs < 3:
            causes.append("REGIME-CONCENTRATED")
        if not all_perturb_pos:
            causes.append("PARAM-FRAGILE")
        if gross_profit > 0 and top_share >= 0.30:
            causes.append("TOP-TRADE-CONCENTRATION")
        print(f"TREND-AMBIGUOUS ({' + '.join(causes)})")
        print(f"  net ${base['net']:+.2f}  sharpe {base['sharpe']:.2f}  "
              f"DD {base['mdd']*100:.1f}%  subs {pos_subs}/4  "
              f"topshare {top_share:.2f}  perturb_all_pos={all_perturb_pos}")
        verdict = "AMBIGUOUS-" + "-".join(causes)
    print(f"\nVerdict: {verdict}")
    print(f"Trades: analysis/gate_trades.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
