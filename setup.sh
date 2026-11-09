#!/usr/bin/env bash
# ====================================================================
# LeadForge 1-Click Automated Setup for macOS, Linux, and Android (Termux)
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Tcode-Motion/leadforge/master/setup.sh | bash
# ====================================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}====================================================================${NC}"
echo -e "${YELLOW}                   LEADFORGE AUTOMATED SETUP                        ${NC}"
echo -e "${CYAN}====================================================================${NC}"
echo ""

# 1. Detect OS
OS_TYPE="$(uname -s)"
IS_TERMUX=0
if [ -n "$PREFIX" ] && [[ "$PREFIX" == *"com.termux"* ]]; then
    IS_TERMUX=1
    echo -e "${BLUE}[1/5] Detected Environment: Android (Termux)${NC}"
else
    echo -e "${BLUE}[1/5] Detected Environment: ${OS_TYPE}${NC}"
fi

# 2. Check / Install Python & Git in Termux or System
if [ "$IS_TERMUX" -eq 1 ]; then
    echo -e "${BLUE}[2/5] Updating Termux packages and ensuring Python/Git...${NC}"
    pkg update -y || true
    pkg install -y python git libxml2 libxslt || true
else
    echo -e "${BLUE}[2/5] Checking Python 3 and Git...${NC}"
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}[ERROR] Python 3 was not found.${NC}"
        echo -e "${YELLOW}Please install Python 3.10+ using your system package manager (e.g. brew install python3 or sudo apt install python3 python3-pip).${NC}"
        exit 1
    fi
    if ! command -v git &> /dev/null; then
        echo -e "${RED}[ERROR] Git was not found.${NC}"
        echo -e "${YELLOW}Please install git (e.g. brew install git or sudo apt install git).${NC}"
        exit 1
    fi
fi

PYTHON_BIN="python3"
if ! command -v python3 &> /dev/null && command -v python &> /dev/null; then
    PYTHON_BIN="python"
fi
echo -e "      Found: $($PYTHON_BIN --version)"

# 3. Check / Clone Repository
echo -e "${BLUE}[3/5] Verifying repository files...${NC}"
if [ ! -f "dashboard/app.py" ]; then
    if [ -f "leadforge/dashboard/app.py" ]; then
        cd leadforge
    else
        echo -e "${YELLOW}      Cloning LeadForge repository from GitHub...${NC}"
        git clone https://github.com/Tcode-Motion/leadforge.git
        cd leadforge
    fi
fi
echo -e "${GREEN}      Codebase ready in: $(pwd)${NC}"

# 4. Local Configuration
echo -e "${BLUE}[4/5] Setting up local configuration...${NC}"
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo -e "${GREEN}      Created default .env from .env.example${NC}"
else
    echo -e "${GREEN}      .env configuration verified.${NC}"
fi

# 5. Dependencies
echo -e "${BLUE}[5/5] Installing dependencies...${NC}"
$PYTHON_BIN -m pip install --upgrade pip --quiet || true

if [ "$IS_TERMUX" -eq 0 ]; then
    $PYTHON_BIN -m pip install playwright --quiet || true
    $PYTHON_BIN -m playwright install chromium || echo "Playwright bundled chromium skipped; using native browser."
else
    echo -e "${YELLOW}      Termux environment: skipping Playwright browser bundle.${NC}"
fi
echo -e "${GREEN}      Dependencies verified.${NC}"

# Launch
echo ""
echo -e "${CYAN}====================================================================${NC}"
echo -e "${GREEN}  LEADFORGE IS LIVE!${NC}"
echo -e "${GREEN}  Dashboard URL: http://127.0.0.1:8790${NC}"
echo -e "${YELLOW}  Next time, simply run: bash run.sh (or ./run.sh)${NC}"
echo -e "${CYAN}====================================================================${NC}"
echo ""

$PYTHON_BIN -u dashboard/app.py

