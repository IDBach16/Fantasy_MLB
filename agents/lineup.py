"""
Lineup agent (all 3 leagues). ESPN has live slots+injuries -> optimize the actual
lineup and flag inactive starters. Ottoneu/Fantrax -> recommend the optimal daily
lineup from the roster by position + xwOBA. Code pulls state; Claude decides start/sit.
"""
import os
import json
import pandas as pd
from dotenv import load_dotenv
from anthropic import Anthropic

from analysis import lineups as LU

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
MODEL = "claude-sonnet-4-6"

SYSTEM = (
    "You are a daily fantasy baseball LINEUP optimizer. xwOBA = true talent (for pitchers it's "
    "xwOBA-against, lower=better); woba_actual = recent results; samp = PA/TBF (small = noisy). "
    "Recommend the start/sit board for THIS league under its rules.\n\n"
    "If the data includes live 'slot' + 'injury': (1) FLAG any starter who is injured/inactive "
    "(injury not ACTIVE — e.g. OUT/IL/DAY_TO_DAY/PATERNITY) and name the bench replacement using "
    "'eligible' slots; (2) flag any clearly-better benched player who should start over a weaker starter "
    "by xwOBA. If there's no live slot data, build the OPTIMAL lineup by position from the roster by "
    "xwOBA, and list who sits.\n\n"
    "Output: the recommended STARTERS by position, the SIT/BENCH list, and a short 'changes to make "
    "before lock' list (only real, actionable moves). Cite xwOBA + injury. Be concise and decisive. "
    "Only use the data provided — never invent stats or injuries."
)

CTX = {
    "espn": "ESPN deep ROTA (redraft). Live lineup slots provided; daily lineups. Start your best healthy bats/arms; bench injured/inactive players.",
    "ottoneu": "Ottoneu Old School 5x5, daily lineups locking per-player at game time. Recommend the optimal daily lineup by position from the roster.",
    "fantrax": "Fantrax draft-&-hold (no transactions) — but you still SET A DAILY LINEUP from your 50-man. Recommend the best active lineup by position; deep bench/minors sit.",
}


def analyze(platform):
    if platform == "espn":
        df = LU.espn_lineup()
        cols = ["player", "position", "slot", "injury", "eligible", "xwoba", "woba", "samp"]
        cols = [c for c in cols if c in df.columns]
        data = df[cols].round(3)
    else:
        df = LU.roster_value(platform)
        cols = ["player", "positions", "is_pitcher", "xwoba", "woba_actual", "samp"]
        cols = [c for c in cols if c in df.columns]
        data = df[cols].round(3)
    data = data.astype(object).where(pd.notnull(data), None)
    recs = data.to_dict("records")

    user = (f"LEAGUE ({platform}): {CTX[platform]}\n\n"
            f"MY ROSTER / LINEUP STATE:\n{json.dumps(recs, ensure_ascii=False)}\n\n"
            "Give me the start/sit board and changes to make before lock.")
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=2)
    resp = client.messages.create(model=MODEL, max_tokens=2600, system=SYSTEM,
                                  messages=[{"role": "user", "content": user}])
    return resp.content[0].text


def run(platforms=None):
    if platforms is None:
        from analysis.leagues import with_capability
        platforms = with_capability("lineup")  # all three
    parts = []
    names = {"espn": "Moeller Analytics Minons", "ottoneu": "Chasing Taters",
             "fantrax": "TJStats Patreon League - One"}
    for p in platforms:
        parts.append(f"\n---\n\n## {names.get(p, p)} · {p.upper()}\n\n" + analyze(p))
    return "\n".join(parts)
