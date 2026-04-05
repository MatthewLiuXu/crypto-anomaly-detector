# Crypto Research Agent

An on-demand anomaly scanner for crypto hedge fund analysts. Type a token, get a prioritized feed of what changed and why it matters.

## For Claude Code

**Read these files in order:**

1. `CONTEXT.md` — Full project context, design decisions, API details, and build order. This is the most important file. Read it first.
2. `ARCHITECTURE.md` — File structure, data flow, API specs, collector implementations, detection engine, and synthesis prompts. Contains working code examples for each module.
3. `config/thresholds.yaml` — Anomaly detection thresholds. Referenced by the detection engine.
4. `frontend/index.html` — Mockup UI. Currently calls Claude API directly from the browser. Needs to be rewired in Phase 5 to call the FastAPI backend instead.

**Build order is defined in CONTEXT.md.** Start with Phase 1 (CoinGecko collector + detection engine + scan endpoint). Each phase produces a testable increment.

## Quick Start (after building)

```bash
cp .env.example .env
# Fill in API keys
pip install -r requirements.txt
uvicorn api.main:app --reload
```

## API Keys Needed

- **Anthropic** (Claude): https://console.anthropic.com/
- **CoinGecko** (free Demo): https://www.coingecko.com/en/api/pricing — create free account
- **CryptoPanic** (free): https://cryptopanic.com/developers/api/
