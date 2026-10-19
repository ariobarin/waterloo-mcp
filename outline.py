"""outline.uwaterloo.ca: your course outlines (schedule, instructors, assessments, policies)."""

from bs4 import BeautifulSoup

from web import SignInRequired, Web

HOST = "https://outline.uwaterloo.ca"

SEASONS = {"1": "Winter", "5": "Spring", "9": "Fall"}


def _page(web: Web, path: str) -> BeautifulSoup:
    r = web.get(HOST + path)
    if not r.ok or not r.url.startswith(HOST):  # bounced to UW sign-in
        raise SignInRequired("Outline")
    return BeautifulSoup(r.text, "html.parser")


def search(web: Web, query: str = "") -> list[dict]:
    """Empty query: your enrolled courses. Otherwise: every outline at UW matching the query."""
    r = web.get(f"{HOST}/viewer/api/search/", params={"q": query}, headers={"Accept": "application/json"})
    if not r.ok or "json" not in r.headers.get("content-type", ""):
        raise SignInRequired("Outline")
    return [
        {"id": o["url"].rstrip("/").rsplit("/", 1)[-1], "course": o["courses"], "title": o["title"],
         "term": f"{SEASONS.get(o['term'][-1], '?')} 20{o['term'][1:3]}", "sections": o.get("sections"),
         "instructors": [i.strip() for i in o.get("instructors", []) if i.strip()]}
        for o in sorted(r.json(), key=lambda o: o["term"], reverse=True)  # newest term first
    ]


def outline(web: Web, outline_id: str, section: str | None = None) -> dict:
    main = _page(web, f"/viewer/view/{outline_id}").select_one("main") or BeautifulSoup("", "html.parser")
    sections, current = {}, "Overview"
    for el in main.find_all(["h2", "p", "li", "tr", "h3"]):
        if el.name == "h2":
            current = el.get_text(" ", strip=True)
            continue
        if el.find_parent(["li", "tr"]) or (el.name == "p" and el.find_parent("li")):
            continue  # already counted as part of its row or list item
        line = " ".join(el.get_text(" ", strip=True).split())
        if line:
            sections.setdefault(current, []).append(f"## {line}" if el.name == "h3" else line)
    sections.pop("Table of Contents", None)
    if section:
        key = next((k for k in sections if section.lower() in k.lower()), None)
        return {"section": key, "text": "\n".join(sections.get(key, []))}
    return {"sections": list(sections), "hint": "Call again with section= to read one, e.g. 'Assessments'."}
