"""
Fantasy MLB Command Center — Streamlit dashboard.
Reads CACHED data + saved agent reports (fast, no API / no browser on load).
Regenerate buttons (Data & Refresh page) re-run agents / re-pull data on demand.
Run:  streamlit run dashboard.py
"""
import os
import re
import sys
import json
import glob
import datetime as dt

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
load_dotenv(os.path.join(HERE, ".env"))
REPORTS = os.path.join(HERE, "data", "reports")
CACHE = os.path.join(HERE, "data", "cache")

# On Streamlit Community Cloud there is no .env — secrets come from st.secrets.
# Mirror top-level string secrets into os.environ so the rest of the code is agnostic.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str) and _k not in os.environ:
            os.environ[_k] = _v
except Exception:
    pass

# The Ottoneu re-pull drives Ian's local Chrome — impossible on the cloud host.
IS_CLOUD = sys.platform != "win32"

st.set_page_config(page_title="Fantasy MLB Command Center", page_icon="⚾",
                   layout="wide", initial_sidebar_state="expanded")

# ───────────────────────── theme ─────────────────────────
CSS = open(os.path.join(HERE, "assets", "theme.css"), encoding="utf-8").read()
st.markdown(CSS, unsafe_allow_html=True)

# ───────────────────── access gate ─────────────────────
# The app is exposed publicly via ngrok/cloudflared, and the Data & Refresh page
# has buttons that spend Claude API credits and drive Chrome — so everything is
# password-gated. Fails CLOSED if APP_PASSWORD is missing from .env.
if not st.session_state.get("_authed"):
    _app_pw = os.environ.get("APP_PASSWORD", "")
    st.title("⚾ Fantasy MLB Command Center")
    if not _app_pw:
        st.error("APP_PASSWORD is not set in .env — add it, then restart the app.")
        st.stop()
    _pw = st.text_input("Password", type="password")
    if _pw:
        if _pw == _app_pw:
            st.session_state["_authed"] = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()


# ───────────────────────── helpers ─────────────────────────
def pct_color(p):
    if p is None or pd.isna(p):
        return "#6b7280"
    p = max(0, min(100, p))
    for thr, c in [(90, "#2b5cad"), (75, "#5a86c9"), (55, "#86a9d6"), (45, "#b8bcc2"),
                   (25, "#e0a39a"), (10, "#d4655a")]:
        if p >= thr:
            return c
    return "#c0392b"


def pct_bar(label, p, p2=None):
    p = max(0, min(100, p))
    dot1 = f'<div class="pctDot" style="left:{p}%;background:{pct_color(p)}">{int(round(p))}</div>'
    dot2 = ""
    if p2 is not None and not pd.isna(p2):
        p2 = max(0, min(100, p2))
        dot2 = f'<div class="pctDot pctDot2" style="left:{p2}%">{int(round(p2))}</div>'
    return (f'<div class="pctRow"><div class="pctLabel">{label}</div>'
            f'<div class="pctBarWrap"><div class="pctTrack"></div>{dot1}{dot2}</div></div>')


def _cell(v, avg, higher_better=True, spread=0.05):
    """Cell background tint by how far a stat is above/below league average."""
    if v is None or pd.isna(v):
        return ""
    diff = (v - avg) if higher_better else (avg - v)
    t = max(-1.0, min(1.0, diff / spread))
    if t >= 0:
        return f"background-color: rgba(70,177,127,{0.12 + 0.45 * t:.2f});"
    return f"background-color: rgba(223,101,98,{0.12 + 0.45 * (-t):.2f});"


def _cell_gap(v, spread=0.04):
    """Luck tint: + (overperforming) = amber/regression risk, - (underperforming) = cyan/buy-low."""
    if v is None or pd.isna(v):
        return ""
    t = max(-1.0, min(1.0, v / spread))
    if t >= 0:
        return f"background-color: rgba(226,162,62,{0.12 + 0.42 * t:.2f});"
    return f"background-color: rgba(34,211,238,{0.12 + 0.42 * (-t):.2f});"


def txt_color(v, avg, higher_better=True):
    if v is None or pd.isna(v):
        return "var(--muted)"
    return "var(--green)" if ((v >= avg) if higher_better else (v <= avg)) else "var(--red)"


def badge(text, kind="gray"):
    return f'<span class="badge b-{kind}">{text}</span>'


def kpi(label, value, delta=None):
    d = ""
    if delta is not None:
        cls = "delta-up" if delta >= 0 else "delta-dn"
        d = f'<div class="{cls}">{"+" if delta>=0 else ""}{delta}</div>'
    return f'<div class="card"><div class="kpi-l">{label}</div><div class="kpi">{value}</div>{d}</div>'


def show_report(filename, empty_label="Not generated yet."):
    path = os.path.join(REPORTS, filename)
    if os.path.exists(path):
        ts = dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%b %d, %I:%M %p")
        st.markdown(f"<small class='ts'>Last generated: {ts}</small>", unsafe_allow_html=True)
        body = open(path, encoding="utf-8").read()
        if filename.endswith(".html"):
            import streamlit.components.v1 as components
            components.html(body, height=820, scrolling=True)
        else:
            st.markdown(body)
    else:
        st.info(f"{empty_label}  →  generate it on the **Data & Refresh** page.")


PLOTLY = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
              font=dict(color="#c9d4e0", family="Inter, Segoe UI, sans-serif", size=12),
              margin=dict(l=8, r=8, t=54, b=8), title_font=dict(size=15, color="#e6edf3"),
              coloraxis_colorbar=dict(thickness=10),
              hoverlabel=dict(bgcolor="#161d29", bordercolor="#303c4f",
                              font=dict(family="Inter, Segoe UI, sans-serif", color="#e8eef6")))

# My-team highlight palette (matches theme.css)
MY_OTTONEU = "Bauers Fight Club"
C_ME, C_OTHER = "#22d3ee", "#3d4a5d"
C_GREEN, C_RED, C_AMBER = "#46b17f", "#df6562", "#e2a23e"


def style_fig(fig, title=None):
    fig.update_layout(**PLOTLY)
    if title:
        fig.update_layout(title=title)
    fig.update_xaxes(gridcolor="#222a36", zeroline=False, linecolor="#2a3340")
    fig.update_yaxes(gridcolor="#222a36", zeroline=False, linecolor="#2a3340")
    return fig


def _last_run(filename):
    path = os.path.join(REPORTS, filename)
    if not os.path.exists(path):
        return None
    return dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%b %d, %I:%M %p")


def _teaser(filename, n=2):
    path = os.path.join(REPORTS, filename)
    if not os.path.exists(path):
        return "—"
    out = []
    for ln in open(path, encoding="utf-8").read().splitlines():
        clean = re.sub(r"[#*`>_|]", " ", ln).strip()
        clean = re.sub(r"\s+", " ", clean)
        low = clean.lower()
        if len(clean) > 22 and not low.startswith(("league", "cadence", "as of", "total salary")):
            out.append(clean)
        if len(out) >= n:
            break
    return " · ".join(out)[:170] if out else "—"


def agent_section(filename, agent_name):
    ts = _last_run(filename)
    if ts:
        st.markdown(f'<div class="agentbox"><span class="agent-tag">🤖 {agent_name} AGENT</span>'
                    f'<small class="ts">&nbsp;&nbsp;generated {ts}</small></div>', unsafe_allow_html=True)
        st.markdown(open(os.path.join(REPORTS, filename), encoding="utf-8").read())
    else:
        st.info(f"The **{agent_name} agent** hasn't run yet — run it on the **Data & Refresh** page.")


# ───────────────────────── cached data (cache-only, no browser) ─────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def d_rosters():
    from analysis import rosters as R
    return R.load_all(refresh=False)


@st.cache_data(ttl=900, show_spinner=False)
def d_value():
    from analysis import analyze as A
    df = A.merge_savant(d_rosters())
    df["xwoba"] = df["est_woba"].fillna(df["p_est_woba"])
    df["woba_a"] = df["woba"].fillna(df["p_woba"])
    df["gap"] = (df["woba_a"] - df["xwoba"]).round(3)
    df["samp"] = df["pa"].fillna(df["p_pa"])
    return df


@st.cache_data(ttl=900, show_spinner=False)
def d_surplus():
    from analysis import ottoneu_salary as OS
    return OS.my_roster_value(refresh=False)


@st.cache_data(ttl=900, show_spinner=False)
def d_caps():
    from analysis import league_context as LC
    return LC.team_caps()


@st.cache_data(ttl=900, show_spinner=False)
def d_prospects():
    from analysis import prospects as PR
    return PR.available_prospects(refresh=False)


@st.cache_data(ttl=900, show_spinner=False)
def d_pct(mlbam, is_pitcher):
    from analysis import savant_pct as SP
    return SP.player_percentiles(mlbam, is_pitcher)


@st.cache_data(ttl=900, show_spinner=False)
def d_league_avgs():
    from analysis import savant as SV
    b = SV.batting_expected(2026)
    p = SV.pitching_expected(2026)
    bq = b[b["pa"] >= 50]
    pq = p[p["pa"] >= 50]
    return {"hit_xwoba": float(bq["est_woba"].mean()), "hit_woba": float(bq["woba"].mean()),
            "pit_xwoba": float(pq["est_woba"].mean()), "pit_woba": float(pq["woba"].mean())}


