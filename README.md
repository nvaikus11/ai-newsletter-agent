# AI Newsletter Agent

Fetches the week's AI news from newsletters, YouTube, and LinkedIn thought leaders, then emails a curated digest every Monday morning.

**Sources:** The Rundown AI · Ben's Bites · AI Breakfast · Morning Brew AI · Matt Wolfe · All-In Podcast · Andrew Ng · Sam Altman · Andrej Karpathy

---

## Setup (5 minutes)

### 1. Prerequisites
- Python 3.10+
- A Gmail account

### 2. Get a free LLM API key (pick one)
| Option | Cost | Where |
|--------|------|-------|
| **Groq** ⭐ recommended | Free | [console.groq.com](https://console.groq.com) → API Keys |
| Ollama (local) | Free, offline | [ollama.com](https://ollama.com) → `ollama pull llama3.2` |
| Anthropic | ~$0.01/run | [console.anthropic.com](https://console.anthropic.com) |

### 3. Get a Gmail App Password
1. Enable 2-Step Verification on your Google account
2. Go to [myaccount.google.com](https://myaccount.google.com) → Security → App passwords
3. Create one named "AI Newsletter" → copy the 16-character code

### 4. Install and run

```bash
git clone <repo-url>
cd "AI Newsletter Agent"

# Fill in your credentials
cp .env.example .env
open .env          # or: nano .env / code .env

# Run setup (installs deps + schedules Monday 8am)
bash setup.sh
```

> **To see hidden files in Finder:** press ⌘ + Shift + .

### Run manually anytime
```bash
python3 newsletter.py
```

### Daemon mode (Windows / no cron)
```bash
python3 newsletter.py --daemon   # keep terminal open; fires every Monday 08:00
```

---

## Configuration (`.env`)

```
LLM_BACKEND=groq                  # groq | anthropic | ollama
GROQ_API_KEY=gsk_...              # if using Groq
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
RECIPIENT_EMAIL=you@gmail.com     # where to deliver (defaults to GMAIL_USER)
```
