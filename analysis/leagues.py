"""
Central league registry + CAPABILITIES — the single source of truth for which
agents/features apply to each league (per Ian's rules). Every agent reads this so
it never, e.g., suggests waiver moves in a no-transactions league or prospects in
a no-minors league.

  ESPN     — redraft, MLB only (NO keepers, NO minor leaguers), waivers on
  Fantrax  — draft & hold (NO keepers, NO transactions at all); lineups only
  Ottoneu  — the full deal: keeper + transactions + prospects all matter
"""

LEAGUES = {
    "ottoneu": {
        "platform": "ottoneu", "league_id": "907", "team_id": "6418",
        "name": "Chasing Taters", "scoring": "Old School 5x5 roto", "salary_cap": 400,
        "keeper": True, "dynasty": True, "transactions": True, "trades": True,
        "prospects": True, "lineup": True,
    },
    "espn": {
        "platform": "espn", "league_id": 255806481, "team_id": 1,
        "name": "Moeller Analytics Minons", "scoring": "deep roto (redraft)",
        "keeper": False, "dynasty": False, "transactions": True, "trades": True,
        "prospects": False,   # redraft — MLB only, no minor leaguers
        "lineup": True,
    },
    "fantrax": {
        "platform": "fantrax", "league_id": "xkklb8bimlzfgn7d", "team_id": "n57zugwlmlzmuolo",
        "name": "TJStats Patreon League - One", "scoring": "roto/points",
        "keeper": False, "dynasty": False, "transactions": False, "trades": False,
        "prospects": False,   # draft & hold — no transactions; lineups only
        "lineup": True,
    },
}


def with_capability(cap: str):
    """League keys that support a capability (e.g. 'transactions', 'prospects', 'keeper')."""
    return [k for k, v in LEAGUES.items() if v.get(cap)]
