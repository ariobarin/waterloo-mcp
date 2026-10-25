"""Sign in to every service once in a real browser (Duo included) and save the cookies.

Run on your own computer:
    pip install playwright && playwright install chromium
    python login.py                              # writes cookies.json here
    python login.py --push myhost:waterloo-mcp   # or send it straight to the server over ssh, keep no copy
    python login.py --email you@uwaterloo.ca     # fill UW's and Piazza's sign-in forms; you still approve Duo
    python login.py --email you@uwaterloo.ca --piazza-email you@gmail.com   # if Piazza uses another email

Your passwords go only to UW's and Piazza's own sign-in pages in the browser window. With --email they are
asked for once, hidden, kept in memory for this run and never written anywhere.

autologin.py reuses this headless on the server, with passwords from its environment (see README).
"""

import argparse
import getpass
import json
import os
import subprocess
import time
from pathlib import Path

from playwright.sync_api import Error, sync_playwright

PROFILE = Path(__file__).with_name(".login-profile")  # keeps your SSO session between runs

# name, start page, signed-in page, hint, whether it goes through UW single sign-on (and so Duo)
SERVICES = [
    ("LEARN", "https://learn.uwaterloo.ca/d2l/home", "https://learn.uwaterloo.ca/d2l/home",
     "sign in and approve Duo", True),
    ("WaterlooWorks", "https://waterlooworks.uwaterloo.ca/waterloo.htm?action=login",
     "https://waterlooworks.uwaterloo.ca/myAccount/", "click 'Students/Alumni/Staff' if asked", True),
    ("Odyssey", "https://odyssey.uwaterloo.ca/teaching/schedule", "https://odyssey.uwaterloo.ca/teaching/schedule",
     "usually automatic", True),
    ("Crowdmark", "https://app.crowdmark.com/sign-in/waterloo", "https://app.crowdmark.com/student",
     "usually automatic", True),
    ("Outline", "https://outline.uwaterloo.ca/viewer/?q=", "https://outline.uwaterloo.ca/viewer/", "usually automatic",
     True),
    ("Piazza", "https://piazza.com/account/login", "https://piazza.com/class",
     "log in with your Piazza email and password", False),
]


class Helper:
    """Clicks past WaterlooWorks' and Crowdmark's school pages, fills the UW and Piazza sign-in forms it has
    passwords for, and asks Duo to remember this browser.

    Each password is submitted once: a wrong one is yours to retype, not ours to repeat. Duo stays yours.
    """

    def __init__(self, uw: tuple[str, str] | None = None, piazza: tuple[str, str] | None = None):
        self.uw, self.piazza, self.tried = uw, piazza, set()

    def __call__(self, page):
        try:
            if page.url.startswith("https://app.crowdmark.com/sign-in/waterloo"):
                page.click("text=Sign in with LEARN", timeout=2000)
            elif page.url.startswith("https://waterlooworks.uwaterloo.ca/waterloo.htm"):
                page.click("text=Students/Alumni/Staff", timeout=2000)
            elif ".duosecurity.com/" in page.url:
                page.click("text=Yes, this is my device", timeout=500)  # Duo remembers the browser for a while
            elif self.uw and page.url.startswith("https://adfs.uwaterloo.ca/"):
                if page.is_visible("#passwordInput"):
                    if "uw" not in self.tried:
                        self.tried.add("uw")
                        page.fill("#passwordInput", self.uw[1])
                        page.click("#submitButton")
                elif page.is_visible("#userNameInput") and not page.input_value("#userNameInput"):
                    page.fill("#userNameInput", self.uw[0])
                    page.click("#nextButton")
            elif self.piazza and "piazza" not in self.tried and page.url.startswith("https://piazza.com/account/login"):
                if page.is_visible("#password_field"):
                    self.tried.add("piazza")
                    page.fill("#email_field", self.piazza[0])
                    page.fill("#password_field", self.piazza[1])
                    page.click("#modal_login_button")
        except Error:
            pass  # the page moved on mid-click; try again next tick


def wait_for(page, prefix: str, helper, timeout: float = 300):
    """Wait until the page settles on `prefix`, ignoring the aborted hops SSO redirects cause."""
    end = time.time() + timeout
    while time.time() < end:
        helper(page)
        if page.url.startswith(prefix):
            try:
                page.wait_for_load_state("domcontentloaded")
                return
            except Error:
                pass
        page.wait_for_timeout(500)
    raise TimeoutError(f"Timed out waiting for {prefix}")


def capture(helper, profile: Path = PROFILE, headless: bool = False, timeout: float = 300,
            only: set[str] | None = None) -> tuple[str, list[str]]:
    """Sign in to every service (or `only` these); returns the cookies and the services that didn't make it."""
    failed, sso_failed = [], False
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(profile, headless=headless)
        agent = context.pages[0].evaluate("navigator.userAgent") if context.pages else ""
        if "HeadlessChrome" in agent:  # Duo may turn away a browser that says it's headless
            context.close()
            context = p.chromium.launch_persistent_context(profile, headless=True,
                                                           user_agent=agent.replace("HeadlessChrome", "Chrome"))
        page = context.pages[0] if context.pages else context.new_page()
        for name, start, done, hint, sso in SERVICES:
            if only is not None and name not in only:
                continue
            if sso and sso_failed:
                failed.append(name)  # UW sign-in didn't work; trying again would only send more Duo pushes
                continue
            print(f"{name}: {hint}" + ("..." if headless else " in the browser window..."), flush=True)
            try:
                page.goto(start)
            except Error:
                pass  # an SSO redirect aborted the first hop; wait_for handles the rest
            try:
                wait_for(page, done, helper, timeout)
                print(f"{name}: ok", flush=True)
            except TimeoutError:
                print(f"{name}: timed out, skipped", flush=True)
                failed.append(name)
                sso_failed |= sso
        state = json.dumps(context.storage_state())
        context.close()
    return state, failed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--push", metavar="HOST:DIR", help="ssh host and compose directory to send cookies to")
    parser.add_argument("--email", help="your UW email; asks for your passwords and fills the sign-in forms")
    parser.add_argument("--piazza-email", help="your Piazza email, if not the same as --email")
    args = parser.parse_args()
    uw = piazza = None
    if args.email:
        uw = (args.email, getpass.getpass("UW password: "))
        password = getpass.getpass("Piazza password (blank to type it in the browser): ")
        piazza = (args.piazza_email or args.email, password) if password else None
    state, failed = capture(Helper(uw, piazza))
    if failed:
        print("Not signed in to: " + ", ".join(failed))
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
