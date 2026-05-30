#!/usr/bin/env python3
"""
AI Newsletter Agent — personalized weekly AI digest.
Fetches content from newsletters, YouTube, and LinkedIn thought leaders,
summarises with an LLM, and emails a Markdown digest every Monday morning.

LLM_BACKEND options (set in .env):
  anthropic  — Claude Sonnet. Needs ANTHROPIC_API_KEY (~$0.01/run).
  groq       — llama-3.3-70b via Groq. Free tier, no credit card.
  ollama     — any local model via Ollama. Fully offline, no API key.

Usage:
  python3 newsletter.py            # run once now
  python3 newsletter.py --daemon   # stay running, fire every Monday 08:00
"""

import os, re, ssl, sys, smtplib, time, argparse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import certifi, markdown2, requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from dotenv import load_dotenv

load_dotenv()

# Fix macOS SSL cert lookup so ddgs/requests can reach HTTPS sites.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

# ── Sources ───────────────────────────────────────────────────────────────────

NEWSLETTERS = [
    {
        "name": "The Rundown AI",
        "query": '"The Rundown AI" newsletter',
        "archive": "https://www.therundown.ai/archive",
    },
    {
        "name": "Ben's Bites",
        "query": '"Ben\'s Bites" OR "bensbites" AI newsletter',
        "archive": "https://www.bensbites.com/archive",
    },
    {
        "name": "AI Breakfast",
        "query": '"AI Breakfast" newsletter AI',
        "archive": "https://aibreakfast.beehiiv.com/archive",
    },
    {
        "name": "Morning Brew AI",
        "query": '"Morning Brew" AI artificial intelligence news',
        "archive": None,
    },
]

YOUTUBE_CHANNELS = [
    {
        "name": "Matt Wolfe",
        "query": '"Matt Wolfe" YouTube AI tools 2025 OR 2026',
        "rss_id": None,
    },
    {
        "name": "All-In Podcast",
        "query": '"All-In Podcast" AI 2025 OR 2026',
        "rss_id": "UCESLZhusAkFfsNsApnjF_Cg",
    },
]

THOUGHT_LEADERS = [
    {
        "name": "Andrew Ng",
        "query": '"Andrew Ng" AI 2025 OR 2026',
    },
    {
        "name": "Sam Altman",
        "query": '"Sam Altman" OpenAI AI 2025 OR 2026',
    },
    {
        "name": "Andrej Karpathy",
        "query": '"Andrej Karpathy" AI 2025 OR 2026',
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# ── Fetchers ──────────────────────────────────────────────────────────────────

def ddg_search(query: str, source_name: str, max_results: int = 5) -> list[dict]:
    """Search DuckDuckGo (last month), with one retry on failure."""
    items = []
    for attempt in range(2):
        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, timelimit="m", max_results=max_results)
                for r in results or []:
                    items.append({
                        "source": source_name,
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")[:800],
                    })
            time.sleep(0.6)
            break
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
            else:
                print(f"    [WARN] search({source_name}): {e}")
    return items


def scrape_archive(url: str, source_name: str, max_items: int = 4) -> list[dict]:
    """Scrape a beehiiv-style archive page for recent issue links."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.find_all("a", href=re.compile(r"/p/"))
        seen, items = set(), []
        for link in links:
            href = link["href"]
            if href in seen or len(items) >= max_items:
                continue
            seen.add(href)
            title = link.get_text(strip=True) or link.get("title", "")
            if not title:
                continue
            base = f"https://{url.split('/')[2]}"
            full_url = href if href.startswith("http") else base + href
            items.append({"source": source_name, "title": title, "url": full_url, "snippet": ""})
        return items
    except Exception as e:
        print(f"    [WARN] archive({source_name}): {e}")
        return []


def fetch_youtube_rss(channel_id: str, channel_name: str) -> list[dict]:
    """Fetch recent videos from a YouTube channel's public RSS feed."""
    import feedparser
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        feed = feedparser.parse(url)
        return [
            {
                "source": channel_name,
                "title": e.get("title", ""),
                "url": e.get("link", ""),
                "snippet": e.get("summary", "")[:500],
            }
            for e in feed.entries[:4]
        ]
    except Exception as e:
        print(f"    [WARN] yt-rss({channel_name}): {e}")
        return []


def fetch_all_sources() -> dict[str, list[dict]]:
    collected: dict[str, list[dict]] = {"newsletters": [], "youtube": [], "thought_leaders": []}

    print("  Newsletters...")
    for src in NEWSLETTERS:
        items = scrape_archive(src["archive"], src["name"]) if src.get("archive") else []
        if not items:
            items = ddg_search(src["query"], src["name"])
        print(f"    {src['name']}: {len(items)} item(s)")
        collected["newsletters"].extend(items)

    print("  YouTube channels...")
    for ch in YOUTUBE_CHANNELS:
        items = fetch_youtube_rss(ch["rss_id"], ch["name"]) if ch.get("rss_id") else []
        if not items:
            items = ddg_search(ch["query"], ch["name"])
        print(f"    {ch['name']}: {len(items)} item(s)")
        collected["youtube"].extend(items)

    print("  Thought leaders...")
    for leader in THOUGHT_LEADERS:
        items = ddg_search(leader["query"], leader["name"])
        print(f"    {leader['name']}: {len(items)} item(s)")
        collected["thought_leaders"].extend(items)

    return collected

# ── LLM backends ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are an expert AI industry analyst writing a personalized weekly newsletter. "
    "Your reader closely follows AI — they want signal, not noise. "
    "Write with clarity, sharp insight, and light enthusiasm. "
    "Avoid filler phrases. Lead with what actually matters."
)

