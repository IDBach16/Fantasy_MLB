"""
Every-3-days email report for Bauers Fight Club (Ottoneu 907). Assembles standings,
cap, surplus value, trailing-3-day stats, today's games/probables, pace, available
pool, and prospects, then Claude writes the 10-section HTML email. Stats are the
trailing 3-DAY window (the cadence). Code gathers data; Claude synthesizes.
"""
import os
import json
import datetime as dt
import pandas as pd
from dotenv import load_dotenv
from anthropic import Anthropic

from analysis import rosters as R
from analysis import ottoneu_team as OT
from analysis import ottoneu_salary as OS
from analysis import free_agents as FA
from analysis import prospects as PR
from analysis import mlb_live as ML

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
MODEL = "claude-sonnet-5"  # upgraded from sonnet-4-6 (2026-07-16)

# Shared rules + section list for both report variants (Ian's + the GM's).
_CORE = (
    "Trends are in 'recent_trends': HITTERS have trailing 3/7/30-DAY windows (d3, d7, d30); PITCHERS "
    "have their last 3/6/9 OUTINGS (o3, o6, o9). "
    "Use ONLY the data provided — never invent stats, games, injuries, or names. If something isn't in "
    "the data, say it's not available. Output ONLY the HTML document itself — your reply must start "
    "with <!DOCTYPE html> and end with </html>; no preamble, no markdown fences, no commentary. "
    "Output clean, EMAIL-FRIENDLY HTML (inline styles; clear <h2> "
    "section headers; small tables; concise). Personalize everything to Bauers Fight Club using its real "
    "rank, points, cap, roster, pace, and matchups.\n\n"
    "Write these 10 sections, in order:\n"
    "1) Bauers Fight Club Snapshot — rank, total points, point change (1/7/30-day momentum), roster "
    "spots used, cap used + remaining, and whether we're gaining/losing/steady.\n"
    "2) Today's Games & Probable Starts (use 'schedule' + 'today_date') — HITTERS: for each with a "
    "'today_game', show matchup, opposing probable SP, and game time; note who has NO game today. "
    "STARTING PITCHERS: a SP is ONLY pitching when 'next_start' is set — show the actual DATE (say "
    "'starts today' only if starting_today=true, otherwise the upcoming day) and the matchup/opponent; "
    "if next_start is null, say 'next start not yet announced' and do NOT imply they pitch today. "
    "RELIEVERS: just note if team_plays_today (available) — don't predict appearances. "
    "Flag start/sit and any urgent changes before lock.\n"
    "3) Player Trends — show each notable player's trajectory across THREE windows and INTERPRET it "
    "(heating up / cooling off / steady; is the short window better or worse than the long one?). "
    "HITTERS: 3-day -> 7-day -> 30-day (d3/d7/d30) — R/HR/RBI/SB/AVG. "
    "PITCHERS: last 3 outings -> 6 outings -> 9 outings (o3/o6/o9) — IP/W/SV/K/ERA/WHIP. "
    "Don't just list numbers — explain the direction.\n"
    "4) Roster Strengths & Weaknesses — by position using surplus (avg_salary - salary) + xwOBA; "
    "strongest/weakest hitting & pitching; salary efficiency.\n"
    "5) Games-Played & Innings Pace — using games by position + IP; which spots are ahead/behind pace, "
    "wasted games, need more starts or relief.\n"
    "6) League Standing & Context — rank, gaps to teams just above/below, which categories help vs hurt, "
    "and whether to be aggressive/patient/selective.\n"
    "7) Add/Drop & Waiver — from the available pool + salaries; buckets: Add now / Drop candidate / "
    "Watchlist / Prospect stash / Streamer / Long-term value / Don't act yet. Explain fit, salary, risk, urgency.\n"
    "8) Prospect & Minor League Update — my prospects + top available prospects (PS Score); add/stash/"
    "monitor/overvalued; useful now vs later vs long-term.\n"
    "9) Injury & Risk — injured/inactive, inflated surface stats (wOBA well above xwOBA), declining "
    "trends, pitcher workload.\n"
    "10) Recommended Actions — Do today / Consider soon / Monitor only / No action needed. Simple & direct.\n\n"
)

_BUDGET = (
    "LENGTH BUDGET: the COMPLETE email must stay under ~40,000 characters of HTML — all 10 sections "
    "must fit. Tight tables, no filler. In Section 3 cover ONLY the 10-12 most notable players "
    "(hottest, coldest, role/injury changes) — not the whole roster. In Sections 7-8 keep each "
    "bucket to its best 3-5 names."
)

SYSTEM = (
    "You write the EVERY-3-DAYS fantasy baseball email for Ian's Ottoneu team "
    "**BAUERS FIGHT CLUB** (league 'Chasing Taters', Old School 5x5 ROTO dynasty, $400 cap, 40-man). "
    "The report cadence is every 3 days.\n"
    + _CORE +
    "Tone: analytical but easy to read fast. Explain why the numbers matter for Bauers Fight Club.\n"
    + _BUDGET
)