def d_standings():
    f = os.path.join(CACHE, "standings.json")
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else None


CATS = ["R", "HR", "RBI", "SB", "AVG", "WINS", "SV", "K", "ERA", "WHIP"]
LOW_GOOD = {"ERA", "WHIP"}  # raw stat: lower = better


def _num(v):
    """First number in a standings cell — cells can be '10.5 0.5' (points + day change)."""
    if v is None:
        return None
    m = re.search(r"-?\d+\.?\d*", str(v))
    return float(m.group()) if m else None


@st.cache_data(ttl=900, show_spinner=False)
def d_std_frames():
    """standings.json parsed into clean numeric DataFrames (or None if not cached)."""
    snap = d_standings()
    if not snap:
        return None
    pts = pd.DataFrame(snap.get("standings_categories", []))
    if pts.empty or "Team" not in pts.columns:
        return None
    for c in CATS + ["Total", "Chg"]:
        if c in pts.columns:
            pts[c] = pts[c].map(_num)
    pts = pts.sort_values("Total", ascending=False).reset_index(drop=True)
    pts["Rank"] = range(1, len(pts) + 1)
    tot = pd.DataFrame(snap.get("standings_totals", []))
    for c in tot.columns:
        if c != "Team":
            tot[c] = pd.to_numeric(tot[c], errors="coerce")
    mom = pd.DataFrame(snap.get("points_change_1_7_30_day", []))
    for c in ("1-Day", "7-Day", "30-Day"):
        if c in mom.columns:
            mom[c] = pd.to_numeric(mom[c], errors="coerce")
    gp = pd.DataFrame(snap.get("games_played_by_position", []))
    return {"pts": pts, "tot": tot, "mom": mom, "gp": gp,
            "cats": [c for c in CATS if c in pts.columns],
            "hit": pd.DataFrame(snap.get("my_hitters", [])),
            "pit": pd.DataFrame(snap.get("my_pitchers", []))}


def season_elapsed():
    """Fraction of the MLB season elapsed (games-pace yardstick)."""
    start, end = dt.date(2026, 3, 26), dt.date(2026, 9, 27)
    return max(0.0, min(1.0, (dt.date.today() - start).days / (end - start).days))


def league_levers(f, team=MY_OTTONEU):
    """Per category: the raw-stat gap to GAIN a roto point (pass the next tier up)
    and the cushion to DEFEND against the nearest chaser. sigma = gap / league std."""
    pts, tot, cats = f["pts"], f["tot"], f["cats"]
    merow = pts[pts["Team"] == team]
    trow = tot[tot["Team"] == team]
    if merow.empty or trow.empty:
        return {"gains": [], "defends": []}
    merow, trow = merow.iloc[0], trow.iloc[0]
    gains, defends = [], []
    for c in cats:
        if c not in tot.columns or pd.isna(merow[c]) or pd.isna(trow[c]):
            continue
        sd = float(tot[c].std()) or 1.0
        mine_raw = float(trow[c])
        above = pts[pts[c] > merow[c]]
        if len(above):
            tier = above[above[c] == above[c].min()]["Team"]
            raws = tot[tot["Team"].isin(tier)][c].dropna()
            if len(raws):
                target = float(raws.max() if c in LOW_GOOD else raws.min())
                gap = max((mine_raw - target) if c in LOW_GOOD else (target - mine_raw), 0.0)
                who = tot[(tot["Team"].isin(tier)) & (tot[c] == target)]["Team"]
                gains.append({"cat": c, "gap": round(gap, 4), "sigma": round(gap / sd, 3),
                              "pass_team": who.iloc[0] if len(who) else tier.iloc[0],
                              "direction": "lower" if c in LOW_GOOD else "raise"})
        below = pts[pts[c] < merow[c]]
        if len(below):
            tier = below[below[c] == below[c].max()]["Team"]
            raws = tot[tot["Team"].isin(tier)][c].dropna()
            if len(raws):
                chaser_v = float(raws.min() if c in LOW_GOOD else raws.max())
                cushion = max((chaser_v - mine_raw) if c in LOW_GOOD else (mine_raw - chaser_v), 0.0)
                who = tot[(tot["Team"].isin(tier)) & (tot[c] == chaser_v)]["Team"]
                defends.append({"cat": c, "cushion": round(cushion, 4), "sigma": round(cushion / sd, 3),
                                "chaser": who.iloc[0] if len(who) else tier.iloc[0]})
    return {"gains": gains, "defends": defends}


def d_top100():
    f = os.path.join(CACHE, "top100.csv")
    return pd.read_csv(f) if os.path.exists(f) else None


@st.cache_data(ttl=900, show_spinner=False)
def d_prospect_universe(player_type):
    from connectors import prospect_savant as PS
    from analysis import prospects as PR
    df = PS.pull_all(player_type, 2026).copy()
    df["pscore"] = pd.to_numeric(df["pscore"], errors="coerce")
    df["score_p"] = pd.to_numeric(df.get("score_p"), errors="coerce")
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    roster = PR.ottoneu_full_roster()
    own = {str(r["FG MinorLeagueID"]): r["Team Name"] for _, r in roster.iterrows()
           if pd.notna(r["FG MinorLeagueID"])}
    df["ottoneu"] = df["MinorMasterId"].astype(str).map(own).fillna("✅ Available")
    df["primary_pos"] = df["Position"].astype(str).str.split("/").str[0]
    return df


@st.cache_data(ttl=1800, show_spinner=False)
def d_my_pitchers():
    v = d_value()
    p = v[(v["is_pitcher"]) & v["mlbam"].notna()].copy()
    p["mlbam"] = p["mlbam"].astype(int)
    p = p.drop_duplicates("mlbam")
    p["key"] = p["player"].astype(str) + "  (" + p["platform"].astype(str) + ")"
    return p.sort_values("player")


@st.cache_data(ttl=1800, show_spinner=False)
def d_arsenal(mlbam, year, recent_days):
    from analysis import pitch_model as PM
    return PM.prep(PM.pitcher_pitches(mlbam, year), recent_days=recent_days)


@st.cache_data(ttl=1800, show_spinner=False)
def d_staff_pitch(year):
    from analysis import pitch_model as PM
    return PM.staff(d_my_pitchers(), year, only_cached=True)


LEAGUES = {"ottoneu": "Chasing Taters", "espn": "Moeller Analytics Minons",
           "fantrax": "TJStats Patreon League - One"}
TEAMS = {"ottoneu": "Bauers Fight Club", "espn": "Whiff Rate Wreckers", "fantrax": "IDBach16"}


