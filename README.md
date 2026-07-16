# Fantasy MLB — Automated Multi-League Analysis & Management

An automated, AI-agent-driven app that connects to all of Ian's fantasy baseball
leagues, pulls every relevant data source, analyzes each team against that league's
specific rules, sends a daily noon email per league, fires real-time alerts, and —
with explicit permission — helps manage lineups and roster moves.

> Status: **SETUP — collecting league access, one team at a time.** No app logic built yet.

---

## Recommended stack (proposed — chosen as the clear best fit; can be adjusted)
- **Language:** Python 3.13 — best fit by far: Statcast tooling (pybaseball / Baseball Savant),
  fantasy-platform libraries (espn-api, yahoo_fantasy_api, fantraxapi), pandas for analysis,
  the Anthropic SDK for the agents, and it matches Ian's existing stack.
- **Storage:** SQLite to start (zero-config, local) for roster history, value history, and
  recommendation history → can graduate to Postgres if we host it.
- **Agents:** Claude tool-use loop (same pattern as Scouting Agent 2.0 — code owns the data/math,
  Claude orchestrates & explains). **Claude API key provided by Ian later — NOT assumed connected.**
- **Scheduler:** APScheduler (in-process) and/or Windows Task Scheduler for refreshes, agent runs,
  alerts, and the daily noon email.
- **Dashboard:** Streamlit (fast multi-page data app matching the tab list) — can move to a
  polished web frontend later.
- **Email:** SMTP (Gmail App Password) or SendGrid for the noon email + alerts.
- **Secrets:** `python-dotenv` + `.env` now; a secrets manager if/when hosted.

## Architecture (layers)
1. **Connectors** — per-platform (ESPN / Yahoo / Fantrax / Ottoneu / …) + Baseball Savant,
   Prospect Savant, FanGraphs, projections, injuries, depth charts.
2. **Storage** — SQLite + history tables (rosters, values, transactions, recommendations).
3. **Agents** (12) — see below. Read-only analysis by default.
4. **Orchestration** — scheduler: timed refreshes, agent runs, alerts, noon email.
5. **Presentation** — Streamlit dashboard + email.
6. **Action layer** — permission-gated roster/lineup changes, **separated** from data & analysis.

## Agents
League Access & Setup · Roster Analysis · Baseball Savant · Prospect Scouting ·
Ottoneu Value · Waiver / Add-Drop · Trade Evaluation · Keeper / Salary · Lineup Optimization ·
Injury / Risk · Alert & Email Update.

## Primary data sources
Baseball Savant (Statcast) · Prospect Savant (https://prospectsavant.com/leaders) ·
Ottoneu rosters/salaries/avg-salary/available players · FanGraphs · projections · injuries ·
depth charts · playing-time estimates · league available-player pools · transaction history.

## Security model (non-negotiable)
- **Secrets live only in `.env`** (gitignored) or a secrets manager — never hardcoded, never in
  the UI, never in logs, never in chat output.
- **Non-secret config** (league IDs, scoring, roster rules) lives in `leagues/<slug>.yaml`,
  which references secrets **by env-var name only** (never the value).
- **Read-only by default.** Any team-changing action (set lineup, add, drop, accept/reject trade,
  waiver claim) is **explained and confirmed** before execution unless Ian pre-authorizes that
  specific action type for that league.

## Roadmap
1. **Secure intake — one league at a time** ← we are here
2. Data connectors (per league + Savant / Prospect Savant)
3. Storage + history
4. Analysis agents (recommend-only)
5. Dashboard (the tab list)
6. Scheduler + daily noon email + alerts
7. Permission-gated roster actions

## Layout
```
Fantasy_MLB/
  README.md
  .gitignore
  .env.example        # copy to .env (gitignored) and fill in — Ian only
  leagues/
    _TEMPLATE.yaml    # the full per-league intake checklist
  data/
    exports/          # manual CSVs (e.g. Ottoneu exports) — gitignored
    cache/            # pulled-data cache — gitignored
```
