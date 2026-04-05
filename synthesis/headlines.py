import json
import anthropic

SYSTEM_PROMPT = """You are writing anomaly alert headlines for a crypto hedge fund terminal.

For each anomaly, write exactly 1-2 sentences using the raw data provided.
- Include specific numbers from the data
- State what happened, not what it means
- If news context is available and directly relevant, include the catalyst
- Never use filler phrases like "it's worth noting" or "interestingly"
- Never speculate on cause unless the data directly supports it

Return ONLY a JSON array of headline strings, one per anomaly, same order as input.
No other text. No markdown fences. Just the JSON array."""


async def generate_headlines(anomalies: list[dict], token: str, api_key: str) -> list[str]:
    """
    Send all anomalies to Claude in a single batch call.
    Returns a list of headline strings, one per anomaly, same order.
    """
    user_content = json.dumps({
        "token": token,
        "anomalies": [
            {
                "metric": a["metric"],
                "severity": a["severity"],
                "change_pct": a["change_pct"],
                "comparison_window": a["comparison_window"],
                "source": a["source"],
                "raw_data": a["raw_data"],
            }
            for a in anomalies
        ],
    }, indent=2)

    client = anthropic.AsyncAnthropic(api_key=api_key)
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    text = message.content[0].text
    return json.loads(text)
