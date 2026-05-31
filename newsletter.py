#!/usr/bin/env python3
"""
AI Newsletter Agent — AGENTIC edition.

The LLM drives the entire research process via a ReAct loop:
  - Decides what to search for each week
  - Follows up on interesting stories
  - Fetches full article content when snippets aren't enough
  - Decides when it has enough to write
  - Writes and sends the newsletter itself

Tools available to the agent:
  search_web     — DuckDuckGo search (no API key, last month)
  fetch_page     — read the full text of any URL
  send_newsletter — write and deliver the final digest

LLM_BACKEND:
  anthropic  — Claude Sonnet. Best for agentic reasoning. ~$0.05/run.
  groq       — llama-3.3-70b via Groq. Free tier. Good quality.

Usage:
  python3 newsletter.py            # run once now
  python3 newsletter.py --daemon   # stay running, fire every Monday 08:00
"""

import os, re, sys, json, smtplib, time, argparse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import certifi, markdown2, requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

MAX_ITERATIONS = 20   # hard cap on agent loop turns
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# ── Tool implementations ───────────────────────────────────────────────────────

def _search_web(query: str, max_results: int = 5) -> str:
    """DuckDuckGo search scoped to the last month."""
    try:
        with DDGS() as ddgs:
            raw = ddgs.text(query, timelimit="m", max_results=min(max_results, 10))
            results = list(raw or [])
        time.sleep(0.5)
    except Exception as e:
        return f"Search error: {e}"

    if not results:
        return "No results found for that query."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. {r.get('title','')}\n"
            f"   URL: {r.get('href','')}\n"
            f"   {r.get('body','')[:400]}"
        )
    return "\n\n".join(lines)


def _fetch_page(url: str) -> str:
    """Fetch and clean the main text of a webpage."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:5000]
    except Exception as e:
        return f"Could not fetch page: {e}"


# The agent writes the newsletter by calling this tool.
# We store it here and send it after the loop exits.
_pending: dict = {}

def _send_newsletter(subject: str, body: str) -> str:
    _pending["subject"] = subject
    _pending["body"] = body
    return "Newsletter queued — research session complete."


def execute_tool(name: str, args: dict) -> str:
    dispatch = {
        "search_web":      lambda: _search_web(args.get("query", ""), args.get("max_results", 5)),
        "fetch_page":      lambda: _fetch_page(args.get("url", "")),
        "send_newsletter": lambda: _send_newsletter(args.get("subject", ""), args.get("body", "")),
    }
    fn = dispatch.get(name)
    return fn() if fn else f"Unknown tool: {name}"


# ── Tool schemas ───────────────────────────────────────────────────────────────

# Anthropic native format
TOOLS_ANTHROPIC = [
    {
        "name": "search_web",
        "description": (
            "Search the web for recent AI news, articles, YouTube videos, and posts. "
            "Covers the past month. Run multiple targeted searches — one broad, then "
            "specific follow-ups on stories that matter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string", "description": "Search query. Be specific."},
                "max_results": {"type": "integer", "description": "Results to return (1–10). Default 5.", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_page",
        "description": (
            "Fetch the full text of a webpage. Use when a search snippet isn't enough "
            "to understand a story — read the full article, newsletter issue, or post."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to fetch."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "send_newsletter",
        "description": (
            "Write and send the completed newsletter. Call this once you have researched "
            "enough (aim for 8–15 searches). This ends the research session."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Email subject line."},
                "body":    {"type": "string", "description": "Full newsletter in Markdown."},
            },
            "required": ["subject", "body"],
        },
    },
]

# OpenAI-compatible format (Groq)
TOOLS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name":        t["name"],
            "description": t["description"],
            "parameters":  t["input_schema"],
        },
    }
    for t in TOOLS_ANTHROPIC
]


# ── System prompt ──────────────────────────────────────────────────────────────

def system_prompt() -> str:
    today = datetime.now().strftime("%A, %B %d, %Y")
    week_label = datetime.now().strftime("%B %d, %Y")
    return f"""You are an expert AI industry analyst and newsletter curator. Today is {today}.

Every Monday morning you research the past week's AI developments and write a sharp digest.
Your reader closely follows AI — they want signal, not noise.

━━ YOUR RESEARCH PROCESS ━━
1. Start with a broad search: "AI news this week" or "biggest AI announcements {today[:4]}"
2. Dig into preferred sources: The Rundown AI, Ben's Bites, AI Breakfast, Morning Brew AI
3. Search for recent YouTube content from Matt Wolfe and All-In Podcast
4. Search for posts and insights from Andrew Ng, Sam Altman, Andrej Karpathy
5. When you find something important or surprising → fetch the full page for details
6. Follow interesting threads: if a model launched, search for reactions and benchmarks
7. After 8–15 searches, when you have a clear picture → call send_newsletter

