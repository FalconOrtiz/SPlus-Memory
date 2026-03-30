#!/bin/bash
# Memory Engine Cron — Periodic flush + orphan recovery
# Add to crontab: */5 * * * * bash ~/.hermes/memory-engine/scripts/memory_cron.sh
#
# What it does:
#   1. Checks if there's an active session with buffered data
#   2. Flushes the buffer to the quantum index
#   3. If session is orphaned (process dead), recovers it
#
# This ensures memory is captured even if session crashes.

SCRIPTS_DIR="$HOME/.hermes/memory-engine/scripts"
LOG="$HOME/.hermes/memory-engine/logs/cron.log"

mkdir -p "$(dirname "$LOG")"

echo "[$(date -Iseconds)] cron tick" >> "$LOG"

# Check if active session exists
ACTIVE="$HOME/.hermes/memory-engine/sessions/active.json"
if [ -f "$ACTIVE" ]; then
    # Check if the owning process is still alive
    PID=$(python3 -c "import json; print(json.load(open('$ACTIVE')).get('pid', 0))" 2>/dev/null)
    
    if [ -n "$PID" ] && [ "$PID" -gt 0 ]; then
        if kill -0 "$PID" 2>/dev/null; then
            # Session alive — just flush buffer
            RESULT=$(python3 "$SCRIPTS_DIR/session_autosave.py" flush --json 2>/dev/null)
            FLUSHED=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('flushed',0))" 2>/dev/null)
            if [ "$FLUSHED" -gt 0 ] 2>/dev/null; then
                echo "[$(date -Iseconds)] flushed $FLUSHED facts" >> "$LOG"
            fi
        else
            # Session orphaned — recover
            python3 "$SCRIPTS_DIR/session_autosave.py" recover >> "$LOG" 2>&1
            echo "[$(date -Iseconds)] orphan recovered" >> "$LOG"
        fi
    fi
fi

# Trim log (keep last 500 lines)
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 500 ]; then
    tail -200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