# ───────────────────────── pages ─────────────────────────
def page_overview():
    st.markdown('<div class="hero">⚾ Command <span>Center</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">All leagues at a glance · cached data</div>', unsafe_allow_html=True)
    st.write("")
    val = d_value()
    avgs = d_league_avgs()
    try:
        surplus = d_surplus()
        cap_used = float(pd.to_numeric(surplus["salary"], errors="coerce").sum())
    except Exception:
        cap_used = None
    cols = st.columns(3)
    for i, (plat, lname) in enumerate(LEAGUES.items()):
        d = val[val["platform"] == plat]
        hit = d[~d["is_pitcher"]]
        avg_x = hit["xwoba"].dropna().mean()
        inj = int((d["samp"].fillna(0) == 0).sum())
        with cols[i]:
            cap_line = ""
            if plat == "ottoneu" and cap_used is not None:
                cap_line = f'<div class="kpi-l" style="margin-top:8px">Cap</div><div>${cap_used:.0f} / $400 · ${400-cap_used:.0f} left</div>'
            st.markdown(
                f'<div class="card accent"><div style="font-size:17px;font-weight:800">{TEAMS[plat]}</div>'
                f'<div class="sub">{lname} · {plat.upper()}</div><hr>'
                f'<div class="kpi-l">Roster</div><div class="kpi">{len(d)}</div>'
                f'<div class="kpi-l" style="margin-top:8px">Avg hitter xwOBA '
                f'<span style="color:var(--muted);text-transform:none;letter-spacing:0;font-weight:500">vs MLB {avgs["hit_xwoba"]:.3f}</span></div>'
                f'<div style="font-size:22px;font-weight:800;font-family:var(--mono);'
                f'color:{txt_color(avg_x, avgs["hit_xwoba"])}">{avg_x:.3f}</div>'
                f'{cap_line}'
                f'<div style="margin-top:10px">{badge(f"{inj} no recent data", "yellow") if inj else badge("healthy","green")}</div>'
                f'</div>', unsafe_allow_html=True)
    st.write("")

    # ── Ottoneu pulse: where Bauers Fight Club sits right now ──
    f = d_std_frames()
    if f is not None and (f["pts"]["Team"] == MY_OTTONEU).any():
        import plotly.graph_objects as go
        pts = f["pts"]
        me = pts[pts["Team"] == MY_OTTONEU].iloc[0]
        mrow = f["mom"][f["mom"]["Team"] == MY_OTTONEU]
        d7 = float(mrow["7-Day"].iloc[0]) if len(mrow) else 0.0
        d30 = float(mrow["30-Day"].iloc[0]) if len(mrow) else 0.0
        st.subheader("Ottoneu pulse")
        pc1, pc2, pc3, pc4 = st.columns([1, 1, 1, 3])
        pc1.markdown(kpi("Rank", f"{int(me['Rank'])} <span style='font-size:.55em;color:var(--muted)'>of {len(pts)}</span>"),
                     unsafe_allow_html=True)
        pc2.markdown(kpi("Points", f"{me['Total']:g}", delta=round(d7, 1)), unsafe_allow_html=True)
        pc3.markdown(kpi("30-day", f"{d30:+g}"), unsafe_allow_html=True)
        with pc4:
            p = pts.sort_values("Total")
            names = [t if len(t) <= 14 else t[:13] + "…" for t in p["Team"]]
            fig = go.Figure(go.Bar(
                x=p["Total"], y=names, orientation="h",
                marker=dict(color=[C_ME if t == MY_OTTONEU else C_OTHER for t in p["Team"]])))
            style_fig(fig)
            fig.update_layout(height=250, margin=dict(l=8, r=8, t=8, b=8),
                              xaxis_title="", yaxis_title="",
                              yaxis=dict(tickfont=dict(size=10)))
            st.plotly_chart(fig, width="stretch")
        st.write("")

    # ── luck chart: buy-low vs sell-high across all three leagues ──
    st.subheader("Quick highlights")
    lk = val[(val["gap"].abs() > 0.03) & (val["samp"] >= 60)].copy()
    if len(lk):
        import plotly.graph_objects as go
        lk = pd.concat([lk.sort_values("gap").head(7), lk.sort_values("gap").tail(7)]).drop_duplicates("player")
        lk = lk.sort_values("gap")
        lk["lbl"] = lk["player"] + "  ·  " + lk["platform"]
        fig = go.Figure(go.Bar(
            x=lk["gap"], y=lk["lbl"], orientation="h",
            text=[f"{w:.3f} vs x{x:.3f}" for w, x in zip(lk["woba_a"], lk["xwoba"])],
            textposition="outside",
            marker=dict(color=[C_GREEN if g < 0 else C_RED for g in lk["gap"]], line=dict(width=0))))
        fig.add_vline(x=0, line_color="#3a4655")
        style_fig(fig, "Luck index — wOBA vs expected  ·  ◀ buy-low (due to heat up)   sell-high (due to cool off) ▶")
        pad = float(lk["gap"].abs().max()) * 1.45
        fig.update_layout(height=440, xaxis_title="wOBA − xwOBA", yaxis_title="",
                          xaxis_range=[-pad, pad])
        st.plotly_chart(fig, width="stretch")
    st.write("")
    st.subheader("🤖 AI Agent Recommendations")
    st.caption("Latest output from each AI agent — open its page for the full analysis.")
    agents = [("lineups.md", "Lineup", "⚡ Action Center"),
              ("waiver_add_drop.md", "Waiver / Add-Drop", "⚡ Action Center"),
              ("keeper_salary_ottoneu.md", "Keeper / Salary", "💰 Ottoneu Value"),
              ("trade_targets_ottoneu.md", "Trade", "💱 Trade Center"),
              ("available_prospect_targets.md", "Prospect", "🌱 Prospect Hub"),
              ("injury_risk.md", "Injury / Risk", "⚡ Action Center")]
    acols = st.columns(3)
    for i, (f, nm, where) in enumerate(agents):
        with acols[i % 3]:
            st.markdown(f'<div class="agent-card"><span class="nm">🤖 {nm}</span>'
                        f'<div class="tz">{_last_run(f) or "not run yet"} · {where}</div>'
                        f'<div class="ts2">{_teaser(f)}</div></div>', unsafe_allow_html=True)


def page_action():
    st.markdown('<div class="hero">⚡ Today\'s Action Center</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">What to do before lineup locks</div>', unsafe_allow_html=True)
    st.write("")
    tabs = st.tabs(["🟢 Lineups", "🔄 Add / Drop", "🚑 Injury / Risk"])
    with tabs[0]:
        agent_section("lineups.md", "Lineup")
    with tabs[1]:
        agent_section("waiver_add_drop.md", "Waiver / Add-Drop")
    with tabs[2]:
        agent_section("injury_risk.md", "Injury / Risk")


@st.cache_data(ttl=900, show_spinner=False)
def d_chat_context(deep: bool):
    """Everything the Analyst needs to reason about the league, as one JSON-able dict.
    deep=True adds live MLB trends/schedules via the email agent's assemble() (slow first load)."""
    def recs(df, n=None):
        d = df if n is None else df.head(n)
        d = d.round(3)
        return d.astype(object).where(pd.notnull(d), None).to_dict("records")

    ctx = {"as_of": dt.date.today().isoformat(),
           "my_team": MY_OTTONEU,
           "league": "Chasing Taters — Ottoneu Old School 5x5 roto DYNASTY, $400 cap, 40-man roster",
           "season_pct_elapsed": round(season_elapsed(), 3),
           "games_caps": {"C": 162, "1B": 162, "2B": 162, "SS": 162, "MI": 162, "3B": 162,
                          "OF": 810, "Util": 162, "IP": 1500}}
    f = d_std_frames()
    if f:
        ctx["standings_points_by_category"] = recs(f["pts"])
        ctx["raw_category_totals"] = recs(f["tot"])
        ctx["points_change_1_7_30_day"] = recs(f["mom"])
        ctx["games_played_by_position"] = recs(f["gp"])
        ctx["category_levers"] = league_levers(f)
        ctx["my_season_hitters"] = recs(f["hit"])
        ctx["my_season_pitchers"] = recs(f["pit"])
    try:
        ctx["my_roster_value"] = recs(d_surplus()[["player", "pos", "salary", "avg_salary",
                                                   "surplus", "est_woba", "p_est_woba"]])
    except Exception:
        pass
    try:
        ctx["league_cap_situations"] = recs(d_caps())
    except Exception:
        pass
    try:
        v = d_value()
        lk = v[v["gap"].notna() & (v["samp"].fillna(0) >= 60)]
        lk = pd.concat([lk.nsmallest(15, "gap"), lk.nlargest(15, "gap")]).drop_duplicates("player")
        ctx["statcast_luck_watch"] = recs(lk[["player", "platform", "positions", "xwoba", "woba_a",
                                              "gap", "samp"]].sort_values("gap"))
    except Exception:
        pass
    try:
        ctx["top_available_prospects"] = recs(
            d_prospects()[["name", "ptype", "level", "team", "age", "pscore"]], 15)
    except Exception:
        pass
    t100 = d_top100()
    if t100 is not None and "ottoneu_owner" in t100.columns:
        av = t100[t100["ottoneu_owner"].astype(str).str.contains("AVAILABLE")]
        cols = [c for c in ["Rank", "Name", "Position", "FV", "Age"] if c in av.columns]
        ctx["top100_prospects_available_in_my_league"] = recs(av[cols], 25)
    if deep:
        try:
            from agents import daily_email as DE
            d = DE.assemble()
            ctx["today_schedule_and_probables"] = d.get("schedule")
            ctx["recent_trends"] = d.get("recent_trends")
            ctx["available_hitters"] = d.get("available_hitters")
            ctx["available_pitchers"] = d.get("available_pitchers")
        except Exception as e:
            ctx["deep_data_error"] = f"{type(e).__name__}: {e}"
    return ctx


CHAT_SYSTEM = (
    "You are the lead analyst and assistant GM for **BAUERS FIGHT CLUB**, Ian's team in the Ottoneu "
    "league 'Chasing Taters' (Old School 5x5 roto DYNASTY, $400 cap, 40-man). You're chatting with Ian "
    "inside his dashboard. Your job: analyze the league situation and find the moves that make his team "
    "better, short- and long-term.\n"
    "Ground EVERY claim in the DATA below — never invent stats, players, or injuries; if something isn't "
    "in the data, say so plainly. Key structures: 'category_levers' gives the exact raw-stat gap to GAIN "
    "a roto point in each category (and the cushion to DEFEND); 'statcast_luck_watch' is wOBA vs xwOBA "
    "(negative gap = buy-low, positive = sell-high/regression); 'my_roster_value' has salary vs market "
    "(surplus); 'league_cap_situations' shows which rivals can absorb salary in trades; games caps are "
    "hard Ottoneu limits.\n"
    "Style: direct, numbers-first, specific player names, concise — short paragraphs, bullets, small "
    "tables. Think roto strategy: cheapest points first, dynasty timeline (compete vs build), cap "
    "efficiency. When a question is ambiguous or a decision hinges on something you can't see, ask ONE "
    "sharp clarifying question. End multi-part answers with a one-line **Bottom line**.\n\nDATA:\n")


def _stream_answer(system, msgs):
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=2)
    with client.messages.stream(model="claude-sonnet-5", max_tokens=4000,
                                system=system, messages=msgs) as stream:
        yield from stream.text_stream