━━ NEWSLETTER FORMAT (use exactly) ━━
# Your AI Week in Review — {week_label}

## TL;DR
- [bullet 1]
- [bullet 2]
- [bullet 3]
- [bullet 4]
- [bullet 5]
(5 bullets, one punchy sentence each, biggest stories only)

## This Week in AI
**[Theme heading]**
[2–3 sentences explaining what happened and why it matters]

(repeat for 3–4 themes)

## From the Feeds
[Highlight the single most valuable newsletter issue or YouTube video. 2 sentences + URL.]

## Thought Leaders
**Andrew Ng:** [1–2 sentences]
**Sam Altman:** [1–2 sentences]
**Andrej Karpathy:** [1–2 sentences]
(skip anyone with no meaningful results this week)

## One Thing to Try
[One concrete, actionable recommendation based on this week's content]

━━ STYLE ━━
Under 700 words total. Direct. No filler. Explain significance not just events."""


# ── Agentic loops ──────────────────────────────────────────────────────────────

def _log_tool_call(name: str, args: dict):
    preview = args.get("query") or args.get("url") or args.get("subject") or ""
    print(f"    ↳ {name}({preview[:70]})")


def _force_send_prompt() -> str:
    return (
        "You have used your full research budget. "
        "Call send_newsletter now with the best newsletter you can write from what you have gathered."
    )


def _run_anthropic() -> bool:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    messages = [{"role": "user", "content": "Research and send this week's AI newsletter."}]
    forced = False

    for turn in range(MAX_ITERATIONS + 1):
        # On the final turn, force the agent to send whatever it has
        if turn == MAX_ITERATIONS and not _pending:
            print(f"  [Agent] Hit {MAX_ITERATIONS}-turn limit — forcing send.")
            messages.append({"role": "user", "content": _force_send_prompt()})
            forced = True

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt(),
            tools=TOOLS_ANTHROPIC,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        # Log agent's text commentary
        for block in response.content:
            if hasattr(block, "text") and block.text.strip():
                snippet = block.text.strip().replace("\n", " ")
                print(f"  [Agent] {snippet[:140]}{'...' if len(snippet) > 140 else ''}")

        if response.stop_reason == "end_turn":
            break

        # Execute tool calls
        tool_results, newsletter_sent = [], False
        for block in response.content:
            if block.type != "tool_use":
                continue
            _log_tool_call(block.name, block.input)
            result = execute_tool(block.name, block.input)
            if block.name == "send_newsletter":
                newsletter_sent = True
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

        if newsletter_sent or forced:
            break

    return bool(_pending)


def _extract_failed_gen(exc: Exception) -> str:
    """Pull 'failed_generation' text out of a Groq 400 error, if present."""
    raw = getattr(exc, "response", None)
    if raw is None:
        return ""
    try:
        return raw.json().get("error", {}).get("failed_generation", "")
    except Exception:
        return ""


def _run_groq() -> bool:
    """
    Two-phase Groq agent.

    Phase 1 — Research only (send_newsletter hidden from the model).
              Catches the case where the model skips to writing early —
              that content is saved as the newsletter draft.

    Phase 2 — Write: fresh lean context (tool results only, no chat history).
              Forces send_newsletter; falls back to capturing plain-text output
              if the model still won't use the tool.
    """
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    model  = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    week_label = datetime.now().strftime("%B %d, %Y")

    research_tools = [t for t in TOOLS_OPENAI if t["function"]["name"] != "send_newsletter"]

    messages: list[dict] = [
        {"role": "system", "content": system_prompt()},
        {
            "role": "user",
            "content": (
                "Research this week's AI news using search_web and fetch_page. "
                "Cover: The Rundown AI, Ben's Bites, AI Breakfast, Morning Brew AI, "
                "Matt Wolfe, All-In Podcast, Andrew Ng, Sam Altman, Andrej Karpathy. "
                "Do 8–12 searches. Only call tools — do not write the newsletter yet."
            ),
        },
    ]

    # ── Phase 1: research ──────────────────────────────────────────────────
    print("  [Phase 1] Researching...")
    for _turn in range(MAX_ITERATIONS):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=research_tools,
                tool_choice="auto",
                max_tokens=2048,
            )
        except Exception as e:
            # Model jumped ahead and tried to write the newsletter.
            # Grab it from failed_generation and short-circuit to send.
            draft = _extract_failed_gen(e)
            if draft and len(draft) > 300:
                print("  [Agent] Model wrote newsletter early — capturing and sending.")
                _send_newsletter(f"Your AI Week in Review — {week_label}", draft)
                return True
            print(f"  [WARN] Phase 1 API error: {e}")
            break

        msg = response.choices[0].message

        assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if msg.content and msg.content.strip():
            snippet = msg.content.strip().replace("\n", " ")
            print(f"  [Agent] {snippet[:140]}{'...' if len(snippet) > 140 else ''}")

        if not msg.tool_calls:
            print("  [Agent] Research complete.")
            break

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            _log_tool_call(tc.function.name, args)
            result = execute_tool(tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    if _pending:          # newsletter already captured from an early draft
        return True

    # ── Phase 2: write — fresh lean context ───────────────────────────────
    print("  [Phase 2] Writing newsletter...")

    # Use only tool results — skip the full chat history to save token budget.
    research_block = "\n\n---\n\n".join(
        m["content"] for m in messages
        if m.get("role") == "tool" and m.get("content")
    )

    write_messages = [
        {"role": "system", "content": system_prompt()},
        {
            "role": "user",
            "content": (
                f"Here is your research for this week:\n\n{research_block}\n\n"
                f"Call send_newsletter with the complete Markdown newsletter "
                f"(follow the format in your instructions). "
                f"Subject: 'Your AI Week in Review — {week_label}'"
            ),
        },
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=write_messages,
            tools=TOOLS_OPENAI,
            tool_choice={"type": "function", "function": {"name": "send_newsletter"}},
            max_tokens=4096,
        )
        msg = response.choices[0].message
        if msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.function.name == "send_newsletter":
                    args = json.loads(tc.function.arguments)
                    _log_tool_call(tc.function.name, args)
                    execute_tool(tc.function.name, args)

    except Exception as e:
        draft = _extract_failed_gen(e)
        if draft and len(draft) > 300:
            print("  [Agent] Captured newsletter from model text output.")
            _send_newsletter(f"Your AI Week in Review — {week_label}", draft)
        else:
            print(f"  [WARN] Phase 2 failed: {e}")

    return bool(_pending)


# ── Email delivery ─────────────────────────────────────────────────────────────

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
<hr><p style="color:#888;font-size:.8em">AI Newsletter Agent · {recipient}</p>
</body></html>"""

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


# ── Entry point ────────────────────────────────────────────────────────────────

def validate_env():
    backend = os.getenv("LLM_BACKEND", "groq").lower()
    required = {"anthropic": ["ANTHROPIC_API_KEY"], "groq": ["GROQ_API_KEY"]}
    missing = [
        k for k in ["GMAIL_USER", "GMAIL_APP_PASSWORD"] + required.get(backend, [])
        if not os.getenv(k)
    ]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}\nFill in .env and retry.")
    if backend not in ("anthropic", "groq"):
        sys.exit(f"LLM_BACKEND '{backend}' not supported in agentic mode. Use: anthropic or groq")


