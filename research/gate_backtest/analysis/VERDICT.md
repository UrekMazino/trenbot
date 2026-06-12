# TRENDBOT Gate Verdict — TREND-DEAD (2026-06-12)

*Per `WORK_ITEM_GATE.md` (verdicts locked at commit `0af2f90` before the real-data pull). Tool: `gate_backtest.py`, importing the bot's own `QuantTrendStrategy` (zero transcription drift), paper.py exit semantics with locked no-lookahead corrections. Data: 49,999 confirmed BTC-USDT-SWAP 1H bars, 2020-09-27 → 2026-06-12 (5.7 years, multiple full bull/bear regimes; depth was our page cap, not the API's). Costs locked: 0.12% RT + 0.005%/8h funding both sides. $1,000 notional.*

---

## Verdict: **TREND-DEAD** — routes to: TRENDBOT shelved before further effort

| Metric | Value | Gate |
|---|---|---|
| Net after costs (5.7y) | **−$959.05** (823 trades) | FAIL (> 0 required) |
| Sharpe | 0.43 | FAIL (≥ 0.8) |
| Max drawdown | 124.5% of $1k equity (account wiped) | FAIL (< 25%) |
| Sub-periods positive | 1/4 | FAIL (≥ 3/4) |
| Perturbations (±20% × 3 params) | **6/6 negative** (−$694 to −$1,132) | FAIL (all positive) |
| Top-trade concentration | 0.02 | pass (moot) |

Not a parameter accident (every neighbor loses), not concentration (loss is broad-based), not one bad regime (3 of 4 sub-periods negative across 5.7 years).

## The decomposition — the same finding, third strategy

| Component | Value |
|---|---|
| Total gross PnL | **+$146.34** (+0.018%/trade ≈ +0.3%/yr on notional) |
| Total costs | **$1,105.39** (0.134%/trade) |
| Total net | −$959.05 |
| Win rate / payoff | 33% gross winners / 2.07 payoff ratio |
| Avg hold | 22.9h |

The trend mechanics WORK as designed — winners average +$31 vs losers −$15, the classic trend profile, and 822/823 exits are stop-losses (the 2.5×ATR trail always fires before the EMA-cross or opposite-signal exits can — a structural fact about the bot's exit design: it is in practice a pure trailing-stop system). But the edge those mechanics extract is **+0.018% per trade against 0.134% per trade of costs — costs are 7.5× the gross edge.**

**This is now the third independent strategy with the same signature on this venue:**
1. OKXStatBot daily reversion: gross −$1.4/trade — negative before costs.
2. OKXStatBot G1 daily continuation: gross −$0.29/trade — breakeven before costs.
3. TRENDBOT 1H trend: gross +$0.18/trade — breakeven-ish before costs, killed by costs.

The accumulating program-level conclusion: **at retail-observable timescales (minutes → hours → days) on OKX crypto markets, simple price-pattern strategies extract gross edges of roughly ±0.1% per trade — indistinguishable from a costed random walk. The fee+slippage floor (0.12–0.42% RT) decides every verdict.**

## Observation (NOT a verdict-changer; locked grid forbids post-hoc rescue)

Long/short split: longs +$215 net, shorts −$1,174 net over a span where BTC rose secularly. A long-only variant is a *post-hoc* observation carrying the standard opposite-trap warning — it was not in the locked design, the asymmetry is regime-correlated (one secular bull), and +$215/5.7y on $1k (~3.8%/yr) is below holding BTC outright by an enormous margin. Recorded for honesty, not as a path.

## Honest limitations

- Funding charged flat 0.005%/8h both sides (multi-year history unobtainable — the ~92-day wall); conservative for shorts. Removing the funding charge entirely changes net by ~+$235 — still deeply negative.
- Fill model: next-bar-open (conservative vs paper.py's fill-at-close); stop fills gap-aware intrabar.
- Single symbol (BTC — the bot's own MVP scope). Other symbols would face the same cost floor with thinner books.

## Routing

Per the locked verdict: **TRENDBOT is shelved before further effort.** The paper-mode trial it was built for is not started — running paper for months would re-measure, slowly and noisily, what 5.7 years of data just answered in one pass. Reopen condition: a materially different strategy hypothesis (different signal class or timescale) or a cost-structure change (maker infra cutting RT below ~0.04%, where the gross edge would clear) — each testable first against the cached 5.7-year dataset for $0.

---

*Gate run 2026-06-12, one session, $0 live. The bot's code is untouched and correct as built — the verdict is about the strategy's edge, not the implementation. Trades: `analysis/gate_trades.csv` (regenerable).*
