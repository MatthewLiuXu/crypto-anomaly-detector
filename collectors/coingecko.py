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
