#!/usr/bin/env python3
"""
Session Capture Pipeline — Auto-extract and ingest facts from conversations.
Zero LLM tokens: pure pattern matching + procedural extraction.
"""

import re
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent))
from quantum_index import QuantumIndex


@dataclass
class ExtractedFact:
    text: str
    fact_type: str
    status: str
    confidence: float
    context: Dict


# ── Classification patterns (bilingual ES/EN) ──────────────────

CLASSIFICATION_PATTERNS = {
    "DECISION": {
        "patterns": [
            r"decidimos|vamos a usar|agreed|decided|will use|elegimos",
            r"the plan is|la decisión|optamos por|we.?ll go with",
            r"final decision|conclusión|acordamos",
        ],
        "default_status": "committed",
    },
    "ACTION": {
        "patterns": [
            r"hice|arreglé|fixed|created|deployed|installed|configured",
            r"built|wrote|pushed|committed|merged|shipped|set up",
            r"implementé|construí|desplegué|actualicé|migré",
        ],
        "default_status": "completed",
    },
    "LEARNING": {
        "patterns": [
            r"aprendí|learned|turns out|resulta que|the trick is",
            r"discovered|figured out|descubrí|la clave es|key insight",
            r"important to note|hay que tener en cuenta|gotcha|caveat",
        ],
        "default_status": "completed",
    },
    "PREFERENCE": {
        "patterns": [
            r"prefiero|I prefer|me gusta|I like|don.?t like|no me gusta",
            r"I want|quiero|mejor si|rather have|would rather",
            r"my style|mi estilo|always use|siempre uso",
        ],
        "default_status": "committed",
    },
    "ERROR_FIX": {
        "patterns": [
            r"error|bug|fix|broke|failed|arreglar|fallo|crash",
            r"the issue was|el problema era|root cause|workaround",
            r"resolved by|se arregló con|solution was",
        ],
        "default_status": "completed",
    },
    "CONFIGURATION": {
        "patterns": [
            r"config|setup|\.env|variable|\.yaml|\.json|settings",
            r"ssh|port|credentials|api.?key|token|secret",
            r"installed|brew|pip|npm|apt|dependency",
        ],
        "default_status": "committed",
    },
    "PLAN": {
        "patterns": [
            r"\bplan\b|next step|todo|will\b|vamos|después|tomorrow",
            r"mañana|fase|phase|roadmap|sprint|milestone|backlog",
            r"need to|necesitamos|hay que|should|deberíamos",
        ],
        "default_status": "pending",
    },
}

# Skip patterns — conversations that are just chat, not facts
SKIP_PATTERNS = [
    r"^(ok|okay|vale|sí|yes|no|sure|claro|bien|gracias|thanks)\s*\.?$",
    r"^(hola|hey|hi|hello|good morning|buenas)\b",
    r"^(jaja|haha|lol|xd|lmao)\b",
    r"^\s*$",
]


def classify_segment(text: str) -> Tuple[str, float]:
    """
    Classify a text segment into a fact type.
    Returns (type, confidence).
    """
    text_lower = text.lower().strip()

    # Check skip patterns
    for pattern in SKIP_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return "SKIP", 0.0

    # Too short to be meaningful
    if len(text_lower) < 15:
        return "SKIP", 0.0

    # Score each type
    scores = {}
    for fact_type, config in CLASSIFICATION_PATTERNS.items():
        score = 0
        for pattern in config["patterns"]:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            score += len(matches)
        if score > 0:
            scores[fact_type] = score

    if not scores:
        # If nothing matched but text is substantial, classify as DISCUSSION
        if len(text_lower) > 50:
            return "DISCUSSION", 0.3
        return "SKIP", 0.0

    # Best match
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    confidence = min(0.95, 0.4 + (best_score * 0.15))

    return best_type, confidence


def split_into_segments(text: str) -> List[str]:
    """
    Split a transcript into logical segments.
    Handles: bullet points, paragraphs, numbered lists, speaker turns.
    """
    segments = []

    # Split by double newlines (paragraphs)
    paragraphs = re.split(r'\n\s*\n', text)

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Check for bullet points or numbered lists
        bullets = re.findall(r'^[\s]*[-*•]\s+(.+)$', para, re.MULTILINE)
        if bullets:
            segments.extend(bullets)
            continue

        numbered = re.findall(r'^[\s]*\d+[.)]\s+(.+)$', para, re.MULTILINE)
        if numbered:
            segments.extend(numbered)
            continue

        # Check for speaker turns (e.g., "User:", "Assistant:", "Falcon:")
        turns = re.split(r'\n(?=(?:User|Assistant|Human|Falcon|Hermes|Hermes):)', para)
        if len(turns) > 1:
            for turn in turns:
                # Remove speaker label
                cleaned = re.sub(r'^(?:User|Assistant|Human|Falcon|Hermes|Hermes):\s*', '', turn.strip())
                if cleaned:
                    segments.append(cleaned)
            continue

        # Single paragraph — split by sentences if long
        if len(para) > 300:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            # Group sentences into chunks of ~150 chars
            chunk = ""
            for sent in sentences:
                if len(chunk) + len(sent) > 200 and chunk:
                    segments.append(chunk.strip())
                    chunk = sent
                else:
                    chunk = (chunk + " " + sent).strip()
            if chunk:
                segments.append(chunk)
        else:
            segments.append(para)

    return [s.strip() for s in segments if s.strip()]


