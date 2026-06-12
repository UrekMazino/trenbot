"""Weekly fidelity replay — mitigation #5 of WORK_ITEM_PAPER_TRIAL.md.

Question: do the paper trades the live bot recorded match what the gate
engine produces on the same candle history? A mismatch (a paper trade the
engine doesn't produce, or vice versa, beyond fill-timing tolerance) is a
KILL condition — it means the live pipeline and the gated strategy have
diverged, and the trial's evidence is no longer about the gated thing.

Method:
- Fetch 4H candles covering [trial_start - 300 warmup bars, now] from the
  public endpoint (same data the bot sees).
- Run the gate engine (gate_backtest.simulate, bar_hours=4) over them and
  keep engine trades whose ENTRY falls inside the trial period.
- Load paper trades from the bot's SQLite store (trial period).
- Match by side + entry time within +/-1 bar (the locked fill-timing
  tolerance: the engine fills next-bar-open, the paper bot at signal
  close).
- FIDELITY-CLEAN if both directions match fully; otherwise FIDELITY-
  MISMATCH (per the work item: HALT + review -> write KILL_SWITCH.txt).

Run weekly (manual or scheduled):
    python research/paper_trial/fidelity_replay.py
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import certifi
import httpx

HERE = Path(__file__).resolve().parent
BOT_ROOT = HERE.parents[1]
sys.path.insert(0, str(BOT_ROOT / "research" / "gate_backtest"))

from gate_backtest import TrendStrategyParams, simulate  # noqa: E402

DB = BOT_ROOT / "data" / "okxtrendbot.sqlite"
STATUS_CSV = HERE / "trial_status.csv"
KILL_MARKER = HERE / "KILL_SWITCH.txt"
REPLAY_LOG = HERE / "fidelity_replays.csv"
SYMBOL = "BTC-USDT-SWAP"
BAR_MS = 4 * 3_600_000
WARMUP_BARS = 300
TOLERANCE_BARS = 1


def trial_start_ms() -> int:
    rows = list(csv.DictReader(STATUS_CSV.open(encoding="utf-8")))
    first = datetime.fromisoformat(rows[0]["ts_utc"])
    return int(first.timestamp() * 1000)


def fetch_4h(since_ms: int) -> list[dict]:
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


def paper_trades(since_ms: int) -> list[dict]:
    db = sqlite3.connect(DB)
    out = []
    for side, entry_ts, exit_ts, pnl in db.execute(
            "SELECT side, entry_ts, exit_ts, pnl_usdt FROM paper_trades "
            "WHERE symbol=? ORDER BY id", (SYMBOL,)):
        try:
            ts = datetime.fromisoformat(str(entry_ts).replace("Z", "+00:00"))
            ems = int(ts.timestamp() * 1000)
        except ValueError:
            continue
        if ems >= since_ms:
            out.append({"side": str(side).lower(), "entry_ms": ems,
                        "exit_ts": exit_ts, "pnl": pnl})
    db.close()
    return out


def main() -> int:
    if not STATUS_CSV.exists():
        print("No trial_status.csv yet — trial has not started.")
        return 1
    t0 = trial_start_ms()
    fetch_from = t0 - WARMUP_BARS * BAR_MS
    bars = fetch_4h(fetch_from)
    print(f"Replay: {len(bars)} bars fetched "
          f"({datetime.fromtimestamp(bars[0]['ts']/1000, timezone.utc):%Y-%m-%d} -> "
          f"{datetime.fromtimestamp(bars[-1]['ts']/1000, timezone.utc):%Y-%m-%d}); "
          f"trial began {datetime.fromtimestamp(t0/1000, timezone.utc):%Y-%m-%d %H:%M}")

    engine = simulate(bars, TrendStrategyParams(), bar_hours=4.0)
    engine_trades = [{"side": t["side"], "entry_ms": bars[t["entry_i"]]["ts"]}
                     for t in engine["trades"] if bars[t["entry_i"]]["ts"] >= t0]
    live_trades = paper_trades(t0)
    print(f"Engine trades in trial period: {len(engine_trades)}; "
          f"paper trades recorded: {len(live_trades)}")

    tol = TOLERANCE_BARS * BAR_MS
    unmatched_live, used = [], set()
    for lt in live_trades:
        hit = next((j for j, et in enumerate(engine_trades)
                    if j not in used and et["side"] == lt["side"]
                    and abs(et["entry_ms"] - lt["entry_ms"]) <= tol), None)
        if hit is None:
            unmatched_live.append(lt)
        else:
            used.add(hit)
    unmatched_engine = [et for j, et in enumerate(engine_trades) if j not in used]

    clean = not unmatched_live and not unmatched_engine
    verdict = "FIDELITY-CLEAN" if clean else "FIDELITY-MISMATCH"
    print(f"\n{verdict}")
    if unmatched_live:
        print(f"  paper trades the engine did NOT produce: {unmatched_live}")
    if unmatched_engine:
        print(f"  engine trades the paper bot did NOT take: "
              f"{[(t['side'], datetime.fromtimestamp(t['entry_ms']/1000, timezone.utc).isoformat()) for t in unmatched_engine]}")

    new = not REPLAY_LOG.exists()
    with REPLAY_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts_utc", "verdict", "engine_trades", "paper_trades",
                        "unmatched_live", "unmatched_engine"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    verdict, len(engine_trades), len(live_trades),
                    len(unmatched_live), len(unmatched_engine)])

    if not clean:
        KILL_MARKER.write_text(
            f"KILL tripped {datetime.now(timezone.utc).isoformat()}\n"
            f"reason: fidelity mismatch (live={len(unmatched_live)} "
            f"engine={len(unmatched_engine)} unmatched)\n"
            f"Per WORK_ITEM_PAPER_TRIAL.md mitigation #5: HALT for review.\n",
            encoding="utf-8")
        print("KILL marker written — trial halted for review.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
