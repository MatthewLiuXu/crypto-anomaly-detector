# Crypto Research Agent — Architecture

## File Structure

```
crypto-research-agent/
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
│
├── config/
│   └── thresholds.yaml
│
├── collectors/
│   ├── __init__.py
│   ├── base.py                   # BaseCollector interface
│   ├── coingecko.py              # Price, volume, mcap, supply, ATH
│   ├── defillama.py              # TVL by protocol and chain
│   └── cryptopanic.py            # News headlines + sentiment
│
├── detection/
│   ├── __init__.py
│   └── engine.py                 # Threshold checks → anomaly list
│
├── synthesis/
│   ├── __init__.py
│   ├── headlines.py              # Batch anomalies → 1-2 sentence headlines
│   └── drilldown.py              # Single anomaly → full drill-down
│
├── api/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app, CORS, StaticFiles mount
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── scan.py               # POST /scan
│   │   └── drilldown.py          # POST /drilldown
│   └── models.py                 # Pydantic request/response models
│
├── frontend/
│   └── index.html                # Anomaly feed UI
│
└── tests/
    ├── test_collectors.py
    ├── test_detection.py
    └── test_api.py
```

---

## Data Flow

```
Analyst types "SUI" → hits SCAN
         │
         ▼
    POST /scan { "token": "SUI" }
         │
         ▼
┌─────────────────────────────────────────────┐
│  1. RESOLVE                                  │
│     CoinGecko GET /search?query=SUI          │
│     → coingecko_id: "sui"                    │
│     DeFiLlama: match against cached          │
│     /protocols list → slug: "sui" (or null)  │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  2. COLLECT (parallel async)                 │
│                                              │
│  CoinGecko:                                  │
│  GET /coins/markets?vs_currency=usd&ids=sui  │
│  → price, 24h/7d/30d %, volume, mcap,        │
│    FDV, supply, ATH, ath_change_%            │
│                                              │
│  DeFiLlama (if slug resolved):               │
│  GET /protocol/sui                           │
│  → tvl, change_1d, change_7d                 │
│  OR GET /v2/chains (if token is a chain)     │
│                                              │
│  CryptoPanic:                                │
│  GET /posts/?auth_token=X&currencies=SUI     │
│  → headlines, published_at, votes            │
│                                              │
│  All return raw dicts. 3-4 API calls total.  │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  3. DETECT (pure math, no AI)                │
│                                              │
│  Compare each metric against thresholds.yaml │
│  - price_change_24h > 15%? → high severity   │
│  - tvl_change_1d > 20%? → high severity      │
│  - volume/mcap ratio > 0.20? → high          │
│  - ath_change_pct within 10%? → flag         │
│  - bearish headline count > 3? → flag        │
│                                              │
│  Output: list of Anomaly dicts with          │
│  severity, metric, raw values, change %.     │
│  No prose yet.                               │
│                                              │
│  If 0 anomalies: return early with           │
│  "nothing notable" message. Skip Claude.     │
└──────────────┬──────────────────────────────┘
               │
               ▼  (only if anomalies found)
┌─────────────────────────────────────────────┐
│  4. SYNTHESIZE HEADLINES (1 Claude call)     │
│                                              │
│  Send all anomalies + news context to Claude │
│  in a single batch. Claude returns a JSON    │
│  array of 1-2 sentence headlines.            │
│  No filler, no speculation, numbers only.    │
└──────────────┬──────────────────────────────┘
               │
               ▼
         Return JSON to frontend
         Frontend renders anomaly cards
```

```
Analyst clicks an anomaly card
         │
         ▼
    POST /drilldown { token, anomaly }
         │
         ▼
┌─────────────────────────────────────────────┐
│  1. Re-pull fresh data from relevant         │
│     collectors for this token                │
│                                              │
│  2. Send raw data + anomaly context to       │
│     Claude with constrained system prompt    │
│     + web_search tool enabled                │
│                                              │
│  3. Claude returns structured analysis:      │
│     What Happened → Likely Cause →           │
│     How Unusual → Position Implication →     │
│     SIGNAL tag                               │
│                                              │
│  4. Return markdown to frontend              │
└─────────────────────────────────────────────┘
```

---

## API Endpoints

