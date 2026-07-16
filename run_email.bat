@echo off
REM Scheduled email send (runs after run_refresh.bat). Needs .env (Claude key +
REM SMTP creds). Emails a STALE DATA / GENERATION FAILED subject if the pipeline broke.
cd /d D:\Fantasy_MLB
echo. >> "data\cache\email.log"
echo ===== EMAIL RUN %date% %time% ===== >> "data\cache\email.log"
py -3 send_daily_email.py >> "data\cache\email.log" 2>&1
echo ===== EXIT CODE %errorlevel% ===== >> "data\cache\email.log"
