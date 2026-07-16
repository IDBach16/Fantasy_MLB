"""
Baseball Savant (Statcast) data via pybaseball, keyed to MLBAM player_id.
Cached to data/cache so analysis is fast and doesn't re-hit Savant every run.
"""
import os
import pandas as pd
import pybaseball as pyb

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
os.makedirs(CACHE, exist_ok=True)


def _cached(name, fn, refresh=False):
    f = os.path.join(CACHE, name)
    if not refresh and os.path.exists(f):
        return pd.read_csv(f)
    df = fn()
    df.to_csv(f, index=False)
    return df


def batting_expected(year=2026, refresh=False):
    """xwOBA / xBA / xSLG vs actual — the over/under-performer signal."""
    return _cached(f"savant_bat_xstats_{year}.csv",
                   lambda: pyb.statcast_batter_expected_stats(year, minPA=1), refresh)


def pitching_expected(year=2026, refresh=False):
    return _cached(f"savant_pit_xstats_{year}.csv",
                   lambda: pyb.statcast_pitcher_expected_stats(year, minPA=1), refresh)


def batting_barrels(year=2026, refresh=False):
    """Exit velo, barrel%, hard-hit% for hitters."""
    return _cached(f"savant_bat_barrels_{year}.csv",
                   lambda: pyb.statcast_batter_exitvelo_barrels(year, minBBE=1), refresh)
