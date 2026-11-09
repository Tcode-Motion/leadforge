@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LeadForge

echo LeadForge
echo.

where python >nul 2>nul
if errorlevel 1 goto python_missing
python --version >nul 2>nul
if errorlevel 1 goto python_missing

if not exist "dashboard\data" mkdir "dashboard\data"
if not exist "dashboard\data\logs" mkdir "dashboard\data\logs"
if not exist "dashboard\data\runs" mkdir "dashboard\data\runs"
if not exist "dashboard\data\notes" mkdir "dashboard\data\notes"
if not exist "dashboard\data\runtime" mkdir "dashboard\data\runtime"

for /f %%T in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString()"') do set "LEADFORGE_LAUNCH_TOKEN=%%T"
if not defined LEADFORGE_LAUNCH_TOKEN set "LEADFORGE_LAUNCH_TOKEN=%RANDOM%-%RANDOM%"

set "LEADFORGE_INFO=%CD%\dashboard\data\server-info.json"
set "LEADFORGE_LOG=%CD%\dashboard\data\logs\leadforge.log"
set "LEADFORGE_ERROR_LOG=%CD%\dashboard\data\logs\errors.jsonl"

echo LeadForge is starting...
echo The browser will open at the real dashboard address.
echo If the usual port is busy, LeadForge switches to a free one.
echo Keep the server window open while you use LeadForge.
echo.

start "LeadForge browser opener" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\dashboard\wait_and_open.ps1" -InfoPath "%LEADFORGE_INFO%" -LaunchToken "%LEADFORGE_LAUNCH_TOKEN%" -LogPath "%LEADFORGE_LOG%" -TimeoutSeconds 40

python dashboard\app.py
set "LEADFORGE_EXIT=%ERRORLEVEL%"
if not "%LEADFORGE_EXIT%"=="0" goto startup_failed
exit /b 0

:python_missing
echo Python was not found on this PC.
echo Install Python 3.12 from https://www.python.org/downloads/
echo Tick the box "Add python.exe to PATH" during install, then run this file again.
echo.
pause
exit /b 1

:startup_failed
echo.
echo LeadForge could not start. Nothing was hidden.
echo Read these logs:
echo %LEADFORGE_LOG%
echo %LEADFORGE_ERROR_LOG%
echo.
pause
exit /b %LEADFORGE_EXIT%
