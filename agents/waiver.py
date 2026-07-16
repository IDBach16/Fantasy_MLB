"""
Waiver / add-drop agent — Claude pairs each league's AVAILABLE pool (ranked by xwOBA
true talent, computed in code) with the user's current roster (worst xwOBA first =
drop candidates) and recommends add/drop moves under that league's rules.
Code does the data; Claude does the judgment. No invented stats.
"""
import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

from analysis import free_agents as FA
from analysis import rosters as R
from analysis import analyze as A

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
MODEL = "claude-sonnet-4-6"

LEAGUES = {
    "espn": {"name": "Moeller Analytics Minons",
             "ctx": "ESPN deep ROTO, 9 teams, REDRAFT (win-now, no future value). Many categories "
                    "incl. power, speed, ratios and sabermetric stats. No salary cap. Churn free agents "
                    "aggressively for category gains; only current-season production matters."},
    "ottoneu": {"name": "Chasing Taters",
                "ctx": "Ottoneu Old School 5x5 ROTO DYNASTY, 12 teams, $400 cap, 40-man rosters. "
                       "Adds cost $1+ and count vs the cap; value = cheap 5x5 production (R/HR/RBI/SB/AVG, "
                       "W/SV/K/ERA/WHIP). Dynasty, so weigh youth/long-term too, but this is the active roster."},
}

SYSTEM = (
    "You are a fantasy baseball WAIVER-WIRE analyst. For one league you receive: AVAILABLE hitters "
    "(ranked by xwOBA = true talent) and AVAILABLE pitchers (ranked by xwOBA-against, lower=better), "
    "plus the user's CURRENT roster (hitters sorted worst-xwOBA first = drop candidates; pitchers too). "
    "wOBA = actual results, est_woba/xwOBA = deserved; a big gap flags luck. pa = sample (flag small ones).\n\n"
    "Recommend moves under THIS league's rules:\n"
    "1. TOP ADDS — the 3-5 best available, each with a SPECIFIC drop from the roster and why (the add's "
    "xwOBA beats the drop's, or fills a category need).\n"
    "2. DROP CANDIDATES — weakest rostered players (low xwOBA, overperforming their xwOBA = sell, or small role).\n"
    "3. STREAM/MONITOR — short-term or watch-list adds.\n"
    "Cite the specific xwOBA/wOBA and PA numbers. Flag small samples (<60 PA) as speculative. "
    "Tailor to the league (redraft=win-now churn; dynasty=cheap value + youth). Be decisive and concise. "
    "Only use the numbers provided — never invent stats."
)


def _payload(plat):
    if plat == "espn":
        ah, ap = FA.espn_available()
        avail_h = ah[[c for c in ["player", "position", "mlb_team", "pa", "woba", "est_woba"] if c in ah.columns]].round(3).to_dict("records")
    else:
        ah, ap = FA.ottoneu_available()
        avail_h = ah[["player", "pa", "woba", "est_woba"]].round(3).to_dict("records")
    avail_p = ap[[c for c in ["player", "mlb_team", "pa", "woba", "est_woba"] if c in ap.columns]].round(3).to_dict("records")

    df = A.merge_savant(R.load_all(refresh=False))
    mine = df[df["platform"] == plat]
    my_h = (mine[(~mine["is_pitcher"]) & mine["est_woba"].notna()]
            [["player", "positions", "pa", "woba", "est_woba"]].sort_values("est_woba").round(3).to_dict("records"))
    my_p = (mine[(mine["is_pitcher"]) & mine["p_est_woba"].notna()]
            [["player", "p_pa", "p_woba", "p_est_woba"]].sort_values("p_est_woba", ascending=False).round(3).to_dict("records"))
    return avail_h, avail_p, my_h, my_p


def analyze(plat):
    ah, ap, mh, mp = _payload(plat)
    L = LEAGUES[plat]
    user = (
        f"LEAGUE: {L['name']} — {L['ctx']}\n\n"
        f"AVAILABLE HITTERS (by xwOBA):\n{json.dumps(ah, ensure_ascii=False)}\n\n"
        f"AVAILABLE PITCHERS (by xwOBA-against, lower=better):\n{json.dumps(ap, ensure_ascii=False)}\n\n"
        f"MY HITTERS (worst xwOBA first):\n{json.dumps(mh, ensure_ascii=False)}\n\n"
        f"MY PITCHERS:\n{json.dumps(mp, ensure_ascii=False)}\n\n"
        "Give add/drop recommendations for this league."
    )
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=2)
    resp = client.messages.create(model=MODEL, max_tokens=3000, system=SYSTEM,
                                  messages=[{"role": "user", "content": user}])
    return resp.content[0].text


def run(platforms=None):
    # default: only leagues that actually allow transactions (excludes Fantrax draft-&-hold)
    if platforms is None:
        from analysis.leagues import with_capability
        platforms = [p for p in with_capability("transactions") if p in LEAGUES]
    parts = []
    for p in platforms:
        parts.append(f"\n---\n\n## {LEAGUES[p]['name']} · {p.upper()}\n\n" + analyze(p))
    return "\n".join(parts)
