"""
ONE-TIME Ottoneu login using your REAL Chrome (passes Cloudflare).
Opens a real Chrome window with its own saved profile. Log in normally; the session
is saved and reused from then on. No password is typed by the script.

Run:  python setup_login.py
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from connectors.ottoneu import OttoneuConnector, BASE, LOGIN_SIGNALS, CHALLENGE_SIGNALS, find_browser

print("=" * 64, flush=True)
print(" OTTONEU LOGIN  —  opening your REAL Chrome (this one passes Cloudflare).", flush=True)
print(f" browser: {find_browser()}", flush=True)
print(" 1) In the Chrome window, log into Ottoneu normally.", flush=True)
print(" 2) If a Cloudflare check shows, click it (real Chrome can pass it).", flush=True)
print(" 3) Land on your Ottoneu home — this auto-detects + saves your session.", flush=True)
print("=" * 64, flush=True)

with OttoneuConnector(headless=False, start_url=BASE + "/login") as c:
    pg = c.page()
    time.sleep(6)
    # Early diagnostic: did REAL Chrome get past Cloudflare on first load?
    try:
        html = pg.content().lower()
        if any(s in html for s in CHALLENGE_SIGNALS):
            print("[..] Cloudflare check is showing — click the checkbox in the window.", flush=True)
        else:
            print("[OK] Real Chrome reached Ottoneu (no hard block) — go ahead and log in.", flush=True)
    except Exception:
        pass

    # PASSIVE detection — we only READ the page(s); we never navigate, so we can't
    # bump you off the login screen. Just log in normally in the Chrome window.
    print("Waiting for login (just log in normally — I will NOT touch the page)...", flush=True)
    ok = False
    for i in range(200):  # ~10 minutes
        time.sleep(3)
        try:
            for p in c._ctx.pages:
                try:
                    html = p.content().lower()
                except Exception:
                    continue
                if any(s in html for s in LOGIN_SIGNALS):
                    ok = True
                    break
            if ok:
                break
        except Exception:
            pass
        if i % 10 == 9:
            print(f"  still waiting... ({(i+1)*3}s)", flush=True)

    if not ok:
        print("\n[X] Didn't detect login yet. The Chrome window stays open — "
              "finish logging in there, then tell Claude and we'll re-run discovery.", flush=True)
        sys.exit(1)

    print("\n[OK] LOGGED IN — session saved to the dedicated Chrome profile (reused next time).", flush=True)
    print("Discovering your leagues/teams...", flush=True)
    teams = c.discover_my_teams()
    leagues = {}
    for t in teams:
        leagues.setdefault(t["league_id"], []).append(t)
    print(f"\nFound {len(leagues)} league ID(s):", flush=True)
    for lid, items in leagues.items():
        label = next((x["text"] for x in items if x["text"]), "")
        print(f"  - league_id = {lid}   {('-- ' + label) if label else ''}", flush=True)
    print("\nDone. You can leave Chrome open.", flush=True)
