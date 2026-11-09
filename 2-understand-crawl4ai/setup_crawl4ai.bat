@echo off
cd /d %~dp0
echo Setting up crawl4ai. This is one time only and can take a few minutes.
python -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install crawl4ai
crawl4ai-setup
echo.
echo Setup done. Now read HOW_TO.md in this folder.
pause
