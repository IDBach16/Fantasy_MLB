"""
Lineup state + value per league for the lineup agent.
  - ESPN: live slot + injuryStatus + eligibleSlots (optimize the actual lineup)
  - Ottoneu/Fantrax: roster + positions + xwOBA (recommend the optimal daily lineup)
All enriched with 2026 Savant true talent (xwOBA / xwOBA-against).
"""
import pandas as pd

from . import players as PL
from . import savant as SV
from . import analyze as A
from . import rosters as R


def _bat():
    b = SV.batting_expected(2026)[["player_id", "pa", "woba", "est_woba"]].copy()
    b["player_id"] = pd.to_numeric(b["player_id"], errors="coerce")
    return b


def _pit():
    p = SV.pitching_expected(2026)[["player_id", "pa", "woba", "est_woba"]].copy()
    p.columns = ["player_id", "p_pa", "p_woba", "p_est_woba"]
    p["player_id"] = pd.to_numeric(p["player_id"], errors="coerce")
    return p


def espn_lineup():
    from connectors.espn import get_league
    lg = get_league(255806481, 2026)
    team = next((t for t in lg.teams if t.team_id == 1), None)
    rows = []
    for p in getattr(team, "roster", []):
        rows.append({
            "player": p.name,
            "position": getattr(p, "position", None),
            "slot": getattr(p, "lineupSlot", None),
            "injury": getattr(p, "injuryStatus", None),
            "eligible": [s for s in getattr(p, "eligibleSlots", []) if s not in ("BE", "IL")],
            "mlbam": PL.name_to_mlbam(p.name),
        })
    df = pd.DataFrame(rows)
    df["mlbam"] = pd.to_numeric(df["mlbam"], errors="coerce")
    df = df.merge(_bat(), left_on="mlbam", right_on="player_id", how="left").drop(columns=["player_id"])
    df = df.merge(_pit(), left_on="mlbam", right_on="player_id", how="left").drop(columns=["player_id"])
    df["xwoba"] = df["est_woba"].fillna(df["p_est_woba"])
    df["samp"] = df["pa"].fillna(df["p_pa"])
    return df


def roster_value(platform):
    df = A.merge_savant(R.load_all(refresh=False))
    d = df[df["platform"] == platform].copy()
    d["xwoba"] = d["est_woba"].fillna(d["p_est_woba"])
    d["woba_actual"] = d["woba"].fillna(d["p_woba"])
    d["samp"] = d["pa"].fillna(d["p_pa"])
    return d