### POST /scan

**Request:**
```json
{
  "token": "SUI"
}
```

**Response:**
```json
{
  "token": "SUI",
  "resolved": {
    "coingecko_id": "sui",
    "defillama_slug": "sui",
    "name": "Sui"
  },
  "scanned_at": "2026-04-05T14:30:00Z",
  "market_context": {
    "price_usd": 3.42,
    "market_cap": 10800000000,
    "volume_24h": 892000000,
    "fdv": 34200000000
  },
  "anomalies": [
    {
      "id": "price-24h",
      "severity": "high",
      "metric": "Price",
      "change_pct": 14.7,
      "value_current": 3.42,
      "value_comparison": 2.98,
      "comparison_window": "24h",
      "headline": "Price up 14.7% in 24h on 2.8x average volume. Grayscale SUI Trust filing hit the wire this morning.",
      "source": "CoinGecko",
      "raw_data": {
        "price_usd": 3.42,
        "price_change_24h_pct": 14.7,
        "price_change_7d_pct": 22.3,
        "volume_24h": 892000000
      }
    }
  ],
  "no_anomalies_message": null
}
```

If nothing crosses a threshold:
```json
{
  "token": "SUI",
  "anomalies": [],
  "no_anomalies_message": "No significant anomalies. Price, TVL, and volume within normal ranges."
}
```

### POST /drilldown

**Request:**
```json
{
  "token": "SUI",
  "anomaly": {
    "id": "price-24h",
    "severity": "high",
    "metric": "Price",
    "change_pct": 14.7,
    "headline": "Price up 14.7% in 24h...",
    "raw_data": {}
  }
}
```

**Response:**
```json
{
  "analysis": "## SUI — Price Drill-Down\n\n### What Happened\n...",
  "signal": "MONITOR",
  "signal_reason": "Filing is a catalyst but no confirmed fund launch yet.",
  "generated_at": "2026-04-05T14:32:00Z"
}
```

---

## Collector Implementations

### coingecko.py

```python
import httpx
from typing import Optional

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

async def resolve_token(ticker: str, api_key: str) -> Optional[dict]:
    """Resolve a ticker to a CoinGecko ID via /search."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{COINGECKO_BASE}/search",
            params={"query": ticker},
            headers={"x-cg-demo-api-key": api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        coins = data.get("coins", [])
        if not coins:
            return None
        # Prefer exact symbol match
        for coin in coins:
            if coin.get("symbol", "").upper() == ticker.upper():
                return {"coingecko_id": coin["id"], "name": coin["name"]}
        return {"coingecko_id": coins[0]["id"], "name": coins[0]["name"]}


async def collect_market_data(coingecko_id: str, api_key: str) -> dict:
    """
    Pull market data via /coins/markets.
    Single call, returns everything needed for detection.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": coingecko_id,
                "price_change_percentage": "1h,24h,7d,30d",
            },
            headers={"x-cg-demo-api-key": api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return {}
        coin = data[0]
        return {
            "price_usd": coin.get("current_price"),
            "price_change_24h_pct": coin.get("price_change_percentage_24h"),
            "price_change_7d_pct": coin.get("price_change_percentage_7d_in_currency"),
            "price_change_30d_pct": coin.get("price_change_percentage_30d_in_currency"),
            "volume_24h": coin.get("total_volume"),
            "market_cap": coin.get("market_cap"),
            "fdv": coin.get("fully_diluted_valuation"),
            "circulating_supply": coin.get("circulating_supply"),
            "max_supply": coin.get("max_supply"),
            "ath": coin.get("ath"),
            "ath_change_pct": coin.get("ath_change_percentage"),
            "high_24h": coin.get("high_24h"),
            "low_24h": coin.get("low_24h"),
        }
```

### defillama.py