def _user_prompt(content_block: str) -> str:
    week_str = datetime.now().strftime("%B %d, %Y")
    return f"""Here is raw AI content collected from the past ~30 days. Focus on the most recent and significant developments:

{content_block}

Write a polished Monday-morning AI newsletter digest for {week_str}. Use this exact structure:

# Your AI Week in Review — {week_str}

## TL;DR
5 bullet points. One punchy sentence each. Cover only the biggest stories.

## This Week in AI
3–4 short sections, each with a **bold heading**. 2–3 sentences per section. Explain the *significance*, not just the event.

## From the Feeds
Highlight the single most valuable newsletter issue or YouTube video. 2 sentences on why it's worth it. Include the URL.

## Thought Leaders
What are Andrew Ng, Sam Altman, and Andrej Karpathy thinking or doing lately? 1–2 sentences per person. Skip anyone with no meaningful results.

## One Thing to Try
One concrete, actionable suggestion based on this week's content.

---
Keep the total under 650 words. Be direct. No filler. Format cleanly in Markdown."""


def _format_items(items: list[dict]) -> str:
    if not items:
        return "(no results)\n"
    out = ""
    for item in items:
        if not item.get("title") and not item.get("snippet"):
            continue
        out += f"\n---\nSOURCE: {item['source']}\nTITLE: {item['title']}\nURL: {item['url']}\n"
        if item.get("snippet"):
            out += f"SNIPPET: {item['snippet']}\n"
    return out


def _build_content_block(collected: dict) -> str:
    return (
        "=== NEWSLETTERS ===\n" + _format_items(collected["newsletters"]) +
        "\n=== YOUTUBE ===\n" + _format_items(collected["youtube"]) +
        "\n=== THOUGHT LEADERS ===\n" + _format_items(collected["thought_leaders"])
    )


def _llm_anthropic(prompt: str) -> str:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _llm_groq(prompt: str) -> str:
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    chat = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2048,
        temperature=0.6,
    )
    return chat.choices[0].message.content


