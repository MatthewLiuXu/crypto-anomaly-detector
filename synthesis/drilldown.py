import json
import anthropic

SYSTEM_PROMPT = """You are a crypto research terminal for hedge fund analysts.
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
### Signal"""


async def generate_drilldown(token: str, anomaly: dict, api_key: str) -> dict:
    """
    Generate a structured drill-down analysis for a single anomaly.
    Returns dict with analysis markdown, signal tag, and signal reason.
    """
    user_content = json.dumps({
        "token": token,
        "anomaly": anomaly,
    }, indent=2)

    client = anthropic.AsyncAnthropic(api_key=api_key)
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": user_content}],
    )

    text = ""
    for block in message.content:
        if block.type == "text":
            text += block.text

    # Extract signal tag from the analysis
    signal = None
    signal_reason = None
    for line in text.split("\n"):
        upper = line.upper()
        for tag in ["ACCUMULATE", "MONITOR", "REDUCE", "IGNORE"]:
            if f"SIGNAL: {tag}" in upper or f"SIGNAL:{tag}" in upper:
                signal = tag
                # Reason is rest of text after the tag
                after = line.split(tag, 1)
                if len(after) > 1 and after[1].strip().strip("*").strip():
                    signal_reason = after[1].strip().strip("*").strip().strip("—").strip("-").strip()
                break
        if signal:
            break

    return {
        "analysis": text.strip(),
        "signal": signal,
        "signal_reason": signal_reason,
    }