```python
import httpx
from typing import Optional

LLAMA_BASE = "https://api.llama.fi"

# Cache this on startup: call once, reuse forever
_protocol_cache: list[dict] | None = None

async def _load_protocols() -> list[dict]:
    global _protocol_cache
    if _protocol_cache is not None:
        return _protocol_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{LLAMA_BASE}/protocols")
        resp.raise_for_status()
        _protocol_cache = resp.json()
        return _protocol_cache


async def resolve_slug(ticker: str) -> Optional[str]:
    """Try to match a ticker to a DeFiLlama protocol slug."""
    protocols = await _load_protocols()
    ticker_upper = ticker.upper()
    # Exact symbol match first
    for p in protocols:
        if p.get("symbol", "").upper() == ticker_upper:
            return p.get("slug")
    # Name match fallback
    for p in protocols:
        if ticker_upper in p.get("name", "").upper():
            return p.get("slug")
    return None


async def collect_tvl(slug: str) -> Optional[dict]:
    """Pull TVL data for a protocol. Returns None if not found."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{LLAMA_BASE}/protocol/{slug}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return {
            "tvl_total": data.get("currentChainTvls", {}).get("total")
                         or data.get("tvl", [{}])[-1].get("totalLiquidityUSD") if data.get("tvl") else None,
            "change_1d": data.get("change_1d"),
            "change_7d": data.get("change_7d"),
            "chains": list(data.get("currentChainTvls", {}).keys()),
        }


async def collect_chain_tvl(chain_name: str) -> Optional[dict]:
    """Pull TVL for a chain (e.g., 'Sui', 'Arbitrum')."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{LLAMA_BASE}/v2/chains")
        resp.raise_for_status()
        chains = resp.json()
        for c in chains:
            if c.get("name", "").upper() == chain_name.upper():
                return {
                    "tvl_total": c.get("tvl"),
                    "change_1d": c.get("change_1d"),  # may not exist
                    "change_7d": c.get("change_7d"),  # may not exist
                }
        return None
```

### cryptopanic.py

```python
import httpx
from typing import Optional
from datetime import datetime, timedelta, timezone

CPANIC_BASE = "https://cryptopanic.com/api/v1"

async def collect_news(token: str, api_key: str) -> Optional[dict]:
    """Pull recent headlines + sentiment for a token."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{CPANIC_BASE}/posts/",
            params={
                "auth_token": api_key,
                "currencies": token.upper(),
                "kind": "news",
            },
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        results = data.get("results", [])

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = []
        bullish_count = 0
        bearish_count = 0

        for post in results:
            published = post.get("published_at", "")
            headline = {
                "title": post.get("title"),
                "published_at": published,
                "source": post.get("source", {}).get("title"),
                "url": post.get("url"),
                "kind": post.get("kind"),
            }
            recent.append(headline)

            # Count sentiment from votes
            votes = post.get("votes", {})
            if votes.get("positive", 0) > votes.get("negative", 0):
                bullish_count += 1
            elif votes.get("negative", 0) > votes.get("positive", 0):
                bearish_count += 1

        return {
            "headlines": recent[:10],  # cap at 10 most recent
            "total_count": len(results),
            "bullish_count_24h": bullish_count,
            "bearish_count_24h": bearish_count,
            "negative_count_24h": bearish_count,  # alias for detection engine
        }
```

---

## Detection Engine (detection/engine.py)

