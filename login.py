"""Sign in to every service once in a real browser (Duo included) and save the cookies.

Run on your own computer:
    pip install playwright && playwright install chromium
    python login.py
Then copy cookies.json to the server's data volume. Your password goes only to UW's own sign-in page.
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

SERVICES = {
    "LEARN": ("https://learn.uwaterloo.ca/d2l/home", "https://learn.uwaterloo.ca/d2l/home"),
    "WaterlooWorks": ("https://waterlooworks.uwaterloo.ca/waterloo.htm?action=login",
                      "https://waterlooworks.uwaterloo.ca/myAccount/"),
    "Odyssey": ("https://odyssey.uwaterloo.ca/teaching/schedule", "https://odyssey.uwaterloo.ca/teaching/schedule"),
    "Crowdmark": ("https://app.crowdmark.com/sign-in/waterloo", "https://app.crowdmark.com/student"),
}


def main():
    out = Path(__file__).with_name("cookies.json")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        for name, (start, done) in SERVICES.items():
            print(f"{name}: sign in in the browser window (Crowdmark: click 'Sign in with LEARN')...")
            page.goto(start)
            page.wait_for_url(f"{done}**", timeout=300_000)
            print(f"{name}: ok")
        out.write_text(json.dumps(context.storage_state()))
        browser.close()
    print(f"Saved {out}. Copy it to the server, e.g.:\n"
          f"  docker compose cp cookies.json waterloo-mcp:/data/cookies.json && docker compose restart")


if __name__ == "__main__":
    main()
