#!/usr/bin/env bash
# ====================================================================
# LeadForge Launcher for macOS, Linux, and Android (Termux)
# ====================================================================

set -e
cd "$(dirname "$0")"

PYTHON_BIN="python3"
if ! command -v python3 &> /dev/null && command -v python &> /dev/null; then
    PYTHON_BIN="python"
fi

if ! command -v $PYTHON_BIN &> /dev/null; then
    echo "[ERROR] Python was not found. Please install Python 3.10+."
    exit 1
fi

echo "===================================================================="
echo "                         LEADFORGE PIPELINE                         "
echo "===================================================================="
echo "Starting LeadForge at http://127.0.0.1:8790 ..."
echo ""

$PYTHON_BIN -u dashboard/app.py

