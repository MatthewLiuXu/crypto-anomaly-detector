import yaml
from datetime import datetime, timezone
from pathlib import Path


def load_thresholds() -> dict:
    path = Path(__file__).parent.parent / "config" / "thresholds.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def detect(
    token: str,
    market_data: dict,
    tvl_data: dict | None,
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

    # Sort by severity
    sev_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    anomalies.sort(key=lambda a: sev_order.get(a["severity"], 2))
    return anomalies


def _classify(value: float, tiers: dict) -> str | None:
    if value >= tiers["high"]:
        return "high"
    elif value >= tiers["medium"]:
        return "medium"
    elif value >= tiers["low"]:
        return "low"
    elif "info" in tiers and value >= tiers["info"]:
        return "info"
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
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
