"""Crowdmark: assessments, due dates and whether marks are back (read-only)."""

from web import SignInRequired, Web

API = "https://app.crowdmark.com/api/v2/student"


def _get(web: Web, path: str) -> dict:
    r = web.get(API + path, headers={"Accept": "application/vnd.api+json"})
    if not r.ok or "json" not in r.headers.get("content-type", ""):
        raise SignInRequired("Crowdmark")
    return r.json()


def assessments(web: Web) -> list[dict]:
    courses = {c["id"]: c["attributes"]["name"] for c in _get(web, "/courses")["data"]}
    data = _get(web, "/assignments")
    exams = {i["id"]: i for i in data.get("included", []) if i["type"] == "exam-masters"}
    out = []
    for a in data["data"]:
        attrs = a["attributes"]
        exam = exams.get(a["relationships"]["exam-master"]["data"]["id"], {})
        course = exam.get("relationships", {}).get("course", {}).get("data") or {}
        out.append({
            "course": courses.get(course.get("id")),
            "title": exam.get("attributes", {}).get("title"),
            "type": exam.get("attributes", {}).get("type"),
            "due": attrs.get("due"),
            "submitted_at": attrs.get("submitted-at"),
            "marks_released_at": attrs.get("marks-sent-at"),
            "points": attrs.get("normalized-points"),
            "out_of": exam.get("attributes", {}).get("total-points"),
            "locked": attrs.get("is-locked"),
        })
    return sorted(out, key=lambda x: x["due"] or "", reverse=True)