def run_once():
    # Reset state for this run (important in daemon mode)
    _pending.clear()

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n[{ts}] AI Newsletter Agent — agentic run starting")
    validate_env()

    backend = os.getenv("LLM_BACKEND", "groq").lower()
    print(f"Backend : {backend}")
    print(f"Watching: The Rundown AI · Ben's Bites · AI Breakfast · Morning Brew")
    print(f"          Matt Wolfe · All-In Podcast · Andrew Ng · Sam Altman · Karpathy")
    print("─" * 56)

    runners = {"anthropic": _run_anthropic, "groq": _run_groq}
    success = runners[backend]()

    print("─" * 56)

    if not success:
        sys.exit("Agent finished without producing a newsletter. Check output above.")

    subject = _pending["subject"]
    body    = _pending["body"]

    print("Sending email...")
    send_email(subject, body)

    archive_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "newsletters")
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, f"{datetime.now().strftime('%Y-%m-%d')}.md")
    with open(archive_path, "w") as f:
        f.write(body)
    print(f"  Archived → {archive_path}")
    print("Done!\n")


def run_daemon():
    import schedule
    print("Daemon mode — will fire every Monday at 08:00. Ctrl+C to stop.")
    schedule.every().monday.at("08:00").do(run_once)
    if datetime.now().weekday() == 0:
        print("Today is Monday — running now...")
        run_once()
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Newsletter Agent (Agentic)")
    parser.add_argument("--daemon", action="store_true",
                        help="Stay running, fire every Monday at 08:00")
    args = parser.parse_args()
    run_daemon() if args.daemon else run_once()
