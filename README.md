# OKXTRENDBOT

Independent quantitative trend-following bot for OKX.

This project is intentionally separate from `OKXStatBot`. It has its own codebase, config, database, logs, and strategy assumptions so the statarb bot stays clean.

## MVP Scope

- Fixed first symbol: `BTC-USDT-SWAP`.
- First mode: `paper`, not live trading.
- Strategy family: single-symbol quantitative trend following.
- No cointegration, no hedge ratio, no pair z-score.
- Separate SQLite database under `data/okxtrendbot.sqlite`.

## Strategy Concept

`OKXStatBot` trades pair mean reversion.

`OKXTRENDBOT` trades directional continuation:

- Long when BTC has confirmed bullish trend and breakout continuation.
- Short when BTC has confirmed bearish trend and breakdown continuation.
- Stay flat during chop, weak trend, or overextended moves.
- Use ATR stops and small risk while validating.

## Quick Start

```powershell
cd C:\Users\jcvia\PyCharmMiscProject\OKXTRENDBOT
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
python -m okxtrendbot.cli init-db
python -m pytest -q
```

To evaluate a candle CSV:

```powershell
python -m okxtrendbot.cli evaluate --csv data\BTC-USDT-SWAP-1H.csv
```

CSV columns expected:

```text
ts,open,high,low,close,volume
```

To fetch current public OKX candles:

```powershell
python -m okxtrendbot.cli fetch-candles --limit 300
```

To run one paper-mode signal step:

```powershell
python -m okxtrendbot.cli paper-step
```

`paper-step` saves the latest candles to CSV, evaluates the BTC trend model, records the signal, and manages the paper lifecycle:

- Opens a simulated position when there is a `LONG` or `SHORT` signal and no open position.
- Holds and trails the ATR stop while the trend remains valid.
- Closes on stop loss, opposite signal, or EMA trend invalidation.
- Records closed paper trades with realized PnL.

A `FLAT` signal is normal and means the trend model chose not to open a new trade.

Inspect paper status:

```powershell
python -m okxtrendbot.cli paper-status
```

Reset paper positions/trades while preserving signal history:

```powershell
python -m okxtrendbot.cli paper-reset --yes
```

## Credentials

No OKX API credentials are needed for the current paper lifecycle. It only uses public candle data and simulated orders.

Use separate demo/live credentials later only when we intentionally add private account reads or actual order placement:

```env
OKX_API_KEY=
OKX_API_SECRET=
OKX_PASSPHRASE=
```

## Why Separate?

The statarb validator needs two tickers and pair relationship metrics. Trend following needs one ticker and directional metrics. Mixing them too early would make performance attribution and risk control muddy.

The future bridge should be portfolio-level only: shared risk limits can decide whether both bots are allowed to run, but their strategies should remain independent.
