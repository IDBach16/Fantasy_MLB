"""
Reusable REAL-Chrome session over CDP — passes Cloudflare / anti-bot and persists
logins in a dedicated profile. Shared by all cookie/login-based connectors
(Ottoneu, ESPN private leagues, Fantrax, ...).
"""
from __future__ import annotations
import os
import socket
import subprocess
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "secrets" / "chrome_profile"
DEFAULT_PORT = 9222

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


class RealChrome:
    """Connect to an already-running real Chrome (debug port) or launch one."""

    def __init__(self, start_url: str = "about:blank", headless: bool = False, port: int = DEFAULT_PORT):
        self.start_url = start_url
        self.headless = headless
        self.port = port
        self._proc = self._pw = self._browser = self._ctx = None

    def __enter__(self):
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        launched = False
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
            launched = True
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
        self._ctx = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        if not launched and self.start_url not in ("about:blank", ""):
            # connected to an existing Chrome -> open the target in a new tab
            try:
                pg = self._ctx.new_page()
                pg.goto(self.start_url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
        return self

    def __exit__(self, *exc):
        # Stop the Playwright client; leave Chrome running so logins persist.
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    @property
    def context(self):
        return self._ctx

    def cookies(self, url=None):
        return self._ctx.cookies(url) if url else self._ctx.cookies()
