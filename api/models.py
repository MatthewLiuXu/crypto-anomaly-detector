from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ScanRequest(BaseModel):
    token: str


class ResolvedToken(BaseModel):
    coingecko_id: str
    defillama_slug: Optional[str] = None
    name: str


class MarketContext(BaseModel):
    price_usd: Optional[float] = None
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    fdv: Optional[float] = None


class Anomaly(BaseModel):
    id: str
    severity: str
    metric: str
    change_pct: Optional[float] = None
    value_current: Optional[float] = None
    value_comparison: Optional[float] = None
    comparison_window: str
    headline: Optional[str] = None
    source: str
    raw_data: dict
    detected_at: datetime


class ScanResponse(BaseModel):
    token: str
    resolved: ResolvedToken
    scanned_at: datetime
    market_context: MarketContext
    anomalies: list[Anomaly]
    no_anomalies_message: Optional[str] = None


class TrendingAnomaly(BaseModel):
    token: str
    severity: str
    metric: str
    change_pct: Optional[float] = None
    comparison_window: str
    source: str
    summary: str
    detected_at: datetime


class TrendingResponse(BaseModel):
    anomalies: list[TrendingAnomaly]
    scanned_tokens: int
    scanned_at: datetime


class DrilldownRequest(BaseModel):
    token: str
    anomaly: dict


class DrilldownResponse(BaseModel):
    analysis: str
    signal: Optional[str] = None
    signal_reason: Optional[str] = None
    generated_at: datetime
