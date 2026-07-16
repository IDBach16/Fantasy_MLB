"""
Generate the Bauers Fight Club 3-day report, save an HTML preview, and EMAIL it if
SMTP creds are set in .env (Gmail App Password). Run this on the every-3-days schedule.
Every OTHER report (~6 days, tracked in data/cache/gm_email_state.json) it ALSO
generates a separate "Front Office Report" written in GM voice and sends it to
GM_EMAIL_TO (Mr. Corey Arnold).
  python send_daily_email.py
"""
import os
import re
import sys
import json
import datetime as dt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
load_dotenv(os.path.join(HERE, ".env"))
from agents import daily_email as DE

print("Generating Bauers Fight Club 3-day report...")


def _age_days(name):
    p = os.path.join(HERE, "data", "cache", name)
    if not os.path.exists(p):
        return None
    return (dt.datetime.now() - dt.datetime.fromtimestamp(os.path.getmtime(p))).days


def _insert_after_body(doc, block):
    """Insert an HTML block just inside <body> (or prepend if there's no body tag)."""
    out, n = re.subn(r"(<body[^>]*>)", lambda m: m.group(1) + block, doc, count=1)
    return out if n else block + doc


def _strip_fences(s):
    """Cut the response down to the bare HTML document: drop any model preamble
    before <!DOCTYPE html>/<html>, anything after </html>, and markdown fences."""
    s = s.strip()
    m = re.search(r"<!DOCTYPE\s+html|<html[\s>]", s, flags=re.I)
    if m:
        s = s[m.start():]
    end = s.lower().rfind("</html>")
    if end != -1:
        s = s[:end + len("</html>")]
    return re.sub(r"^```html\s*|\s*```$", "", s.strip())


# Big tappable button at the top of every email -> the deployed dashboard.
DASH_URL = os.environ.get("DASHBOARD_URL", "https://idbach16-fantasy-mlb.streamlit.app").strip()
DASH_BTN = (
    '<div style="text-align:center;margin:0 0 16px;font-family:Arial,sans-serif;">'
    f'<a href="{DASH_URL}" '
    'style="display:inline-block;background:#0fb6cc;color:#04222a;font-weight:bold;'
    'font-size:14px;text-decoration:none;padding:12px 26px;border-radius:8px;">'
    '&#9918; Open the Command Center dashboard</a>'
    '<div style="font-size:11px;color:#8a98ac;margin-top:6px;">'
    'live standings math &middot; trends &middot; trade finder &middot; AI analyst '
    '&middot; password: 42069</div></div>')

# If the scheduled refresh silently stopped running, flag it loudly instead of
# presenting old caches as current.
stale = []
for _f in ("rosters.csv", "standings.json"):
    _age = _age_days(_f)
    if _age is None:
        stale.append(f"{_f} is missing")
    elif _age > 3:
        stale.append(f"{_f} is {_age} days old")

stale_banner = ""
if stale:
    stale_banner = ('<p style="background:#c0392b;color:#fff;padding:10px;border-radius:4px;">'
                    f'<strong>⚠ Stale platform data:</strong> {"; ".join(stale)} — '
                    'the scheduled refresh (refresh_all.py) may not be running.</p>')

flag = ""
data = None
try:
    data = DE.assemble()
    html = _strip_fences(DE.generate(data))
except Exception as e:
    # Never die silently — still save/send SOMETHING so a broken pipeline is visible.
    flag = "⚠ GENERATION FAILED — "
    html = (f"<h2>Report generation failed</h2><pre>{type(e).__name__}: {e}</pre>"
            f"<p>Fix the error and re-run send_daily_email.py.</p>")
    print(f"⚠ generate() failed: {type(e).__name__}: {e}")

html = _insert_after_body(html, DASH_BTN)
if stale:
    flag = flag or "⚠ STALE DATA — "
    html = _insert_after_body(html, stale_banner)

