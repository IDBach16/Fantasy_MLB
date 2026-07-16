"""
First analysis pass: join rosters to Savant and produce a per-league read —
roster offense strength, plus sell-high (overperforming) / buy-low (underperforming)
flags from the wOBA-vs-xwOBA gap.
"""
import pandas as pd
from . import savant as S

OVER = 0.030   # wOBA this far ABOVE xwOBA = overperforming (sell-high)
UNDER = -0.030  # this far BELOW = underperforming (buy-low)
MIN_PA = 40


def merge_savant(df, year=2026):
    df = df.copy()
    df["mlbam"] = pd.to_numeric(df["mlbam"], errors="coerce")
    bat = S.batting_expected(year)[["player_id", "pa", "woba", "est_woba", "ba", "est_ba", "slg", "est_slg"]].copy()
    bat["player_id"] = pd.to_numeric(bat["player_id"], errors="coerce")
    pit = S.pitching_expected(year)[["player_id", "pa", "woba", "est_woba"]].copy()
    pit.columns = ["player_id", "p_pa", "p_woba", "p_est_woba"]
    pit["player_id"] = pd.to_numeric(pit["player_id"], errors="coerce")

    df = df.merge(bat, left_on="mlbam", right_on="player_id", how="left").drop(columns=["player_id"])
    df = df.merge(pit, left_on="mlbam", right_on="player_id", how="left").drop(columns=["player_id"])
    df["bat_gap"] = (df["woba"] - df["est_woba"]).round(3)     # + over (sell-high), - under (buy-low)
    df["pit_gap"] = (df["p_woba"] - df["p_est_woba"]).round(3)  # + unlucky (buy-low), - lucky (sell-high)
    return df


def _fmt(v, nd=3):
    return "-" if pd.isna(v) else f"{v:.{nd}f}"


def league_report(df, lname) -> str:
    d = df[df["league_name"] == lname]
    out = [f"\n{'='*70}", f"  {lname}  ({d['team_name'].iloc[0] if len(d) else '?'})", f"{'='*70}"]

    hit = d[(~d["is_pitcher"]) & d["est_woba"].notna()].sort_values("est_woba", ascending=False)
    out.append(f"\n  HITTERS — by true talent (xwOBA)   [{len(hit)} with MLB data]")
    out.append(f"  {'Player':22} {'PA':>4} {'wOBA':>6} {'xwOBA':>6} {'gap':>6}")
    for _, r in hit.head(12).iterrows():
        out.append(f"  {str(r['player'])[:22]:22} {int(r['pa']):>4} {_fmt(r['woba']):>6} {_fmt(r['est_woba']):>6} {_fmt(r['bat_gap']):>6}")

    pit = d[(d["is_pitcher"]) & d["p_est_woba"].notna()].sort_values("p_est_woba")
    if len(pit):
        out.append(f"\n  PITCHERS — by xwOBA-against (lower=better)   [{len(pit)}]")
        out.append(f"  {'Player':22} {'TBF':>4} {'wOBA':>6} {'xwOBA':>6} {'gap':>6}")
        for _, r in pit.head(10).iterrows():
            out.append(f"  {str(r['player'])[:22]:22} {int(r['p_pa']):>4} {_fmt(r['p_woba']):>6} {_fmt(r['p_est_woba']):>6} {_fmt(r['pit_gap']):>6}")

    sell = hit[(hit["pa"] >= MIN_PA) & (hit["bat_gap"] >= OVER)].sort_values("bat_gap", ascending=False)
    buy = hit[(hit["pa"] >= MIN_PA) & (hit["bat_gap"] <= UNDER)].sort_values("bat_gap")
    if len(sell):
        out.append("\n  📉 SELL-HIGH (hitting over their xwOBA): " +
                   ", ".join(f"{r['player']} (+{r['bat_gap']:.3f})" for _, r in sell.head(5).iterrows()))
    if len(buy):
        out.append("\n  📈 BUY-LOW (hitting under their xwOBA): " +
                   ", ".join(f"{r['player']} ({r['bat_gap']:.3f})" for _, r in buy.head(5).iterrows()))

    prospects = d[d["mlbam"].isna()]
    if len(prospects):
        out.append(f"\n  🌱 Prospects / no-MLB-data ({len(prospects)}): " +
                   ", ".join(prospects["player"].head(10).astype(str)) +
                   (" ..." if len(prospects) > 10 else "") + "  → Prospect Savant (next phase)")
    return "\n".join(out)


def full_report(df) -> str:
    df = merge_savant(df)
    parts = ["FANTASY MLB — CROSS-LEAGUE ROSTER ANALYSIS (2026 Statcast)"]
    for lname in df["league_name"].dropna().unique():
        parts.append(league_report(df, lname))
    return "\n".join(parts)
