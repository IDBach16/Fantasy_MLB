"""
Prospect Savant connector (prospectsavant.com -> oriolebird.pythonanywhere.com API).

Minor-league / prospect metrics incl. PS Score (`pscore`) and percentiles, keyed by
`MinorMasterId` (e.g. "sa3025333") — the SAME id Ottoneu exports as "FG MinorLeagueID",
so Ottoneu prospects join here by ID (no fuzzy name matching).

Endpoint: GET /leaders/{hitters|pitchers}/{level}/{season}/{qual}/{ageMin}/{ageMax}
"""
import os
import time
import urllib.parse
import pandas as pd
import requests

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
os.makedirs(CACHE, exist_ok=True)

BASE = "https://oriolebird.pythonanywhere.com"
LEVELS = ["AAA", "AA", "A+", "A", "Rk"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://prospectsavant.com/",
    "Origin": "https://prospectsavant.com",
}

HIT_KEEP = ["name", "MinorMasterId", "MLBAMId", "age", "level", "team", "Position", "Bats",
            "pscore", "score_p", "pa", "woba", "xwoba", "wrcplus", "iso", "bbrate", "krate",
            "chaserate", "whiffrate", "zcontact", "ev90", "maxev", "barrelpa", "bat_speed",
            "spd", "savant_url", "UPURL"]
PIT_KEEP = ["name", "MinorMasterId", "MLBAMId", "age", "level", "team", "Position", "Throws",
            "pscore", "score_p", "ip", "krate", "bbrate", "chaserate", "whiffrate", "zcontact",
            "velocity", "spin_rate", "xwoba", "woba", "savant_url", "UPURL"]


def pull_level(player_type, level, season=2026, qual=0, age_min=16, age_max=30):
    enc = urllib.parse.quote(level, safe="")
    url = f"{BASE}/leaders/{player_type}/{enc}/{season}/{qual}/{age_min}/{age_max}"
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    df = pd.DataFrame(r.json().get("data", []))
    if len(df):
        df["level"] = level
    return df


def pull_all(player_type="hitters", season=2026, refresh=False) -> pd.DataFrame:
    cache_file = os.path.join(CACHE, f"psavant_{player_type}_{season}.csv")
    if not refresh and os.path.exists(cache_file):
        return pd.read_csv(cache_file)
    frames = []
    for lv in LEVELS:
        try:
            d = pull_level(player_type, lv, season)
            frames.append(d)
            print(f"  [{player_type}/{lv}] {len(d)}")
        except Exception as e:
            print(f"  [{player_type}/{lv}] ERROR {str(e)[:100]}")
        time.sleep(1)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    keep = HIT_KEEP if player_type == "hitters" else PIT_KEEP
    df = df[[c for c in keep if c in df.columns]]
    df.to_csv(cache_file, index=False)
    return df
