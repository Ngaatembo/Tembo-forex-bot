# AI-Powered Forex Trading Intelligence & Paper-Trading Platform

A modular research platform for analyzing forex markets — combining
price data, technical indicators, news, and economic events — to test
whether a statistically meaningful trading edge exists after realistic
costs. **This is not an autonomous live-money trading bot.**

## Status: Phase 0 — Architecture

This repository currently contains the project skeleton only:
directory structure, configuration, database schema foundation, a
minimal FastAPI app with a health endpoint, and a test framework.
No market data, news, AI analysis, strategies, or trading logic are
implemented yet. See `docs/development-roadmap.md` for what comes next.

**Live execution is disabled by default and requires both an explicit
config flag and a real broker adapter implementation that does not
exist yet.** See `docs/risk-management.md`.

## Structure

```
ai-trading-platform/
├── backend/       FastAPI app (see backend/README.md)
├── frontend/      React/Next.js dashboard (Phase 9+)
├── notebooks/     Research/experiment notebooks
├── docs/          Architecture, strategy, risk, data-source docs
└── .env.example   All environment variables the app expects
```

## Quick start

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload
```

Then check `http://localhost:8000/health`.

## Documentation

- `docs/architecture.md` — system design and module responsibilities
- `docs/strategy.md` — strategy engine design (Phase 3+)
- `docs/risk-management.md` — risk controls and the kill-switch contract
- `docs/data-sources.md` — market data / news / economic providers
- `docs/development-roadmap.md` — the phased build plan (Phase 0–10)

## Core principles

1. Never promise profitability.
2. Never let AI output bypass risk management.
3. Never use future information in historical backtests.
4. Every strategy must be independently backtestable and measurable.
5. Live execution is isolated from research and requires deliberate opt-in.

See `docs/development-roadmap.md` for the full rule set.
