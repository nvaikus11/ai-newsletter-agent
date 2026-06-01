#!/bin/bash
# AI Newsletter Agent — one-time setup
# Works on macOS (uses launchd) and Linux (uses cron).
# On Windows, use --daemon mode or set up Task Scheduler manually.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-python3}"

echo "=== AI Newsletter Agent Setup ==="
echo ""

# ── 1. Install dependencies ──────────────────────────────────────────────────
echo "Installing Python dependencies..."
"$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
echo "  Done."

# ── 2. Create .env if missing ────────────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo ""
    echo "Created .env from .env.example."
fi

echo ""
echo "Open .env and fill in your credentials before continuing:"
echo "  $SCRIPT_DIR/.env"
echo ""
echo "  LLM options (pick one):"
echo "  A) Groq      — free, sign up at console.groq.com"
echo "  B) Anthropic — ~\$0.05/run, sign up at console.anthropic.com"
echo ""
echo "  Gmail: you need a Gmail App Password (not your regular password)."
echo "  Get one at: myaccount.google.com → Security → App passwords"
echo ""
read -p "Press Enter once you've filled in .env to continue..."

# ── 3. Schedule ──────────────────────────────────────────────────────────────
echo ""
OS="$(uname -s)"
PYTHON_PATH="$("$PYTHON" -c 'import sys; print(sys.executable)')"

if [ "$OS" = "Darwin" ]; then
    # macOS — launchd (fires even when Terminal is closed)
    PLIST_SRC="$SCRIPT_DIR/com.ainewsletter.weekly.plist"
    PLIST_DST="$HOME/Library/LaunchAgents/com.ainewsletter.weekly.plist"

    # Substitute both __PYTHON_PATH__ and __SCRIPT_DIR__ in the plist template
    sed \
        -e "s|__PYTHON_PATH__|$PYTHON_PATH|g" \
        -e "s|__SCRIPT_DIR__|$SCRIPT_DIR|g" \
        "$PLIST_SRC" > "$PLIST_DST"

    launchctl unload "$PLIST_DST" 2>/dev/null || true
    launchctl load "$PLIST_DST"
    echo "Scheduled via launchd: every Monday at 08:00."
    echo "Logs: $SCRIPT_DIR/newsletter.log"

elif [ "$OS" = "Linux" ]; then
    # Linux — cron
    CRON_JOB="0 8 * * 1 cd \"$SCRIPT_DIR\" && $PYTHON_PATH newsletter.py >> \"$SCRIPT_DIR/newsletter.log\" 2>&1"
    # Add only if not already present
    ( crontab -l 2>/dev/null | grep -v "newsletter.py"; echo "$CRON_JOB" ) | crontab -
    echo "Scheduled via cron: every Monday at 08:00."
    echo "Check with: crontab -l"

else
    # Windows / other — daemon mode
    echo "Automatic scheduling not supported on this OS."
    echo "Use daemon mode instead:"
    echo "  python3 newsletter.py --daemon"
    echo ""
    echo "Or on Windows, open Task Scheduler and create a weekly job:"
    echo "  Program : $PYTHON_PATH"
    echo "  Arguments: $SCRIPT_DIR/newsletter.py"
    echo "  Schedule : weekly, Monday, 08:00"
fi

# ── 4. Test run ──────────────────────────────────────────────────────────────
echo ""
read -p "Run the newsletter now as a test? [y/N] " -n 1 -r; echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    "$PYTHON" "$SCRIPT_DIR/newsletter.py"
fi

echo ""
echo "Setup complete. Your newsletter will arrive every Monday at 08:00."
