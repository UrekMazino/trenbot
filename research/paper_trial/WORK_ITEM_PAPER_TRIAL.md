# Work Item — 4H Paper Trial (Option B) with Risk Mitigations
## Criteria LOCKED at commit time, before the first paper step runs.

**Authorized 2026-06-12** (operator: "we'll go for Option B, implement mitigation risk"), routing from the MTF gate (`4970c89`: 4H TF-AMBIGUOUS — the program's first cost-clearing strategy, failed on quality gates: Sharpe 0.52, DD 34.7%, 2/4 sub-periods).

## 1. What this trial IS and IS NOT (locked framing)

A 4-month paper slice **cannot validate a 5.7-year edge** — the gate's own data shows 2 of 4 ~17-month sub-periods were negative, so a short paper window can be legitimately red while the strategy works as designed, and legitimately green while it doesn't. Therefore:

- **PRIMARY question (answerable): execution fidelity.** Do live-fetched signals, fills, stops, and trades match what the gate engine produces on the same candles? Paper validates the *pipeline*, not the edge.
- **SECONDARY (collected, not judged early): a fresh out-of-sample regime sample** to put beside the backtest.
- **NOT: edge confirmation, and NOT automatic live authorization.** Live is a separate gate, written only after this trial passes, as its own operator decision.

## 2. Configuration (locked)

`TREND_BOT_TIMEFRAME=4H`; all signal params at bot defaults (= the gated configuration: EMA 20/60, ATR 14, breakout 20, stop 2.5×ATR). **Risk mitigation #1 — conservative sizing held at bot defaults:** paper equity $1,000, risk 0.25%/trade ($2.50), max notional $100/position. All measurements in % terms so sizing scale doesn't distort reads. **Foreclosed for the trial's duration:** parameter changes, timeframe changes, long-only switching, signal-logic edits. The configuration that was gated is the configuration that papers.

## 3. Risk mitigations (the operator's ask — operational controls, not strategy rescues)

| # | Mitigation | Trigger → action |
|---|---|---|
| 1 | Conservative sizing | bot defaults (above) — max single-position exposure 10% of paper equity |
| 2 | **Drawdown kill-switch** | paper equity drawdown ≥ **15%** from peak → trial HALTS for operator review (tighter than the gate's 35% envelope: paper exists to catch divergence early, not ride the full envelope) |
| 3 | **Stale-data guard** | latest fetched candle older than 2 bar-periods → step SKIPPED + logged (never act on stale data) |
| 4 | **Profile-divergence kill** | after ≥ 8 closed trades: win rate < 15% or payoff ratio < 1.0 (gate profile: ~37% / ~2.0) → HALT + fidelity review |
| 5 | **Fidelity check** | weekly: replay the gate engine over the trial's candle history; any paper trade the engine doesn't produce (or vice versa, beyond fill-timing tolerance) → HALT |
| 6 | Operational watchdog | 3+ consecutive missed scheduled steps → flagged in status log |

Implementation: a guarded wrapper (`paper_step_guarded.py`) runs each step, then audits the bot's own SQLite store against #2/#3/#4/#6 and refuses further steps after a kill (marker file), so a tripped kill cannot be silently stepped past.

## 4. Pre-committed review gates

- **Review point: ≥ 4 months AND ≥ 10 closed paper trades, whichever later.**
- **TRIAL-PASS:** no kill tripped; fidelity clean (#5); uptime ≥ 95% of scheduled steps. → The live-decision gate gets *written* (not passed) — its own work item with its own locked criteria, sized off the trial's observed regime.
- **TRIAL-FAIL:** any kill trips, or fidelity mismatch. → Halt; diagnose; a fidelity bug is repairable (repair ≠ re-spec); a profile/drawdown kill routes back to Option A (shelve) with the trial data as the closing evidence.
- **Borderline resolves DOWN.** Paper PnL alone — green or red — does not override these gates in either direction.

---

*Paper-trial work item v1.0, 2026-06-12. Locked before the first step. Scheduling: every 4H at UTC bar close +2 min. The gated configuration papers unchanged; the kill-switches are operational armor, not tuning.*
