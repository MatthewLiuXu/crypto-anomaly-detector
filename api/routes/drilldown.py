import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.models import DrilldownRequest, DrilldownResponse
from synthesis.drilldown import generate_drilldown

router = APIRouter()


@router.post("/drilldown", response_model=DrilldownResponse)
async def drilldown(req: DrilldownRequest):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")

    result = await generate_drilldown(req.token, req.anomaly, api_key)

    return DrilldownResponse(
        analysis=result["analysis"],
        signal=result["signal"],
        signal_reason=result["signal_reason"],
        generated_at=datetime.now(timezone.utc),
    )
