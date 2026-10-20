"""Piazza: your classes, feeds, search and full posts (read-only), through its JSON-RPC API.

Uses the browser session from login.py. Method names follow the piazza-api library (MIT).
"""

import json
import random

from fastmcp.exceptions import ToolError

from web import SignInRequired, Web, text

API = "https://piazza.com/logic/api"


def _call(web: Web, method: str, **params):
    session = next((c.value for c in web.session.cookies.jar if c.name == "session_id"), None)
    if session is None:
        raise SignInRequired("Piazza")
    r = web.post(f"{API}?method={method}&aid={random.getrandbits(48):x}",
                 data=json.dumps({"method": method, "params": params}),
                 headers={"CSRF-Token": session, "Content-Type": "application/json"})
    body = r.json() if "json" in r.headers.get("content-type", "") else {}
    if body.get("error"):
        if "log" in str(body["error"]).lower():
            raise SignInRequired("Piazza")
        raise ToolError(f"Piazza: {body['error']}")
    if "result" not in body:
        raise SignInRequired("Piazza")
    return body["result"]


def classes(web: Web) -> list[dict]:
    return [
        {"id": n["id"], "course": n.get("course_number"), "name": n.get("name"), "term": n.get("term"),
         "active": n.get("status") == "active"}
        for n in _call(web, "user.status").get("networks", [])
    ]


def _summary(p: dict) -> dict:
    return {"id": p.get("id"), "number": p.get("nr"), "subject": text(p.get("subject")),
            "preview": text(p.get("content_snipet"), 200), "type": p.get("type"),
            "updated": p.get("updated"), "unanswered": p.get("no_answer") == 1, "pinned": bool(p.get("pin"))}


def feed(web: Web, class_id: str, limit: int = 30) -> list[dict]:
    result = _call(web, "network.get_my_feed", nid=class_id, limit=limit, offset=0, sort="updated")
    return [_summary(p) for p in result.get("feed", [])]


def search(web: Web, class_id: str, query: str) -> list[dict]:
    return [_summary(p) for p in _call(web, "network.search", nid=class_id, query=query)]


def post(web: Web, class_id: str, post_id: str) -> dict:
    p = _call(web, "content.get", nid=class_id, cid=post_id, student_view=None)
    latest = (p.get("history") or [{}])[0]

    def replies(children):
        out = []
        for c in children or []:
            body = (c.get("history") or [{}])[0].get("content") or c.get("subject")
            out.append({"type": c.get("type"), "text": text(body), "replies": replies(c.get("children"))})
        return out

    return {"number": p.get("nr"), "subject": text(latest.get("subject")), "text": text(latest.get("content")),
            "tags": p.get("tags"), "created": p.get("created"), "answers_and_followups": replies(p.get("children"))}
