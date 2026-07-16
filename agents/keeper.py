"""
Keeper / salary agent (Ottoneu only — the one keeper+salary league).

Claude classifies each rostered player KEEP / EXTEND / TRADE / CUT / MONITOR using
surplus value (Ottoneu market price - your salary) + 2026 Savant production, under
the $400-cap Old School 5x5 dynasty rules. Code computes the value; Claude judges.
"""
import os
import json
import pandas as pd
from dotenv import load_dotenv
from anthropic import Anthropic

from analysis import ottoneu_salary as OS

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
MODEL = "claude-sonnet-4-6"

SYSTEM = (
    "You are an Ottoneu KEEPER/SALARY strategist for an Old School 5x5 ROTO DYNASTY league "
    "($400 salary cap, 40-man rosters, allocation arbitration). For each rostered player you get: "
    "salary (what the user pays), avg_salary (Ottoneu market price for THIS game type), "
    "surplus (avg_salary - salary; + = bargain, - = overpaid), Roster% (how widely owned league-wide), "
    "and 2026 Savant production (woba_actual vs xwoba; xwoba is true talent — for pitchers it's "
    "xwOBA-against where lower=better; a gap = luck). samp = PA/TBF (flag small samples).\n\n"
    "Classify EVERY player into exactly one bucket: KEEP (strong surplus or cheap core), "
    "EXTEND/HOLD (cheap $1-5 with upside — lock long-term), TRADE (overpaid star or sell-high — convert "
    "to value), CUT (negative surplus + weak production + replaceable at $1-2), or MONITOR. "
    "Ottoneu nuance: keep elite talent even slightly over market, but a LARGE negative surplus on a star "
    "is a cap-efficiency / trade-for-value flag, not an auto-cut. Cheap players with positive surplus are "
    "auto-keeps. Weigh DYNASTY youth. Cite the specific salary / avg_salary / surplus and xwOBA numbers.\n\n"
    "Be decisive and concise (one line of reasoning per player is fine; group within buckets). "
    "End with a BOTTOM LINE: total salary committed vs $400 cap, count of clear keeps, and the top 2-3 "
    "cap-saving cuts or trade-for-value moves. Only use the numbers provided — never invent stats."
)


def build_payload():
    df = OS.my_roster_value(refresh=False).copy()
    df["xwoba"] = df["est_woba"].fillna(df["p_est_woba"])
    df["woba_actual"] = df["woba"].fillna(df["p_woba"])
    df["samp"] = df["pa"].fillna(df["p_pa"])
    recs = df[["player", "pos", "salary", "avg_salary", "surplus", "Roster%", "samp",
               "woba_actual", "xwoba"]].round(3)
    recs = recs.astype(object).where(pd.notnull(recs), None)
    total = float(pd.to_numeric(df["salary"], errors="coerce").sum())
    return recs.to_dict("records"), total


def analyze():
    recs, total = build_payload()
    user = (
        f"LEAGUE: Ottoneu 'Chasing Taters' (907) — Old School 5x5 dynasty, $400 cap, 40-man.\n"
        f"TOTAL SALARY COMMITTED: ${total:.0f} of $400 ({len(recs)} players rostered).\n\n"
        f"MY ROSTER (sorted by surplus, bargains first):\n{json.dumps(recs, ensure_ascii=False)}\n\n"
        "Give me keep/extend/trade/cut/monitor decisions."
    )
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=2)
    resp = client.messages.create(model=MODEL, max_tokens=3500, system=SYSTEM,
                                  messages=[{"role": "user", "content": user}])
    return resp.content[0].text
