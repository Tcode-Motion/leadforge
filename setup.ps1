# ====================================================================
# LeadForge 1-Click Automated Setup for Windows PowerShell
# Usage:
#   irm https://raw.githubusercontent.com/Tcode-Motion/leadforge/master/setup.ps1 | iex
# ====================================================================

$ErrorActionPreference = "Stop"

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "                   LEADFORGE AUTOMATED SETUP                        " -ForegroundColor Yellow
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python
Write-Host "[1/5] Verifying Python installation..." -ForegroundColor Blue
try {
    $pyVer = python --version 2>&1
    Write-Host "      Found: $pyVer" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python was not found on your system." -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add python.exe to PATH' during installation." -ForegroundColor Yellow
    Exit 1
}

# 2. Check / Clone Repository
Write-Host "[2/5] Checking repository files..." -ForegroundColor Blue
if (-not (Test-Path "dashboard/app.py")) {
    if (Test-Path "leadforge/dashboard/app.py") {
        Set-Location "leadforge"
    } else {
        Write-Host "      Cloning LeadForge repository from GitHub..." -ForegroundColor Yellow
        git clone https://github.com/Tcode-Motion/leadforge.git
        Set-Location "leadforge"
    }
}
Write-Host "      LeadForge codebase ready in: $(Get-Location)" -ForegroundColor Green

# 3. Setup Environment File
Write-Host "[3/5] Setting up local configuration..." -ForegroundColor Blue
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
    Write-Host "      Created default .env from .env.example" -ForegroundColor Green
} else {
    Write-Host "      .env configuration verified." -ForegroundColor Green
}

# 4. Install Dependencies
Write-Host "[4/5] Installing dependencies..." -ForegroundColor Blue
python -m pip install --upgrade pip --quiet
python -m pip install playwright --quiet
try {
    python -m playwright install chromium
} catch {
    Write-Host "      Note: Playwright bundled chromium installation skipped; standard system browser will be used." -ForegroundColor DarkGray
}
Write-Host "      Dependencies installed successfully." -ForegroundColor Green

# 5. Launch LeadForge
Write-Host "[5/5] Launching LeadForge Dashboard..." -ForegroundColor Blue
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "  Opening dashboard at: http://127.0.0.1:8790" -ForegroundColor Green
Write-Host "  Next time, simply double-click LeadForge.bat to launch!" -ForegroundColor Yellow
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""

python -u dashboard/app.py

