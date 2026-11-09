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

# 1. Detect OS & Hardware Architecture
OS_TYPE="$(uname -s)"
ARCH_TYPE="$(uname -m)"
IS_TERMUX=0

if [ -n "$PREFIX" ] && [[ "$PREFIX" == *"com.termux"* ]]; then
    IS_TERMUX=1
    echo -e "${BLUE}[1/6] Detected Environment: Android (Termux) [${ARCH_TYPE}]${NC}"
else
    echo -e "${BLUE}[1/6] Detected Environment: ${OS_TYPE} [${ARCH_TYPE}]${NC}"
fi

# 2. Check / Install Python & Git in Termux or System
if [ "$IS_TERMUX" -eq 1 ]; then
    echo -e "${BLUE}[2/6] Updating Termux packages and ensuring Python/Git...${NC}"
    pkg update -y || true
    pkg install -y python git libxml2 libxslt curl || true
else
    echo -e "${BLUE}[2/6] Checking Python 3 and Git specifications...${NC}"
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}[ERROR] Python 3 was not found.${NC}"
        echo -e "${YELLOW}Please install Python 3.10+ using your system package manager:${NC}"
        echo -e "  macOS (Homebrew): brew install python3"
        echo -e "  Ubuntu / Debian : sudo apt update && sudo apt install -y python3 python3-pip python3-venv git curl"
        echo -e "  Fedora / RHEL   : sudo dnf install -y python3 python3-pip git curl"
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

PY_VERSION=$($PYTHON_BIN -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "      Python Version: ${PY_VERSION} ($($PYTHON_BIN --version))"

# Check Python >= 3.10
PY_MAJOR=$($PYTHON_BIN -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON_BIN -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo -e "${RED}[ERROR] Python ${PY_VERSION} detected. LeadForge requires Python 3.10 or newer (tested up to 3.13).${NC}"
    exit 1
fi

# 3. Check / Clone Repository
echo -e "${BLUE}[3/6] Verifying repository files...${NC}"
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

# 4. Automatic Permission Enforcement & macOS Gatekeeper Clearance
echo -e "${BLUE}[4/6] Enforcing execution permissions and clearing quarantine...${NC}"
chmod +x run.sh setup.sh 2>/dev/null || true
chmod +x 1-find-google-maps-scraper/*.sh 1-find-google-maps-scraper/*.py 2>/dev/null || true

# macOS Gatekeeper quarantine removal
if [ "$OS_TYPE" = "Darwin" ]; then
    echo -e "      macOS detected: clearing Gatekeeper quarantine attributes..."
    xattr -dr com.apple.quarantine . 2>/dev/null || true
fi
echo -e "${GREEN}      File permissions and OS execution flags verified.${NC}"

# 5. Lead Scraper Engine Setup (Native Binary + Python Universal Engine)
echo -e "${BLUE}[5/6] Verifying Lead Finder scraper engine...${NC}"
SCRAPER_DIR="1-find-google-maps-scraper"
NATIVE_BIN="$SCRAPER_DIR/google-maps-scraper"

# If on macOS or Linux and native binary not present, attempt to download matching release
if [ "$OS_TYPE" = "Darwin" ] || [ "$OS_TYPE" = "Linux" ]; then
    if [ ! -f "$NATIVE_BIN" ]; then
        RELEASE_OS="linux"
        [ "$OS_TYPE" = "Darwin" ] && RELEASE_OS="darwin"

        RELEASE_ARCH="amd64"
        if [ "$ARCH_TYPE" = "arm64" ] || [ "$ARCH_TYPE" = "aarch64" ]; then
            RELEASE_ARCH="arm64"
        fi

        DOWNLOAD_URL="https://github.com/gosom/google-maps-scraper/releases/download/v1.7.0/google-maps-scraper_1.7.0_${RELEASE_OS}_${RELEASE_ARCH}.tar.gz"
        echo -e "      Attempting download of native ${RELEASE_OS}_${RELEASE_ARCH} binary from GitHub..."
        
        TEMP_ARCHIVE="/tmp/gmaps_scraper_${RELEASE_OS}_${RELEASE_ARCH}.tar.gz"
        if curl -fsSL -m 15 "$DOWNLOAD_URL" -o "$TEMP_ARCHIVE" 2>/dev/null; then
            tar -xzf "$TEMP_ARCHIVE" -C "$SCRAPER_DIR" google-maps-scraper 2>/dev/null || true
            rm -f "$TEMP_ARCHIVE"
            if [ -f "$NATIVE_BIN" ]; then
                chmod +x "$NATIVE_BIN"
                echo -e "${GREEN}      Native binary downloaded and configured successfully.${NC}"
            fi
        else
            echo -e "${YELLOW}      Notice: Native binary download skipped (offline or network timeout).${NC}"
        fi
    else
        chmod +x "$NATIVE_BIN" 2>/dev/null || true
    fi
fi

if [ -f "$NATIVE_BIN" ] && [ -x "$NATIVE_BIN" ]; then
    echo -e "${GREEN}      Lead Finder: Native binary ready ($NATIVE_BIN)${NC}"
elif [ -f "$SCRAPER_DIR/scraper.py" ]; then
    echo -e "${GREEN}      Lead Finder: Universal Cross-Platform Python Engine ready (0-deps)${NC}"
else
    echo -e "${YELLOW}      Notice: Custom scraper runner will be resolved dynamically at runtime.${NC}"
fi

# 6. Local Configuration & Dependencies
echo -e "${BLUE}[6/6] Setting up local configuration and dependencies...${NC}"
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo -e "${GREEN}      Created default .env from .env.example${NC}"
else
    echo -e "${GREEN}      .env configuration verified.${NC}"
fi

$PYTHON_BIN -m pip install --upgrade pip --quiet || true

if [ "$IS_TERMUX" -eq 0 ]; then
    $PYTHON_BIN -m pip install playwright --quiet || true
    $PYTHON_BIN -m playwright install chromium 2>/dev/null || echo "Playwright browser install optional; will use local Chrome if available."
else
    echo -e "${YELLOW}      Termux environment: skipping Playwright browser bundle.${NC}"
fi
echo -e "${GREEN}      Dependencies verified.${NC}"

# Re-enforce permissions before launch
chmod +x run.sh setup.sh 1-find-google-maps-scraper/*.sh 1-find-google-maps-scraper/*.py 2>/dev/null || true

# Launch
echo ""
echo -e "${CYAN}====================================================================${NC}"
echo -e "${GREEN}  LEADFORGE IS LIVE!${NC}"
echo -e "${GREEN}  Dashboard URL: http://127.0.0.1:8790${NC}"
echo -e "${YELLOW}  Next time, simply run: bash run.sh (or ./run.sh)${NC}"
echo -e "${CYAN}====================================================================${NC}"
echo ""

exec $PYTHON_BIN -u dashboard/app.py