def page_analyst():
    st.markdown('<div class="hero">🧠 Ask the <span>Analyst</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Chat with an AI analyst that has your whole league situation loaded — '
                'standings math, roster value, luck, cap space, prospects</div>', unsafe_allow_html=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("ANTHROPIC_API_KEY is not set in .env.")
        return
    st.write("")
    tc1, tc2, tc3 = st.columns([2, 2, 1])
    deep = tc1.toggle("Live trends & today's schedules (slower first question)", value=False)
    use_reports = tc2.toggle("Include latest agent reports", value=False)
    if tc3.button("🧹 Clear chat"):
        st.session_state["analyst_chat"] = []
        st.rerun()
    hist = st.session_state.setdefault("analyst_chat", [])

    STARTERS = ["📈 How do I climb out of last place?",
                "🎯 Which categories should I target first, and how?",
                "💱 What trades should I explore — and with which teams?",
                "🔮 Compete now or build for next year? Lay out the plan."]
    q = None
    if not hist:
        sc = st.columns(2)
        for i, s in enumerate(STARTERS):
            if sc[i % 2].button(s, width="stretch"):
                q = s.split(" ", 1)[1]
    for m in hist:
        with st.chat_message(m["role"], avatar="🧢" if m["role"] == "user" else "🧠"):
            st.markdown(m["content"])
    typed = st.chat_input("Ask about your team, the standings, trades, prospects, strategy…")
    q = typed or q
    if not q:
        if not hist:
            st.caption("Pick a starter question or type your own. Each answer costs a few cents of "
                       "Claude API — data reloads every 15 min.")
        return
    hist.append({"role": "user", "content": q})
    with st.chat_message("user", avatar="🧢"):
        st.markdown(q)
    with st.chat_message("assistant", avatar="🧠"):
        try:
            with st.spinner("Reading the league…"):
                ctx = d_chat_context(deep)
                if use_reports:
                    ctx = dict(ctx)
                    ctx["agent_reports"] = {
                        os.path.basename(p): open(p, encoding="utf-8").read()[:5000]
                        for p in glob.glob(os.path.join(REPORTS, "*.md"))}
            system = CHAT_SYSTEM + json.dumps(ctx, ensure_ascii=False, default=str)
            msgs = [{"role": m["role"], "content": m["content"]} for m in hist[-12:]]
            text = st.write_stream(_stream_answer(system, msgs))
        except Exception as e:
            text = f"⚠ The analyst hit an error: {type(e).__name__}: {e}"
            st.error(text)
    hist.append({"role": "assistant", "content": text})


def page_team():
    st.markdown('<div class="hero">📋 Team Dashboard</div>', unsafe_allow_html=True)
    plat = st.radio("League", list(LEAGUES), format_func=lambda p: f"{TEAMS[p]} ({p})", horizontal=True)
    val = d_value()
    d = val[val["platform"] == plat].copy()
    avgs = d_league_avgs()
    hit = d[(~d["is_pitcher"]) & d["xwoba"].notna()].sort_values("xwoba", ascending=False)
    pit = d[(d["is_pitcher"]) & d["xwoba"].notna()].sort_values("xwoba")
    c1, c2, c3 = st.columns(3)
    c1.markdown(kpi("Roster", len(d)), unsafe_allow_html=True)
    c2.markdown(kpi("Your avg hitter xwOBA", f'{hit["xwoba"].mean():.3f}'), unsafe_allow_html=True)
    c3.markdown(kpi("MLB avg xwOBA", f'{avgs["hit_xwoba"]:.3f}'), unsafe_allow_html=True)
    st.write("")

    # ── roster quality at a glance ──
    import plotly.graph_objects as go

    def _quality_fig(df, avg, higher_better, title, xlab):
        q = df.copy()
        q["diff"] = (q["xwoba"] - avg) if higher_better else (avg - q["xwoba"])
        q = q.sort_values("diff")
        fig = go.Figure(go.Bar(
            x=q["diff"], y=q["player"], orientation="h",
            text=[f"{v:.3f}" for v in q["xwoba"]], textposition="outside",
            marker=dict(color=[C_GREEN if v >= 0 else C_RED for v in q["diff"]], line=dict(width=0))))
        fig.add_vline(x=0, line_color="#3a4655")
        style_fig(fig, title)
        pad = max(float(q["diff"].abs().max()) * 1.5, 0.02)
        fig.update_layout(height=max(300, 26 * len(q) + 90), xaxis_title=xlab, yaxis_title="",
                          xaxis_range=[-pad, pad])
        return fig

    g1, g2 = st.columns(2)
    with g1:
        if len(hit):
            st.plotly_chart(_quality_fig(hit, avgs["hit_xwoba"], True,
                                         "Hitters vs MLB average — xwOBA (right = better)",
                                         f"xwOBA − MLB avg ({avgs['hit_xwoba']:.3f})"),
                            width="stretch")
    with g2:
        if len(pit):
            st.plotly_chart(_quality_fig(pit, avgs["pit_xwoba"], False,
                                         "Pitchers vs MLB average — xwOBA against (right = better)",
                                         f"MLB avg ({avgs['pit_xwoba']:.3f}) − xwOBA against"),
                            width="stretch")

    st.subheader("Hitters — colored vs MLB league average")
    st.caption(f"🟢 above MLB avg · 🔴 below  (MLB hitter xwOBA ≈ {avgs['hit_xwoba']:.3f}, wOBA ≈ {avgs['hit_woba']:.3f}).  "
               "gap → 🟡 overperforming (regression risk) · 🔵 underperforming (buy-low).")
    hc = hit[["player", "positions", "xwoba", "woba_a", "gap", "samp"]].rename(columns={"woba_a": "woba"})
    hsty = (hc.style
            .map(lambda v: _cell(v, avgs["hit_xwoba"], True, 0.05), subset=["xwoba"])
            .map(lambda v: _cell(v, avgs["hit_woba"], True, 0.06), subset=["woba"])
            .map(_cell_gap, subset=["gap"])
            .format({"xwoba": "{:.3f}", "woba": "{:.3f}", "gap": "{:+.3f}", "samp": "{:.0f}"}, na_rep="—"))
    st.dataframe(hsty, width="stretch", hide_index=True)

    st.subheader("Pitchers — xwOBA-against, colored vs MLB league average")
    st.caption(f"🟢 better than MLB avg · 🔴 worse  (lower xwOBA-against = better; MLB ≈ {avgs['pit_xwoba']:.3f}).  "
               "gap → 🔵 unlucky (buy-low) · 🟡 lucky (regression risk).")
    pc = pit[["player", "positions", "xwoba", "woba_a", "gap", "samp"]].rename(
        columns={"woba_a": "woba", "xwoba": "xwOBA_against"})
    psty = (pc.style
            .map(lambda v: _cell(v, avgs["pit_xwoba"], False, 0.05), subset=["xwOBA_against"])
            .map(lambda v: _cell(v, avgs["pit_woba"], False, 0.06), subset=["woba"])
            .map(lambda v: _cell_gap(-v), subset=["gap"])
            .format({"xwOBA_against": "{:.3f}", "woba": "{:.3f}", "gap": "{:+.3f}", "samp": "{:.0f}"}, na_rep="—"))
    st.dataframe(psty, width="stretch", hide_index=True)


def page_compare():
    st.markdown('<div class="hero">⚖️ Player Comparison</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Baseball Savant percentile ranks · 0 = worst, 100 = best in MLB</div>',
                unsafe_allow_html=True)
    val = d_value()
    named = val[val["mlbam"].notna()].copy()
    named["key"] = named["player"] + "  (" + named["platform"] + ")"
    options = sorted(named["key"].unique())
    c1, c2 = st.columns(2)
    a = c1.selectbox("Player A", options, index=options.index(next((o for o in options if "Elly" in o), options[0])))
    b = c2.selectbox("Player B", options, index=options.index(next((o for o in options if "Soto" in o), options[1])))
    ra = named[named["key"] == a].iloc[0]
    rb = named[named["key"] == b].iloc[0]
    pa = d_pct(int(ra["mlbam"]), bool(ra["is_pitcher"]))
    pb = d_pct(int(rb["mlbam"]), bool(rb["is_pitcher"]))
    st.markdown(f'<div class="legend"><span class="dot-leg" style="background:#2b5cad"></span>'
                f'<b>{ra["player"]}</b> (colored dot) &nbsp;&nbsp;'
                f'<span class="dot-leg" style="background:#fff;border:2px solid var(--gold)"></span>'
                f'<b>{rb["player"]}</b> (gold-ring dot)</div>', unsafe_allow_html=True)
    st.write("")
    if not pa:
        st.warning(f"No Savant percentile data for {ra['player']} (prospect or insufficient MLB sample).")
        return
    pb_map = {lbl: v for lbl, v in (pb or [])}
    t1, t2 = st.tabs(["📊 Percentile bars", "🕸 Shape (radar)"])
    with t1:
        rows = "".join(pct_bar(lbl, v, pb_map.get(lbl)) for lbl, v in pa)
        st.markdown(f'<div class="card">{rows}</div>', unsafe_allow_html=True)
    with t2:
        import plotly.graph_objects as go
        labels = [lbl for lbl, _ in pa]
        va = [v for _, v in pa]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=va + va[:1], theta=labels + labels[:1], fill="toself",
                                      name=ra["player"], line=dict(color="#22d3ee", width=2),
                                      fillcolor="rgba(34,211,238,.18)"))
        if pb_map:
            vb = [pb_map.get(lbl) for lbl in labels]
            if all(v is not None for v in vb):
                fig.add_trace(go.Scatterpolar(r=vb + vb[:1], theta=labels + labels[:1], fill="toself",
                                              name=rb["player"], line=dict(color="#f4c531", width=2),
                                              fillcolor="rgba(244,197,49,.14)"))
        fig.update_layout(**PLOTLY)
        fig.update_layout(height=560, polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(range=[0, 100], gridcolor="#222a36", tickfont=dict(size=10)),
            angularaxis=dict(gridcolor="#222a36")),
            legend=dict(orientation="h", y=-0.06, x=0.5, xanchor="center"))
        st.plotly_chart(fig, width="stretch")
        st.caption("Percentile ranks, 0–100 — bigger shape = better across the board.")
    if not pb:
        st.caption(f"({rb['player']} has no Savant percentile data — showing {ra['player']} only.)")


