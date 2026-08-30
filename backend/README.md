# Backend — AI Forex Research Platform

FastAPI backend for the research/backtesting/paper-trading platform.
See the root `README.md` and `docs/architecture.md` for the full picture.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env   # then fill in real values
```

## Run

```bash
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/health` — with no `.env` configured, all
providers report `not_configured` and `live_execution_enabled` is `false`.
This is the expected Phase 0 state.

## Test

```bash
pytest
```
