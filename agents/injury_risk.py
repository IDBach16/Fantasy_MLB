"""
Injury / Risk agent (all leagues). Claude buckets each roster's risks: injured/not
playing, regression risk (inflated surface stats), cooling off, workload/role.
Code computes signals; Claude interprets. No invented injuries.
"""
import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

from analysis import risk as RK

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
MODEL = "claude-sonnet-4-6"

SYSTEM = (
    "You are a fantasy baseball INJURY & RISK analyst. Per player you get: season xwoba/woba/gap "
    "(gap = woba - xwoba; large POSITIVE gap = overperforming = REGRESSION RISK; for pitchers xwoba is "
    "xwOBA-against, lower=better), samp (PA/TBF), recent windows (hitters: games_last_7d + last_3d/last_30d; "
    "pitchers: recent_outings_3 / _9), and injury (explicit status — ONLY ESPN has this; null elsewhere).\n\n"
    "Flag risks in buckets:\n"
    "🚑 INJURED / NOT PLAYING — explicit injury status if present; OR a regular hitter with games_last_7d "
    "near 0 (INFER 'not playing — injured or benched' and SAY it's inferred when there's no status).\n"
    "📉 REGRESSION RISK (inflated stats) — meaningful sample with a large positive gap (woba well above "
    "xwoba); their surface stats will fall — sell-high / don't trust the line.\n"
    "❄️ COOLING OFF — recent window clearly worse than the longer window / season.\n"
    "🔧 WORKLOAD / ROLE — pitchers with heavy or shrinking recent usage, tiny samples, or role risk.\n"
    "👀 MONITOR — smaller concerns.\n\n"
    "For each player: cite the specific numbers and say what to consider (bench / replace / hold / sell). "
    "Be concise and decisive. Only use the data provided; clearly mark inferred (non-ESPN) injuries as inferred."
)

NAMES = {"espn": "Moeller Analytics Minons", "ottoneu": "Chasing Taters",
         "fantrax": "TJStats Patreon League - One"}


def analyze(platform):
    data = RK.league_risk(platform)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=2)
    user = (f"LEAGUE: {NAMES.get(platform, platform)} ({platform}). Roster risk data:\n\n"
            f"{json.dumps(data, ensure_ascii=False, default=str)}\n\n"
            "Give me the injury/risk report.")
    resp = client.messages.create(model=MODEL, max_tokens=2600, system=SYSTEM,
                                  messages=[{"role": "user", "content": user}])
    return resp.content[0].text


def run(platforms=None):
    if platforms is None:
        from analysis.leagues import with_capability
        platforms = with_capability("lineup")  # risk applies wherever you hold players
    parts = []
    for p in platforms:
        parts.append(f"\n---\n\n## {NAMES.get(p, p)} · {p.upper()}\n\n" + analyze(p))
    return "\n".join(parts)
