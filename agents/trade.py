"""
Trade evaluator (Ottoneu 907 — the salary/dynasty league where trade value is richest).
Claude turns league-wide value (buy-low targets on other teams, my sell-high chips,
my roster needs) into acquisition targets, players to move, and realistic packages.
Code computes value; Claude judges fit + fairness. No invented stats.
"""
import os
import json
import pandas as pd
from dotenv import load_dotenv
from anthropic import Anthropic

from analysis import trade_targets as TT
from analysis import league_context as LC

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
MODEL = "claude-sonnet-4-6"

SYSTEM = (
    "You are an Ottoneu DYNASTY TRADE strategist (Old School 5x5 ROTO, $400 cap, 40-man) for "
    "Bauers Fight Club. This is a KEEPER/salary league, so EVERY trade must work under BOTH teams' caps.\n\n"
    "You get:\n"
    "- TEAM_CAPS: each team's cap_used / cap_space / spots_open (approx — total rostered salary; a few read "
    "over $400 because the export includes minor-leaguers, so treat that as 'no room / would need to shed').\n"
    "- ALL_TEAM_ROSTERS: each team's core players (salary + xwOBA + gap) — read their construction to infer "
    "each team's NEEDS (weak/thin positions) and SURPLUS (depth they'd move).\n"
    "- BUY_LOW_TARGETS: other-team players with strong xwOBA but lagging results (owner may sell cheap).\n"
    "- MY_SELL_HIGH: my overperformers to move while value is high. MY_ROSTER: my full team.\n"
    "gap = woba_actual - xwoba (+ overperform=sell, - underperform=buy; pitchers' xwoba is xwOBA-against, "
    "lower=better). surplus = market avg salary - salary.\n\n"
    "RULES for realistic keeper-league trades:\n"
    "- A team can only ADD a player's salary if it has the cap_space (or sheds equal/greater salary in the deal). "
    "Match salaries so BOTH teams stay <= $400.\n"
    "- Target trade PARTNERS whose roster NEED matches my SURPLUS, and who hold a buy-low chip I need. "
    "Cap-strapped teams (low/negative cap_space) are likely SELLERS; teams with room can absorb salary.\n"
    "- Respect spots_open (40-man) and dynasty youth.\n\n"
    "Output:\n"
    "1. ACQUIRE — 4-5 buy-low targets that fit my needs, with why (xwoba vs results), salary/cap fit, dynasty value, "
    "and WHICH team to target (citing their cap + roster).\n"
    "2. TRADE AWAY — my sell-high/overpaid chips to move, and the team(s) that fit them (need + cap room).\n"
    "3. PACKAGE IDEAS — 2-3 realistic, salary-matched swaps that help BOTH sides and keep BOTH under $400 "
    "(show the cap math for each side).\n"
    "Cite xwoba / gap / salary / cap numbers. Realistic value — no fleece jobs. Decisive + concise. "
    "Only use the data provided — never invent stats."
)


def _recs(df, cols, n=None):
    d = df[[c for c in cols if c in df.columns]]
    if n:
        d = d.head(n)
    d = d.round(3)
    return d.astype(object).where(pd.notnull(d), None).to_dict("records")


def build_payload():
    lv = TT.league_value()
    buy = TT.buy_low_targets(lv, n=20)
    sell = TT.my_sell_high(lv)
    mine = lv[lv["team_id"].astype(str) == TT.MY_TEAM]
    caps = LC.team_caps(lv)
    return {
        "my_team": "Bauers Fight Club",
        "cap": 400, "roster_max": 40,
        "team_caps": caps[["team", "cap_used", "cap_space", "players", "spots_open"]].to_dict("records"),
        "all_team_rosters": LC.condensed_rosters(lv, per_team=12),
        "buy_low_targets": _recs(buy, ["player", "team", "pos", "salary", "avg_salary", "surplus",
                                       "xwoba", "woba_actual", "gap", "samp"]),
        "my_sell_high": _recs(sell, ["player", "pos", "salary", "avg_salary", "surplus",
                                     "xwoba", "woba_actual", "gap"], 10),
        "my_roster": _recs(mine, ["player", "pos", "salary", "avg_salary", "surplus", "xwoba", "gap"]),
    }


def analyze():
    data = build_payload()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=2)
    user = ("Bauers Fight Club keeper-league trade analysis. Use the team caps + every team's roster to "
            "find realistic, cap-valid trades. Data below.\n\n" +
            json.dumps(data, ensure_ascii=False, default=str) +
            "\n\nGive me acquire targets, trade-away chips, and realistic salary-matched package ideas.")
    resp = client.messages.create(model=MODEL, max_tokens=4096, system=SYSTEM,
                                  messages=[{"role": "user", "content": user}])
    return resp.content[0].text
