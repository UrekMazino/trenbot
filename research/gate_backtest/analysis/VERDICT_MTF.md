# TRENDBOT MTF Gate Verdict — 4H & 1D both TF-AMBIGUOUS (2026-06-12)

*Per `WORK_ITEM_MTF_GATE.md` (verdicts locked at `95bb014` before the resample existed). Same strategy import, same mechanics, same locked costs (bar_hours unit extension recorded). Data: the cached 5.7-year set resampled to 12,499 4H bars / 2,083 1D bars.*

---

## Verdicts (locked gates)

| | 4H | 1D |
|---|---|---|
| Net after costs (5.7y, $1k notional) | **+$843.46** | +$188.92 |
| Trades | 213 | 34 |
| Sharpe | 0.52 (gate ≥ 0.8: FAIL) | 0.27 (FAIL) |
| Max drawdown | 34.7% (gate < 25%: FAIL) | 48.5% (FAIL) |
| Sub-periods positive | 2/4 (gate ≥ 3: FAIL) | 2/4 (FAIL) |
| Top-trade share | 0.06 (pass) | 0.21 (pass) |
| Perturbations ±20% | **6/6 positive** (pass) | 5/6 (breakout=16 → −$141: FAIL) |
| **Verdict** | **TF-AMBIGUOUS (MARGINAL-NET + REGIME-CONCENTRATED)** | **TF-AMBIGUOUS (MARGINAL-NET + REGIME-CONCENTRATED + PARAM-FRAGILE)** |

**Routing per the locked work item: Mixed/AMBIGUOUS → operator call, sub-causes as routing input.** Neither DEAD (the timescale hypothesis is NOT closed) nor VIABLE (no paper authorization).

## The headline finding — the cost-floor mechanism is confirmed end-to-end

Same strategy, same costs, three timeframes:

| Timeframe | Gross edge/trade | Cost/trade | Edge/cost | Net (5.7y) |
|---|---|---|---|---|
| 1H | +0.018% | 0.134% | **0.13×** | −$959 |
| 4H | +0.571% | ~0.175% | **3.3×** | +$843 |
| 1D | +0.965% | ~0.41% | **2.4×** | +$189 |

Edges scale with horizon; costs barely move. The inversion happens between 1H and 4H — exactly the mechanism the work item hypothesized (and the same one StatBot measured: 0.7× at minutes → 12–55× at days). **4H trend is the first strategy in this entire research program whose gross edge clears its cost floor.**

## Why it still failed the gates (the honest quality picture)

+$843 over 5.7 years on $1,000 notional ≈ +14.8%/yr simple — but the path is the problem the gates were built to catch:

- **Regime concentration:** sub-period nets +$295 / −$19 / +$732 / −$165. All profit came from two trending eras (≈2020-21 bull, ≈2023-24 recovery); the strategy bled or flatlined through the other ~2.8 years. A live operator would have sat through years of nothing punctuated by 35% drawdowns — Sharpe 0.52 is the honest summary.
- **Long/short asymmetry persists:** 4H longs +$1,183 / shorts −$340 (secular-bull span; the long-only variant remains a foreclosed post-hoc observation).
- **1D adds parameter fragility** (one perturbation flips negative) on thin N (34 trades).
- **Benchmark honesty:** BTC buy-and-hold over the same span returned several hundred percent (with its own, deeper drawdowns). A 14.8%/yr-on-notional trend bot with 35% DD is not obviously better than either holding or doing nothing.

## Skeptical notes (the wanted-direction result got the scrutiny)

Exit economics coherent (all stops, 36.6% winners at trend-profile payoff); no concentration (top trade 6%); parameter-ROBUST at 4H (all six perturbations positive, +$569 to +$910) — the 4H result is not a single-cell artifact. The failures are genuinely about *quality* (risk-adjusted return and temporal consistency), not validity.

## Operator decision (per locked routing)

- **Option A — honor the gates and shelve.** The gates were locked to encode "worth running a bot for"; Sharpe 0.5 with multi-year flat stretches and 35% DD didn't meet them, and borderline resolves down. The cached dataset and confirmed cost-floor finding are preserved. *(Program-consistent default.)*
- **Option B — paper mode at 4H anyway.** The bot is built; paper is cheap but slow (4H signals → months per handful of trades) and would mostly re-measure what 5.7 years already showed: a real-but-mediocre, regime-dependent edge. If chosen, paper criteria must be pre-committed first.
- **Either way:** no third timeframe, no parameter mining, no long-only rescue — all foreclosed by the lock.

---

*MTF gate run 2026-06-12, $0 live, resample-only (no new data pulls). Trades: `analysis/gate_trades_4H.csv`, `gate_trades_1D.csv`. The timescale hypothesis was directionally right — and the locked gates held against the program's first cost-clearing result anyway. Both facts are the finding.*
