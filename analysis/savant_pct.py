"""
Official Baseball Savant PERCENTILE ranks (0-100) per player — for the Savant-style
slider bars on the Player Comparison page and player cards.
"""
import os
import pandas as pd
import pybaseball as pyb

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
os.makedirs(CACHE, exist_ok=True)

# (savant column, display label) in Savant slider order
BAT_METRICS = [("xwoba", "xwOBA"), ("xba", "xBA"), ("xslg", "xSLG"), ("xobp", "xOBP"),
               ("xiso", "xISO"), ("brl_percent", "Barrel%"), ("hard_hit_percent", "Hard-Hit%"),
               ("exit_velocity", "Avg EV"), ("bat_speed", "Bat Speed"),
               ("squared_up_rate", "Squared-Up%"), ("chase_percent", "Chase%"),
               ("whiff_percent", "Whiff%"), ("k_percent", "K%"), ("bb_percent", "BB%"),
               ("sprint_speed", "Sprint Speed")]
PIT_METRICS = [("xwoba", "xwOBA"), ("xba", "xBA"), ("xslg", "xSLG"), ("xera", "xERA"),
               ("brl_percent", "Barrel%"), ("hard_hit_percent", "Hard-Hit%"),
               ("exit_velocity", "Avg EV"), ("k_percent", "K%"), ("bb_percent", "BB%"),
               ("whiff_percent", "Whiff%"), ("chase_percent", "Chase%"),
               ("fb_velocity", "FB Velo"), ("fb_spin", "FB Spin"), ("curve_spin", "Curve Spin")]


def _cached(name, fn, refresh=False):
    f = os.path.join(CACHE, name)
    if not refresh and os.path.exists(f):
        return pd.read_csv(f)
    df = fn()
    df.to_csv(f, index=False)
    return df


def batter_pct(year=2026, refresh=False):
    return _cached(f"savant_pct_bat_{year}.csv",
                   lambda: pyb.statcast_batter_percentile_ranks(year), refresh)


def pitcher_pct(year=2026, refresh=False):
    return _cached(f"savant_pct_pit_{year}.csv",
                   lambda: pyb.statcast_pitcher_percentile_ranks(year), refresh)


def player_percentiles(mlbam, is_pitcher=False, year=2026):
    """[(label, percentile 0-100), ...] for a player, or None."""
    if mlbam is None or pd.isna(mlbam):
        return None
    df = pitcher_pct(year) if is_pitcher else batter_pct(year)
    metrics = PIT_METRICS if is_pitcher else BAT_METRICS
    row = df[df["player_id"] == int(mlbam)]
    if not len(row):
        return None
    r = row.iloc[0]
    return [(label, float(r[col])) for col, label in metrics
            if col in df.columns and pd.notna(r[col])]
