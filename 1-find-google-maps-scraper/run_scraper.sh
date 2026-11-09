#!/usr/bin/env bash
# ====================================================================
# LeadForge Maps Scraper Runner for macOS, Linux, and Android (Termux)
# ====================================================================

set -e
cd "$(dirname "$0")"

PYTHON_BIN="python3"
if ! command -v python3 &> /dev/null && command -v python &> /dev/null; then
    PYTHON_BIN="python"
fi

echo "===================================================================="
echo "          LEADFORGE LEAD FINDER (MAPS SCRAPER)                      "
echo "===================================================================="
echo "Finding leads. The search will query verified places for your queries."
echo "Do not close this window while it works."
echo ""

# Prefer native binary if available and executable on this OS
if [ -x "./google-maps-scraper" ]; then
    ./google-maps-scraper -input queries.txt -results results.csv -exit-on-inactivity 3m
else
    # Universal Cross-Platform Python Engine
    $PYTHON_BIN scraper.py -input queries.txt -results results.csv -exit-on-inactivity 3m
fi

echo ""
echo "Done. Your leads are saved in results.csv in this folder."
