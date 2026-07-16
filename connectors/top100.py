"""
Top-100 prospects from tjstats.ca (JS-rendered → pulled via real Chrome), cross-
referenced with Ottoneu rosters to show who owns each one / who's AVAILABLE.
"""
import io
import os
import time
import pandas as pd

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
os.makedirs(CACHE, exist_ok=True)
URL = "https://tjstats.ca/top-100-prospects/"


def fetch_top100():
    from connectors.browser import RealChrome
    with RealChrome(start_url=URL) as rc:
        ctx = rc.context
        pg = None
        for _ in range(40):
            time.sleep(1.5)
            pg = next((p for p in ctx.pages if "top-100" in (p.url or "")), None) or pg
            if not pg:
                continue
            try:
                html = pg.content()
            except Exception:
                continue
            if "Loading prospects" in html:
                continue
            try:
                for t in pd.read_html(io.StringIO(html)):
                    if "Name" in t.columns and len(t) >= 20:
                        return t
            except Exception:
                pass
    raise RuntimeError("Top-100 table did not populate")


def top100_with_ownership(refresh=False) -> pd.DataFrame:
    cache_file = os.path.join(CACHE, "top100.csv")
    if not refresh and os.path.exists(cache_file):
        return pd.read_csv(cache_file)
    from analysis import prospects as PR, players as PL
    df = fetch_top100()
    keep = [c for c in ["Rank", "Name", "Team", "Position", "FV", "Age"] if c in df.columns]
    df = df[keep].copy()
    roster = PR.ottoneu_full_roster()
    roster["norm"] = roster["Name"].map(PL._norm)
    owner = dict(zip(roster["norm"], roster["Team Name"]))
    df["norm"] = df["Name"].map(PL._norm)
    df["ottoneu_owner"] = df["norm"].map(owner).fillna("✅ AVAILABLE")
    df = df.drop(columns=["norm"])
    df.to_csv(cache_file, index=False)
    return df
