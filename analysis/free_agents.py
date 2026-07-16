"""
Available MLB player pools per league, joined to 2026 Savant (true-talent xwOBA).
  - ESPN:    espn-api free_agents()
  - Ottoneu: Savant leaders minus everyone rostered (by MLBAM)
(Fantrax is a 50-man dynasty — thin FA pool; added later.)
"""
import pandas as pd

from . import players as PL
from . import savant as SV
from . import prospects as PR


def _bat():
    b = SV.batting_expected(2026)[["player_id", "pa", "woba", "est_woba"]].copy()
    b["player_id"] = pd.to_numeric(b["player_id"], errors="coerce")
    return b


def _pit():
    p = SV.pitching_expected(2026)[["player_id", "pa", "woba", "est_woba"]].copy()
    p["player_id"] = pd.to_numeric(p["player_id"], errors="coerce")
    return p


def espn_available(min_pa=30, top=25):
    from connectors.espn import get_league
    lg = get_league(255806481, 2026)
    fas = lg.free_agents(size=250)
    rows = []
    for p in fas:
        rows.append({"player": p.name, "position": getattr(p, "position", None),
                     "mlb_team": getattr(p, "proTeam", None),
                     "mlbam": PL.name_to_mlbam(p.name)})
    fa = pd.DataFrame(rows)
    fa["mlbam"] = pd.to_numeric(fa["mlbam"], errors="coerce")
    hit = fa.merge(_bat(), left_on="mlbam", right_on="player_id", how="inner")
    hit = hit[hit["pa"] >= min_pa].sort_values("est_woba", ascending=False).head(top)
    pit = fa.merge(_pit(), left_on="mlbam", right_on="player_id", how="inner")
    pit = pit[pit["pa"] >= min_pa].sort_values("est_woba").head(top)
    return hit, pit


def ottoneu_available(min_pa=40, top=25):
    roster = PR.ottoneu_full_roster()
    rostered = set()
    for fg in roster["FG MajorLeagueID"].dropna():
        m = PL.fg_to_mlbam(fg)
        if m:
            rostered.add(m)
    b = _bat()
    p = _pit()
    hit = b[(~b["player_id"].isin(rostered)) & (b["pa"] >= min_pa)].sort_values("est_woba", ascending=False).head(top)
    pit = p[(~p["player_id"].isin(rostered)) & (p["pa"] >= min_pa)].sort_values("est_woba").head(top)
    # attach names
    hit = hit.assign(player=hit["player_id"].map(_name_map()))
    pit = pit.assign(player=pit["player_id"].map(_name_map()))
    return hit, pit


_NAMES = None
def _name_map():
    global _NAMES
    if _NAMES is None:
        reg = PL.register()
        _NAMES = {int(m): f"{f} {l}" for m, f, l in
                  zip(reg["key_mlbam"], reg["name_first"], reg["name_last"]) if pd.notna(m)}
    return _NAMES
