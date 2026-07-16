"""
Fantrax connector — calls the fxpa data endpoints DIRECTLY using saved browser
cookies. We bypass fantraxapi's League/FantraxAPI object init on purpose: that init
crashes on this league (KeyError building a scoring-date lookup, a bug in their
date parsing). The underlying request layer works fine, so we use it directly.
"""
import json
import os
import requests
from fantraxapi.api import _request, Method

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIE_FILE = os.path.join(ROOT, "secrets", "fantrax_cookies.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def load_session() -> requests.Session:
    cks = json.load(open(COOKIE_FILE))
    s = requests.Session()
    s.headers["User-Agent"] = UA
    for c in cks:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))
    return s


def call(league_id: str, method: str, session=None, **kwargs):
    return _request(league_id, Method(method, **kwargs), session=session or load_session())


def league_info(league_id, session=None):
    return call(league_id, "getFantasyLeagueInfo", session=session)


def standings(league_id, session=None):
    return call(league_id, "getStandings", session=session)


def my_roster(league_id, session=None):
    """Roster for the logged-in user's own team (no teamId = own team)."""
    return call(league_id, "getTeamRosterInfo", view="STATS", session=session)


def team_roster(league_id, team_id, session=None):
    return call(league_id, "getTeamRosterInfo", teamId=team_id, view="STATS", session=session)


def transactions(league_id, session=None, per_page=100):
    return call(league_id, "getTransactionDetailsHistory", maxResultsPerPage=str(per_page), session=session)
