"""
Unified roster loader — pulls all three leagues into ONE common table:
[platform, league_name, team_name, player, positions, mlb_team, salary, fg_id, mlbam, is_pitcher]

Each platform connects differently (Ottoneu real-Chrome, ESPN espn-api+cookies,
Fantrax saved cookies); this normalizes them so the analysis layer is platform-agnostic.
"""
import io
import os
import re
import pandas as pd

from . import players as P

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
os.makedirs(CACHE, exist_ok=True)

LEAGUES = {
    "ottoneu": {"league_id": "907", "team_id": "6418", "league_name": "Chasing Taters"},
    "espn":    {"league_id": 255806481, "team_id": 1, "league_name": "Moeller Analytics Minons"},
    "fantrax": {"league_id": "xkklb8bimlzfgn7d", "team_id": "n57zugwlmlzmuolo", "league_name": "TJStats Patreon League - One"},
}

PITCH_RE = re.compile(r"\b(SP|RP|P)\b", re.I)
COLS = ["platform", "league_name", "team_name", "player", "positions",
        "mlb_team", "salary", "fg_id", "mlbam", "is_pitcher"]


def _row(platform, lname, tname, player, positions, mlb_team=None, salary=None, fg_id=None):
    mlbam = P.resolve(name=player, fg_id=fg_id)
    return {
        "platform": platform, "league_name": lname, "team_name": tname,
        "player": player, "positions": positions, "mlb_team": mlb_team,
        "salary": salary, "fg_id": fg_id, "mlbam": mlbam,
        "is_pitcher": bool(positions and PITCH_RE.search(str(positions))),
    }


def load_ottoneu():
    from connectors.ottoneu import OttoneuConnector
    L = LEAGUES["ottoneu"]
    with OttoneuConnector(headless=False) as c:
        text = c.roster_export(L["league_id"])
    df = pd.read_csv(io.StringIO(text))
    mine = df[df["TeamID"].astype(str) == L["team_id"]]
    rows = []
    for _, r in mine.iterrows():
        sal = str(r.get("Salary", "")).replace("$", "").strip()
        rows.append(_row("ottoneu", L["league_name"], r.get("Team Name"),
                         r.get("Name"), r.get("Position(s)"), r.get("MLB Team"),
                         int(sal) if sal.isdigit() else None,
                         r.get("FG MajorLeagueID")))
    return rows


def load_espn():
    from connectors.espn import get_league
    L = LEAGUES["espn"]
    lg = get_league(L["league_id"], 2026)
    team = next((t for t in lg.teams if t.team_id == L["team_id"]), None)
    rows = []
    if team:
        for p in getattr(team, "roster", []):
            rows.append(_row("espn", L["league_name"], team.team_name,
                             p.name, getattr(p, "position", None),
                             getattr(p, "proTeam", None)))
    return rows


def load_fantrax():
    import connectors.fantrax as fx
    L = LEAGUES["fantrax"]
    s = fx.load_session()
    r = fx.team_roster(L["league_id"], L["team_id"], session=s)
    tname = "IDBach16"
    rows = []
    for t in r.get("tables", []):
        for row in t.get("rows", []):
            sc = row.get("scorer") or {}
            nm = sc.get("name") or sc.get("shortName")
            if not nm:
                continue
            pos = sc.get("posShortNames") or sc.get("posShortName") or ""
            rows.append(_row("fantrax", L["league_name"], tname, nm, pos,
                             sc.get("teamShortName")))
    return rows


LOADERS = {"ottoneu": load_ottoneu, "espn": load_espn, "fantrax": load_fantrax}


def load_all(refresh=True, only=None) -> pd.DataFrame:
    cache_file = os.path.join(CACHE, "rosters.csv")
    if not refresh and os.path.exists(cache_file):
        return pd.read_csv(cache_file)
    prev = pd.read_csv(cache_file) if os.path.exists(cache_file) else pd.DataFrame(columns=COLS)
    rows, pulled = [], set()
    for plat, fn in LOADERS.items():
        if only and plat not in only:
            continue
        try:
            got = fn()
            if not got:
                raise RuntimeError("returned 0 players")
            rows.extend(got)
            pulled.add(plat)
            print(f"  [{plat}] {len(got)} players")
        except Exception as e:
            print(f"  [{plat}] ERROR: {type(e).__name__} - {str(e)[:160]}")
    df = pd.DataFrame(rows, columns=COLS)
    # A failed (or skipped) platform must not wipe its players from the cache —
    # carry its previous rows forward and only replace what pulled cleanly.
    carry = prev[~prev["platform"].isin(pulled)]
    if len(carry):
        print(f"  ! kept previous cache rows for: {', '.join(sorted(carry['platform'].unique()))}")
        df = pd.concat([df, carry], ignore_index=True)
    df.to_csv(cache_file, index=False)
    return df