out_dir = os.path.join(HERE, "data", "reports")
os.makedirs(out_dir, exist_ok=True)
preview = os.path.join(out_dir, "daily_email_preview.html")
with open(preview, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Preview saved -> {preview}")

# ---------- GM copy (Mr. Corey Arnold) — full report re-generated in GM voice ----------
GM_STATE = os.path.join(HERE, "data", "cache", "gm_email_state.json")
GM_EVERY_DAYS = 6  # every OTHER report (reports go out every 3 days)

# Fallback framing if the GM-voice generation fails: standard report + cover note.
GM_COVER = (
    '<div style="background:#fff;border:1px solid #ddd;border-left:4px solid #1a1a2e;'
    'padding:12px 16px;border-radius:4px;margin-bottom:16px;font-size:13px;'
    'font-family:Arial,sans-serif;color:#222;">'
    '<p style="margin:0 0 8px;"><b>Mr. Corey Arnold</b><br>'
    'General Manager — Bauers Fight Club</p>'
    "<p style=\"margin:0;\">Mr. Arnold — your front-office briefing on the ballclub is below: "
    "current standing, today's matchups and probable starters, player form, roster value and "
    "cap position, games-played pace, waiver and trade recommendations, the farm system, and "
    "the injury report. Recommended moves for your approval are in Section 10.<br>"
    '— BFC Baseball Operations</p></div>')


def gm_due():
    if not os.path.exists(GM_STATE):
        return True
    try:
        with open(GM_STATE, encoding="utf-8") as f:
            last = json.load(f)["last_sent"]
        return (dt.date.today() - dt.date.fromisoformat(last)).days >= GM_EVERY_DAYS
    except Exception:
        return True


def gm_mark_sent():
    with open(GM_STATE, "w", encoding="utf-8") as f:
        json.dump({"last_sent": dt.date.today().isoformat()}, f)


gm_to = os.environ.get("GM_EMAIL_TO", "").strip()
gm_html = None
if gm_to and gm_due():
    if data is not None:
        print("Generating GM Front Office Report (Mr. Corey Arnold)...")
        try:
            gm_html = _insert_after_body(_strip_fences(DE.generate_gm(data)), DASH_BTN)
        except Exception as e:
            print(f"⚠ GM generation failed ({type(e).__name__}: {e}) — "
                  "using the standard report with a GM cover note instead.")
            gm_html = _insert_after_body(html, GM_COVER)
        if stale:
            gm_html = _insert_after_body(gm_html, stale_banner)
        gm_preview = os.path.join(out_dir, "gm_email_preview.html")
        with open(gm_preview, "w", encoding="utf-8") as f:
            f.write(gm_html)
        print(f"GM preview saved -> {gm_preview}")
    else:
        print("⚠ Skipping GM report this run — data assembly failed.")

# ---------- send ----------
user = os.environ.get("SMTP_USER", "").strip()
# Google displays app passwords as "xxxx xxxx xxxx xxxx" — strip spaces so a
# straight paste works.
pw = os.environ.get("SMTP_PASS", "").strip().replace(" ", "")
to = os.environ.get("EMAIL_TO", "").strip()
host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
port = int(os.environ.get("SMTP_PORT", "587"))


def send(to_addr, subject, body_html, tries=2):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.attach(MIMEText(body_html, "html"))
    for attempt in range(1, tries + 1):
        try:
            with smtplib.SMTP(host, port, timeout=120) as s:
                s.starttls()
                s.login(user, pw)
                s.sendmail(user, [to_addr], msg.as_string())
            return
        except smtplib.SMTPAuthenticationError:
            raise  # retrying a bad password can't help
        except Exception:
            if attempt == tries:
                raise
            print(f"  send attempt {attempt} failed — retrying...")


if user and pw:
    if to:
        try:
            send(to, f"{flag}⚾ Bauers Fight Club — 3-Day Report ({dt.date.today():%b %d})", html)
            print(f"✅ SENT to {to}")
        except Exception as e:
            print(f"⚠ Send failed: {e}\n   (Preview is still saved.)")
    if gm_to:
        if gm_html is not None:
            try:
                send(gm_to, f"{flag}⚾ Bauers Fight Club — Front Office Report ({dt.date.today():%b %d})", gm_html)
                gm_mark_sent()
                print(f"✅ SENT GM report to {gm_to}")
            except Exception as e:
                print(f"⚠ GM send failed: {e}\n   (GM preview is still saved.)")
        else:
            print(f"ℹ GM report not due yet (goes out every {GM_EVERY_DAYS} days).")
else:
    print("ℹ No SMTP creds yet — previews saved only.")
    print("  To enable sending: add SMTP_USER (your Gmail) + SMTP_PASS (Gmail App Password) to .env")
