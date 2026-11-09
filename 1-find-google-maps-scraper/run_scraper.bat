@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo Finding leads. The search will query verified places for your queries.
echo Do not close this window while it works.
if exist "google-maps-scraper.exe" (
    google-maps-scraper.exe -input queries.txt -results results.csv -exit-on-inactivity 3m
) else (
    python scraper.py -input queries.txt -results results.csv -exit-on-inactivity 3m
)
echo.
echo Done. Your leads are in results.csv in this folder.
pause
