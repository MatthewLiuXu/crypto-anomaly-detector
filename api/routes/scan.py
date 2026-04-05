import os
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.models import (
    ScanRequest,
    ScanResponse,
    ResolvedToken,
    MarketContext,
    Anomaly,
)
from collectors.coingecko import resolve_token, collect_market_data
from collectors.defillama import resolve_slug, collect_tvl, collect_chain_tvl, resolve_chain_name
from detection.engine import load_thresholds, detect
from synthesis.headlines import generate_headlines

router = APIRouter()


@router.post("/scan", response_model=ScanResponse)
async def scan(req: ScanRequest):
    cg_key = os.environ.get("COINGECKO_API_KEY", "")
    if not cg_key:
        raise HTTPException(status_code=500, detail="COINGECKO_API_KEY not set")

    # 1. Resolve ticker across sources in parallel
    cg_resolve, llama_slug, chain_name = await asyncio.gather(
        resolve_token(req.token, cg_key),
        resolve_slug(req.token),
        resolve_chain_name(req.token),
    )
    if not cg_resolve:
        raise HTTPException(status_code=404, detail=f"Could not resolve token: {req.token}")

    # 2. Collect data in parallel
    async def get_tvl():
        # For L1/L2 chains, use chain TVL (has historical data for % changes)
        if chain_name:
            result = await collect_chain_tvl(chain_name)
            if result:
                return result
        # For DeFi protocols, use protocol TVL
        if llama_slug:
            return await collect_tvl(llama_slug)
        return None

    market_data, tvl_data = await asyncio.gather(
        collect_market_data(cg_resolve["coingecko_id"], cg_key),
        get_tvl(),
    )

    if not market_data:
        raise HTTPException(status_code=404, detail=f"No market data for: {cg_resolve['coingecko_id']}")

    # 3. Detect anomalies
    thresholds = load_thresholds()
    anomalies = detect(req.token, market_data, tvl_data=tvl_data, thresholds=thresholds)

    # 4. Generate headlines via Claude (only if anomalies exist)
    no_anomalies_msg = None
    if anomalies:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            headlines = await generate_headlines(anomalies, req.token, anthropic_key)
            for i, a in enumerate(anomalies):
                if i < len(headlines):
                    a["headline"] = headlines[i]
    else:
        no_anomalies_msg = "No significant anomalies. Price, TVL, and volume within normal ranges."

    # 5. Build response
    anomaly_models = [
        Anomaly(
            id=a["id"],
            severity=a["severity"],
            metric=a["metric"],
            change_pct=a["change_pct"],
            value_current=market_data.get("price_usd"),
            comparison_window=a["comparison_window"],
            headline=a["headline"],
            source=a["source"],
            raw_data=a["raw_data"],
            detected_at=a["detected_at"],
        )
        for a in anomalies
    ]

    return ScanResponse(
        token=req.token,
        resolved=ResolvedToken(
            coingecko_id=cg_resolve["coingecko_id"],
            defillama_slug=llama_slug,
            name=cg_resolve["name"],
        ),
        scanned_at=datetime.now(timezone.utc),
        market_context=MarketContext(
            price_usd=market_data.get("price_usd"),
            market_cap=market_data.get("market_cap"),
            volume_24h=market_data.get("volume_24h"),
            fdv=market_data.get("fdv"),
        ),
        anomalies=anomaly_models,
        no_anomalies_message=no_anomalies_msg,
    )
