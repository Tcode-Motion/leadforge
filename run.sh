#!/usr/bin/env bash
# ====================================================================
# LeadForge Launcher for macOS, Linux, and Android (Termux)
# ====================================================================

set -e
cd "$(dirname "$0")"

# 1. Automatic Permission Enforcement & macOS Gatekeeper Clearance
chmod +x run.sh setup.sh 1-find-google-maps-scraper/*.sh 1-find-google-maps-scraper/*.py 2>/dev/null || true
if [ "$(uname -s 2>/dev/null)" = "Darwin" ]; then
    xattr -dr com.apple.quarantine . 2>/dev/null || true
fi

# 2. Detect Python 3
PYTHON_BIN="python3"
if ! command -v python3 &> /dev/null && command -v python &> /dev/null; then
    PYTHON_BIN="python"
fi

if ! command -v $PYTHON_BIN &> /dev/null; then
    echo "[ERROR] Python was not found. Please install Python 3.10+ (tested up to 3.13)."
    exit 1
fi

echo "===================================================================="
echo "                         LEADFORGE PIPELINE                         "
echo "===================================================================="
echo "Starting LeadForge at http://127.0.0.1:8790 ..."
echo ""

exec $PYTHON_BIN -u dashboard/app.py
