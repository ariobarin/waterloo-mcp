"""Optional: sign in again on the server by itself, so you don't have to run login.py when a session ends.

Runs next to server.py (see README, "Sign in automatically"). When the server hits a signed-out service it
touches DATA_DIR/login-wanted; this signs in with login.py's flow in a headless browser and writes fresh
cookies, which the server picks up without a restart. UW still asks for Duo: approve the push on your phone.
The browser profile is kept, so Duo can remember it and skip the push for a while.

Passwords come from the environment and go only to UW's and Piazza's own sign-in pages:
    UW_USERNAME, UW_PASSWORD           your UW email and password
    PIAZZA_EMAIL, PIAZZA_PASSWORD      optional; Piazza is skipped (left as it is) without them
"""

import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

from login import SERVICES, Helper, capture

DATA = Path(os.environ.get("DATA_DIR", Path(__file__).with_name("data")))
WANTED = DATA / "login-wanted"  # the server adds one line per signed-out service
COOKIES = DATA / "cookies.json"
PROFILE = DATA / "login-profile"
SCREEN = DATA / "login-screen.png"  # the headless browser's last screenshot, to see what a sign-in is stuck on
DUO_CODE = DATA / "duo-code"  # while Duo waits for its code, so sign_in_status can show it
MIN_GAP = 15 * 60  # never sign in more often than this, so a bad password can't lock the account
MAX_GAP = 6 * 3600


def merge(new_state: str) -> str:
    """New cookies over the old ones, so services we didn't sign in to this time keep theirs."""
    key = lambda c: (c["name"], c["domain"], c.get("path", "/"))
    try:
        old = json.loads(COOKIES.read_text(encoding="utf-8"))
        old = old["cookies"] if isinstance(old, dict) else old
    except (FileNotFoundError, ValueError):
        old = []
    cookies = {key(c): c for c in old}
    cookies.update({key(c): c for c in json.loads(new_state)["cookies"]})
    return json.dumps({"cookies": list(cookies.values())})


class Watch:
    """Login.py's helper, plus what you'd see if the browser had a screen: each site it passes through, the
    code Duo wants typed into Duo Mobile (also in DATA/duo-code, for sign_in_status), the text of any other
    page that asks for something, and a screenshot in DATA/login-screen.png."""

    ASKS = ("accounts.google.com/",)

    def __init__(self, helper):
        self.helper, self.host, self.text, self.code, self.shot = helper, "", "", "", 0.0

    def __call__(self, page):
        self.helper(page)
        try:
            host = urlparse(page.url).netloc
            if host != self.host:
                self.host = host
                print(f"  at {host}", flush=True)
            if ".duosecurity.com/" in page.url:
                text = " ".join(page.inner_text("body", timeout=500).split())
                code = re.search(r"verification code\D*?(\d{3,8})\b", text)
                if code and code[1] != self.code:
                    self.code = code[1]
                    DUO_CODE.write_text(self.code)
                    print(f"  Duo code: {self.code}  (type it into Duo Mobile)", flush=True)
            elif any(a in page.url for a in self.ASKS):
                text = " ".join(page.inner_text("body", timeout=500).split())[:300]
                if text != self.text:
                    self.text = text
                    print(f"  page says: {text}", flush=True)
            if time.time() - self.shot > 3:
                self.shot = time.time()
                page.screenshot(path=SCREEN)
        except Exception:
            pass  # the page moved on; look again next tick


def sign_in(services: set[str]) -> list[str]:
    uw = (os.environ["UW_USERNAME"], os.environ["UW_PASSWORD"])
    piazza = (os.environ["PIAZZA_EMAIL"], os.environ["PIAZZA_PASSWORD"]) if os.environ.get("PIAZZA_PASSWORD") else None
    try:
        state, failed = capture(Watch(Helper(uw, piazza)), PROFILE, headless=True, timeout=120, only=services)
    finally:
        DUO_CODE.unlink(missing_ok=True)  # the code is only good while this sign-in waits for it
    fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(merge(state))
    os.replace(tmp, COOKIES)
    return failed


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    known = {s[0] for s in SERVICES} - (set() if os.environ.get("PIAZZA_PASSWORD") else {"Piazza"})
    if not COOKIES.exists():
        WANTED.write_text("\n".join(known))  # fresh setup: sign in to everything, no login.py needed
    gap, last = MIN_GAP, 0.0
    while True:
        time.sleep(10)
        if not WANTED.exists() or time.time() - last < gap:
            continue
        services = set(WANTED.read_text(encoding="utf-8").split()) & known
        WANTED.unlink(missing_ok=True)
        if not services:
            continue  # e.g. only Piazza, without its password here
        last = time.time()
        print("Signing in to " + ", ".join(sorted(services)) + "...", flush=True)
        try:
            failed = sign_in(services)
        except Exception as e:  # keep the loop alive; the next request tries again after the gap
            print(f"Sign-in failed: {e}", flush=True)
            failed = sorted(services)
        print("Signed in." if not failed else "Not signed in to: " + ", ".join(failed), flush=True)
        gap = MIN_GAP if not failed else min(gap * 2, MAX_GAP)  # back off while it keeps failing


if __name__ == "__main__":
    main()
