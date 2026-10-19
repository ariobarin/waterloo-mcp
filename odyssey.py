"""Odyssey: your midterm, quiz and final schedule with rooms and seats."""

from bs4 import BeautifulSoup

from web import SignInRequired, Web

URL = "https://odyssey.uwaterloo.ca/teaching/schedule"


def exam_schedule(web: Web) -> list[dict]:
    r = web.get(URL)
    table = BeautifulSoup(r.text, "html.parser").select_one("table")
    if not r.url.startswith(URL) or table is None:
        raise SignInRequired("Odyssey")
    headers = [th.get_text(strip=True).lower() for th in table.select("th")]
    return [
        dict(zip(headers, (td.get_text(" ", strip=True) for td in tr.select("td"))))
        for tr in table.select("tr") if tr.select("td")
    ]
