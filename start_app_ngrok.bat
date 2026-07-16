@echo off
REM Launches the dashboard + your PERMANENT ngrok URL (same address every reboot).
cd /d D:\Fantasy_MLB
if not exist "D:\Fantasy_MLB\bin\ngrok_domain.txt" (
  echo [!] ngrok_domain.txt not found - run setup first.
  pause & exit /b
)
set /p DOMAIN=<D:\Fantasy_MLB\bin\ngrok_domain.txt
if "%DOMAIN%"=="" ( echo [!] ngrok domain is blank. & pause & exit /b )
start "FantasyMLB Dashboard" /min py -3 -m streamlit run dashboard.py --server.headless true --server.port 8501
timeout /t 8 /nobreak >nul
start "FantasyMLB Permanent URL: https://%DOMAIN%" "D:\Fantasy_MLB\bin\ngrok.exe" http --url=https://%DOMAIN% 8501
