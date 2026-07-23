@echo off
REM Scheduled email send (runs after run_refresh.bat). Needs .env (Claude key +
REM SMTP creds). Emails a STALE DATA / GENERATION FAILED subject if the pipeline
REM broke. D: is an external LaCie USB drive — wait for it to mount after wake.
set tries=0
:waitdrive
if exist "D:\Fantasy_MLB\send_daily_email.py" goto ready
set /a tries+=1
if %tries% geq 24 exit /b 2
timeout /t 5 /nobreak >nul
goto waitdrive
:ready
cd /d D:\Fantasy_MLB
echo. >> "data\cache\email.log"
echo ===== EMAIL RUN %date% %time% ===== >> "data\cache\email.log"
py -3 send_daily_email.py >> "data\cache\email.log" 2>&1
echo ===== EXIT CODE %errorlevel% ===== >> "data\cache\email.log"
exit /b 0
