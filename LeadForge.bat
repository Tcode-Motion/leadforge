@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title LeadForge Dashboard

echo ====================================================================
echo                         LEADFORGE PIPELINE                         
echo ====================================================================
echo.

echo  [1/4] Checking Python environment...
where python >nul 2>nul
if errorlevel 1 goto python_missing

for /f "tokens=*" %%V in ('python --version 2^>^&1') do set "PY_VER=%%V"
echo        Found: !PY_VER!

echo  [2/4] Setting up storage and data directories...
if not exist "dashboard\data" mkdir "dashboard\data"
if not exist "dashboard\data\logs" mkdir "dashboard\data\logs"
if not exist "dashboard\data\runs" mkdir "dashboard\data\runs"
if not exist "dashboard\data\notes" mkdir "dashboard\data\notes"
if not exist "dashboard\data\runtime" mkdir "dashboard\data\runtime"
echo        Storage folders verified.

echo  [3/4] Preparing dashboard launch token...
set "LEADFORGE_LAUNCH_TOKEN=%RANDOM%-%RANDOM%-%RANDOM%-%RANDOM%"
echo        Launch token ready.

set "LEADFORGE_INFO=%CD%\dashboard\data\server-info.json"
set "LEADFORGE_LOG=%CD%\dashboard\data\logs\leadforge.log"
set "LEADFORGE_ERROR_LOG=%CD%\dashboard\data\logs\errors.jsonl"
set "LEADFORGE_MANAGED_LAUNCH=1"
set "CHROME_CRASHPAD_PIPE_NAME="

echo  [4/4] Starting server and launching browser...
echo.

start "LeadForge browser opener" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\dashboard\wait_and_open.ps1" -InfoPath "%LEADFORGE_INFO%" -LaunchToken "%LEADFORGE_LAUNCH_TOKEN%" -LogPath "%LEADFORGE_LOG%" -TimeoutSeconds 30

python -u dashboard\app.py
set "LEADFORGE_EXIT=%ERRORLEVEL%"
if "%LEADFORGE_EXIT%"=="0" exit /b 0
if "%LEADFORGE_EXIT%"=="-1" exit /b 0
if "%LEADFORGE_EXIT%"=="130" exit /b 0
if "%LEADFORGE_EXIT%"=="-1073741510" exit /b 0
if "%LEADFORGE_EXIT%"=="3221225786" exit /b 0
goto startup_failed

:python_missing
echo.
echo ====================================================================
echo  [ERROR] Python was not found on this computer.
echo ====================================================================
echo  1. Download and install Python 3.10+ from:
echo     https://www.python.org/downloads/
echo  2. CRITICAL: Make sure to check the box:
echo     "Add python.exe to PATH" during installation.
echo  3. After installation, double-click LeadForge.bat again.
echo.
pause
exit /b 1

:startup_failed
echo.
echo ====================================================================
echo  [ERROR] LeadForge exited with code %LEADFORGE_EXIT%.
echo ====================================================================
echo  Please review the error logs:
echo    - Main log:  %LEADFORGE_LOG%
echo    - Error log: %LEADFORGE_ERROR_LOG%
echo.
pause
exit /b %LEADFORGE_EXIT%
