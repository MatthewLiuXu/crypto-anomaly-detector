# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

On-demand crypto anomaly scanner for hedge fund analysts. Type a token, get a prioritized feed of what changed and why. Anomaly detection is pure math (thresholds in `config/thresholds.yaml`), not AI. Claude is used only for two narrow tasks: writing headlines for flagged anomalies and providing drill-down analysis on click.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server
uvicorn api.main:app --reload

# Test a scan
curl -X POST localhost:8000/scan -d '{"token":"SUI"}'

# Run tests
pytest tests/
pytest tests/test_detection.py        # single file
pytest tests/test_detection.py -k "test_price"  # single test
```

## Architecture

**Data flow:** `POST /scan` → resolve token → collect data (parallel async) → detect anomalies (math) → synthesize headlines (Claude) → return JSON

**Key constraint:** Fully stateless. No database, no cron, no watchlist. CoinGecko/DeFiLlama return historical comparisons in their responses; we use their built-in baselines.

### Layers

- **`collectors/`** — Async data fetchers (httpx). Each returns raw dicts. Three sources: CoinGecko (price/volume/mcap), DeFiLlama (TVL), CryptoPanic (news/sentiment). DeFiLlama protocols list should be cached on startup.
- **`detection/engine.py`** — Pure function. Compares metrics against `config/thresholds.yaml`. No API calls, no Claude. Returns anomaly list sorted by severity.
- **`synthesis/`** — Two modules: `headlines.py` (batch all anomalies → JSON array of 1-2 sentence strings) and `drilldown.py` (single anomaly → structured markdown analysis with web search). Claude prompts forbid filler phrases and require leading with hard numbers.
- **`api/`** — FastAPI app. Two routes: `POST /scan` and `POST /drilldown`. Serves frontend via StaticFiles mount. Pydantic models in `models.py`.
- **`frontend/index.html`** — Single-file UI. Needs to call the FastAPI backend (not Claude directly).

### API budget per scan: 3-4 calls

| Source | Endpoint | Auth |
|--------|----------|------|
| CoinGecko `/search` | Resolve ticker → ID | `x-cg-demo-api-key` header |
| CoinGecko `/coins/markets` | All market data | Same |
| DeFiLlama `/protocol/{slug}` | TVL (if applicable) | None |
| CryptoPanic `/posts/` | Headlines + sentiment | `auth_token` query param |

### Build Order

Defined in `CONTEXT.md`. Five phases, each producing a testable increment. Start with Phase 1 (CoinGecko collector + detection engine + scan endpoint).

## Environment

Requires `.env` with `ANTHROPIC_API_KEY`, `COINGECKO_API_KEY`, `CRYPTOPANIC_API_KEY`. Copy from `.env.example`.

## Key Design Rules

- Detection is math-only — Claude never decides what's anomalous
- Claude headlines: no filler, no speculation, numbers only, JSON array output
- Claude drill-downs: strict structure (What Happened → Likely Cause → How Unusual → Position Implication → SIGNAL tag), web search enabled
- If 0 anomalies detected, return early with "nothing notable" message — skip Claude entirely
- Deployment target: Railway, FastAPI serves API + static frontend
