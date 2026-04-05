# Project Context — Crypto Research Agent

## What This Is

An on-demand anomaly scanner for crypto hedge fund analysts. The analyst types a token, the backend pulls structured data from APIs, checks for anomalies using threshold-based math (not AI), and returns a prioritized feed. Claude is used only for two narrow tasks: writing human-readable headlines for detected anomalies, and providing on-demand drill-down analysis when the analyst clicks an anomaly.

## Who It's For

Analysts at blockchain hedge funds like Pantera Capital. Their daily workflow involves checking 5-10 dashboards every morning for what changed overnight. This tool replaces that manual process.

## Key Design Decisions (from conversation)

### 1. Anomaly detection is math, not AI
Claude never decides what's anomalous. The backend compares current numbers against thresholds defined in `config/thresholds.yaml`. If price moved more than X%, that's an anomaly. Claude only writes prose about anomalies the code already flagged.

### 2. Fully on-demand, no background jobs
The original architecture had cron jobs, a watchlist, and a database for storing snapshots. We eliminated all of that. CoinGecko and DeFiLlama already return historical comparisons (24h change, 7d change) in their API responses. We use their built-in baselines instead of computing our own. This means: no database, no cron, no watchlist, fully stateless.

### 3. Claude has two narrow jobs with tight constraints
**Job 1 — Headlines:** After detection, all anomalies are sent to Claude in a single batch call. Claude writes a 1-2 sentence headline per anomaly using only the raw data provided. Returns JSON array of strings. No filler, no speculation.

**Job 2 — Drill-down:** When the analyst clicks an anomaly, the backend re-pulls fresh data, then sends the raw data + anomaly context to Claude with a constrained system prompt. The output follows a strict structure: What Happened → Likely Cause → How Unusual → Position Implication → Signal tag (ACCUMULATE / MONITOR / REDUCE / IGNORE). Claude also gets web search enabled for drill-downs to find additional context.

### 4. The UI is a feed, not a chatbot
The analyst doesn't "ask Claude about SUI." They type a token, get a scannable feed of discrete anomalies ranked by severity, and click into the ones that matter. The interaction model is: scan → prioritize → drill down.

### 5. Three data sources for MVP
- **CoinGecko** (free/demo tier): Price, volume, market cap, supply, ATH, % changes
- **DeFiLlama** (free, no auth): TVL by protocol/chain with daily/weekly changes
- **CryptoPanic** (free tier): News headlines with community sentiment votes

### 6. Output quality constraints
The system prompt for Claude explicitly forbids filler phrases ("it's worth noting", "interestingly", "notably"), requires leading with hard numbers, and mandates "cause unclear" when evidence doesn't support a causal claim. Every response ends with a SIGNAL tag forcing an actionable stance.

## API Details (from docs review)

### CoinGecko
- **Base URL:** `https://api.coingecko.com/api/v3/`
- **Auth:** Header `x-cg-demo-api-key: YOUR_KEY` (free Demo plan)
- **Rate limit:** 30 calls/min, 10,000 calls/month
- **Key endpoints:**
  - `GET /search?query={ticker}` — Resolve ticker → coingecko ID (1 call)
  - `GET /coins/markets?vs_currency=usd&ids={id}` — Price, volume, mcap, % changes, ATH, supply. Batches up to 250 coins per call. **This is the primary endpoint.** Returns: `current_price`, `price_change_percentage_24h`, `price_change_percentage_7d`, `price_change_percentage_30d`, `total_volume`, `market_cap`, `fully_diluted_valuation`, `circulating_supply`, `max_supply`, `ath`, `ath_change_percentage`, `high_24h`, `low_24h`.
  - `GET /coins/{id}?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false` — Full metadata. Heavier. Only use if `/coins/markets` doesn't have what you need.
  - `GET /search/trending` — Top 7 trending coins (bonus signal)

### DeFiLlama
- **Base URL:** `https://api.llama.fi`
- **Auth:** None required
- **Rate limit:** ~50-100 calls/min (not formally documented, generous)
- **Key endpoints:**
  - `GET /protocols` — Full list of ~4000 protocols with slugs, names, symbols. **Cache this on startup** and build a ticker → slug mapping.
  - `GET /protocol/{protocol}` — Historical TVL, chain breakdowns, `change_1d`, `change_7d`. This is the primary TVL endpoint.
  - `GET /tvl/{protocol}` — Current TVL only (single number). Lighter alternative.
  - `GET /v2/chains` — TVL for all chains. Use when the token IS a chain (SUI, ARB, etc.).
  - `GET /summary/fees/{protocol}` — Fee and revenue data with history.
  - `GET /summary/dexs/{protocol}` — DEX volume data.
- **Slug resolution:** DeFiLlama uses its own slugs (e.g., "aave", "lido"), not tickers. Must resolve via the cached `/protocols` list.

### CryptoPanic
- **Base URL:** `https://cryptopanic.com/api/v1/`
- **Auth:** `auth_token` query parameter
- **Rate limit:** ~50-200 requests/hour on free tier
- **Key endpoint:**
  - `GET /posts/?auth_token={key}&currencies={TOKEN}` — Recent news filtered by token. Returns: `title`, `published_at`, `kind` (news/media/blog/twitter/reddit), `source`, `url`, `votes` (bullish/bearish/important/liked counts).
  - Useful filters: `filter=important`, `filter=bearish`, `kind=news`
- **Free tier limitations:** No `panic_score` (Enterprise only), no `size` parameter (default page size), no `panic_period`.

### Budget per scan: 3-4 API calls total
| Source | Calls | Data |
|--------|-------|------|
| CoinGecko `/search` | 1 | Resolve ticker |
| CoinGecko `/coins/markets` | 1 | All market data |
| DeFiLlama `/protocol/{slug}` | 0-1 | TVL (if applicable) |
| CryptoPanic `/posts` | 1 | Headlines + sentiment |

At 30 calls/min CoinGecko limit: ~8 full scans/min. Monthly cap of 10,000 calls ≈ 2,500+ scans/month.

## Deployment Target

Railway (already used for other projects). FastAPI serves both the API and the static frontend via `StaticFiles` mount.

## Build Order

### Phase 1: Scan endpoint with price data only
1. `collectors/coingecko.py` — resolve ticker + pull market data via `/coins/markets`
2. `detection/engine.py` — price threshold checks
3. `config/thresholds.yaml` — initial thresholds
4. `api/main.py` + `api/routes/scan.py` — POST /scan
5. `api/models.py` — Pydantic models
6. Test: `curl -X POST localhost:8000/scan -d '{"token":"SUI"}'`

### Phase 2: Add Claude headlines
7. `synthesis/headlines.py` — batch headline generation
8. Wire into scan route
9. Test: scan returns anomalies with human-readable headlines

### Phase 3: Add TVL + news
10. `collectors/defillama.py` — TVL data
11. `collectors/cryptopanic.py` — news + sentiment
12. Expand detection engine with TVL, volume, sentiment rules

### Phase 4: Drill-down
13. `synthesis/drilldown.py` — constrained analysis with web search
14. `api/routes/drilldown.py` — POST /drilldown
15. Wire frontend to call drilldown endpoint

### Phase 5: Frontend integration
16. Update `frontend/index.html` to call FastAPI backend
17. Serve via StaticFiles
18. Deploy to Railway
