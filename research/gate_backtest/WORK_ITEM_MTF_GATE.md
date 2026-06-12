# Work Item — TRENDBOT Timeframe-Escalation Gate (4H / 1D)
## The last evidence-backed mitigation candidate. Verdicts LOCKED at commit time, before any resample exists.

**Authorized 2026-06-12** (operator: "go for 4H/1D timeframe gate"), following TREND-DEAD at 1H (commit `93ef616`).

**Hypothesis (the one structural argument that survived the mitigation audit):** costs are fixed per trade (~0.12–0.13% RT + funding); edges scale with holding horizon. The same entry logic on 4H/1D bars holds days-to-weeks targeting moves 5–20× larger against the same per-trade cost bill — the same mechanism that inverted StatBot's edge/cost from 0.7× (minute) to 12–55× (daily). **Honest priors against:** G1 showed chop still dominates daily-scale *spreads* (different object — single-asset may differ); 1D trade count over 5.7 years will be small (UNDERPOWERED is a live outcome, pre-named).

## 1. Spec (locked)

- **Data:** resample the cached 5.7-year 1H dataset (UTC-aligned buckets; complete buckets only) → 4H and 1D. No new pulls needed.
- **Strategy:** the bot's own `QuantTrendStrategy`, default params, imported directly — identical to the 1H gate. 300-bar sliding window (the bot's operating mode, timeframe-agnostic).
- **Mechanics:** identical to the 1H gate (next-bar-open fills, stop-active-from-prior-bar, gap-aware intrabar stop fills, MTM equity).
- **Costs:** identical locked model — 0.12% RT + 0.005%/8h funding both sides. **Unit fix recorded (extension, not re-spec):** the simulator's funding term gains a `bar_hours` parameter so holds are charged in real hours at 4H/1D (the 1H results are unchanged at `bar_hours=1`); Sharpe annualization likewise parametrized. The cost *model* does not change — only its unit handling at new timeframes.
- **Two independent runs:** the 4H gate and the 1D gate, each with base + the same six ±20% perturbations.
- **Long+short as coded.** The long-only variant stays foreclosed (post-hoc trap, recorded at the 1H gate).

## 2. Pre-committed verdicts (per timeframe; LOCKED)

> **TF-VIABLE** — ALL of: net > 0 after costs; Sharpe ≥ 0.8; max DD < 25%; ≥ 3 of 4 equal sub-periods net-positive; top trade < 30% of gross profit; all six ±20% perturbations net-positive; **n ≥ 30 closed trades.** A VIABLE result gets the skeptical audit (peek test + sign-by-exit-type) before acceptance.
>
> **TF-DEAD** — net ≤ 0 after costs, or positivity only via concentration (top trade ≥ 50% of gross).
>
> **TF-AMBIGUOUS** — named sub-causes: MARGINAL-NET · REGIME-CONCENTRATED · PARAM-FRAGILE · TOP-TRADE-CONCENTRATION · **UNDERPOWERED (n < 30 — pre-named as the likely 1D outcome; it is "couldn't test," never "passed").**

**Overall routing (locked):** both timeframes DEAD → the timescale hypothesis closes and **TRENDBOT is shelved finally** — no further mitigation candidates exist; the cost-floor finding stands as the binding fact. Either timeframe VIABLE → audit, then operator decides on the bot's paper mode at that timeframe with pre-committed paper criteria. AMBIGUOUS → operator call, sub-cause as routing input. **Lock direction:** this is the last candidate — pressure toward VIABLE is maximal; borderline resolves DOWN; the grid does not grow; no third timeframe gets added post-hoc.

---

*MTF gate work item v1.0, 2026-06-12. Locked before the resample. Pattern: verdicts before data; the wanted answer gets the hardest audit; a final no is final.*
