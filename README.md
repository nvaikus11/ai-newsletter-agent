# AI Newsletter Agent

A truly **agentic** AI newsletter that researches and writes itself. Every Monday morning, an LLM autonomously searches the web, decides what's worth reading, fetches full articles on the biggest stories, and emails you a curated digest — no manual curation needed.

**Monitored sources:** The Rundown AI · Ben's Bites · AI Breakfast · Morning Brew AI · Matt Wolfe (YouTube) · All-In Podcast (YouTube) · Andrew Ng · Sam Altman · Andrej Karpathy

> **Why "agentic"?** Most newsletter tools fetch fixed sources and paste them into a template. This one gives the LLM a set of tools (`search_web`, `fetch_page`, `send_newsletter`) and lets it decide what to search for, which articles to read in full, and when it has enough to write. The queries, sources, and depth of research vary each week based on what's actually happening in AI.

---

## What you'll receive

```
Subject: Your AI Week in Review — June 2, 2026

## TL;DR
- Anthropic's Opus 4.8 outperforms GPT-5.5 on agentic benchmarks
- Apple rebuilds Siri on Google Gemini with a ChatGPT-style interface
- Andrej Karpathy joins Anthropic to lead pre-training research
- Sam Altman admits OpenAI "totally screwed up" the ChatGPT launch
- AI doubles developer output — but not equally across skill levels

## This Week in AI
**Anthropic Takes the Lead** ...
**Apple's AI-Powered Siri** ...
...

## From the Feeds   ## Thought Leaders   ## One Thing to Try
```

---

## Setup (~10 minutes)

### Step 1 — Check Python

```bash
python3 --version   # needs 3.10 or higher
```

If you don't have Python: [python.org/downloads](https://www.python.org/downloads/)

---

### Step 2 — Get a free LLM API key

Only **Groq** and **Anthropic** are supported. Groq is free and recommended.

| Option | Cost | Sign up |
|--------|------|---------|
| **Groq** ⭐ | Free forever | [console.groq.com](https://console.groq.com) → API Keys → Create key |
| Anthropic | ~$0.05/run | [console.anthropic.com](https://console.anthropic.com) → add $5 credit |

> **Groq model note:** The agent uses `meta-llama/llama-4-scout-17b-16e-instruct` by default. Do not change this — other Groq models do not support the tool-calling required for the agent to work.

---

### Step 3 — Get a Gmail App Password

The agent sends email via Gmail SMTP. This requires an **App Password** (not your regular Gmail password).

1. Enable **2-Step Verification** on your Google account at [myaccount.google.com](https://myaccount.google.com)
2. Go to **Security → App passwords**
3. Create one named `AI Newsletter`
4. Copy the **16-character code** — you'll need it in Step 5

---

### Step 4 — Clone the repo

```bash
git clone https://github.com/nvaikus11/ai-newsletter-agent.git
cd "ai-newsletter-agent"
```

---

### Step 5 — Configure `.env`

```bash
cp .env.example .env
```

Open `.env` in any text editor:

| OS | Command |
|----|---------|
| macOS | `open -e .env` |
| Windows | `notepad .env` |
| Linux | `nano .env` |

> **Note:** `.env` is a hidden file (starts with a dot). In macOS Finder press **⌘ Shift .** to show hidden files.

Fill in your values:

```
LLM_BACKEND=groq
GROQ_API_KEY=gsk_...            ← paste your Groq key
GMAIL_USER=you@gmail.com        ← the Gmail that sends the newsletter
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx  ← the 16-char App Password
RECIPIENT_EMAIL=you@gmail.com   ← where to deliver it (can be same or different)
```

---

### Step 6 — Install and run

```bash
bash setup.sh
```

This will:
1. Install all Python dependencies
2. Ask you to confirm your `.env` is filled in
3. Schedule the agent to run every **Monday at 08:00** automatically
4. Offer to send a test newsletter right now

**Or run it manually anytime:**

```bash
python3 newsletter.py
```

---

## Scheduling

| Platform | How it works |
|----------|-------------|
| **macOS** | `setup.sh` registers a launchd job — runs at 08:00 every Monday even when Terminal is closed |
| **Linux** | `setup.sh` adds a cron job — same behavior |
| **Windows** | Use daemon mode: `python3 newsletter.py --daemon` (keep the terminal open) |

---

## Customization

All sources and settings live inside `newsletter.py`. Open it in any editor and find these sections near the top:

**Change the sources** — edit the `system_prompt()` function, which tells the agent which sources to search:
```python
# Around line 176 — update source names, add new ones, remove any
"Cover: The Rundown AI, Ben's Bites, AI Breakfast ..."
```

**Change the send time** — edit `setup.sh` (for macOS/Linux) or the `--daemon` schedule:
```python
schedule.every().monday.at("08:00").do(run_once)  # change "08:00" to any time
```

**Switch LLM backend** — change `LLM_BACKEND` in `.env`:
```
LLM_BACKEND=anthropic   # switch to Claude for better writing quality
```

---

## Troubleshooting

**`ModuleNotFoundError`** — run `pip3 install -r requirements.txt` and try again.

**Gmail login failed** — make sure you used the App Password (16 chars), not your regular Gmail password. Also confirm 2-Step Verification is enabled on your Google account.

**Groq 400 error / tool_use_failed** — you may have changed the `GROQ_MODEL`. Reset it to `meta-llama/llama-4-scout-17b-16e-instruct` or remove the line entirely to use the default.

**No results / empty newsletter** — DuckDuckGo occasionally rate-limits. Wait a few minutes and run again.

**`.env` file not visible** — it's a hidden file. On macOS press **⌘ Shift .** in Finder. On Linux use `ls -la` to confirm it exists.

**SSL certificate error** — run `pip3 install --upgrade certifi` and try again.

---

## How it works

```
Monday 08:00
    │
    ▼
Agent wakes up with 3 tools: search_web · fetch_page · send_newsletter
    │
    ├─ search_web("AI news this week")          ← agent decides this
    ├─ search_web("Karpathy Anthropic")          ← interesting result, follows up
    ├─ fetch_page("therundown.ai/p/...")         ← reads full article
    ├─ search_web("Sam Altman OpenAI statement")
    ├─ ... 8–18 tool calls, dynamically chosen
    │
    └─ send_newsletter(subject, body)            ← agent decides when it's done
            │
            ▼
    Formatted email → your inbox
    Markdown copy  → newsletters/YYYY-MM-DD.md
```
