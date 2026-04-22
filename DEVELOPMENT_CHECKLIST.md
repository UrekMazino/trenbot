# OKXTRENDBOT Development Checklist

This checklist tracks the path from the current BTC-only trend MVP toward the operational maturity of OKXStatBot, while keeping the projects independent.

## Phase 1: Strategy Core

- [x] Create independent `OKXTRENDBOT` project and Git repo.
- [x] Add BTC-only trend strategy core.
- [x] Add EMA, ATR, breakout, and overextension checks.
- [x] Add public OKX candle fetch.
- [x] Add signal recording.
- [x] Add paper position/trade lifecycle.
- [x] Add CLI commands: `init-db`, `fetch-candles`, `evaluate`, `paper-step`, `paper-status`, `paper-reset`.
- [ ] Add historical backtest runner.
- [ ] Add replay/grid search for strategy parameters.
- [ ] Add signal quality statistics.

## Phase 2: Runtime Bot

- [x] Add `paper-run --interval` continuous runtime.
- [x] Add runtime state file.
- [x] Add rotating runtime logs.
- [x] Add run records.
- [x] Add run event records.
- [ ] Add graceful stop handling.
- [ ] Prevent duplicate bot instances.
- [ ] Resume open paper position after restart.
- [ ] Add heartbeat/health records.

## Phase 3: Database Normalization

- [x] Normalize `runs`.
- [x] Normalize `run_events`.
- [x] Normalize `trend_signals`.
- [x] Normalize `paper_positions`.
- [x] Normalize `paper_trades`.
- [ ] Add `equity_snapshots`.
- [ ] Add `bot_configs`.
- [ ] Add `reports`.

## Phase 4: API And Dashboard

- [ ] Add FastAPI backend.
- [ ] Add dashboard shell.
- [ ] Add start/stop controls.
- [ ] Add live terminal/log stream.
- [ ] Add BTC trend state card.
- [ ] Add latest signal table.
- [ ] Add open paper position card.
- [ ] Add closed paper trades table.
- [ ] Add paper PnL/equity chart.
- [ ] Add settings page.
- [ ] Add basic permissions.

## Phase 5: Reports And Analytics

- [ ] Add run report generation.
- [ ] Add trade summary.
- [ ] Add win/loss summary.
- [ ] Add PnL curve.
- [ ] Add drawdown.
- [ ] Add signal distribution.
- [ ] Add entry/exit reason breakdown.
- [ ] Add config snapshot.
- [ ] Add CSV/JSON export.
- [ ] Add clear logs/reports workflow.

## Phase 6: Risk Manager

- [ ] Add max daily paper loss.
- [ ] Add max open position/notional guard.
- [ ] Add max consecutive losses guard.
- [ ] Add cooldown after loss.
- [ ] Add stale-data detection.
- [ ] Add high-volatility no-trade gate.
- [ ] Add mode separation: paper, demo, live.

## Phase 7: Demo Trading

- [ ] Add separate OKX demo credential loading.
- [ ] Add demo balance fetch.
- [ ] Add order preview.
- [ ] Add demo order placement.
- [ ] Add position reconciliation.
- [ ] Add emergency close.
- [ ] Add demo trade records.

## Phase 8: Docker And Operations

- [ ] Add Dockerfile.
- [ ] Add docker-compose stack.
- [ ] Add bot worker service.
- [ ] Add API service.
- [ ] Add web service.
- [ ] Add DB service.
- [ ] Add health checks.
- [ ] Add persistent volumes.

## Phase 9: Live Trading Gate

- [ ] Add separate live credentials.
- [ ] Add explicit live-mode unlock.
- [ ] Add tiny-notional first-run mode.
- [ ] Add full audit logs.
- [ ] Add kill switch.
- [ ] Add read-only fallback mode.