def _llm_ollama(prompt: str) -> str:
    """Call a local Ollama instance (must be running: `ollama serve`)."""
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    resp = requests.post(
        f"{base_url}/api/chat",
        json={
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def build_newsletter(collected: dict) -> str:
    total = sum(len(v) for v in collected.values())
    if total == 0:
        return "# AI Week in Review\n\nNo content fetched this week. Check your network and try again."

    content_block = _build_content_block(collected)
    prompt = _user_prompt(content_block)

    backend = os.getenv("LLM_BACKEND", "anthropic").lower()
    generators = {"anthropic": _llm_anthropic, "groq": _llm_groq, "ollama": _llm_ollama}

    if backend not in generators:
        sys.exit(f"Unknown LLM_BACKEND '{backend}'. Choose: anthropic, groq, ollama")

    print(f"  Using backend: {backend}")
    return generators[backend](prompt)


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(subject: str, body_md: str):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("RECIPIENT_EMAIL", gmail_user)

    html_body = markdown2.markdown(
        body_md, extras=["break-on-newline", "cuddled-lists", "fenced-code-blocks"]
    )
    html = f"""<html>
<head><meta charset="utf-8"><style>
  body {{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
         max-width:620px;margin:40px auto;padding:0 16px;color:#1a1a1a;line-height:1.65}}
  h1 {{font-size:1.45em;border-bottom:3px solid #0066cc;padding-bottom:10px;margin-bottom:20px}}
  h2 {{font-size:1.05em;color:#222;margin-top:28px;margin-bottom:6px;
       text-transform:uppercase;letter-spacing:.04em}}
  ul {{padding-left:20px}} li {{margin-bottom:7px}}
  a {{color:#0066cc;text-decoration:none}} a:hover {{text-decoration:underline}}
  hr {{border:none;border-top:1px solid #e0e0e0;margin:28px 0}} p {{margin:8px 0}}
  strong {{color:#111}}
</style></head>
<body>{html_body}
<hr><p style="color:#888;font-size:.8em">
  AI Newsletter Agent · Sent to {recipient}
</p></body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"AI Newsletter <{gmail_user}>"
    msg["To"] = recipient
    msg.attach(MIMEText(body_md, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_user, gmail_password)
        smtp.sendmail(gmail_user, recipient, msg.as_string())
    print(f"  Email sent → {recipient}")


# ── Core run ──────────────────────────────────────────────────────────────────

def validate_env():
    backend = os.getenv("LLM_BACKEND", "anthropic").lower()
    required_keys = {
        "anthropic": ["ANTHROPIC_API_KEY"],
        "groq":      ["GROQ_API_KEY"],
        "ollama":    [],  # Ollama is local, no key needed
    }
    base_required = ["GMAIL_USER", "GMAIL_APP_PASSWORD"]
    missing = [k for k in base_required + required_keys.get(backend, []) if not os.getenv(k)]
    if missing:
        sys.exit(
            f"Missing env vars: {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in the values."
        )


def run_once():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[{ts}] AI Newsletter Agent — starting run...")
    validate_env()

    print("Fetching content...")
    collected = fetch_all_sources()
    total = sum(len(v) for v in collected.values())
    print(f"Collected {total} items.")

    print("Generating newsletter...")
    newsletter_md = build_newsletter(collected)

    week_str = datetime.now().strftime("%B %d, %Y")
    subject = f"Your AI Week in Review — {week_str}"

    print("Sending email...")
    send_email(subject, newsletter_md)

    archive_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "newsletters")
    os.makedirs(archive_dir, exist_ok=True)
    path = os.path.join(archive_dir, f"{datetime.now().strftime('%Y-%m-%d')}.md")
    with open(path, "w") as f:
        f.write(newsletter_md)
    print(f"  Archived → {path}")
    print("Done!")


# ── Daemon mode (cross-platform scheduler) ────────────────────────────────────

def run_daemon():
    """Stay alive and fire every Monday at 08:00 local time. Works on any OS."""
    import schedule
    print("Daemon mode: will run every Monday at 08:00. Press Ctrl+C to stop.")
    schedule.every().monday.at("08:00").do(run_once)

    # Run immediately on first start if today is Monday and it hasn't run yet.
    if datetime.now().weekday() == 0:
        print("Today is Monday — running now...")
        run_once()

    while True:
        schedule.run_pending()
        time.sleep(30)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Newsletter Agent")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Stay running and fire every Monday at 08:00 (cross-platform alternative to cron/launchd)",
    )
    args = parser.parse_args()

    if args.daemon:
        run_daemon()
    else:
        run_once()
