#!/usr/bin/env python3

"""
Weekly LLM brand monitor.

Asks ChatGPT, Claude, Gemini, and Perplexity a fixed set of questions about
your business, has one of them synthesize the results into a structured
report, and posts that report to a Slack channel via an incoming webhook.

Only the providers you've set an API key for will run, so you can start with
one and add more later. Set the keys as environment variables:

    OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, PERPLEXITY_API_KEY
    SLACK_WEBHOOK_URL

If SLACK_WEBHOOK_URL is missing, the report is printed to the console instead
of posted (handy for local testing).
"""

import os
import re
import json
import datetime
import requests
import config

# ── Provider definitions ──────────────────────────────────────────────────
PROVIDERS = {
    "openai":     {"label": "ChatGPT (OpenAI)",   "env": "OPENAI_API_KEY",     "model": "gpt-5.5"},
    "anthropic":  {"label": "Claude (Anthropic)", "env": "ANTHROPIC_API_KEY",  "model": "claude-sonnet-4-6"},
    "gemini":     {"label": "Gemini (Google)",    "env": "GEMINI_API_KEY",     "model": "gemini-3.5-flash"},
    "perplexity": {"label": "Perplexity (Sonar)", "env": "PERPLEXITY_API_KEY", "model": "sonar-pro"},
}

MONITOR_SYSTEM = (
    "You are a helpful AI assistant responding to an ordinary consumer. "
    "Answer the question directly and naturally, the way you would for any user."
)

TIMEOUT = 120

def postjson(url, headers, payload):
    r = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

# ── One function per API ────────────────────────────────────────────────────
def call_openai(model, system, user):
    data = postjson(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
         "Content-Type": "application/json"},
        {"model": model,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}],
         "max_completion_tokens": 900},
    )
    return data["choices"][0]["message"]["content"]

def call_perplexity(model, system, user):
    data = postjson(
        "https://api.perplexity.ai/chat/completions",
        {"Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
         "Content-Type": "application/json"},
        {"model": model,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
    )
    return data["choices"][0]["message"]["content"]

def call_anthropic(model, system, user):
    data = postjson(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"],
         "anthropic-version": "2023-06-01",
         "Content-Type": "application/json"},
        {"model": model, "max_tokens": 900, "system": system,
         "messages": [{"role": "user", "content": user}]},
    )
    return "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text")

def call_gemini(model, system, user):
    key = os.environ["GEMINI_API_KEY"]
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    data = postjson(
        url, {"Content-Type": "application/json"},
        {"system_instruction": {"parts": [{"text": system}]},
         "contents": [{"role": "user", "parts": [{"text": user}]}]},
    )
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if "text" in p)

DISPATCH = {
    "openai": call_openai,
    "anthropic": call_anthropic,
    "gemini": call_gemini,
    "perplexity": call_perplexity,
}

def query(provider, system, user):
    return DISPATCH[provider](PROVIDERS[provider]["model"], system, user)

def enabled_providers():
    return [p for p in PROVIDERS if os.getenv(PROVIDERS[p]["env"])]

# ── Step 1: collect raw answers ────────────────────────────────────────────
def collect_answers(providers):
    results = {}
    for p in providers:
        label = PROVIDERS[p]["label"]
        results[p] = []
        for prompt in config.PROMPTS:
            print(f"  [{label}] {prompt[:60]}...")
            try:
                answer = query(p, MONITOR_SYSTEM, prompt).strip()
            except Exception as e:
                answer = f"[ERROR contacting {label}: {e}]"
            results[p].append({"prompt": prompt, "answer": answer})
    return results

# ── Step 2: synthesize into a structured report ────────────────────────────
SYNTH_SYSTEM = (
    "You are a brand-monitoring analyst. You review how AI assistants describe "
    "a business and report findings precisely and honestly. Return only JSON."
)

SYNTH_TEMPLATE = """Analyze how several AI assistants answered questions about "{brand}".

TRUE FACTS (use these to spot mistakes the assistants make):

{truth}

COMPETITORS to watch for being recommended:

{competitors}

Below are the raw answers, grouped by assistant.

{transcript}

Return ONLY a JSON object with exactly this shape:

{{
  "overall_summary": "2-3 sentence plain-English summary of how {brand} is represented across all assistants this week",
  "overall_sentiment": "positive | neutral | mixed | negative",
  "share_of_voice": "1-2 sentences on whether {brand} gets recommended UNPROMPTED when asked generic 'which dealer' questions",
  "models": [
    {{
      "name": "assistant label",
      "recommended": true,
      "sentiment": "positive | neutral | mixed | negative",
      "key_points": ["short bullets of what it actually said about the brand"],
      "inaccuracies": ["anything it got wrong vs the true facts; empty list if none"],
      "competitors_mentioned": ["competitor names it brought up"]
    }}
  ],
  "action_items": ["concrete things the business could do this week to improve how it shows up, e.g. fix a wrong fact on a specific platform"]
}}

No prose, no markdown fences — JSON only."""