def page_pitch_lab():
    st.markdown('<div class="hero">🔬 Pitch <span>Lab</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Pitch-by-pitch Statcast · arsenal shape, movement, whiff & run value</div>',
                unsafe_allow_html=True)
    import plotly.express as px
    import plotly.graph_objects as go
    from analysis import pitch_model as PM

    def _fmt(v, fmt, pct=False):
        if v is None or pd.isna(v):
            return "—"
        return fmt.format(v * 100 if pct else v)

    tabs = st.tabs(["🎯 Single Pitcher", "📊 Staff Overview"])

    # ── single-pitcher deep dive ──
    with tabs[0]:
        mp = d_my_pitchers()
        if not len(mp):
            st.info("No rostered pitchers with MLB ids — run a roster refresh.")
        else:
            keys = mp["key"].tolist()
            default = next((k for k in keys if "Webb" in k), keys[0])
            c1, c2 = st.columns([3, 2])
            sel = c1.selectbox("Pitcher", keys, index=keys.index(default))
            tf = c2.radio("Window", ["Full 2026", "Last 30 days"], horizontal=True)
            mid = int(mp[mp["key"] == sel].iloc[0]["mlbam"])
            recent = 30 if tf == "Last 30 days" else None
            if not PM.has_cache(mid, 2026):
                st.caption("⏳ First load for this pitcher pulls live from Savant (a few seconds) then caches. "
                           "Pull them all at once on **Data & Refresh**.")
            d = d_arsenal(mid, 2026, recent)
            if not len(d):
                st.info("No pitch data in this window.")
            else:
                s = PM.summary(d)
                o = PM.overall(d)
                hand = str(d["p_throws"].dropna().iloc[0]) if ("p_throws" in d.columns and d["p_throws"].notna().any()) else "?"
                handlbl = {"L": "LHP", "R": "RHP"}.get(hand, "")
                k = st.columns(6)
                k[0].markdown(kpi("Pitches", o["pitches"]), unsafe_allow_html=True)
                k[1].markdown(kpi("Pitch types", o["types"]), unsafe_allow_html=True)
                k[2].markdown(kpi("FB velo", _fmt(o["fb_velo"], "{:.1f}")), unsafe_allow_html=True)
                k[3].markdown(kpi("Whiff%", _fmt(o["whiff"], "{:.1f}%", pct=True)), unsafe_allow_html=True)
                k[4].markdown(kpi("CSW%", _fmt(o["csw"], "{:.1f}%", pct=True)), unsafe_allow_html=True)
                k[5].markdown(kpi("xwOBAcon", _fmt(o["xwobacon"], "{:.3f}")), unsafe_allow_html=True)
                st.write("")
                cmap = {pt: PM.color_for(pt) for pt in d["pitch_type"].unique()}
                g1, g2 = st.columns([3, 2])
                with g1:
                    fig = px.scatter(d, x="HB", y="IVB", color="pitch_type", color_discrete_map=cmap,
                                     opacity=0.45, height=470,
                                     hover_data={"velo": ":.1f", "HB": ":.1f", "IVB": ":.1f"})
                    fig.update_traces(marker=dict(size=6, line=dict(width=0)))
                    cent = d.groupby("pitch_type").agg(HB=("HB", "mean"), IVB=("IVB", "mean")).reset_index()
                    fig.add_trace(go.Scatter(
                        x=cent["HB"], y=cent["IVB"], mode="markers+text", text=cent["pitch_type"],
                        textposition="top center", showlegend=False,
                        marker=dict(size=16, color=[cmap[p] for p in cent["pitch_type"]],
                                    line=dict(width=2, color="#0d1117")),
                        textfont=dict(color="#e6edf3", size=12)))
                    fig.add_hline(y=0, line_color="#2a3340")
                    fig.add_vline(x=0, line_color="#2a3340")
                    style_fig(fig, f"Pitch movement · {handlbl} (pitcher's view, in)")
                    fig.update_layout(xaxis_title="← glove side    horizontal break    arm side →",
                                      yaxis_title="induced vertical break", legend_title="")
                    st.plotly_chart(fig, width="stretch")
                with g2:
                    fig2 = px.box(d, x="velo", y="pitch_type", color="pitch_type",
                                  color_discrete_map=cmap, height=470, points=False)
                    style_fig(fig2, "Velocity by pitch")
                    fig2.update_layout(showlegend=False, yaxis_title="", xaxis_title="MPH")
                    st.plotly_chart(fig2, width="stretch")

                st.subheader("Arsenal")
                disp = s.rename(columns={
                    "pitch": "Pitch", "name": "Name", "usage": "Usage", "n": "#", "velo": "Velo",
                    "spin": "Spin", "ext": "Ext", "whiff": "Whiff%", "csw": "CSW%",
                    "ts_whiff": "2K whiff%", "xwobacon": "xwOBAcon", "rv100": "RV/100"})[
                    ["Pitch", "Name", "Usage", "#", "Velo", "Spin", "HB", "IVB", "Ext",
                     "Whiff%", "CSW%", "2K whiff%", "xwOBAcon", "RV/100"]]

                def _ars(row):
                    out = pd.Series("", index=row.index)
                    pt = row["Pitch"]
                    out["Whiff%"] = _cell(row["Whiff%"], PM.whiff_bench(pt), True, 0.10)
                    out["CSW%"] = _cell(row["CSW%"], PM.csw_bench(pt), True, 0.10)
                    out["xwOBAcon"] = _cell(row["xwOBAcon"], PM.BENCH["xwobacon"], False, 0.08)
                    out["RV/100"] = _cell(row["RV/100"], PM.BENCH["rv100"], True, 3.0)
                    return out

                sty = (disp.style.apply(_ars, axis=1)
                       .format({"Usage": "{:.1%}", "Velo": "{:.1f}", "Spin": "{:.0f}", "HB": "{:+.1f}",
                                "IVB": "{:+.1f}", "Ext": "{:.1f}", "Whiff%": "{:.1%}", "CSW%": "{:.1%}",
                                "2K whiff%": "{:.1%}", "xwOBAcon": "{:.3f}", "RV/100": "{:+.2f}"}, na_rep="—"))
                st.dataframe(sty, width="stretch", hide_index=True)
                st.caption(
                    "Movement = pitcher's view, inches — IVB = induced vertical; **HB + = arm-side"
                    + (", lefties mirrored" if hand == "L" else "") + "**. "
                    "Whiff% = swinging strike ÷ swings (foul tips are contact, excluded) · "
                    "CSW% = called + swinging ÷ pitches · 2K whiff% = whiff rate on 2-strike swings · "
                    "xwOBAcon = contact quality allowed (lower = better) · "
                    "RV/100 = run value per 100 pitches, pitcher's view (+ = good; opposite sign to Savant's RV). "
                    "Rate cells below a min sample are blanked; green/red = vs that pitch type's MLB average.")

                cc = s.dropna(subset=["whiff"]).sort_values("whiff")
                if len(cc):
                    figb = px.bar(cc, x="whiff", y="pitch", orientation="h", color="pitch",
                                  color_discrete_map=cmap, height=340,
                                  text=cc["whiff"].map(lambda v: f"{v*100:.0f}%"))
                    style_fig(figb, "Whiff% by pitch")
                    figb.update_layout(showlegend=False, yaxis_title="", xaxis_title="Whiff%")
                    figb.update_xaxes(tickformat=".0%")
                    st.plotly_chart(figb, width="stretch")

    # ── staff overview ──
    with tabs[1]:
        stf = d_staff_pitch(2026)
        if not len(stf):
            st.info("No pitch data cached yet — go to **Data & Refresh → Pull pitch-by-pitch data** "
                    "to pull all your pitchers (a few minutes), then this fills in.")
        else:
            st.caption(f"{len(stf)} pitchers with cached data · sorted by run value · "
                       "🟢 better than MLB avg · 🔴 worse. Pull more on Data & Refresh.")
            disp = stf[["player", "platform", "pitches", "types", "fb_velo", "whiff", "csw",
                        "xwobacon", "rv100", "best_whiff_pitch", "best_whiff"]].sort_values("rv100", ascending=False)
            sty = (disp.style
                   .map(lambda v: _cell(v, PM.BENCH["whiff"], True, 0.08), subset=["whiff"])
                   .map(lambda v: _cell(v, PM.BENCH["csw"], True, 0.08), subset=["csw"])
                   .map(lambda v: _cell(v, PM.BENCH["xwobacon"], False, 0.06), subset=["xwobacon"])
                   .map(lambda v: _cell(v, PM.BENCH["rv100"], True, 3.0), subset=["rv100"])
                   .format({"fb_velo": "{:.1f}", "whiff": "{:.1%}", "csw": "{:.1%}", "xwobacon": "{:.3f}",
                            "rv100": "{:+.2f}", "best_whiff": "{:.1%}"}, na_rep="—"))
            st.dataframe(sty, width="stretch", hide_index=True, height=480)
            fig = px.scatter(stf, x="xwobacon", y="whiff", size="pitches", color="rv100",
                             color_continuous_scale=[(0, "#e74c3c"), (0.5, "#9aa0a6"), (1, "#2ecc71")],
                             hover_name="player", height=470,
                             hover_data={"fb_velo": ":.1f", "csw": ":.1%", "platform": True})
            fig.update_traces(marker=dict(line=dict(width=1, color="#0d1117")))
            style_fig(fig, "Staff: whiff% vs contact quality allowed (up + left = dominant)")
            fig.update_layout(xaxis_title="xwOBA on contact (lower = better) →", yaxis_title="Whiff%")
            fig.update_yaxes(tickformat=".0%")
            st.plotly_chart(fig, width="stretch")


