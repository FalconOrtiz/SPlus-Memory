#!/bin/bash

# Memory Engine Initialization Script
# Phase 1-2: Semantic Retrieval + Temporal Weighting
# Created: 2026-03-23

set -e

ENGINE_HOME="$HOME/.hermes/memory-engine"
PYTHON_SCRIPT="$ENGINE_HOME/scripts/memory_engine.py"
DB_PATH="$ENGINE_HOME/db/memory.db"
LOG_FILE="$ENGINE_HOME/logs/memory-engine.log"

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║  Hermes Memory Engine - Phase 1-2 Initialization      ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Check Python
echo "[1/5] Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.9+"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python $PYTHON_VERSION found"
echo ""

# Check dependencies
echo "[2/5] Checking dependencies..."
MISSING_DEPS=0

# Check PyYAML
if ! python3 -c "import yaml" 2>/dev/null; then
    echo "⚠ PyYAML not found, installing..."
    pip3 install pyyaml --quiet
else
    echo "✓ PyYAML installed"
fi

# Check sqlite3
if ! python3 -c "import sqlite3" 2>/dev/null; then
    echo "❌ sqlite3 not available (should be built-in)"
    exit 1
else
    echo "✓ sqlite3 available"
fi

echo ""

# Create directories
echo "[3/5] Creating directories..."
mkdir -p "$ENGINE_HOME"/{config,db,scripts,logs}
echo "✓ Directories created"
echo ""

# Initialize database
echo "[4/5] Initializing database..."
if [ -f "$DB_PATH" ]; then
    echo "⚠ Database already exists at $DB_PATH"
    read -p "  Overwrite? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm "$DB_PATH"
        echo "  ✓ Old database removed"
    else
        echo "  Keeping existing database"
    fi
fi

# Initialize with memory_engine.py
if [ ! -f "$DB_PATH" ]; then
    python3 "$PYTHON_SCRIPT" --init 2>&1 | tee -a "$LOG_FILE"
else
    echo "✓ Database already initialized"
fi
echo ""

# Check status
echo "[5/5] Verifying installation..."
STATUS=$(python3 "$PYTHON_SCRIPT" --status 2>&1)

if echo "$STATUS" | grep -q "operational"; then
    echo "✓ Memory Engine operational"
else
    echo "⚠ Status check failed. See logs:"
    echo "  tail -50 $LOG_FILE"
fi

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║  ✓ Initialization Complete                            ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Review config: $ENGINE_HOME/config/memory-engine.yaml"
echo "  2. Add facts: python3 $PYTHON_SCRIPT --add-fact 'text' --source 'manual'"
echo "  3. Search: python3 $PYTHON_SCRIPT --query 'search text'"
echo "  4. View logs: tail -f $LOG_FILE"
echo ""
echo "Documentation: $ENGINE_HOME/README.md"
echo ""