def build_transcript(results):
    chunks = []
    for p, items in results.items():
        chunks.append(f"=== {PROVIDERS[p]['label']} ===")
        for it in items:
            ans = it["answer"]
            if len(ans) > 1500:
                ans = ans[:1500] + " [...truncated]"
            chunks.append(f"Q: {it['prompt']}\nA: {ans}\n")
    return "\n".join(chunks)

def parse_json_lenient(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)

def synthesize(results, providers):
    synth_provider = next((p for p in config.SYNTH_PREFERENCE if p in providers),
                          providers[0])
    user = SYNTH_TEMPLATE.format(
        brand=config.BRAND_NAME,
        truth=config.GROUND_TRUTH.strip(),
        competitors=", ".join(config.COMPETITORS),
        transcript=build_transcript(results),
    )
    raw = query(synth_provider, SYNTH_SYSTEM, user)
    return parse_json_lenient(raw)

# ── Step 3: format for Slack ───────────────────────────────────────────────
SENTIMENT_ICON = {"positive": "🟢", "neutral": "🟡", "mixed": "🟡", "negative": "🔴"}

def _trunc(s, n=2900):
    return s if len(s) <= n else s[:n - 1] + "..."

def build_slack_blocks(report, date_str):
    icon = SENTIMENT_ICON.get(str(report.get("overall_sentiment", "")).lower(), "⚪")
    blocks = [
        {"type": "header",
         "text": {"type": "plain_text",
                  "text": f"{config.BRAND_NAME} — Weekly LLM Report"}},
        {"type": "context",
         "elements": [{"type": "mrkdwn", "text": f"Week of {date_str}"}]},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": _trunc(
                      f"{icon} Overall: {report.get('overall_summary', 'n/a')}\n\n"
                      f"*Sentiment:* {report.get('overall_sentiment', 'n/a')}\n"
                      f"*Share of voice:* {report.get('share_of_voice', 'n/a')}")}},
        {"type": "divider"},
    ]
    for m in report.get("models", []):
        rec = "✅ recommends you" if m.get("recommended") else "➖ does not recommend you"
        sent = SENTIMENT_ICON.get(str(m.get("sentiment", "")).lower(), "⚪")
        lines = [f"*{m.get('name', 'Assistant')}*  {sent}  {rec}"]
        if m.get("key_points"):
            lines.append("\n".join(f"• {kp}" for kp in m["key_points"][:4]))
        if m.get("inaccuracies"):
            lines.append("⚠️ Got wrong: " + "; ".join(m["inaccuracies"][:4]))
        if m.get("competitors_mentioned"):
            lines.append("_Also mentioned:_ " + ", ".join(m["competitors_mentioned"][:6]))
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn", "text": _trunc("\n".join(lines))}})
    actions = report.get("action_items", [])
    if actions:
        blocks.append({"type": "divider"})
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn",
                                "text": _trunc("*This week's action items*\n" +
                                               "\n".join(f"• {a}" for a in actions[:8]))}})
    return blocks

def post_to_slack(blocks, fallback_text):
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    payload = {"text": fallback_text, "blocks": blocks}
    if not webhook:
        print("\n[no SLACK_WEBHOOK_URL set — printing payload instead]\n")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    r = requests.post(webhook, json=payload, timeout=30)
    r.raise_for_status()
    print("Posted report to Slack.")

def fallback_blocks(results, date_str, error):
    lines = [f"*{config.BRAND_NAME} — Weekly LLM Report* (week of {date_str})",
             f"_Summary step failed ({error}); showing raw first answers._"]
    for p, items in results.items():
        first = items[0]["answer"] if items else ""
        lines.append(f"\n*{PROVIDERS[p]['label']}* — {items[0]['prompt']}\n{first[:400]}")
    text = _trunc("\n".join(lines))
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}], text

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    providers = enabled_providers()
    if not providers:
        raise SystemExit(
            "No API keys found. Set at least one of: "
            + ", ".join(PROVIDERS[p]["env"] for p in PROVIDERS))
    date_str = datetime.date.today().strftime("%b %d, %Y")
    print(f"Running weekly report for {config.BRAND_NAME} "
          f"({len(providers)} assistant(s), {len(config.PROMPTS)} prompts each)...")
    results = collect_answers(providers)
    try:
        report = synthesize(results, providers)
        blocks = build_slack_blocks(report, date_str)
        fallback = f"{config.BRAND_NAME} weekly LLM report — {report.get('overall_summary', '')}"
    except Exception as e:
        print(f"Synthesis failed: {e}")
        blocks, fallback = fallback_blocks(results, date_str, e)
    post_to_slack(blocks, fallback)

if __name__ == "__main__":
    main()
