#!/usr/bin/env python3
"""
Session Autosave — Persistent memory capture that survives crashes.

Strategy: Instead of hooking session close (unreliable — crashes/disconnects
skip hooks), we use three layers:

  Layer 1 — INCREMENTAL FLUSH (during session)
    Periodically scans the active session log and ingests new facts.
    Runs every N minutes via cron or heartbeat.
    Even if session dies mid-conversation, last flush is preserved.

  Layer 2 — SESSION CLOSE (graceful)
    Final flush when session ends normally.
    Captures anything since last incremental flush.

  Layer 3 — ORPHAN RECOVERY (post-crash)
    On next session start, detects unflushed session data.
    Recovers and ingests anything that wasn't captured.

Files:
  ~/.hermes/memory-engine/sessions/active.json    — current session state
  ~/.hermes/memory-engine/sessions/buffer.jsonl    — incremental fact buffer
  ~/.hermes/memory-engine/sessions/archive/        — completed sessions
"""

import json
import os
import sys
import time
import fcntl
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from quantum_index import QuantumIndex
from session_capture import extract_facts, classify_segment

SESSIONS_DIR = Path.home() / ".hermes/memory-engine/sessions"
ACTIVE_FILE = SESSIONS_DIR / "active.json"
BUFFER_FILE = SESSIONS_DIR / "buffer.jsonl"
ARCHIVE_DIR = SESSIONS_DIR / "archive"
LOCK_FILE = SESSIONS_DIR / ".lock"


def ensure_dirs():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


# ── File locking (prevents concurrent writes) ───────────────────

class FileLock:
    def __init__(self, path):
        self.path = path
        self.fd = None

    def __enter__(self):
        self.fd = open(self.path, 'w')
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *args):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        self.fd.close()


# ── Layer 1: Session State Management ────────────────────────────

def start_session(session_id: str = None) -> str:
    """
    Register a new active session.
    Called at session start. If a previous session exists and wasn't
    closed, triggers orphan recovery first.
    """
    ensure_dirs()

    # Check for orphaned session (Layer 3)
    if ACTIVE_FILE.exists():
        recover_orphaned_session()

    sid = session_id or f"ses_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"

    state = {
        "session_id": sid,
        "started_at": datetime.now().isoformat(),
        "last_flush": None,
        "facts_flushed": 0,
        "buffer_lines": 0,
        "status": "active",
        "pid": os.getpid(),
    }

    with FileLock(LOCK_FILE):
        ACTIVE_FILE.write_text(json.dumps(state, indent=2))

    # Clear buffer for new session
    BUFFER_FILE.write_text("")

    return sid


