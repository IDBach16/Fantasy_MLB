@echo off
REM DAILY data-only refresh (no Claude agents, no API cost). Scheduled task
REM FantasyMLB_DataRefresh runs this every day at 11:00 AM in the interactive
REM session. D: is an external LaCie USB drive that can take a minute to mount
REM after wake — wait for it before doing anything (this was silently killing
REM every catch-up run fired seconds after wake-from-sleep).
set tries=0
:waitdrive
if exist "D:\Fantasy_MLB\refresh_all.py" goto ready
set /a tries+=1
if %tries% geq 24 exit /b 2
timeout /t 5 /nobreak >nul
goto waitdrive
:ready
cd /d D:\Fantasy_MLB
py -3 refresh_all.py --data-only >> "data\cache\refresh.log" 2>&1
REM Push fresh data to GitHub -> Streamlit Cloud redeploys with current caches.
git add data/cache data/reports >nul 2>&1
git commit -m "auto: daily data refresh" >nul 2>&1
git push origin master >nul 2>&1
exit /b 0
