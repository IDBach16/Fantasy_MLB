"""
Refresh job (run by Task Scheduler).
  refresh_all.py               full run: platform + Savant data, then all 6 Claude agents -> reports
  refresh_all.py --data-only   data refresh only, NO Claude agents (free — used by the DAILY task)
Needs the logged-in Chrome session (Ottoneu) + .env (Claude key). Run on Ian's PC
IN THE INTERACTIVE SESSION (Chrome is non-headless — "run only when user is
logged on" in Task Scheduler, or the Ottoneu pull cannot pass Cloudflare).
"""
import os
import sys
import json
import datetime as dt

DATA_ONLY = "--data-only" in sys.argv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dotenv import load_dotenv
load_dotenv(os.path.join(HERE, ".env"))

CACHE = os.path.join(HERE, "data", "cache")
REPORTS = os.path.join(HERE, "data", "reports")


def log(m):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {m}", flush=True)


def safe(label, fn):
    try:
        log(label + " ...")
        fn()
    except Exception as e:
        log(f"  ! {label} failed: {str(e)[:160]}")


def _dump_standings():
    from analysis import ottoneu_team as OT
    snap = OT.snapshot()
    with open(os.path.join(CACHE, "standings.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f)


log("===== REFRESH START =====")

from analysis import refresh_lock as RL
if not RL.acquire():
    log("Another refresh is already running (refresh.lock is fresh) — exiting.")
    sys.exit(0)

try:
    # 1) platform data (browser/cookies/api)
    from analysis import rosters as R, prospects as PR, ottoneu_salary as OS
    from connectors import top100 as T100
    safe("rosters (all leagues)", lambda: R.load_all(refresh=True))
    safe("ottoneu full roster", lambda: PR.ottoneu_full_roster(refresh=True))
    safe("ottoneu avg salaries", lambda: OS.load_avg_values(refresh=True))
    safe("ottoneu standings", _dump_standings)
    safe("top-100 x ownership", lambda: T100.top100_with_ownership(refresh=True))

    # 2) Savant / prospect data (public APIs)
    from analysis import savant as SV, savant_pct as SP
    safe("savant batting expected", lambda: SV.batting_expected(2026, refresh=True))
    safe("savant pitching expected", lambda: SV.pitching_expected(2026, refresh=True))
    safe("savant batter percentiles", lambda: SP.batter_pct(2026, refresh=True))
    safe("savant pitcher percentiles", lambda: SP.pitcher_pct(2026, refresh=True))
    safe("prospect savant universe", lambda: PR.ps_universe(refresh=True))

    # 3) agents -> reports (skipped on the daily --data-only run: no Claude cost)
    if DATA_ONLY:
        log("--data-only: skipping Claude agents")
    else:
        from agents import waiver, keeper, lineup, trade, prospect_finder, injury_risk
        jobs = [("waiver_add_drop.md", waiver.run), ("keeper_salary_ottoneu.md", keeper.analyze),
                ("lineups.md", lineup.run), ("trade_targets_ottoneu.md", trade.analyze),
                ("available_prospect_targets.md", prospect_finder.find), ("injury_risk.md", injury_risk.run)]
        for out, fn in jobs:
            safe(f"agent -> {out}", lambda out=out, fn=fn:
                 open(os.path.join(REPORTS, out), "w", encoding="utf-8").write(fn()))
finally:
    RL.release()

log("===== REFRESH COMPLETE =====")
