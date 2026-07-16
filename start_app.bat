@echo off
REM Launches the dashboard + a Cloudflare quick tunnel (remote URL shown in the tunnel window).
cd /d D:\Fantasy_MLB
start "FantasyMLB Dashboard" /min py -3 -m streamlit run dashboard.py --server.headless true --server.port 8501
timeout /t 8 /nobreak >nul
start "FantasyMLB Tunnel (your public URL is here)" "D:\Fantasy_MLB\bin\cloudflared.exe" tunnel --url http://localhost:8501
