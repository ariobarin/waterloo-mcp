"""outline.uwaterloo.ca: your course outlines (schedule, instructors, assessments, policies)."""

from bs4 import BeautifulSoup

from web import SignInRequired, Web

HOST = "https://outline.uwaterloo.ca"


def _page(web: Web, path: str) -> BeautifulSoup:
    r = web.get(HOST + path)
    soup = BeautifulSoup(r.text, "html.parser")
    if not r.url.startswith(HOST) or soup.select_one('a[href="/oidc/logout/"]') is None:
        raise SignInRequired("Outline")
    return soup


def my_outlines(web: Web) -> list[dict]:
    soup = _page(web, "/viewer/?q=")
    out = []
    for row in soup.select("tr"):
        link = row.select_one('a[href^="/viewer/view/"]')
        cells = [td.get_text(" ", strip=True) for td in row.select("td")]
        if link and cells:
            term = row.find_previous(["h2", "h3", "h4"])
            out.append({"id": link["href"].rsplit("/", 1)[-1], "course": cells[0],
                        "title": cells[1] if len(cells) > 1 else None,
                        "term": term.get_text(strip=True) if term else None})
    return out


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
