"""LEARN (D2L Brightspace) through its REST API, using your browser session."""

import re
from datetime import datetime, timedelta, timezone

from web import SignInRequired, Web, text

HOST = "https://learn.uwaterloo.ca"
LP = "/d2l/api/lp/1.43"
LE = "/d2l/api/le/1.57"


class Learn:
    def __init__(self, web: Web):
        self.web = web

    def _api(self, path: str):
        for attempt in range(2):
            r = self.web.get(HOST + path, headers={"Accept": "application/json"})
            if r.status_code == 404:
                raise LookupError(f"Not found on LEARN: {path}")
            if r.ok and "json" in r.headers.get("content-type", ""):
                return r.json()
            if r.status_code not in (401, 403) and "json" in r.headers.get("content-type", ""):
                raise RuntimeError(f"LEARN error {r.status_code}: {r.text[:200]}")
            if attempt == 0:
                self.web.get(HOST + "/d2l/home")  # bounce through SSO to renew
        raise SignInRequired("LEARN")

    def whoami(self):
        return self._api(f"{LP}/users/whoami")

    def courses(self):
        data = self._api(f"{LP}/enrollments/myenrollments/?orgUnitTypeId=3")
        return [
            {"id": e["OrgUnit"]["Id"], "name": e["OrgUnit"]["Name"], "code": e["OrgUnit"]["Code"],
             "start": e["Access"]["StartDate"], "end": e["Access"]["EndDate"]}
            for e in data.get("Items", [])
            if e["Access"]["IsActive"] and e["Access"]["CanAccess"]
        ]

    def grades(self, course: int):
        return [
            {"name": g["GradeObjectName"], "points": g.get("PointsNumerator"), "out_of": g.get("PointsDenominator"),
             "weighted": g.get("WeightedNumerator"), "weight": g.get("WeightedDenominator"),
             "displayed": g.get("DisplayedGrade")}
            for g in self._api(f"{LE}/{course}/grades/values/myGradeValues/")
        ]

    def assignments(self, course: int):
        return [
            {"id": f["Id"], "name": f["Name"], "due": f.get("DueDate"), "end": f.get("EndDate"),
             "instructions": text((f.get("Instructions") or {}).get("Html"), 400)}
            for f in self._api(f"{LE}/{course}/dropbox/folders/")
        ]

    def assignment(self, course: int, folder: int):
        f = self._api(f"{LE}/{course}/dropbox/folders/{folder}")
        subs = self._api(f"{LE}/{course}/dropbox/folders/{folder}/submissions/")
        return {
            "id": f["Id"], "name": f["Name"], "due": f.get("DueDate"), "end": f.get("EndDate"),
            "instructions": text((f.get("Instructions") or {}).get("Html")),
            "attachments": [a.get("FileName") for a in f.get("Attachments", [])],
            "my_submissions": [
                {"date": s.get("SubmissionDate"), "files": [x.get("FileName") for x in s.get("Files", [])]}
                for entity in subs for s in entity.get("Submissions", [])
            ],
        }

    def due(self, days: int = 14):
        now = datetime.now(timezone.utc)
        fmt = "%Y-%m-%dT%H:%M:%S.000Z"  # D2L's UTCDateTime format
        window = f"startDateTime={(now - timedelta(days=1)).strftime(fmt)}&endDateTime={(now + timedelta(days=days)).strftime(fmt)}"
        events = []
        for c in self.courses():
            page = self._api(f"{LE}/{c['id']}/calendar/events/myEvents/?{window}")
            for e in page.get("Objects", []) if isinstance(page, dict) else page:  # paged result
                events.append({"course": c["code"], "title": e["Title"], "start": e["StartDateTime"],
                               "end": e["EndDateTime"], "done": self._done(c["id"], e.get("AssociatedEntity")),
                               "details": text(e.get("Description"), 200)})
        return sorted(events, key=lambda e: e["start"])

    def _done(self, course: int, entity: dict | None) -> bool | None:
        """Whether you've submitted the quiz or dropbox behind a calendar event; None if unknowable."""
        kind, eid = (entity or {}).get("AssociatedEntityType", ""), (entity or {}).get("AssociatedEntityId")
        if kind.endswith("Quiz"):
            # Students can't read the attempts API, but the quiz summary page says "Completed - N".
            page = self.web.get(f"{HOST}/d2l/lms/quizzing/user/quiz_summary.d2l?ou={course}&qi={eid}").text
            found = re.search(r"Completed\s*-\s*(\d+)", text(page) or "")
            return int(found[1]) > 0 if found else None
        if kind.endswith("Dropbox"):
            subs = self._api(f"{LE}/{course}/dropbox/folders/{eid}/submissions/")
            return any(entity.get("Submissions") for entity in subs)
        return None

    def announcements(self, course: int, limit: int = 10):
        news = sorted(self._api(f"{LE}/{course}/news/"), key=lambda n: n.get("StartDate") or "", reverse=True)
        return [
            {"title": n["Title"], "date": n.get("StartDate"), "body": text((n.get("Body") or {}).get("Html"), 1500)}
            for n in news[:limit]
        ]

    def content(self, course: int):
        def node(m):
            return {
                "title": m["Title"],
                "modules": [node(x) for x in m.get("Modules", [])],
                "topics": [{"id": t.get("TopicId") or t.get("Id"), "title": t["Title"], "url": t.get("Url")}
                           for t in m.get("Topics", [])],
            }
        return [node(m) for m in self._api(f"{LE}/{course}/content/toc").get("Modules", [])]

    def file_url(self, course: int, topic: int) -> str:
        return f"{HOST}{LE}/{course}/content/topics/{topic}/file"

    def topic(self, course: int, topic: int):
        t = self._api(f"{LE}/{course}/content/topics/{topic}")
        return {"title": t["Title"], "url": t.get("Url"), "type": t.get("TypeIdentifier"),
                "description": text((t.get("Description") or {}).get("Html"))}