SYSTEM_GM = (
    "You are the Director of Baseball Operations for the Ottoneu team **BAUERS FIGHT CLUB** "
    "(league 'Chasing Taters', Old School 5x5 ROTO dynasty, $400 cap, 40-man roster), writing the "
    "club's FRONT OFFICE REPORT to its General Manager, **Mr. Corey Arnold**. This report goes to "
    "the GM every 6 days.\n"
    + _CORE +
    "VOICE: a professional MLB-style front-office memo written TO the GM. Open the email with a short "
    "salutation block addressed to 'Mr. Corey Arnold, General Manager — Bauers Fight Club' and one or "
    "two sentences framing the briefing. Throughout, write as staff reporting up to him: 'your club', "
    "'your roster', 'our rotation', 'we recommend', 'for your approval' — never 'my team', 'I', or "
    "'Ian'. Keep every number grounded in the provided data. In Section 10, present each move as a "
    "recommendation awaiting the GM's sign-off. End the email with a one-line sign-off from "
    "'BFC Baseball Operations'.\n"
    "Tone: authoritative, concise, decision-oriented — the GM should be able to act on it in five minutes.\n"
    + _BUDGET
)


def assemble():
    roster = R.load_all(refresh=False)
    otto = roster[roster["platform"] == "ottoneu"].copy()

    # Read the refresh job's cached standings (browser-free, robust for scheduled runs);
    # fall back to a live pull only if the cache is missing.
    _sf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache", "standings.json")
    snap = json.load(open(_sf, encoding="utf-8")) if os.path.exists(_sf) else OT.snapshot()
    value = OS.my_roster_value(refresh=False)
    cap_used = float(pd.to_numeric(value["salary"], errors="coerce").sum())

    games = ML.today_games()
    starts = ML.probable_starts(days=7)
    trends = ML.recent_windows(otto)
    today_iso = dt.date.today().isoformat()
    sched = []
    for _, r in otto.iterrows():
        is_pit = bool(r["is_pitcher"])
        mid = r["mlbam"]
        g = ML.game_for(r["mlb_team"], games)
        e = {"player": r["player"], "positions": r["positions"], "team": r["mlb_team"], "is_pitcher": is_pit}
        if is_pit:
            st = starts.get(int(mid)) if pd.notna(mid) else None
            e["role"] = "SP" if "SP" in str(r["positions"]).upper() else "RP"
            e["next_start"] = st                                   # {date, opp, home} or None
            e["starting_today"] = bool(st and st["date"] == today_iso)
            e["team_plays_today"] = bool(g)                        # reliever availability
        else:
            e["today_game"] = g                                   # {opp, opp_sp, time, home}
        sched.append(e)

    ah, ap = FA.ottoneu_available()
    av_pros = PR.available_prospects(refresh=False)
    my_pros = PR.my_prospects(refresh=False)

    def recs(df, cols, n=None):
        d = df[[c for c in cols if c in df.columns]]
        if n:
            d = d.head(n)
        return d.round(3).astype(object).where(pd.notnull(d.round(3)), None).to_dict("records")

    return {
        "as_of": dt.date.today().isoformat(),
        "cadence": "every 3 days; recent_3day stats are the trailing 3-day window",
        "cap": {"used": round(cap_used, 1), "cap": 400, "remaining": round(400 - cap_used, 1),
                "roster_spots_used": int(len(value)), "roster_max": 40},
        "snapshot": snap,
        "roster_value": recs(value, ["player", "pos", "salary", "avg_salary", "surplus", "est_woba", "p_est_woba"]),
        "recent_trends": trends,
        "schedule": sched,
        "today_date": today_iso,
        "available_hitters": recs(ah, ["player", "pa", "woba", "est_woba"], 12),
        "available_pitchers": recs(ap, ["player", "pa", "woba", "est_woba"], 12),
        "available_prospects": recs(av_pros, ["name", "ptype", "level", "age", "pscore", "score_p"], 15),
        "my_prospects": recs(my_pros, ["name", "ptype", "level", "age", "pscore", "score_p"]),
    }


def _gen(data, system, ask):
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=2)
    user = ask + "\n\n" + json.dumps(data, ensure_ascii=False, default=str)
    # Stream so the 10-section report can run long without HTTP timeouts;
    # 8000 tokens was silently truncating the email mid-section.
    with client.messages.stream(model=MODEL, max_tokens=64000, system=system,
                                messages=[{"role": "user", "content": user}]) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "max_tokens":
        print("! WARNING: report hit the 64K output cap — email may be truncated")
    # Join text blocks defensively — content[0] isn't guaranteed to be the (only) text block.
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def generate(data=None):
    """Ian's every-3-days report. Pass pre-assembled data to avoid re-pulling."""
    return _gen(data if data is not None else assemble(), SYSTEM,
                "Here is all of Bauers Fight Club's data. Write the every-3-days HTML email report "
                "(10 sections).")


def generate_gm(data=None):
    """GM-voice Front Office Report to Mr. Corey Arnold — same data, separate generation."""
    return _gen(data if data is not None else assemble(), SYSTEM_GM,
                "Here is all of Bauers Fight Club's data. Write the FRONT OFFICE REPORT to "
                "General Manager Corey Arnold (10 sections).")