```python
import yaml
from pathlib import Path

def load_thresholds() -> dict:
    path = Path(__file__).parent.parent / "config" / "thresholds.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def detect(
    token: str,
    market_data: dict,
    tvl_data: dict | None,
    news_data: dict | None,
    thresholds: dict,
) -> list[dict]:
    """
    Pure function. No API calls, no Claude. Just math.
    Returns list of anomaly dicts sorted by severity.
    """
    anomalies = []

    # --- Price 24h ---
    p24 = market_data.get("price_change_24h_pct")
    if p24 is not None:
        ap24 = abs(p24)
        sev = _classify(ap24, thresholds["price_change_24h"])
        if sev:
            anomalies.append(_make(
                sev, "Price", p24, "24h", "CoinGecko", market_data
            ))

    # --- Price 7d ---
    p7d = market_data.get("price_change_7d_pct")
    if p7d is not None:
        ap7d = abs(p7d)
        sev = _classify(ap7d, thresholds["price_change_7d"])
        if sev:
            anomalies.append(_make(
                sev, "Price (7d)", p7d, "7d", "CoinGecko", market_data
            ))

    # --- Volume spike (volume/mcap ratio) ---
    vol = market_data.get("volume_24h", 0)
    mcap = market_data.get("market_cap", 0)
    if mcap and mcap > 0:
        vol_ratio = vol / mcap
        sev = _classify(vol_ratio, thresholds["volume_vs_mcap"])
        if sev:
            anomalies.append(_make(
                sev, "Volume",
                round(vol_ratio * 100, 1),
                "vol/mcap %", "CoinGecko", market_data
            ))

    # --- ATH proximity ---
    ath_pct = market_data.get("ath_change_pct")
    if ath_pct is not None and abs(ath_pct) <= thresholds["ath_proximity"]["trigger"]:
        anomalies.append(_make(
            "medium", "ATH Proximity",
            round(ath_pct, 1),
            "vs ATH", "CoinGecko", market_data
        ))

    # --- TVL 1d ---
    if tvl_data:
        t1d = tvl_data.get("change_1d")
        if t1d is not None:
            sev = _classify(abs(t1d), thresholds["tvl_change_1d"])
            if sev:
                anomalies.append(_make(
                    sev, "TVL", t1d, "24h", "DeFiLlama", tvl_data
                ))

    # --- TVL 7d ---
    if tvl_data:
        t7d = tvl_data.get("change_7d")
        if t7d is not None:
            sev = _classify(abs(t7d), thresholds["tvl_change_7d"])
            if sev:
                anomalies.append(_make(
                    sev, "TVL (7d)", t7d, "7d", "DeFiLlama", tvl_data
                ))

    # --- News sentiment ---
    if news_data:
        neg = news_data.get("negative_count_24h", 0)
        if neg >= thresholds["news_sentiment"]["negative_count_trigger"]:
            anomalies.append(_make(
                "medium", "Sentiment", None, "24h", "CryptoPanic", news_data
            ))

    # Sort by severity
    sev_order = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(key=lambda a: sev_order.get(a["severity"], 2))
    return anomalies


def _classify(value: float, tiers: dict) -> str | None:
    if value >= tiers["high"]:
        return "high"
    elif value >= tiers["medium"]:
        return "medium"
    elif value >= tiers["low"]:
        return "low"
    return None


def _make(severity, metric, change_pct, window, source, raw_data):
    return {
        "id": f"{metric.lower().replace(' ', '-')}-{window}",
        "severity": severity,
        "metric": metric,
        "change_pct": change_pct,
        "comparison_window": window,
        "source": source,
        "headline": None,  # filled by synthesis step
        "raw_data": raw_data,
    }
```

---

## Synthesis Prompts

### headlines.py — System Prompt

```
You are writing anomaly alert headlines for a crypto hedge fund terminal.

For each anomaly, write exactly 1-2 sentences using the raw data provided.
- Include specific numbers from the data
- State what happened, not what it means
- If news context is available and directly relevant, include the catalyst
- Never use filler phrases like "it's worth noting" or "interestingly"
- Never speculate on cause unless the data directly supports it

Return ONLY a JSON array of headline strings, one per anomaly, same order as input.
No other text. No markdown fences. Just the JSON array.
```

### drilldown.py — System Prompt

```
You are a crypto research terminal for hedge fund analysts.
An anomaly was flagged by automated monitoring. Provide a drill-down.

RULES:
- Lead with hard numbers
- Explain likely cause ONLY if evidence supports it — otherwise write "cause unclear"
- Never use phrases like "it's worth noting", "interestingly", "notably"
- Use markdown: ## for title, ### for subsections, **bold** for key data, - for bullets
- Be brutally concise — every sentence must carry information
- End with --- then **SIGNAL: [ACCUMULATE | MONITOR | REDUCE | IGNORE]** with one sentence justification

STRUCTURE:
## [Asset] — [Metric] Drill-Down
### What Happened
### Likely Cause
### How Unusual Is This
### Position Implication
### Signal
```

---

## Environment (.env.example)

```bash
ANTHROPIC_API_KEY=sk-ant-...
COINGECKO_API_KEY=CG-...
CRYPTOPANIC_API_KEY=...

HOST=0.0.0.0
PORT=8000
```

---

## Requirements

```
fastapi>=0.110.0
uvicorn>=0.27.0
httpx>=0.27.0
anthropic>=0.40.0
pyyaml>=6.0
pydantic>=2.5
python-dotenv>=1.0.0
```