def extract_facts(text: str, context: Dict = None) -> List[ExtractedFact]:
    """
    Extract structured facts from a text transcript.
    """
    context = context or {}
    segments = split_into_segments(text)
    facts = []

    for segment in segments:
        fact_type, confidence = classify_segment(segment)

        if fact_type in ("SKIP", "DISCUSSION"):
            continue

        if confidence < 0.35:
            continue

        config = CLASSIFICATION_PATTERNS.get(fact_type, {})
        status = config.get("default_status", "pending")

        fact_context = {
            "status": status,
            "who": context.get("who", "falcon"),
            "project": context.get("project", ""),
            "phase": context.get("phase", ""),
        }

        facts.append(ExtractedFact(
            text=segment,
            fact_type=fact_type,
            status=status,
            confidence=confidence,
            context=fact_context,
        ))

    return facts


def capture_session(text: str, context: Dict = None) -> Dict:
    """
    Full pipeline: extract facts from session text, ingest into quantum index.
    """
    facts = extract_facts(text, context)

    idx = QuantumIndex()
    idx.connect()

    ingested = []
    skipped = 0

    try:
        for fact in facts:
            try:
                fact_id = idx.ingest(fact.text, context=fact.context)
                ingested.append({
                    "id": fact_id,
                    "type": fact.fact_type,
                    "status": fact.status,
                    "summary": fact.text[:100],
                    "confidence": fact.confidence,
                })
            except Exception as e:
                skipped += 1

        stats = idx.get_stats()
    finally:
        idx.close()

    return {
        "captured": len(ingested),
        "skipped": skipped,
        "facts": ingested,
        "total_in_index": stats["total_facts"],
        "timestamp": datetime.now().isoformat(),
    }


def capture_from_markdown_file(filepath: str, context: Dict = None) -> Dict:
    """
    Read a markdown file and extract facts from it.
    """
    path = Path(filepath)
    if not path.exists():
        return {"error": f"File not found: {filepath}"}

    text = path.read_text(encoding="utf-8", errors="replace")

    # Add source info to context
    ctx = context or {}
    ctx["source"] = str(path)

    return capture_session(text, context=ctx)


def import_memory_directory(base_dir: str = None) -> Dict:
    """
    Scan memory directories and import all markdown files.
    """
    home = Path.home()
    dirs_to_scan = [
        home / "memory",
        home / ".hermes" / "memory-engine",
    ]
    files_to_scan = [
        home / "MEMORY.md",
    ]

    if base_dir:
        dirs_to_scan.insert(0, Path(base_dir))

    total_captured = 0
    total_files = 0
    results = []

    for d in dirs_to_scan:
        if d.exists():
            for md_file in sorted(d.glob("**/*.md")):
                if md_file.name.startswith("."):
                    continue
                result = capture_from_markdown_file(
                    str(md_file),
                    context={"who": "falcon", "status": "completed"}
                )
                total_captured += result.get("captured", 0)
                total_files += 1
                results.append({"file": str(md_file), "captured": result.get("captured", 0)})

    for f in files_to_scan:
        if f.exists():
            result = capture_from_markdown_file(
                str(f),
                context={"who": "falcon", "status": "committed"}
            )
            total_captured += result.get("captured", 0)
            total_files += 1
            results.append({"file": str(f), "captured": result.get("captured", 0)})

    return {
        "files_scanned": total_files,
        "total_captured": total_captured,
        "details": results,
    }


# ── CLI ──────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Session Capture Pipeline")
    parser.add_argument("--text", type=str, help="Capture facts from text")
    parser.add_argument("--file", type=str, help="Capture facts from file")
    parser.add_argument("--import-all", action="store_true", help="Import all memory files")
    parser.add_argument("--who", default="falcon")
    parser.add_argument("--project", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    context = {"who": args.who, "project": args.project}

    if args.text:
        result = capture_session(args.text, context=context)
    elif args.file:
        result = capture_from_markdown_file(args.file, context=context)
    elif args.import_all:
        result = import_memory_directory()
    else:
        parser.print_help()
        return

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if "error" in result:
            print(f"Error: {result['error']}")
            return

        if "files_scanned" in result:
            print(f"\n  Files scanned:  {result['files_scanned']}")
            print(f"  Facts captured: {result['total_captured']}")
            for d in result.get("details", []):
                if d["captured"] > 0:
                    print(f"    {d['file']}: {d['captured']} facts")
        else:
            print(f"\n  Facts captured: {result['captured']}")
            print(f"  Skipped:        {result['skipped']}")
            print(f"  Total in index: {result['total_in_index']}")
            for f in result.get("facts", []):
                print(f"    [{f['type']}] {f['status']}: {f['summary']}")
        print()


if __name__ == "__main__":
    main()