def page_value():
    st.markdown('<div class="hero">💰 Ottoneu Value Center</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Salary vs market vs production · surplus = market − your salary</div>',
                unsafe_allow_html=True)
    try:
        s = d_surplus().copy()
    except Exception as e:
        st.info("Surplus data not cached yet — run a refresh.")
        return
    s["xwoba"] = s["est_woba"].fillna(s["p_est_woba"])
    import plotly.express as px
    plot = s.dropna(subset=["avg_salary", "salary"]).copy()
    fig = px.scatter(plot, x="salary", y="avg_salary", color="surplus",
                     color_continuous_scale=[(0, "#e74c3c"), (0.5, "#9aa0a6"), (1, "#2ecc71")],
                     hover_name="player",
                     hover_data={"pos": True, "surplus": True, "salary": True, "avg_salary": True},
                     height=480)
    mx = float(max(plot["salary"].max(), plot["avg_salary"].max())) + 4
    fig.add_shape(type="line", x0=0, y0=0, x1=mx, y1=mx, line=dict(color="#3a4655", dash="dash"))
    fig.add_annotation(x=mx * 0.22, y=mx * 0.86, text="BARGAINS", showarrow=False,
                       font=dict(color="#2ecc71", size=13, family="Segoe UI"))
    fig.add_annotation(x=mx * 0.84, y=mx * 0.16, text="OVERPAID", showarrow=False,
                       font=dict(color="#e74c3c", size=13, family="Segoe UI"))
    fig.update_traces(marker=dict(size=13, line=dict(width=1, color="#0d1117")))
    style_fig(fig, "Your salary vs Ottoneu market — above the dashed line = surplus value")
    fig.update_layout(xaxis_title="Your salary ($)", yaxis_title="Ottoneu market salary ($)")
    st.plotly_chart(fig, width="stretch")

    sv = plot.dropna(subset=["surplus"]).copy()
    if len(sv):
        import plotly.graph_objects as go
        sv = pd.concat([sv.nlargest(8, "surplus"), sv.nsmallest(8, "surplus")]).drop_duplicates("player")
        sv = sv.sort_values("surplus")
        fig2 = go.Figure(go.Bar(
            x=sv["surplus"], y=sv["player"], orientation="h",
            text=[f"${sa:g} → mkt ${av:g}" for sa, av in zip(sv["salary"], sv["avg_salary"])],
            textposition="outside",
            marker=dict(color=[C_GREEN if v >= 0 else C_RED for v in sv["surplus"]], line=dict(width=0))))
        fig2.add_vline(x=0, line_color="#3a4655")
        style_fig(fig2, "Biggest bargains & biggest overpays — surplus $ (market − your salary)")
        pad = float(sv["surplus"].abs().max()) * 1.5
        fig2.update_layout(height=470, xaxis_title="surplus $", yaxis_title="", xaxis_range=[-pad, pad])
        st.plotly_chart(fig2, width="stretch")

    with st.expander("Full roster value table"):
        st.dataframe(s[["player", "pos", "salary", "avg_salary", "surplus", "xwoba"]]
                     .sort_values("surplus", ascending=False), width="stretch", hide_index=True)
    st.divider()
    st.subheader("Keeper / salary recommendations")
    agent_section("keeper_salary_ottoneu.md", "Keeper / Salary")


def page_prospects():
    st.markdown('<div class="hero" style="color:#b9a3ff">🌱 Prospect Hub</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Prospect Savant · long-term upside · available in Ottoneu</div>',
                unsafe_allow_html=True)
    try:
        av = d_prospects()
    except Exception:
        st.info("Prospect data not cached yet — run a refresh.")
        return
    maxage = st.slider("Max age", 16, 28, 23)
    top = av[(av["pscore"].notna()) & (av["age"] <= maxage)].head(40)
    import plotly.express as px
    tb = top.head(18).sort_values("pscore")
    fig = px.bar(tb, x="pscore", y="name", orientation="h", color="pscore",
                 color_continuous_scale=["#3a2a6b", "#8e6cf0", "#c4b3ff"], height=560,
                 hover_data=["level", "age", "team"])
    fig.update_traces(marker_line_color="#0d1117", marker_line_width=1)
    style_fig(fig, "Top available prospects by PS Score")
    fig.update_layout(yaxis_title="", xaxis_title="PS Score", coloraxis_showscale=False)
    st.plotly_chart(fig, width="stretch")
    st.dataframe(top[["name", "ptype", "level", "team", "age", "pscore", "score_p"]],
                 width="stretch", hide_index=True)
    st.divider()
    st.subheader("🏆 Top 100 Prospects (tjstats.ca) × Ottoneu ownership")
    t100 = d_top100()
    if t100 is not None:
        avail = int(t100["ottoneu_owner"].astype(str).str.contains("AVAILABLE").sum())
        c1, c2 = st.columns([1, 2])
        c1.markdown(kpi("Top-100 available in your league", f"{avail} / 100"), unsafe_allow_html=True)
        only_av = st.checkbox("Show only AVAILABLE", value=False)
        show = t100[t100["ottoneu_owner"].astype(str).str.contains("AVAILABLE")] if only_av else t100
        cols = [c for c in ["Rank", "Name", "Position", "FV", "Age", "ottoneu_owner"] if c in show.columns]
        st.dataframe(show[cols].rename(columns={"ottoneu_owner": "Ottoneu Owner"}),
                     width="stretch", hide_index=True, height=460)
    else:
        st.info("Top-100 not cached yet — run **Refresh** on the Data & Refresh page.")
    st.divider()
    agent_section("available_prospect_targets.md", "Prospect")


