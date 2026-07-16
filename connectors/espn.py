"""ESPN connector — espn-api with cookies loaded from .env (private leagues)."""
import os
from dotenv import load_dotenv
from espn_api.baseball import League

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def get_league(league_id: int, year: int) -> League:
    return League(
        league_id=league_id, year=year,
        espn_s2=os.environ.get("ESPN_S2"),
        swid=os.environ.get("ESPN_SWID"),
    )
