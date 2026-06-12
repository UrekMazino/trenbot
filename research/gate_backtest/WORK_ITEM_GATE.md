# Work Item — TRENDBOT Offline Gate Backtest
## Read-only research. No bot-code changes, no live trading. Verdicts LOCKED at commit time, before any real data is pulled.

**Authorized 2026-06-12** (operator: "start TRENDBOT's gate run"). The bot is a built MVP whose premise — EMA-trend + breakout continuation on BTC-USDT-SWAP 1H — has never been tested on real data. Per the discipline that ran OKXStatBot and OKXFundingBot: the gate runs offline for $0 BEFORE any further effort (paper-running the bot for months, live capital, feature work) is spent.

---

## 1. The question

Does the bot's **exact coded strategy** — entries per `src/okxtrendbot/strategy.py` (`QuantTrendStrategy.evaluate`, default params: EMA 20/60, ATR 14, breakout 20, gap ≥ 0.20 ATR, extension ≤ 3.0 ATR), exits per `src/okxtrendbot/paper.py` (2.5×ATR trailing stop, intrabar stop fill, opposite-signal exit, trend-invalidation exit) — clear realistic costs on multi-year real BTC-USDT-SWAP 1H data?

**Fidelity rule:** the gate imports the bot's own `QuantTrendStrategy` for signal generation (zero transcription drift). The portfolio loop reimplements `paper.py` semantics with two no-lookahead corrections, recorded as deltas:
- Entries and signal-based exits fill at the **NEXT bar's open** (the paper trader fills at signal-bar close — optimistic; the gate does not inherit that).
- The stop active during bar *t* is the stop as of the END of bar *t−1*; trailing updates take effect the following bar. Stop exits fill intrabar at the stop price (matches both `paper.py` and how a real stop order works).
- Signals computed on a **300-bar sliding window** — the bot's own `candle_limit` operating mode.

## 2. Data

- OKX `history-candles`, `BTC-USDT-SWAP`, bar=1H, **as far back as the API serves** (target ≥ 2 years; actual depth recorded — if the endpoint depth-limits like funding-rate-history did, the sub-period definition below re-scopes automatically). Confirmed bars only.
- Cache: `research/gate_backtest/data/BTC-USDT-SWAP-1H-real.csv` (gitignored, regenerable). The existing `data/BTC-USDT-SWAP-1H.csv` is synthetic test fixture data and is not touched.

## 3. Costs (locked)

- **Fees+slippage:** taker 0.05% + slippage 0.01% per side (BTC tier per the FundingBot cost model) → **0.12% of notional round trip.**
- **Funding:** 0.005%/8h held, charged on ALL positions regardless of side (longs would pay this on median-positive funding; shorts would typically receive — charging both is conservative and resists GO). Multi-year funding history is not publicly available (the ~92-day wall, verified in FundingBot Phase 1); this locked flat assumption is recorded as such.
- **Sizing for the primary gate: fixed $1,000 notional per trade** (clean percentage economics; equity base $1,000). The bot's own risk-sizing defaults (0.25% risk, $100 max notional) reported as context only.

## 4. Pre-committed verdicts (LOCKED at this commit)

> **TREND-VIABLE** — ALL of: net PnL > 0 after costs; Sharpe ≥ 0.8 (1H equity curve, annualized); max drawdown < 25% of equity; ≥ 3 of 4 equal sub-periods of the pulled span net-positive; top single trade < 30% of gross profit; all six single-parameter ±20% perturbations (ema_fast, ema_slow, breakout_lookback — each ±20%, rounded) remain net-positive. **Routes to:** the bot's own paper mode, with paper criteria pre-committed before it starts. A VIABLE result gets the skeptical audit first (sign audit by exit type + a deliberate +1-bar peek test — if peeking dramatically improves results, the no-lookahead implementation is suspect).
>
> **TREND-DEAD** — net ≤ 0 after costs over the full span, OR positivity exists only via concentration (top trade ≥ 50% of gross profit, or a single sub-period carrying an otherwise-negative strategy). **Routes to:** TRENDBOT shelved before further effort. Per the portfolio precedent: the cheap no is the second-best outcome available.
>
> **TREND-AMBIGUOUS** — named sub-causes, un-blurrable: **MARGINAL-NET** (positive but Sharpe/DD gates fail) · **REGIME-CONCENTRATED** (sub-period concentration short of DEAD) · **PARAM-FRAGILE** (perturbation flips sign) · **UNDERPOWERED** (< 30 closed trades on the full span). Operator's call, sub-cause as routing input.
>
> **Lock direction:** the bot is already built — sunk effort pressures toward VIABLE. Borderline resolves DOWN. The parameter grid does not grow; the cost model does not soften after results exist.

## 5. Guardrails

Read-only on bot source (imported, never modified); public endpoints only; cache-then-analyze; no imputation; deltas from `paper.py` recorded (§1); the wanted answer gets the hardest audit.

---

*TRENDBOT gate work item v1.0, 2026-06-12. Locked before the real-data pull. Pattern: OKXStatBot research arc / OKXFundingBot Phase 1 — verdicts before data, borderline down, audit the wanted answer.*
