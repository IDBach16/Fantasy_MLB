"""
Prospect-finder agent — Claude turns the ranked AVAILABLE-prospect pool (Prospect
Savant x Ottoneu, computed in code) into categorized, data-backed targets.

Code does the data/ranking; Claude does the scouting judgment. No invented stats.
"""
import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

from analysis import prospects as PR

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
MODEL = "claude-sonnet-4-6"

LEAGUE_CTX = (
    "Ottoneu 'Chasing Taters' (league 907): Old School 5x5 ROTO, 12 teams, $400 salary cap, "
    "40-man rosters, FULL DYNASTY. Prospects sit on the 40-man at $1-2. "
    "5x5 categories — Batting: R, HR, RBI, SB, AVG | Pitching: W, SV, K, ERA, WHIP. "
    "So value = long-term 5x5 production at a cheap dynasty salary: power + speed + batting average "
    "for hitters; strikeouts + ratios (ERA/WHIP) + saves upside for pitchers."
)

SYSTEM = (
    "You are a sharp dynasty fantasy baseball PROSPECT SCOUT for an Ottoneu Old School 5x5 league.\n"
    "You get: (1) the user's current prospect holdings, and (2) a list of AVAILABLE prospects (on no "
    "roster) with Prospect Savant metrics. Metric guide: pscore = overall Prospect Savant quality "
    "score (higher better); score_p = percentile 0-1; age vs level is key (young for the level = "
    "better); hitters: xwoba/wrcplus/iso (power), bbrate/krate/chaserate/whiffrate (discipline+contact), "
    "ev90/bat_speed; pitchers: velocity, krate, whiffrate.\n\n"
    "Recommend which AVAILABLE prospects to target. Bucket each into exactly one of: "
    "ADD NOW, STASH, WATCHLIST, DEEP-LEAGUE, or AVOID. Rank within each bucket. For each player give a "
    "ONE-LINE data-backed reason citing the specific number(s) that matter and the 5x5 fit. "
    "Weight youth-for-level, proximity to MLB, and 5x5-relevant skills (SB speed + AVG + power for "
    "hitters; K-stuff + ratios for pitchers). Be concise and decisive. Only use the numbers provided — "
    "never invent stats. End with a 3-bullet 'bottom line: who to grab first.'"
)

HIT_COLS = ["name", "ptype", "level", "team", "age", "pscore", "score_p", "xwoba", "wrcplus",
            "iso", "bbrate", "krate", "chaserate", "whiffrate", "ev90", "bat_speed", "velocity"]


def build_payload(top_n=45):
    avail = PR.available_prospects(refresh=False)
    avail = avail[avail["pscore"].notna()]
    cols = [c for c in HIT_COLS if c in avail.columns]
    available = avail[cols].head(top_n).round(3).to_dict("records")
    mine_df = PR.my_prospects(refresh=False)
    mcols = [c for c in ["name", "ptype", "level", "age", "pscore", "score_p"] if c in mine_df.columns]
    mine = mine_df[mcols].round(3).to_dict("records") if len(mine_df) else []
    return available, mine


def find(top_n=45):
    available, mine = build_payload(top_n)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=2)
    user = (
        f"LEAGUE:\n{LEAGUE_CTX}\n\n"
        f"MY CURRENT PROSPECTS ({len(mine)}):\n{json.dumps(mine, ensure_ascii=False)}\n\n"
        f"TOP {len(available)} AVAILABLE PROSPECTS (ranked by PS Score, on no roster):\n"
        f"{json.dumps(available, ensure_ascii=False)}\n\n"
        "Give me the categorized targets."
    )
    resp = client.messages.create(model=MODEL, max_tokens=4096, system=SYSTEM,
                                  messages=[{"role": "user", "content": user}])
    return resp.content[0].text
