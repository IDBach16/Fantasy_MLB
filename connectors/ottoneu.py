"""
Ottoneu connector — drives the user's REAL Chrome via the DevTools protocol (CDP).

Why: vanilla automated browsers (Playwright's bundled Chromium) get stuck forever on
Cloudflare's "security verification" because they carry bot fingerprints. REAL Chrome
passes Cloudflare like a human. So we launch real Chrome with a debugging port + a
dedicated profile (so the Ottoneu login persists), then connect Playwright to it.

No password is scripted — you log in by hand once in the real Chrome window.
The dedicated profile lives in secrets/chrome_profile (gitignored).
"""
from __future__ import annotations
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "secrets" / "chrome_profile"
BASE = "https://ottoneu.fangraphs.com"
DEBUG_PORT = 9222

LOGIN_SIGNALS = ("log out", "logout", "sign out", "my account")
CHALLENGE_SIGNALS = ("just a moment", "security verification",
                     "verifying you are human", "performing security")

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str:
    for p in CHROME_CANDIDATES:
        if p and os.path.exists(p):
            return p
    raise FileNotFoundError("No real Chrome/Edge found in the usual locations.")


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


class OttoneuConnector:
    def __init__(self, headless: bool = False, port: int = DEBUG_PORT, start_url: str = BASE + "/"):
        self.headless = headless
        self.port = port
        self.start_url = start_url
        self._proc = self._pw = self._browser = self._ctx = None

    def __enter__(self):
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        if not _port_open(self.port):
            exe = find_browser()
            args = [exe, f"--remote-debugging-port={self.port}",
                    f"--user-data-dir={PROFILE_DIR}",
                    "--no-first-run", "--no-default-browser-check", self.start_url]
            if self.headless:
                args.insert(1, "--headless=new")
            self._proc = subprocess.Popen(args)
            for _ in range(60):
                if _port_open(self.port):
                    break
                time.sleep(0.5)
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
        self._ctx = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        return self

    def __exit__(self, *exc):
        # Stop the Playwright client but LEAVE Chrome running so the login session
        # persists in the profile and is reused next time.
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def page(self):
        for _ in range(20):
            if self._ctx.pages:
                return self._ctx.pages[0]
            time.sleep(0.5)
        return self._ctx.new_page()

    def home_state(self) -> str:
        """Returns 'challenge' | 'logged_in' | 'logged_out'."""
        pg = self.page()
        pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        html = pg.content().lower()
        if any(s in html for s in CHALLENGE_SIGNALS):
            return "challenge"
        if any(s in html for s in LOGIN_SIGNALS):
            return "logged_in"
        return "logged_out"

    def discover_my_teams(self):
        pg = self.page()
        pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        anchors = pg.eval_on_selector_all(
            "a[href]", "els => els.map(e => [e.textContent.trim(), e.getAttribute('href')])")
        out, seen = [], set()
        for text, href in anchors:
            if not href:
                continue
            rel = href.replace(BASE, "")
            m = re.match(r"^/(\d+)(/.*)?$", rel)
            if not m:
                continue
            key = (m.group(1), rel)
            if key in seen:
                continue
            seen.add(key)
            out.append({"league_id": m.group(1), "text": text, "href": rel})
        return out

    def fetch(self, path: str):
        """Authenticated fetch via real Chrome (passes Cloudflare, carries the session)."""
        url = path if path.startswith("http") else BASE + path
        resp = self._ctx.request.get(url, timeout=60000)
        return resp.status, resp.text()

    def fetch_checked(self, path: str, expect: str = None) -> str:
        """fetch() that refuses to hand back a Cloudflare challenge / expired-session
        page as if it were data. Raises instead, so callers never cache garbage."""
        status, text = self.fetch(path)
        low = text[:3000].lower()
        if status != 200 or any(s in low for s in CHALLENGE_SIGNALS):
            raise RuntimeError(
                f"Ottoneu fetch {path} blocked (HTTP {status} — Cloudflare challenge "
                f"or expired session; open Chrome and log in again)")
        if expect and expect not in text:
            raise RuntimeError(
                f"Ottoneu fetch {path} returned unexpected content (logged out?) — "
                f"missing expected marker {expect!r}")
        return text

    # --- VERIFIED data pulls ---
    def roster_export(self, league_id):
        """Whole-league rosters CSV: TeamID, Team, ottoneu ID, FG IDs, Name, MLB Team,
        Position(s), Salary. VERIFIED working for league 907. Returns CSV text."""
        return self.fetch_checked(f"/{league_id}/rosterexport?csv=1", expect="TeamID")

    def average_values(self, league_id):
        return self.fetch_checked(f"/{league_id}/average_values?csv=1")