def get_active_session() -> Optional[Dict]:
    """Get the current active session state."""
    if not ACTIVE_FILE.exists():
        return None
    try:
        return json.loads(ACTIVE_FILE.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return None


# ── Layer 1: Incremental Buffer ──────────────────────────────────

def buffer_fact(text: str, context: Dict = None):
    """
    Add a fact to the incremental buffer.
    Called during the session whenever something worth remembering happens.
    Buffer is a JSONL file — append-only, crash-safe.
    """
    ensure_dirs()
    context = context or {}

    entry = {
        "text": text,
        "context": context,
        "timestamp": datetime.now().isoformat(),
        "hash": hashlib.md5(text.encode()).hexdigest()[:10],
    }

    with FileLock(LOCK_FILE):
        with open(BUFFER_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # Update session state
    state = get_active_session()
    if state:
        state["buffer_lines"] = state.get("buffer_lines", 0) + 1
        ACTIVE_FILE.write_text(json.dumps(state, indent=2))


def buffer_conversation_turn(role: str, content: str, context: Dict = None):
    """
    Buffer a conversation turn. Classifies and only buffers if it's
    worth remembering (not casual chat).
    """
    fact_type, confidence = classify_segment(content)

    if fact_type in ("SKIP", "DISCUSSION") or confidence < 0.35:
        return False

    ctx = context or {}
    ctx["role"] = role
    ctx["fact_type"] = fact_type

    buffer_fact(content, ctx)
    return True


# ── Layer 1: Incremental Flush ───────────────────────────────────

def flush_buffer() -> Dict:
    """
    Flush the buffer: ingest all buffered facts into the quantum index.
    Called periodically (cron/heartbeat) and on session close.
    Returns summary of what was flushed.
    """
    ensure_dirs()

    if not BUFFER_FILE.exists():
        return {"flushed": 0, "skipped": 0}

    # Read buffer
    with FileLock(LOCK_FILE):
        lines = BUFFER_FILE.read_text().strip().split("\n")
        # Clear buffer after reading
        BUFFER_FILE.write_text("")

    if not lines or lines == [""]:
        return {"flushed": 0, "skipped": 0}

    # Parse entries
    entries = []
    seen_hashes = set()
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            h = entry.get("hash", "")
            if h not in seen_hashes:
                seen_hashes.add(h)
                entries.append(entry)
        except json.JSONDecodeError:
            continue

    if not entries:
        return {"flushed": 0, "skipped": 0}

    # Ingest into quantum index
    idx = QuantumIndex()
    idx.connect()

    flushed = 0
    skipped = 0

    try:
        for entry in entries:
            try:
                context = entry.get("context", {})
                if "status" not in context:
                    context["status"] = "pending"
                if "who" not in context:
                    context["who"] = "falcon"

                idx.ingest(entry["text"], context=context)
                flushed += 1
            except Exception:
                skipped += 1
    finally:
        idx.close()

    # Update session state
    state = get_active_session()
    if state:
        state["last_flush"] = datetime.now().isoformat()
        state["facts_flushed"] = state.get("facts_flushed", 0) + flushed
        state["buffer_lines"] = 0
        ACTIVE_FILE.write_text(json.dumps(state, indent=2))

    return {"flushed": flushed, "skipped": skipped, "timestamp": datetime.now().isoformat()}


# ── Layer 2: Session Close ───────────────────────────────────────

def close_session(summary: str = None) -> Dict:
    """
    Gracefully close the current session.
    Flushes any remaining buffer, archives the session, clears state.
    """
    ensure_dirs()

    # Final flush
    flush_result = flush_buffer()

    state = get_active_session()
    if not state:
        return {"status": "no_active_session", "flush": flush_result}

    # If summary provided, ingest it as a session-level fact
    if summary:
        idx = QuantumIndex()
        idx.connect()
        try:
            idx.ingest(summary, context={
                "status": "completed",
                "who": "falcon",
                "fact_type": "session_summary",
            })
        finally:
            idx.close()

    # Archive session
    state["status"] = "closed"
    state["closed_at"] = datetime.now().isoformat()
    state["close_reason"] = "graceful"
    state["total_flushed"] = state.get("facts_flushed", 0) + flush_result.get("flushed", 0)

    archive_path = ARCHIVE_DIR / f"{state['session_id']}.json"
    archive_path.write_text(json.dumps(state, indent=2))

    # Clear active state
    with FileLock(LOCK_FILE):
        if ACTIVE_FILE.exists():
            ACTIVE_FILE.unlink()

    return {
        "status": "closed",
        "session_id": state["session_id"],
        "total_flushed": state["total_flushed"],
        "flush": flush_result,
    }


# ── Layer 3: Orphan Recovery ────────────────────────────────────

def recover_orphaned_session() -> Dict:
    """
    Recover an orphaned session (crash/disconnect/timeout).
    Called automatically when a new session starts and finds stale state.
    """
    state = get_active_session()
    if not state:
        return {"status": "no_orphan"}

    # Check if the process that owned the session is still alive
    pid = state.get("pid")
    if pid:
        try:
            os.kill(pid, 0)  # signal 0 = check if alive
            # Process still alive — not an orphan
            return {"status": "still_active", "pid": pid}
        except (OSError, ProcessLookupError):
            pass  # Process dead — this is an orphan

    # Flush any remaining buffer data
    flush_result = flush_buffer()

    # Archive as crashed
    state["status"] = "recovered"
    state["closed_at"] = datetime.now().isoformat()
    state["close_reason"] = "orphan_recovery"
    state["recovery_flush"] = flush_result

    archive_path = ARCHIVE_DIR / f"{state['session_id']}_recovered.json"
    archive_path.write_text(json.dumps(state, indent=2))

    # Clear active state
    with FileLock(LOCK_FILE):
        if ACTIVE_FILE.exists():
            ACTIVE_FILE.unlink()

    return {
        "status": "recovered",
        "session_id": state["session_id"],
        "flush": flush_result,
    }


# ── Status ──────────────────────────────────────────────────────

def session_status() -> Dict:
    """Get current session and buffer status."""
    state = get_active_session()

    buffer_lines = 0
    if BUFFER_FILE.exists():
        text = BUFFER_FILE.read_text().strip()
        if text:
            buffer_lines = len(text.split("\n"))

    archives = list(ARCHIVE_DIR.glob("*.json")) if ARCHIVE_DIR.exists() else []

    return {
        "active_session": state,
        "buffer_lines": buffer_lines,
        "archived_sessions": len(archives),
        "sessions_dir": str(SESSIONS_DIR),
    }


# ── CLI ──────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Session Autosave (crash-safe memory capture)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("start", help="Start a new session")
    sub.add_parser("status", help="Show session status")

    p = sub.add_parser("buffer", help="Buffer a fact")
    p.add_argument("text", nargs="+")
    p.add_argument("--status", default="pending")

    sub.add_parser("flush", help="Flush buffer to quantum index")

    p = sub.add_parser("close", help="Close session gracefully")
    p.add_argument("--summary", type=str)

    sub.add_parser("recover", help="Recover orphaned session")

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "start":
        sid = start_session()
        print(f"  ✓ Session started: {sid}")

    elif args.command == "status":
        result = session_status()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            s = result["active_session"]
            if s:
                print(f"\n  Active session: {s['session_id']}")
                print(f"  Started: {s['started_at']}")
                print(f"  Last flush: {s.get('last_flush', 'never')}")
                print(f"  Facts flushed: {s.get('facts_flushed', 0)}")
            else:
                print(f"\n  No active session.")
            print(f"  Buffer lines: {result['buffer_lines']}")
            print(f"  Archived sessions: {result['archived_sessions']}")
            print()

    elif args.command == "buffer":
        text = " ".join(args.text)
        buffer_fact(text, {"status": args.status, "who": "falcon"})
        print(f"  ✓ Buffered fact")

    elif args.command == "flush":
        result = flush_buffer()
        print(f"  ✓ Flushed: {result['flushed']} facts ({result['skipped']} skipped)")

    elif args.command == "close":
        result = close_session(summary=args.summary)
        print(f"  ✓ Session {result.get('session_id', '?')} closed")
        print(f"    Total flushed: {result.get('total_flushed', 0)}")

    elif args.command == "recover":
        result = recover_orphaned_session()
        print(f"  Status: {result['status']}")
        if result.get("flush"):
            print(f"  Recovered: {result['flush'].get('flushed', 0)} facts")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
