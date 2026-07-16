@echo off
REM Scheduled every-3-days data refresh. IMPORTANT: the Ottoneu pull drives REAL
REM (non-headless) Chrome, so the Task Scheduler entry MUST be set to
REM "Run only when user is logged on" — it cannot work in a background session.
cd /d D:\Fantasy_MLB
py -3 refresh_all.py >> "data\cache\refresh.log" 2>&1
REM Push fresh data + agent reports to GitHub -> Streamlit Cloud redeploys.
git add data/cache data/reports >nul 2>&1
git commit -m "auto: full refresh (data + agent reports)" >nul 2>&1
git push origin master >nul 2>&1
