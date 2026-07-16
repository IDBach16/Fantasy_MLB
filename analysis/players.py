"""
Player ID crosswalk via the Chadwick Bureau register (pybaseball).

Every platform speaks a different ID: Ottoneu gives FanGraphs IDs, ESPN/Fantrax give
names. We map them all to MLBAM ids so rosters join cleanly to Baseball Savant.
"""
import re
import unicodedata
import pandas as pd
import pybaseball as pyb

_REG = None
_FG = None      # fangraphs id -> mlbam
_NAME = None    # normalized "first last" -> mlbam


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", s)
    s = re.sub(r"[^a-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def register() -> pd.DataFrame:
    global _REG
    if _REG is None:
        _REG = pyb.chadwick_register()
    return _REG


def _build():
    global _FG, _NAME
    if _FG is not None:
        return
    df = register().copy()
    df = df[df["key_mlbam"].notna()]
    df["_recent"] = pd.to_numeric(df.get("mlb_played_last"), errors="coerce").fillna(0)
    df = df.sort_values("_recent", ascending=False)  # most-recent wins on name collisions
    _FG = {}
    for fgid, mlbam in zip(df["key_fangraphs"], df["key_mlbam"]):
        try:
            _FG.setdefault(int(fgid), int(mlbam))
        except (ValueError, TypeError):
            continue
    _NAME = {}
    for first, last, mlbam in zip(df["name_first"], df["name_last"], df["key_mlbam"]):
        nm = _norm(f"{first} {last}")
        if nm:
            _NAME.setdefault(nm, int(mlbam))


def fg_to_mlbam(fg_id):
    _build()
    try:
        return _FG.get(int(fg_id))
    except (ValueError, TypeError):
        return None


def name_to_mlbam(name):
    _build()
    return _NAME.get(_norm(name))


def resolve(name=None, fg_id=None):
    """Best-effort MLBAM id from a FanGraphs id (preferred) or a name."""
    if fg_id is not None:
        mid = fg_to_mlbam(fg_id)
        if mid:
            return mid
    if name:
        return name_to_mlbam(name)
    return None
