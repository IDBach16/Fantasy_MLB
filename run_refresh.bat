@echo off
REM Scheduled every-3-days FULL refresh (data + Claude agents). The Ottoneu pull
REM drives REAL (non-headless) Chrome, so the Task Scheduler entry MUST be
REM "Run only when user is logged on". D: is an external LaCie USB drive —
REM wait for it to mount after wake before doing anything.
set tries=0
:waitdrive
if exist "D:\Fantasy_MLB\refresh_all.py" goto ready
set /a tries+=1
if %tries% geq 24 exit /b 2
timeout /t 5 /nobreak >nul
goto waitdrive
:ready
cd /d D:\Fantasy_MLB
py -3 refresh_all.py >> "data\cache\refresh.log" 2>&1
REM Push fresh data + agent reports to GitHub -> Streamlit Cloud redeploys.
git add data/cache data/reports >nul 2>&1
git commit -m "auto: full refresh (data + agent reports)" >nul 2>&1
git push origin master >nul 2>&1
exit /b 0
