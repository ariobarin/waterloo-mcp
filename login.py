"""Sign in to every service once in a real browser (Duo included) and save the cookies.

Run on your own computer:
    pip install playwright && playwright install chromium
    python login.py                              # writes cookies.json here
    python login.py --push myhost:waterloo-mcp   # or send it straight to the server over ssh, keep no copy

Your password goes only to UW's own sign-in page in the browser window.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from playwright.sync_api import Error, sync_playwright

PROFILE = Path(__file__).with_name(".login-profile")  # keeps your SSO session between runs

SERVICES = [
    ("LEARN", "https://learn.uwaterloo.ca/d2l/home", "https://learn.uwaterloo.ca/d2l/home",
     "sign in and approve Duo"),
    ("WaterlooWorks", "https://waterlooworks.uwaterloo.ca/waterloo.htm?action=login",
     "https://waterlooworks.uwaterloo.ca/myAccount/", "click 'Students/Alumni/Staff' if asked"),
    ("Odyssey", "https://odyssey.uwaterloo.ca/teaching/schedule", "https://odyssey.uwaterloo.ca/teaching/schedule",
     "usually automatic"),
    ("Crowdmark", "https://app.crowdmark.com/sign-in/waterloo", "https://app.crowdmark.com/student",
     "click 'Sign in with LEARN'"),
    ("Outline", "https://outline.uwaterloo.ca/viewer/?q=", "https://outline.uwaterloo.ca/viewer/", "usually automatic"),
    ("Piazza", "https://piazza.com/account/login", "https://piazza.com/class",
     "log in with your Piazza email and password"),
]


def wait_for(page, prefix: str, timeout: float = 300):
    """Wait until the page settles on `prefix`, ignoring the aborted hops SSO redirects cause."""
    end = time.time() + timeout
    while time.time() < end:
        if page.url.startswith(prefix):
            try:
                page.wait_for_load_state("domcontentloaded")
                return
            except Error:
                pass
        page.wait_for_timeout(500)
    raise TimeoutError(f"Timed out waiting for {prefix}")


def capture() -> str:
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(PROFILE, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        for name, start, done, hint in SERVICES:
            print(f"{name}: {hint} in the browser window...", flush=True)
            try:
                page.goto(start)
            except Error:
                pass  # an SSO redirect aborted the first hop; wait_for handles the rest
            wait_for(page, done)
            print(f"{name}: ok", flush=True)
        state = json.dumps(context.storage_state())
        context.close()
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--push", metavar="HOST:DIR", help="ssh host and compose directory to send cookies to")
    args = parser.parse_args()
    state = capture()
    if not args.push:
        out = Path(os.environ.get("DATA_DIR", Path(__file__).with_name("data"))) / "cookies.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(state)
        print(f"Saved {out}. Restart the server to pick it up.")
        return
    host, directory = args.push.split(":", 1)
    remote = (f"cd {directory} && docker compose stop"
              f" && docker compose run --rm --no-deps -T waterloo-mcp sh -c 'umask 077; cat > /data/cookies.json'"
              f" && docker compose up -d")
    subprocess.run(["ssh", host, remote], input=state.encode(), check=True)
    print(f"Sent to {host}; no copy kept here.")


if __name__ == "__main__":
    main()