def page_prospect_explorer():
    st.markdown('<div class="hero" style="color:#b9a3ff">🔎 Prospect Explorer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Filter the full Prospect Savant universe — PS Score, level, age, position, Ottoneu availability</div>',
                unsafe_allow_html=True)
    ptype = st.radio("Type", ["hitters", "pitchers"], format_func=str.title, horizontal=True)
    try:
        df = d_prospect_universe(ptype)
    except Exception as e:
        st.info(f"Prospect data not available: {e}")
        return

    c1, c2, c3, c4 = st.columns(4)
    levels = c1.multiselect("Level", ["AAA", "AA", "A+", "A", "Rk"], default=["AAA", "AA", "A+", "A", "Rk"])
    positions = sorted(df["primary_pos"].dropna().unique().tolist())
    pos_sel = c2.multiselect("Position", positions, default=[])
    amin, amax = int(df["age"].min()), int(df["age"].max())
    age_rng = c3.slider("Age", amin, amax, (amin, min(24, amax)))
    avail = c4.selectbox("Ottoneu", ["All", "Available only", "Rostered only"])
    c5, c6 = st.columns([1, 2])
    ps_max = int(df["pscore"].max()) if df["pscore"].notna().any() else 60
    min_ps = c5.slider("Min PS Score", 0, ps_max, 0)
    search = c6.text_input("Search name", placeholder="e.g. Nimmala")

    f = df[df["level"].isin(levels) & df["age"].between(*age_rng) & (df["pscore"] >= min_ps)]
    if pos_sel:
        f = f[f["primary_pos"].isin(pos_sel)]
    if avail == "Available only":
        f = f[f["ottoneu"].str.contains("Available")]
    elif avail == "Rostered only":
        f = f[~f["ottoneu"].str.contains("Available")]
    if search:
        f = f[f["name"].str.contains(search, case=False, na=False)]
    f = f.sort_values("pscore", ascending=False)

    k1, k2, k3 = st.columns(3)
    k1.markdown(kpi("Matches", len(f)), unsafe_allow_html=True)
    k2.markdown(kpi("Available (Ottoneu)", int(f["ottoneu"].str.contains("Available").sum())), unsafe_allow_html=True)
    k3.markdown(kpi("Avg PS Score", f'{f["pscore"].mean():.1f}' if len(f) else "—"), unsafe_allow_html=True)
    st.write("")

    if ptype == "hitters":
        cols = ["name", "age", "level", "Position", "ottoneu", "pscore", "score_p", "pa", "xwoba",
                "wrcplus", "iso", "bbrate", "krate", "whiffrate", "chaserate", "ev90", "bat_speed", "spd"]
    else:
        cols = ["name", "age", "level", "Position", "ottoneu", "pscore", "score_p", "ip", "xwoba",
                "krate", "bbrate", "whiffrate", "chaserate", "velocity", "spin_rate"]
    cols = [c for c in cols if c in f.columns]
    st.dataframe(f[cols], width="stretch", hide_index=True, height=560, column_config={
        "score_p": st.column_config.ProgressColumn("PS %ile", min_value=0.0, max_value=1.0, format="%.2f"),
        "pscore": st.column_config.NumberColumn("PS Score", format="%.1f"),
        "ottoneu": st.column_config.TextColumn("Ottoneu"),
    })

    import plotly.express as px
    top = f.head(15).sort_values("pscore")
    if len(top):
        fig = px.bar(top, x="pscore", y="name", orientation="h", color="pscore",
                     color_continuous_scale=["#3a2a6b", "#8e6cf0", "#c4b3ff"], height=460,
                     hover_data=[c for c in ["level", "age", "ottoneu"] if c in top.columns])
        fig.update_traces(marker_line_color="#0d1117", marker_line_width=1)
        style_fig(fig, "Top matches by PS Score")
        fig.update_layout(yaxis_title="", xaxis_title="PS Score", coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")


def page_trades():
    st.markdown('<div class="hero">💱 Trade Center</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Ottoneu · cap-aware buy-low / sell-high</div>', unsafe_allow_html=True)
    try:
        caps = d_caps()
        st.subheader("League cap situations")
        import plotly.graph_objects as go
        cp = caps.sort_values("cap_space")
        names = [t if len(t) <= 16 else t[:15] + "…" for t in cp["team"]]
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=cp["cap_used"], y=names, orientation="h", name="used",
            marker=dict(color=[C_ME if t == MY_OTTONEU else C_OTHER for t in cp["team"]],
                        line=dict(width=0)),
            text=[f"${u:g}" for u in cp["cap_used"]], textposition="inside",
            insidetextanchor="end", textfont=dict(color="#0a0e14")))
        fig.add_trace(go.Bar(
            x=cp["cap_space"], y=names, orientation="h", name="space",
            marker=dict(color="rgba(70,177,127,.35)", line=dict(width=0)),
            text=[f"${s:g} · {int(o)} spots" for s, o in zip(cp["cap_space"], cp["spots_open"])],
            textposition="inside", textfont=dict(color="#d9efe4")))
        fig.add_vline(x=400, line_dash="dash", line_color="#3a4655")
        style_fig(fig, "Cap room by team — who can actually take salary back in a trade")
        fig.update_layout(barmode="stack", height=430, xaxis_title="$ of the $400 cap",
                          yaxis_title="", legend=dict(orientation="h", y=1.06, x=1, xanchor="right"))
        st.plotly_chart(fig, width="stretch")
        st.caption("Green tail = open cap space (with open roster spots). Teams at the top are the "
                   "easiest trade partners for salary dumps; teams at the bottom need salary back.")
        with st.expander("Cap table"):
            st.dataframe(caps[["team", "cap_used", "cap_space", "players", "spots_open"]],
                         width="stretch", hide_index=True)
    except Exception:
        st.info("Cap data not cached — run a refresh.")
    st.divider()
    agent_section("trade_targets_ottoneu.md", "Trade")


def page_league():
    st.markdown('<div class="hero">🏆 League <span>Standings</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Chasing Taters · 5×5 roto · Bauers Fight Club in cyan</div>',
                unsafe_allow_html=True)
    f = d_std_frames()
    if not f:
        st.info("Standings not cached yet — run **Refresh league data** on the Data & Refresh page.")
        return
    import plotly.express as px
    import plotly.graph_objects as go
    pts, tot, mom, gp, cats = f["pts"], f["tot"], f["mom"], f["gp"], f["cats"]
    n = len(pts)
    me = pts[pts["Team"] == MY_OTTONEU]
    if me.empty:
        st.warning(f"{MY_OTTONEU} not found in standings — showing raw tables.")
        st.dataframe(pts, width="stretch", hide_index=True)
        return
    me = me.iloc[0]
    short = {t: (t if len(t) <= 16 else t[:15] + "…") for t in pts["Team"]}

    # ── KPIs ──
    rank = int(me["Rank"])
    up = pts[pts["Rank"] == rank - 1]
    dn = pts[pts["Rank"] == rank + 1]
    mrow = mom[mom["Team"] == MY_OTTONEU]
    d7 = float(mrow["7-Day"].iloc[0]) if len(mrow) else 0.0
    d30 = float(mrow["30-Day"].iloc[0]) if len(mrow) else 0.0
    k = st.columns(5)
    k[0].markdown(kpi("Rank", f"{rank} <span style='font-size:.55em;color:var(--muted)'>of {n}</span>"),
                  unsafe_allow_html=True)
    k[1].markdown(kpi("Total points", f"{me['Total']:g}"), unsafe_allow_html=True)
    k[2].markdown(kpi("To next rank", f"{float(up['Total'].iloc[0]) - float(me['Total']):g} pts" if len(up) else "—",
                      ), unsafe_allow_html=True)
    k[3].markdown(kpi("7-day move", f"{d7:+g}", delta=round(d7, 1)), unsafe_allow_html=True)
    k[4].markdown(kpi("30-day move", f"{d30:+g}", delta=round(d30, 1)), unsafe_allow_html=True)
    st.write("")

    # ── standings bar + momentum ──
    c1, c2 = st.columns([1, 1])
    with c1:
        p = pts.sort_values("Total")
        fig = go.Figure(go.Bar(
            x=p["Total"], y=[short[t] for t in p["Team"]], orientation="h",
            text=[f"{v:g}" for v in p["Total"]], textposition="outside",
            marker=dict(color=[C_ME if t == MY_OTTONEU else C_OTHER for t in p["Team"]],
                        line=dict(width=0))))
        style_fig(fig, "Total roto points")
        fig.update_layout(height=430, xaxis_title="", yaxis_title="",
                          xaxis_range=[0, float(p["Total"].max()) * 1.12])
        st.plotly_chart(fig, width="stretch")
    with c2:
        if len(mom):
            m = mom.copy().sort_values("30-Day")
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=m["30-Day"], y=[short.get(t, t) for t in m["Team"]], orientation="h", name="30-day",
                marker=dict(color=[C_GREEN if v >= 0 else C_RED for v in m["30-Day"]],
                            line=dict(width=[2.5 if t == MY_OTTONEU else 0 for t in m["Team"]],
                                      color=C_ME))))
            fig.add_trace(go.Scatter(
                x=m["7-Day"], y=[short.get(t, t) for t in m["Team"]], mode="markers", name="7-day",
                marker=dict(size=9, color="#e8eef6", line=dict(width=1.5, color="#0d1117"))))
            fig.add_vline(x=0, line_color="#3a4655")
            style_fig(fig, "Momentum — points gained / lost (bars 30-day · dots 7-day)")
            fig.update_layout(height=430, xaxis_title="roto points", yaxis_title="",
                              legend=dict(orientation="h", y=1.06, x=1, xanchor="right"))
            st.plotly_chart(fig, width="stretch")

    # ── category heatmap ──
    hm = pts.set_index("Team")[cats]
    fig = px.imshow(hm.values, x=cats, y=[short[t] for t in hm.index], text_auto=".3~g",
                    color_continuous_scale=["#151b26", "#12505c", "#22d3ee"], aspect="auto")
    my_i = list(hm.index).index(MY_OTTONEU)
    fig.add_shape(type="rect", x0=-0.5, x1=len(cats) - 0.5, y0=my_i - 0.5, y1=my_i + 0.5,
                  line=dict(color=C_ME, width=2.5))
    style_fig(fig, "Roto points by category — teams sorted by total")
    fig.update_layout(height=440, coloraxis_showscale=False)
    fig.update_xaxes(side="top")
    st.plotly_chart(fig, width="stretch")

    # ── cheapest points to gain / tightest to defend ──
    lev = league_levers(f)
    if lev["gains"] or lev["defends"]:
        FMT = {"AVG": "+{:.3f}", "ERA": "−{:.2f}", "WHIP": "−{:.3f}"}
        c3, c4 = st.columns([1, 1])
        with c3:
            if lev["gains"]:
                g = pd.DataFrame(lev["gains"]).sort_values("sigma", ascending=False)
                txt = [FMT.get(r["cat"], "+{:.0f}").format(r["gap"] + (0.001 if r["cat"] == "AVG" else 0))
                       + f"  passes {short.get(r['pass_team'], r['pass_team'])}"
                       for _, r in g.iterrows()]
                fig = go.Figure(go.Bar(
                    x=g["sigma"], y=g["cat"], orientation="h", text=txt, textposition="auto",
                    marker=dict(color=["#2ecc71" if z < 0.35 else ("#e2a23e" if z < 0.9 else "#df6562")
                                       for z in g["sigma"]], line=dict(width=0))))
                style_fig(fig, "Cheapest points to GAIN — shorter bar = easier")
                fig.update_layout(height=400, xaxis_title="distance to next tier (league σ)", yaxis_title="")
                st.plotly_chart(fig, width="stretch")
                st.caption("🟢 within reach now · 🟡 doable · 🔴 long shot.  Label = raw-stat gap and who you'd pass.")
            else:
                st.info("You lead every category — nothing to gain. 👑")
        with c4:
            if lev["defends"]:
                dd = pd.DataFrame(lev["defends"]).sort_values("sigma")
                fig = go.Figure(go.Bar(
                    x=dd["sigma"], y=dd["cat"], orientation="h",
                    text=[short.get(t, t) for t in dd["chaser"]], textposition="auto",
                    marker=dict(color=["#df6562" if z < 0.2 else ("#e2a23e" if z < 0.6 else "#46b17f")
                                       for z in dd["sigma"]], line=dict(width=0))))
                style_fig(fig, "Cushion to DEFEND — shorter bar = more at risk")
                fig.update_layout(height=400, xaxis_title="lead over nearest chaser (league σ)", yaxis_title="")
                st.plotly_chart(fig, width="stretch")
                st.caption("🔴 chaser is right behind (label = who) · 🟡 watch it · 🟢 safe for now.")

    # ── games-played / innings pace ──
    if len(gp) and "Team" in gp.columns:
        gme = gp[gp["Team"] == MY_OTTONEU]
        if len(gme):
            gme = gme.iloc[0]
            caps_gp = {"C": 162, "1B": 162, "2B": 162, "SS": 162, "MI": 162, "3B": 162,
                       "OF": 810, "Util": 162, "IP": 1500}
            el = season_elapsed()
            rows = []
            for slot, cap in caps_gp.items():
                if slot in gme.index and pd.notna(gme[slot]):
                    used = float(gme[slot])
                    rows.append({"slot": slot, "pct": used / cap,
                                 "txt": f"{used:g} / {cap}", "diff": used / cap - el})
            if rows:
                pr = pd.DataFrame(rows)[::-1]
                fig = go.Figure(go.Bar(
                    x=pr["pct"], y=pr["slot"], orientation="h", text=pr["txt"], textposition="outside",
                    marker=dict(color=[C_GREEN if d >= -0.03 else (C_AMBER if d >= -0.08 else C_RED)
                                       for d in pr["diff"]], line=dict(width=0))))
                fig.add_vline(x=el, line_dash="dash", line_color="#e8eef6",
                              annotation_text=f"season pace {el:.0%}", annotation_font_color="#e8eef6")
                style_fig(fig, "Games & innings used vs cap — stay on the white pace line")
                fig.update_layout(height=420, xaxis_title="share of cap used", yaxis_title="",
                                  xaxis=dict(tickformat=".0%", range=[0, 1.12]))
                st.plotly_chart(fig, width="stretch")
                st.caption("🟢 on/ahead of pace · 🟡 slightly behind · 🔴 leaving games on the table "
                           "(behind pace = counting stats you never bank).")

    # ── raw tables ──
    with st.expander("Raw standings tables"):
        st.dataframe(pts, width="stretch", hide_index=True)
        st.dataframe(tot, width="stretch", hide_index=True)
        if len(mom):
            st.dataframe(mom, width="stretch", hide_index=True)
    if len(f["hit"]) or len(f["pit"]):
        with st.expander("My season counting stats (hitters & pitchers)"):
            if len(f["hit"]):
                st.dataframe(f["hit"], width="stretch", hide_index=True)
            if len(f["pit"]):
                st.dataframe(f["pit"], width="stretch", hide_index=True)


