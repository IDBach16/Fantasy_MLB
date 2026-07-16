"""
Pitch-level Statcast modeling for the fantasy pitching staff.

Pulls pitch-by-pitch data (pybaseball -> Baseball Savant) per pitcher, caches each
to data/cache/pitches_{mlbam}_{year}.csv, and derives arsenal-level metrics:
usage, velo, spin, movement (H-break / induced vertical break, inches, pitcher's view),
whiff%, CSW%, 2-strike-whiff%, xwOBA-on-contact, and run value per 100 pitches.

Everything keys off MLBAM player_id (same id the rosters/savant layers use).
"""
import os
import datetime as dt

import pandas as pd
import pybaseball as pyb

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
os.makedirs(CACHE, exist_ok=True)

# ── event sets (Statcast `description`) ──────────────────────────────────────
# whiff = true swing-and-miss (foul tips are CONTACT, so excluded — matches FanGraphs SwStr).
WHIFF = {"swinging_strike", "swinging_strike_blocked"}
# swings exclude bunt attempts entirely (not representative swings).
SWING = WHIFF | {"foul", "foul_tip", "hit_into_play"}
CALLED = {"called_strike"}

# non-competitive / unknown pitch codes to drop (pitchout, intentional, automatic, unknown)
JUNK_TYPES = {"PO", "IN", "AB", "UN"}

# minimum samples before a rate is trustworthy enough to show/color
MIN_SW, MIN_CSW, MIN_2K, MIN_BIP = 10, 10, 5, 5

# consistent Savant-ish colors per pitch code (EP/KN/SC nudged to distinct shades)
PITCH_COLORS = {
    "FF": "#d22d49", "FA": "#d22d49",           # four-seam
    "SI": "#fe9d00", "FT": "#fe9d00",           # sinker / two-seam
    "FC": "#933f2c",                            # cutter
    "SL": "#eee716", "ST": "#ddb33a", "SV": "#c7b370",  # slider / sweeper / slurve
    "CU": "#00d1ed", "KC": "#6236cd", "CS": "#4b57c9",  # curve / knuckle-curve / slow curve
    "CH": "#1dbe3a", "FS": "#3bacac", "FO": "#55a4a4",  # change / splitter / forkball
    "SC": "#a24bd6", "KN": "#7a7a7a", "EP": "#c9a227",  # screw / knuckle / eephus
}
DEFAULT_COLOR = "#9aa0a6"

# overall (all-types-blended) MLB reference points — valid for aggregate/staff coloring
BENCH = {"whiff": 0.24, "csw": 0.28, "xwobacon": 0.370, "rv100": 0.0}

# per-pitch-type MLB reference points (whiff is strongly type-dependent) — for arsenal coloring
WHIFF_BENCH = {"FF": 0.22, "FA": 0.22, "SI": 0.15, "FT": 0.15, "FC": 0.26, "SL": 0.35,
               "ST": 0.33, "SV": 0.33, "CU": 0.31, "KC": 0.32, "CS": 0.28, "CH": 0.31,
               "FS": 0.37, "FO": 0.35, "SC": 0.30, "KN": 0.20, "EP": 0.15}
CSW_BENCH = {"FF": 0.27, "FA": 0.27, "SI": 0.22, "FT": 0.22, "FC": 0.30, "SL": 0.34,
             "ST": 0.33, "SV": 0.33, "CU": 0.31, "KC": 0.32, "CS": 0.29, "CH": 0.28,
             "FS": 0.30, "FO": 0.31, "SC": 0.29, "KN": 0.25, "EP": 0.20}


def whiff_bench(pt):
    return WHIFF_BENCH.get(str(pt), BENCH["whiff"])


def csw_bench(pt):
    return CSW_BENCH.get(str(pt), BENCH["csw"])


def color_for(pt):
    return PITCH_COLORS.get(str(pt), DEFAULT_COLOR)


def _end_date(year):
    today = dt.date.today()
    cap = dt.date(year, 11, 30)
    return (today if today < cap else cap).strftime("%Y-%m-%d")


def _path(mlbam, year):
    return os.path.join(CACHE, f"pitches_{int(mlbam)}_{year}.csv")


