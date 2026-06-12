"""Guarded paper step — runs one bot paper-step, then enforces the locked
risk mitigations (WORK_ITEM_PAPER_TRIAL.md, committed 0c4feeb).

Kill-switches enforced AFTER every step against the bot's own SQLite store:
  #2 drawdown >= 15% of paper equity from peak     -> KILL (marker file)
  #4 profile divergence (>=8 trades: win<15% or payoff<1.0) -> KILL
  #3 stale-data flag (candle CSV older than 2 bars) -> step flagged STALE
  #6 missed-step watchdog (gap > 3 bars since last status row) -> flagged

A tripped kill writes KILL_SWITCH.txt; subsequent invocations refuse to
run until the operator reviews and deletes the marker. Status appended to
trial_status.csv after every invocation (the trial's audit trail).

Run (scheduler or manual):  python research/paper_trial/paper_step_guarded.py
"""

from __future__ import annotations

import csv
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOT_ROOT = HERE.parents[1]
DB = BOT_ROOT / "data" / "okxtrendbot.sqlite"
CANDLE_CSV = BOT_ROOT / "data" / "BTC-USDT-SWAP-4H.csv"
KILL_MARKER = HERE / "KILL_SWITCH.txt"
STATUS_CSV = HERE / "trial_status.csv"

PAPER_EQUITY = 1000.0
DD_KILL = 0.15
PROFILE_MIN_TRADES = 8
PROFILE_WIN_MIN = 0.15
PROFILE_PAYOFF_MIN = 1.0
BAR_HOURS = 4
SYMBOL = "BTC-USDT-SWAP"


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

    # missed-step watchdog (#6)
    if STATUS_CSV.exists():
        try:
            last = list(csv.DictReader(STATUS_CSV.open(encoding="utf-8")))[-1]
            gap_h = (now - datetime.fromisoformat(last["ts_utc"])).total_seconds() / 3600
            if gap_h > 3 * BAR_HOURS:
                flags.append(f"missed_steps_gap={gap_h:.0f}h")
        except Exception:
            pass

    # run the bot's own paper-step (unchanged bot code)
    env = dict(os.environ, PYTHONPATH=str(BOT_ROOT / "src"))
    proc = subprocess.run([sys.executable, "-m", "okxtrendbot.cli", "paper-step"],
                          cwd=BOT_ROOT, env=env, capture_output=True, text=True, timeout=120)
    step_ok = proc.returncode == 0
    if not step_ok:
        flags.append("step_error")
        print(proc.stdout[-500:] if proc.stdout else "", proc.stderr[-500:] if proc.stderr else "")

    # stale-data guard (#3) — bot writes ISO-8601 ts (e.g. 2026-06-12T00:00:00Z)
    try:
        with CANDLE_CSV.open(encoding="utf-8") as f:
            last_ts_raw = list(csv.DictReader(f))[-1]["ts"]
        last_dt = datetime.fromisoformat(last_ts_raw.replace("Z", "+00:00"))
        age_h = (now - last_dt).total_seconds() / 3600
        if age_h > 2 * BAR_HOURS:
            flags.append(f"stale_data={age_h:.1f}h")
    except Exception:
        flags.append("stale_check_failed")

    # audit the store (#2, #4)
    db = sqlite3.connect(DB)
    trades = db.execute(
        "SELECT pnl_usdt FROM paper_trades WHERE symbol=? ORDER BY id", (SYMBOL,)).fetchall()
    pnls = [float(p[0] or 0) for p in trades]
    realized = sum(pnls)
    open_pos = db.execute(
        "SELECT unrealized_pnl_usdt FROM paper_positions WHERE symbol=? AND status='open'",
        (SYMBOL,)).fetchone()
    unrealized = float(open_pos[0] or 0) if open_pos else 0.0
    db.close()

    # equity path from realized sequence (per-trade granularity) + current MTM
    eq, peak = PAPER_EQUITY, PAPER_EQUITY
    worst_dd = 0.0
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

    row["action"] = "STEP_OK" if step_ok else "STEP_ERROR"
    row["flags"] = ";".join(flags)
    log_status(row)
    print(f"{row['action']} trades={row['closed_trades']} equity=${row['equity']} "
          f"dd={row['dd_pct']}% flags=[{row['flags']}]")
    return 0 if step_ok else 1


if __name__ == "__main__":
    sys.exit(main())