def page_data():
    st.markdown('<div class="hero">⚙️ Data & Refresh</div>', unsafe_allow_html=True)
    st.subheader("Cache freshness")
    rows = []
    for f in sorted(glob.glob(os.path.join(CACHE, "*")) + glob.glob(os.path.join(REPORTS, "*"))):
        ts = dt.datetime.fromtimestamp(os.path.getmtime(f))
        rows.append({"file": os.path.basename(f), "updated": ts.strftime("%b %d %I:%M %p"),
                     "age_hrs": round((dt.datetime.now() - ts).total_seconds() / 3600, 1)})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.divider()
    st.subheader("Regenerate")
    st.caption("These make live data pulls / Claude calls — they take a bit.")
    c = st.columns(3)
    if IS_CLOUD:
        c[0].button("🔄 Re-pull rosters + standings + top-100", disabled=True,
                    help="Runs on Ian's PC (drives a logged-in Chrome). The scheduled refresh "
                         "pushes fresh data to this app automatically.")
    if not IS_CLOUD and c[0].button("🔄 Re-pull rosters + standings + top-100"):
        from analysis import refresh_lock as RL
        if not RL.acquire():
            st.warning("A refresh is already running (scheduled job or another session) — "
                       "it shares this button's Chrome profile. Try again in a few minutes.")
        else:
            try:
                with st.spinner("Pulling rosters + standings + top-100 (opens browser)..."):
                    from analysis import rosters as R, ottoneu_team as OT
                    from connectors import top100 as T100
                    R.load_all(refresh=True)
                    snap = OT.snapshot()
                    with open(os.path.join(CACHE, "standings.json"), "w", encoding="utf-8") as f:
                        json.dump(snap, f)
                    try:
                        T100.top100_with_ownership(refresh=True)
                    except Exception as e:
                        st.warning(f"top-100: {e}")
                    st.cache_data.clear()
                st.success("Rosters + standings + top-100 refreshed.")
            finally:
                RL.release()
    if c[1].button("📧 Regenerate daily email"):
        with st.spinner("Generating email..."):
            from agents import daily_email as DE
            html = DE.generate()
            open(os.path.join(REPORTS, "daily_email_preview.html"), "w", encoding="utf-8").write(html)
        st.success("Email regenerated.")
    if c[2].button("🤖 Run all analysis agents"):
        from agents import waiver, keeper, lineup, trade, prospect_finder, injury_risk
        jobs = [("waiver_add_drop.md", waiver.run), ("keeper_salary_ottoneu.md", keeper.analyze),
                ("lineups.md", lineup.run), ("trade_targets_ottoneu.md", trade.analyze),
                ("available_prospect_targets.md", prospect_finder.find), ("injury_risk.md", injury_risk.run)]
        prog = st.progress(0.0)
        for i, (out, fn) in enumerate(jobs):
            with st.spinner(f"Running {out}..."):
                try:
                    open(os.path.join(REPORTS, out), "w", encoding="utf-8").write(fn())
                except Exception as e:
                    st.warning(f"{out}: {e}")
            prog.progress((i + 1) / len(jobs))
        st.success("All agents run.")
    st.divider()
    st.subheader("Pitch-by-pitch data (Pitch Lab)")
    st.caption("Pulls Statcast pitch-level data for every rostered pitcher (~2–4 min). Powers the 🔬 Pitch Lab.")
    if st.button("🔬 Pull pitch-by-pitch data (all pitchers)"):
        from analysis import pitch_model as PM
        mp = d_my_pitchers()
        rows = [r for _, r in mp.iterrows()]
        prog = st.progress(0.0)
        msgs = []
        for i, r in enumerate(rows):
            with st.spinner(f"Pulling {r['player']} ({i+1}/{len(rows)})..."):
                try:
                    n = len(PM.pitcher_pitches(int(r["mlbam"]), 2026, refresh=True))
                    msgs.append(f"{r['player']}: {n}")
                except Exception as e:
                    msgs.append(f"{r['player']}: ERR {str(e)[:40]}")
            prog.progress((i + 1) / len(rows))
        st.cache_data.clear()
        st.success(f"Pulled pitch data for {len(rows)} pitchers.")
        st.caption(" · ".join(msgs))


# ───────────────────────── nav ─────────────────────────
PAGES = {
    "🏠 Overview": page_overview,
    "🧠 Ask the Analyst": page_analyst,
    "⚡ Action Center": page_action,
    "📋 Team Dashboard": page_team,
    "⚖️ Player Comparison": page_compare,
    "🔬 Pitch Lab": page_pitch_lab,
    "💰 Ottoneu Value": page_value,
    "🌱 Prospect Hub": page_prospects,
    "🔎 Prospect Explorer": page_prospect_explorer,
    "💱 Trade Center": page_trades,
    "🏆 League Context": page_league,
    "⚙️ Data & Refresh": page_data,
}
st.sidebar.markdown("### ⚾ Command Center")
st.sidebar.caption("Automated fantasy baseball")
choice = st.sidebar.radio("Navigate", list(PAGES), label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption("Data is cached. Use **Data & Refresh** to pull live / run agents.")

# Header badge reflects real cache age instead of a hardcoded "live".
_stale = []
for _f in ("rosters.csv", "standings.json"):
    _p = os.path.join(CACHE, _f)
    if not os.path.exists(_p):
        _stale.append(f"{_f} missing")
    else:
        _age = (dt.datetime.now() - dt.datetime.fromtimestamp(os.path.getmtime(_p))).days
        if _age > 3:
            _stale.append(f"{_f} {_age}d old")
_badge = ('<div class="sv-live">live</div>' if not _stale else
          '<div class="sv-live" style="background:#c0392b;color:#fff;">stale</div>')
st.markdown(
    '<div class="sv-bar"><div>'
    '<div class="sv-title">&#11042; COMMAND CENTER</div>'
    '<div class="sv-sub">Automated fantasy baseball &middot; cached data</div></div>'
    + _badge + '</div>', unsafe_allow_html=True)
if _stale:
    st.warning("⚠ Platform caches look stale: " + "; ".join(_stale) +
               " — the scheduled refresh may not be running. Use **Data & Refresh → Re-pull**.")
try:
    PAGES[choice]()
except Exception as e:
    st.error(f"Page error: {e}")
    st.caption("If data is missing, run a refresh on the Data & Refresh page.")