def has_cache(mlbam, year=2026):
    return mlbam is not None and not pd.isna(mlbam) and os.path.exists(_path(mlbam, year))


def _read_cached(mlbam, year):
    """Read a cached pitch CSV defensively; empty DataFrame on missing/poisoned file. No pull."""
    if not has_cache(mlbam, year):
        return pd.DataFrame()
    try:
        return pd.read_csv(_path(mlbam, year), low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def pitcher_pitches(mlbam, year=2026, refresh=False):
    """
    Raw pitch-level DataFrame for one pitcher-season, cached to disk.
    For the CURRENT season the cache auto-refreshes once per day (end date = today);
    finished seasons are cached permanently. Empty pulls are NOT written (so they retry).
    """
    if mlbam is None or pd.isna(mlbam):
        return pd.DataFrame()
    f = _path(mlbam, year)
    if not refresh and os.path.exists(f):
        current = year >= dt.date.today().year
        fresh = (not current) or (dt.date.fromtimestamp(os.path.getmtime(f)) >= dt.date.today())
        if fresh:
            try:
                return pd.read_csv(f, low_memory=False)   # valid read (even 0 rows) is trusted
            except pd.errors.EmptyDataError:
                pass  # poisoned/empty file -> re-pull below
    df = pyb.statcast_pitcher(f"{year}-03-01", _end_date(year), int(mlbam))
    df = df if df is not None else pd.DataFrame()
    if len(df):
        df.to_csv(f, index=False)
    return df


def prep(df, recent_days=None):
    """Add computed columns; optionally trim to the last `recent_days` of data.
    HB is handedness-normalized so + is always ARM-SIDE (lefties mirrored)."""
    if df is None or not len(df):
        return pd.DataFrame()
    d = df.copy()
    d = d[d["pitch_type"].notna() & (d["pitch_type"].astype(str) != "")]
    d = d[~d["pitch_type"].astype(str).isin(JUNK_TYPES)]
    if not len(d):
        return d
    d["game_date"] = pd.to_datetime(d["game_date"], errors="coerce")
    if recent_days:
        last = d["game_date"].max()
        if pd.notna(last):
            d = d[d["game_date"] >= (last - pd.Timedelta(days=recent_days))]
    if not len(d):
        return d
    throws = d["p_throws"].dropna() if "p_throws" in d.columns else pd.Series([], dtype=object)
    hand = str(throws.iloc[0]) if len(throws) else "R"
    sign = -1.0 if hand == "L" else 1.0     # mirror LHP so +HB = arm-side for everyone
    d["HB"] = -pd.to_numeric(d["pfx_x"], errors="coerce") * 12.0 * sign
    d["IVB"] = pd.to_numeric(d["pfx_z"], errors="coerce") * 12.0
    d["velo"] = pd.to_numeric(d["release_speed"], errors="coerce")
    d["spin"] = pd.to_numeric(d["release_spin_rate"], errors="coerce")
    d["ext"] = pd.to_numeric(d["release_extension"], errors="coerce") if "release_extension" in d.columns else float("nan")
    desc = d["description"].astype(str)
    d["is_swing"] = desc.isin(SWING)
    d["is_whiff"] = desc.isin(WHIFF)
    d["is_called"] = desc.isin(CALLED)
    d["is_csw"] = d["is_whiff"] | d["is_called"]
    d["in_play"] = d["type"].astype(str).eq("X")
    d["xwobacon"] = pd.to_numeric(d["estimated_woba_using_speedangle"], errors="coerce") if "estimated_woba_using_speedangle" in d.columns else float("nan")
    d["dre"] = pd.to_numeric(d["delta_run_exp"], errors="coerce") if "delta_run_exp" in d.columns else float("nan")
    strikes = pd.to_numeric(d["strikes"], errors="coerce") if "strikes" in d.columns else pd.Series(float("nan"), index=d.index)
    d["two_strk"] = strikes.eq(2)
    return d


def summary(d):
    """Per-pitch-type arsenal table. Rate metrics are blanked (NaN) below sample floors."""
    if d is None or not len(d):
        return pd.DataFrame()
    total = len(d)
    rows = []
    for pt, g in d.groupby("pitch_type"):
        n = len(g)
        sw = int(g["is_swing"].sum())
        wh = int(g["is_whiff"].sum())
        ts = g[g["two_strk"]]
        ts_sw = int(ts["is_swing"].sum())
        ts_wh = int(ts["is_whiff"].sum())
        bip = g[g["in_play"]]
        name = str(g["pitch_name"].dropna().iloc[0]) if g["pitch_name"].notna().any() else pt
        rows.append({
            "pitch": pt, "name": name, "n": n, "usage": n / total,
            "velo": g["velo"].mean(), "velo_max": g["velo"].max(), "spin": g["spin"].mean(),
            "HB": g["HB"].mean(), "IVB": g["IVB"].mean(), "ext": g["ext"].mean(),
            "whiff": (wh / sw) if sw >= MIN_SW else float("nan"),
            "csw": (g["is_csw"].sum() / n) if n >= MIN_CSW else float("nan"),
            "ts_whiff": (ts_wh / ts_sw) if ts_sw >= MIN_2K else float("nan"),
            "xwobacon": bip["xwobacon"].mean() if len(bip) >= MIN_BIP else float("nan"),
            "rv100": -100.0 * g["dre"].mean() if g["dre"].notna().any() else float("nan"),
        })
    return pd.DataFrame(rows).sort_values("usage", ascending=False).reset_index(drop=True)


def overall(d):
    """One-row roll-up across all pitches (KPIs / staff table). fb_velo = true fastballs only."""
    if d is None or not len(d):
        return {}
    sw = int(d["is_swing"].sum())
    wh = int(d["is_whiff"].sum())
    bip = d[d["in_play"]]
    hard = d[d["pitch_type"].isin(["FF", "FA", "SI", "FT"])]   # no cutter — it's slower
    return {
        "pitches": len(d), "types": int(d["pitch_type"].nunique()),
        "fb_velo": hard["velo"].mean() if len(hard) else float("nan"),
        "velo_max": d["velo"].max(),
        "whiff": (wh / sw) if sw else float("nan"),
        "csw": d["is_csw"].sum() / len(d),
        "xwobacon": bip["xwobacon"].mean() if len(bip) else float("nan"),
        "rv100": -100.0 * d["dre"].mean() if d["dre"].notna().any() else float("nan"),
    }


def staff(pitchers, year=2026, refresh=False, only_cached=True):
    """One row per pitcher roll-up. only_cached reads disk as-is (instant, no pulls)."""
    rows, seen = [], set()
    for _, r in pitchers.iterrows():
        mid = r.get("mlbam")
        if mid is None or pd.isna(mid) or int(mid) in seen:
            continue
        seen.add(int(mid))
        if refresh:
            raw = pitcher_pitches(mid, year, refresh=True)
        elif only_cached:
            if not has_cache(mid, year):
                continue
            raw = _read_cached(mid, year)
        else:
            raw = pitcher_pitches(mid, year)
        d = prep(raw)
        o = overall(d)
        if not o:
            continue
        best = summary(d)
        best = best[best["n"] >= 15].dropna(subset=["whiff"]).sort_values("whiff", ascending=False)
        rows.append({
            "player": r.get("player"), "platform": r.get("platform"), "mlbam": int(mid), **o,
            "best_whiff_pitch": (best.iloc[0]["pitch"] if len(best) else "—"),
            "best_whiff": (best.iloc[0]["whiff"] if len(best) else float("nan")),
        })
    return pd.DataFrame(rows)


def refresh_all(pitchers, year=2026, log=print):
    """Pull + cache pitch data for every pitcher (heavy; use behind a button)."""
    done, seen = 0, set()
    for _, r in pitchers.iterrows():
        mid = r.get("mlbam")
        if mid is None or pd.isna(mid) or int(mid) in seen:
            continue
        seen.add(int(mid))
        try:
            n = len(pitcher_pitches(mid, year, refresh=True))
            done += 1
            log(f"  {r.get('player')}: {n} pitches")
        except Exception as e:
            log(f"  {r.get('player')}: ERROR {str(e)[:80]}")
    return done
