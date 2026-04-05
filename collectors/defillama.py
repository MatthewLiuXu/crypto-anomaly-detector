import time

import httpx
from typing import Optional

LLAMA_BASE = "https://api.llama.fi"

# Cache this on startup: call once, reuse forever
_protocol_cache: list[dict] | None = None
_chain_cache: list[dict] | None = None


async def _load_protocols() -> list[dict]:
    global _protocol_cache
    if _protocol_cache is not None:
        return _protocol_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{LLAMA_BASE}/protocols")
        resp.raise_for_status()
        _protocol_cache = resp.json()
        return _protocol_cache


async def _load_chains() -> list[dict]:
    global _chain_cache
    if _chain_cache is not None:
        return _chain_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{LLAMA_BASE}/v2/chains")
        resp.raise_for_status()
        _chain_cache = resp.json()
        return _chain_cache


def _is_chain(ticker: str, chains: list[dict]) -> Optional[str]:
    """Check if ticker matches a chain's tokenSymbol. Returns chain name or None."""
    ticker_upper = ticker.upper()
    for c in chains:
        sym = c.get("tokenSymbol") or ""
        if sym.upper() == ticker_upper:
            return c.get("name")
    return None


async def resolve_slug(ticker: str) -> Optional[str]:
    """Try to match a ticker to a DeFiLlama protocol slug.
    Skip foundations/orgs — prefer actual DeFi protocols."""
    protocols = await _load_protocols()
    ticker_upper = ticker.upper()
    # Exact symbol match first, skip non-protocol entries
    for p in protocols:
        if p.get("symbol", "").upper() == ticker_upper:
            slug = p.get("slug", "")
            # Skip foundations, orgs, and wrapped/staked variants
            if any(skip in slug for skip in ["foundation", "committee", "treasury"]):
                continue
            return slug
    return None


def _compute_change(tvl_history: list[dict], days: int) -> Optional[float]:
    """Compute % change from TVL time series over N days."""
    if not tvl_history or len(tvl_history) < 2:
        return None
    now_tvl = tvl_history[-1].get("totalLiquidityUSD", 0)
    if not now_tvl:
        return None
    target_ts = time.time() - (days * 86400)
    # Search all entries except the last (which is "current")
    candidates = tvl_history[:-1]
    best = min(candidates, key=lambda e: abs(e.get("date", 0) - target_ts))
    old_tvl = best.get("totalLiquidityUSD", 0)
    if not old_tvl:
        return None
    return round(((now_tvl - old_tvl) / old_tvl) * 100, 2)


async def collect_tvl(slug: str) -> Optional[dict]:
    """Pull TVL data for a protocol. Computes changes from history."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{LLAMA_BASE}/protocol/{slug}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        tvl_list = data.get("tvl", [])
        tvl_total = (
            tvl_list[-1].get("totalLiquidityUSD") if tvl_list else None
        )
        # Use API fields if available, otherwise compute from history
        change_1d = data.get("change_1d") or _compute_change(tvl_list, 1)
        change_7d = data.get("change_7d") or _compute_change(tvl_list, 7)
        return {
            "tvl_total": tvl_total,
            "change_1d": change_1d,
            "change_7d": change_7d,
            "chains": list(data.get("currentChainTvls", {}).keys()),
        }


async def collect_chain_tvl(chain_name: str) -> Optional[dict]:
    """Pull TVL for a chain (e.g., 'Ethereum', 'Sui').
    Uses /v2/historicalChainTvl/{chain} to compute changes."""
    chains = await _load_chains()
    # Verify chain exists
    found = False
    for c in chains:
        if c.get("name", "").upper() == chain_name.upper():
            found = True
            chain_name = c["name"]  # use canonical casing
            break
    if not found:
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{LLAMA_BASE}/v2/historicalChainTvl/{chain_name}")
        if resp.status_code != 200:
            return None
        history = resp.json()
        if not history:
            return None
        now_tvl = history[-1].get("tvl", 0)
        change_1d = _compute_pct(history, now_tvl, 1)
        change_7d = _compute_pct(history, now_tvl, 7)
        return {
            "tvl_total": now_tvl,
            "change_1d": change_1d,
            "change_7d": change_7d,
        }


def _compute_pct(history: list[dict], now_tvl: float, days: int) -> Optional[float]:
    if not now_tvl or not history or len(history) < 2:
        return None
    target_ts = time.time() - (days * 86400)
    # Search all entries except the last (which is "current")
    candidates = history[:-1]
    best = min(candidates, key=lambda e: abs(e.get("date", 0) - target_ts))
    old_tvl = best.get("tvl", 0)
    if not old_tvl:
        return None
    return round(((now_tvl - old_tvl) / old_tvl) * 100, 2)


async def resolve_chain_name(ticker: str) -> Optional[str]:
    """Check if a ticker corresponds to an L1/L2 chain. Returns chain name or None."""
    chains = await _load_chains()
    return _is_chain(ticker, chains)
