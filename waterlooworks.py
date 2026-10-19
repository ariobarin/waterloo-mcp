"""WaterlooWorks co-op job board (Orbis), read-only.

Protocol (from ariobarin/waterloo-works-scraper docs/API.md): the jobs page embeds per-session
action tokens; POSTing them back to the same URL returns JSON for listings and HTML for postings.
"""

import json
import re
import time

from bs4 import BeautifulSoup

from web import SignInRequired, Web

JOBS = "https://waterlooworks.uwaterloo.ca/myAccount/co-op/full/jobs.htm"
LOGIN = "https://waterlooworks.uwaterloo.ca/waterloo.htm?action=login"
TOKENS = {
    "list": r"dataParams:\s*\{\s*action:\s*['\"]([^'\"]+)",
    "metadata": r"function getPostingData\([^)]*\)\s*\{[^}]*?action:\s*['\"]([^'\"]+)",
    "details": r"function getPostingOverview\([^)]*\)\s*\{[^}]*?action:\s*['\"]([^'\"]+)",
}


def signed_in(response) -> bool:
    return response.url.startswith("https://waterlooworks.uwaterloo.ca/") and 'href="/logout.htm"' in response.text


def parse_details(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select("script, style, button, input"):
        el.decompose()
    sections = {}
    for panel in soup.select(".panel"):
        heading, fields = panel.select_one("h4"), {}
        for item in panel.select(".tag__key-value-list"):
            label = item.select_one(".label")
            if label is None:
                continue
            key = label.get_text(" ", strip=True).rstrip(":")
            label.decompose()
            for link in item.select("a[href]"):
                if link["href"].startswith(("https://", "http://", "mailto:")):
                    link.append(f" ({link['href']})")
            fields[key] = "\n".join(" ".join(l.split()) for l in item.get_text("\n", strip=True).splitlines() if l.strip())
        if heading and fields:
            sections[heading.get_text(" ", strip=True)] = fields
    return sections


class WaterlooWorks:
    def __init__(self, web: Web, delay: float = 1.0):
        self.web, self.delay = web, delay
        self._tokens: dict[str, str] = {}
        self._last = 0.0

    def ping(self):
        """Load the board (renewing through SSO if needed) and refresh action tokens."""
        page = self.web.get(JOBS)
        if not signed_in(page):
            self.web.get(LOGIN)
            page = self.web.get(JOBS)
        if not signed_in(page):
            raise SignInRequired("WaterlooWorks")
        self._tokens = {k: m[1] for k, p in TOKENS.items() if (m := re.search(p, page.text, re.S))}

    def _post(self, token: str, **fields):
        if token not in self._tokens:
            self.ping()
        time.sleep(max(0.0, self.delay - (time.monotonic() - self._last)))
        try:
            r = self.web.post(JOBS, data={"action": self._tokens[token], **fields})
        finally:
            self._last = time.monotonic()
        if r.status_code in (401, 403) or not r.ok:
            self._tokens = {}
            raise SignInRequired("WaterlooWorks")
        return r

    def jobs(self, page: int = 1, per_page: int = 50, keyword: str = "") -> dict:
        r = self._post("list", isDataViewer="true", page=page, itemsPerPage=per_page, keyword=keyword,
                       sort=json.dumps([{"key": "Id", "direction": "desc"}]), filters="null")
        try:
            data = json.loads(r.text)  # JSON served as ISO-8859-1 text/html
        except ValueError:
            self._tokens = {}
            raise SignInRequired("WaterlooWorks") from None
        jobs = []
        for row in data["data"]:
            f = {i["key"]: i["value"] for i in row["data"]}
            jobs.append({
                "id": str(row["id"]), "title": f["JobTitle"]["postingTitle"], "organization": f.get("Organization"),
                "division": f.get("Division"), "city": f.get("City"), "level": f.get("Level"),
                "openings": f.get("Openings"), "applications": f.get("ApplicationCount"),
                "deadline": f.get("deadline"), "applied": f.get("hasApplication"),
            })
        return {"total": data["totalResults"], "page": page, "jobs": jobs}

    def job(self, posting_id: int) -> dict:
        meta = json.loads(self._post("metadata", postingId=str(posting_id)).text)
        return {
            "id": str(posting_id), "title": meta.get("position"), "organization": meta.get("org"),
            "division": meta.get("div"), "status": meta.get("status"),
            "sections": parse_details(self._post("details", postingId=str(posting_id)).text),
        }
