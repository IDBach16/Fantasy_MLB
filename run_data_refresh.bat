@echo off
REM DAILY data-only refresh (no Claude agents, no API cost). Scheduled task
REM FantasyMLB_DataRefresh runs this every day at 11:00 AM. Like the full refresh,
REM it must run in the interactive session ("Run only when user is logged on").
cd /d D:\Fantasy_MLB
py -3 refresh_all.py --data-only >> "data\cache\refresh.log" 2>&1
REM Push fresh data to GitHub -> Streamlit Cloud redeploys with current caches.
git add data/cache data/reports >nul 2>&1
git commit -m "auto: daily data refresh" >nul 2>&1
git push origin master >nul 2>&1
