import os
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.models import TrendingAnomaly, TrendingResponse
from collectors.coingecko import resolve_token, collect_market_data
from collectors.defillama import resolve_slug, collect_tvl, collect_chain_tvl, resolve_chain_name
from detection.engine import load_thresholds, detect

router = APIRouter()

WATCHLIST = ["BTC", "ETH", "SOL", "SUI", "DOGE", "PEPE", "WIF", "AAVE", "PENDLE", "ENA", "ONDO", "ARB"]


async def _scan_token(token: str, cg_key: str, thresholds: dict, sem: asyncio.Semaphore) -> list[dict]:
    """Scan a single token for anomalies. Returns list of anomaly dicts with token attached."""
    try:
        async with sem:
            cg_resolve, llama_slug, chain_name = await asyncio.gather(
                resolve_token(token, cg_key),
                resolve_slug(token),
                resolve_chain_name(token),
            )
        if not cg_resolve:
            return []

        async def get_tvl():
            if chain_name:
                result = await collect_chain_tvl(chain_name)
                if result:
                    return result
            if llama_slug:
                return await collect_tvl(llama_slug)
            return None

        async with sem:
            market_data, tvl_data = await asyncio.gather(
                collect_market_data(cg_resolve["coingecko_id"], cg_key),
                get_tvl(),
            )

        if not market_data:
            return []

        anomalies = detect(token, market_data, tvl_data=tvl_data, news_data=None, thresholds=thresholds)

        # Filter out info tier — sidebar should only show real signals
        real = [a for a in anomalies if a["severity"] != "info"]
        for a in real:
            a["token"] = token
        return real
    except Exception:
        return []


def _make_summary(token: str, anomaly: dict) -> str:
    metric = anomaly["metric"]
    pct = anomaly["change_pct"]
    window = anomaly["comparison_window"]
    if pct is not None:
        sign = "+" if pct > 0 else ""
        return f"{token} {metric} {sign}{round(pct, 1)}% ({window})"
    return f"{token} {metric} flagged ({window})"


@router.post("/trending", response_model=TrendingResponse)
async def trending():
    cg_key = os.environ.get("COINGECKO_API_KEY", "")
    if not cg_key:
        raise HTTPException(status_code=500, detail="COINGECKO_API_KEY not set")

    thresholds = load_thresholds()
    # Limit concurrency to avoid CoinGecko rate limits
    sem = asyncio.Semaphore(3)

    results = await asyncio.gather(
        *[_scan_token(t, cg_key, thresholds, sem) for t in WATCHLIST]
    )

    all_anomalies = []
    for token_anomalies in results:
        all_anomalies.extend(token_anomalies)

    # Sort by severity
    sev_order = {"high": 0, "medium": 1, "low": 2}
    all_anomalies.sort(key=lambda a: sev_order.get(a["severity"], 2))

    # Take top 15
    top = all_anomalies[:15]

    trending_models = [
        TrendingAnomaly(
            token=a["token"],
            severity=a["severity"],
            metric=a["metric"],
            change_pct=a["change_pct"],
            comparison_window=a["comparison_window"],
            source=a["source"],
            summary=_make_summary(a["token"], a),
            detected_at=a["detected_at"],
        )
        for a in top
    ]

    return TrendingResponse(
        anomalies=trending_models,
        scanned_tokens=len(WATCHLIST),
        scanned_at=datetime.now(timezone.utc),
    )
