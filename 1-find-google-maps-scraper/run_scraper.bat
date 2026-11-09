@echo off
cd /d %~dp0
echo Finding leads. The first run also downloads a small browser, so it can take a few minutes.
echo Do not close this window while it works.
google-maps-scraper.exe -input queries.txt -results results.csv -exit-on-inactivity 3m
echo.
echo Done. Your leads are in results.csv in this folder.
pause
