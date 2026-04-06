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

    # Extract signal tag from the analysis and remove signal lines from the text
    signal = None
    signal_reason = None
    signal_line_idx = None
    lines = text.split("\n")
    for i, line in enumerate(lines):
        upper = line.upper()
        for tag in ["ACCUMULATE", "MONITOR", "REDUCE", "IGNORE"]:
            if f"SIGNAL: {tag}" in upper or f"SIGNAL:{tag}" in upper:
                signal = tag
                signal_line_idx = i
                # Reason is rest of text after the tag
                after = line.split(tag, 1)
                if len(after) > 1 and after[1].strip().strip("*").strip():
                    signal_reason = after[1].strip().strip("*").strip().strip("—").strip("-").strip()
                break
        if signal:
            break

    # Strip the signal line (and any trailing reason line) from the analysis body
    if signal_line_idx is not None:
        # Remove from signal line onward (signal is always at the end)
        lines = lines[:signal_line_idx]

    # Remove trailing "### Signal" heading and "---" separator (frontend renders these)
    while lines and lines[-1].strip() in ("", "---"):
        lines.pop()
    if lines and lines[-1].strip().lower() in ("### signal", "## signal"):
        lines.pop()
    while lines and lines[-1].strip() in ("", "---"):
        lines.pop()

    # Also check if signal_reason wasn't on the same line but on the next line
    if signal and not signal_reason and signal_line_idx is not None:
        remaining = text.split("\n")[signal_line_idx + 1:]
        for line in remaining:
            stripped = line.strip().strip("*").strip("—").strip("-").strip()
            if stripped:
                signal_reason = stripped
                break

    return {
        "analysis": "\n".join(lines).strip(),
        "signal": signal,
        "signal_reason": signal_reason,
    }
