"""
ESPN private-league cookie capture. Opens your REAL browser; you log into ESPN
normally. We capture the espn_s2 + SWID cookies from that session, save them to
.env (values never printed), and verify we can read your team.

Run:  python espn_setup.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from connectors.browser import RealChrome

LEAGUE_ID = 255806481
TEAM_ID = 1
SEASON = 2026
LEAGUE_URL = f"https://fantasy.espn.com/baseball/team?leagueId={LEAGUE_ID}&teamId={TEAM_ID}&seasonId={SEASON}"
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def set_env(updates: dict):
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    out, seen = [], set()
    for ln in lines:
        key = ln.split("=", 1)[0].strip() if "=" in ln else None
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(ln)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


print("=" * 60, flush=True)
print(" ESPN LOGIN — a browser window is opening.", flush=True)
print(" Log into ESPN normally; I'll capture the access cookies.", flush=True)
print("=" * 60, flush=True)

with RealChrome(start_url=LEAGUE_URL, headless=False) as rc:
    print("Waiting for ESPN login (watching for the espn_s2 cookie)...", flush=True)
    espn_s2 = swid = None
    for i in range(200):  # ~10 min
        time.sleep(3)
        try:
            jar = {c["name"]: c["value"] for c in rc.cookies()
                   if c["name"] in ("espn_s2", "SWID")}
        except Exception:
            continue
        if jar.get("espn_s2") and jar.get("SWID"):
            espn_s2, swid = jar["espn_s2"], jar["SWID"]
            break
        if i % 10 == 9:
            print(f"  still waiting... ({(i+1)*3}s)", flush=True)

    if not espn_s2:
        print("\n[X] Didn't capture ESPN cookies. Finish logging in, then re-run.", flush=True)
        sys.exit(1)

    set_env({"ESPN_S2": espn_s2, "ESPN_SWID": swid})
    print(f"\n[OK] Captured ESPN cookies (espn_s2 len={len(espn_s2)}, SWID len={len(swid)}) "
          f"-> saved to .env (values not shown).", flush=True)

    print("Verifying league access...", flush=True)
    from espn_api.baseball import League
    lg = League(league_id=LEAGUE_ID, year=SEASON, espn_s2=espn_s2, swid=swid)
    s = lg.settings
    print(f"League: {getattr(s, 'name', '?')!r} | scoring: {getattr(s, 'scoring_type', '?')} "
          f"| teams: {len(lg.teams)}", flush=True)
    me = next((t for t in lg.teams if t.team_id == TEAM_ID), None)
    if me:
        roster = [p.name for p in getattr(me, "roster", [])]
        print(f"MY TEAM: {me.team_name} | roster ({len(roster)}): {roster[:30]}", flush=True)
    else:
        print("teams:", [(t.team_id, t.team_name) for t in lg.teams][:8], flush=True)
    print("\nDone — ESPN access verified.", flush=True)
