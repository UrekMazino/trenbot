"""TRENDBOT timeframe-escalation gate (4H / 1D) — per WORK_ITEM_MTF_GATE.md
(verdicts locked at commit 95bb014, before any resample existed).

Resamples the cached 5.7-year 1H dataset to UTC-aligned 4H and 1D bars
(complete buckets only) and runs the SAME gate as the 1H run — the bot's
own QuantTrendStrategy, same mechanics, same locked cost model with the
recorded bar_hours unit extension — at each timeframe, base + the six
+/-20% perturbations.

Run:  python gate_backtest_mtf.py
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from gate_backtest import (NOTIONAL, OUT_DIR, TrendStrategyParams, load_candles,
                           simulate)


def resample(bars: list[dict], bucket_hours: int) -> list[dict]:
    """UTC-aligned OHLCV resample; complete buckets only."""
    ms = bucket_hours * 3_600_000
    buckets: dict[int, list[dict]] = defaultdict(list)
    for b in bars:
        buckets[(b["ts"] // ms) * ms].append(b)
    out = []
    for ts in sorted(buckets):
        grp = sorted(buckets[ts], key=lambda b: b["ts"])
        if len(grp) < bucket_hours:        # incomplete bucket (1H inputs)
            continue
        out.append({"ts": ts,
                    "open": grp[0]["open"],
                    "high": max(b["high"] for b in grp),
                    "low": min(b["low"] for b in grp),
                    "close": grp[-1]["close"],
                    "volume": sum(b["volume"] for b in grp)})
    return out


def run_gate(bars: list[dict], bar_hours: float, label: str) -> dict:
    base = simulate(bars, TrendStrategyParams(), bar_hours=bar_hours)
    tr = base["trades"]
    print(f"\n=== {label}: {len(bars)} bars ===")
    print(f"  BASE: trades={base['n']}  net=${base['net']:+.2f}  "
          f"sharpe={base['sharpe']:.2f}  maxDD={base['mdd']*100:.1f}%")

    by_r = defaultdict(lambda: [0, 0, 0.0])
    for t in tr:
        d = by_r[t["reason"]]
        d[0] += 1; d[1] += t["net"] > 0; d[2] += t["net"]
    for k, (cnt, wins, s) in sorted(by_r.items()):
        print(f"    {k:<18} n={cnt:<4} %net>0={wins/cnt:>6.1%} avg={s/cnt:>+8.3f}")

    bounds = [bars[0]["ts"] + k * (bars[-1]["ts"] - bars[0]["ts"]) / 4 for k in range(5)]
    sub_nets = [sum(t["net"] for t in tr if bounds[k] <= t["exit_ts"] < bounds[k + 1] + 1)
                for k in range(4)]
    pos_subs = sum(1 for s in sub_nets if s > 0)
    gross_profit = sum(t["net"] for t in tr if t["net"] > 0)
    top_share = (max((t["net"] for t in tr), default=0.0) / gross_profit
                 if gross_profit > 0 else float("nan"))
    print(f"  sub-period nets: {[f'{s:+.0f}' for s in sub_nets]} (positive {pos_subs}/4); "
          f"top-trade share {top_share:.2f}" if gross_profit > 0 else
          f"  sub-period nets: {[f'{s:+.0f}' for s in sub_nets]}; no gross profit")

    perturb = []
    for name, base_v in [("ema_fast", 20), ("ema_slow", 60), ("breakout_lookback", 20)]:
        for mult in (0.8, 1.2):
            v = max(2, round(base_v * mult))
            r = simulate(bars, TrendStrategyParams(**{name: v}), bar_hours=bar_hours)
            perturb.append((f"{name}={v}", r["net"], r["n"]))
    for lbl, net, cnt in perturb:
        print(f"    perturb {lbl:<22} net=${net:+9.2f}  trades={cnt}")
    all_perturb_pos = all(net > 0 for _, net, _ in perturb)

    # ---- locked verdict ----
    concentration_dead = gross_profit > 0 and top_share >= 0.50
    if base["net"] <= 0 or concentration_dead:
        verdict = "TF-DEAD"
        detail = (f"net ${base['net']:+.2f}"
                  + (f"; top-share {top_share:.0%} >= 50%" if concentration_dead else ""))
    elif base["n"] < 30:
        verdict = "TF-AMBIGUOUS (UNDERPOWERED)"
        detail = f"net ${base['net']:+.2f} but only {base['n']} trades (< 30) — couldn't test, not passed"
    elif (base["sharpe"] >= 0.8 and base["mdd"] < 0.25 and pos_subs >= 3
          and top_share < 0.30 and all_perturb_pos):
        verdict = "TF-VIABLE (pending skeptical audit)"
        detail = "all seven locked conditions met"
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
        verdict = f"TF-AMBIGUOUS ({' + '.join(causes)})"
        detail = (f"net ${base['net']:+.2f} sharpe {base['sharpe']:.2f} "
                  f"DD {base['mdd']*100:.0f}% subs {pos_subs}/4 "
                  f"topshare {top_share:.2f} perturb_all_pos={all_perturb_pos}")
    print(f"  VERDICT {label}: {verdict}\n    {detail}")

    with (OUT_DIR / f"gate_trades_{label}.csv").open("w", newline="", encoding="utf-8") as f:
        if tr:
            w = csv.DictWriter(f, fieldnames=list(tr[0].keys()))
            w.writeheader()
            w.writerows(tr)
    return {"label": label, "verdict": verdict, "detail": detail, "base": base,
            "sub_nets": sub_nets, "top_share": top_share, "perturb": perturb}


def main() -> int:
    bars_1h = load_candles()
    res = []
    for hours, label in ((4, "4H"), (24, "1D")):
        bars = resample(bars_1h, hours)
        res.append(run_gate(bars, float(hours), label))

    print("\n" + "=" * 78)
    print("OVERALL ROUTING (per WORK_ITEM_MTF_GATE.md, locked at 95bb014)")
    print("=" * 78)
    verdicts = [r["verdict"] for r in res]
    if all(v.startswith("TF-DEAD") for v in verdicts):
        print("Both timeframes DEAD -> the timescale hypothesis CLOSES.")
        print("TRENDBOT is SHELVED FINALLY — no further mitigation candidates exist;")
        print("the cost-floor finding stands as the binding fact. No third timeframe")
        print("gets added post-hoc.")
    elif any(v.startswith("TF-VIABLE") for v in verdicts):
        print("A timeframe is VIABLE pending audit -> run skeptical audit (peek test +")
        print("sign-by-exit-type), then operator decides on paper mode at that timeframe.")
    else:
        print("Mixed/AMBIGUOUS -> operator call with sub-causes as routing input:")
        for r in res:
            print(f"  {r['label']}: {r['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
