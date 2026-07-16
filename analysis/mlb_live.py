"""
MLB Stats API (free, no login): today's games + probables, and trailing N-day
player stats — the pieces Ottoneu doesn't expose. Powers the email's §2 (today's
games) and §3 (3-day rolling stats).
"""
import datetime as dt
import pandas as pd
import requests

API = "https://statsapi.mlb.com/api/v1"
_S = requests.Session()
_S.headers["User-Agent"] = "Mozilla/5.0"

_TEAMS = None
_ALIAS = {"OAK": "ATH", "CHW": "CWS", "ARI": "AZ", "WSN": "WSH", "SDP": "SD",
          "SFG": "SF", "TBR": "TB", "KCR": "KC"}


def _teams():
    global _TEAMS
    if _TEAMS is None:
        j = _S.get(f"{API}/teams?sportId=1", timeout=20).json()
        _TEAMS = {}
        for t in j.get("teams", []):
            _TEAMS[t["id"]] = {"abbrev": t.get("abbreviation"), "name": t.get("name")}
    return _TEAMS


def _abbrev(team_id):
    return _teams().get(team_id, {}).get("abbrev")


def today_games(date=None):
    """{team_abbrev: {opp, home, opp_sp, time_utc, status}} for today's slate."""
    date = date or dt.date.today().isoformat()
    j = _S.get(f"{API}/schedule?sportId=1&date={date}&hydrate=probablePitcher,team", timeout=20).json()
    out = {}
    for d in j.get("dates", []):
        for g in d.get("games", []):
            h = g["teams"]["home"]; a = g["teams"]["away"]
            hid, aid = h["team"]["id"], a["team"]["id"]
            hp = (h.get("probablePitcher") or {}).get("fullName")
            ap = (a.get("probablePitcher") or {}).get("fullName")
            t = g.get("gameDate"); status = g.get("status", {}).get("detailedState")
            if _abbrev(hid):
                out[_abbrev(hid)] = {"opp": a["team"]["name"], "home": True, "opp_sp": ap, "time_utc": t, "status": status}
            if _abbrev(aid):
                out[_abbrev(aid)] = {"opp": h["team"]["name"], "home": False, "opp_sp": hp, "time_utc": t, "status": status}
    return out


def probable_starts(days=7, start_date=None):
    """{pitcher_mlbam: {date, opp, home, time_utc}} of upcoming PROBABLE starts over the
    next `days`. Lets us say which DAY a starter actually pitches (not 'today' for everyone)."""
    start = start_date or dt.date.today()
    end = start + dt.timedelta(days=days - 1)
    j = _S.get(f"{API}/schedule?sportId=1&startDate={start.isoformat()}&endDate={end.isoformat()}"
               f"&hydrate=probablePitcher,team", timeout=25).json()
    out = {}
    for d in j.get("dates", []):
        date = d.get("date")
        for g in d.get("games", []):
            for side, opp in (("home", "away"), ("away", "home")):
                pp = g["teams"][side].get("probablePitcher") or {}
                pid = pp.get("id")
                if pid and int(pid) not in out:  # earliest upcoming start wins
                    out[int(pid)] = {"date": date, "opp": g["teams"][opp]["team"]["name"],
                                     "home": side == "home", "time_utc": g.get("gameDate")}
    return out


def game_for(team_code, games):
    if not team_code:
        return None
    code = str(team_code).upper()
    return games.get(code) or games.get(_ALIAS.get(code, code))


def _outs(ip_str):
    s = str(ip_str)
    if "." in s:
        whole, frac = s.split(".")
        return int(whole) * 3 + int(frac)
    return int(float(s)) * 3 if s else 0


def _agg_hit(splits):
    a = dict(runs=0, homeRuns=0, rbi=0, stolenBases=0, hits=0, atBats=0, baseOnBalls=0, strikeOuts=0)
    for sp in splits:
        st = sp["stat"]
        for k in a:
            a[k] += int(st.get(k, 0) or 0)
    a["avg"] = round(a["hits"] / a["atBats"], 3) if a["atBats"] else None
    a["games"] = len(splits)
    return a


def _agg_pit(splits):
    outs = er = k = bb = h = w = sv = 0
    for sp in splits:
        st = sp["stat"]
        outs += _outs(st.get("inningsPitched", 0))
        er += int(st.get("earnedRuns", 0) or 0); k += int(st.get("strikeOuts", 0) or 0)
        bb += int(st.get("baseOnBalls", 0) or 0); h += int(st.get("hits", 0) or 0)
        w += int(st.get("wins", 0) or 0); sv += int(st.get("saves", 0) or 0)
    ip = outs / 3
    return {"ip": round(ip, 1), "w": w, "sv": sv, "k": k,
            "era": round(er * 9 / ip, 2) if ip else None,
            "whip": round((bb + h) / ip, 2) if ip else None, "games": len(splits)}


def recent_stats(roster_df, days=3, season=2026):
    """Trailing-N-day box stats for each rostered player (single window)."""
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    rows = []
    for _, r in roster_df.iterrows():
        mid = r.get("mlbam")
        if pd.isna(mid):
            continue
        grp = "pitching" if r.get("is_pitcher") else "hitting"
        try:
            j = _S.get(f"{API}/people/{int(mid)}/stats?stats=gameLog&group={grp}&season={season}", timeout=15).json()
            splits = j.get("stats", [{}])[0].get("splits", []) if j.get("stats") else []
        except Exception:
            splits = []
        recent = [s for s in splits if s.get("date", "") >= cutoff]
        agg = _agg_pit(recent) if grp == "pitching" else _agg_hit(recent)
        rows.append({"player": r["player"], "is_pitcher": bool(r.get("is_pitcher")), **agg})
    return pd.DataFrame(rows)


def recent_windows(roster_df, hit_days=(3, 7, 30), pit_outings=(3, 6, 9), season=2026):
    """Trends per player, pulling each game log ONCE.
    Hitters: trailing 3/7/30-DAY windows -> d3/d7/d30.
    Pitchers: last 3/6/9 OUTINGS -> o3/o6/o9 (outings are more meaningful than days for arms)."""
    today = dt.date.today()
    cutoffs = {w: (today - dt.timedelta(days=w)).isoformat() for w in hit_days}
    rows = []
    for _, r in roster_df.iterrows():
        mid = r.get("mlbam")
        if pd.isna(mid):
            continue
        is_pit = bool(r.get("is_pitcher"))
        grp = "pitching" if is_pit else "hitting"
        try:
            j = _S.get(f"{API}/people/{int(mid)}/stats?stats=gameLog&group={grp}&season={season}", timeout=15).json()
            splits = j.get("stats", [{}])[0].get("splits", []) if j.get("stats") else []
        except Exception:
            splits = []
        rec = {"player": r["player"], "is_pitcher": is_pit}
        if is_pit:
            for n in pit_outings:
                rec[f"o{n}"] = _agg_pit(splits[-n:] if splits else [])
        else:
            for w in hit_days:
                recent = [s for s in splits if s.get("date", "") >= cutoffs[w]]
                rec[f"d{w}"] = _agg_hit(recent)
        rows.append(rec)
    return rows
