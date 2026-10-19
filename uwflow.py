"""UW Flow: public course info, requisites and ratings. No sign-in."""

from curl_cffi import requests

QUERY = """query($code: String!) {
  course(where: {code: {_eq: $code}}) {
    code name description prereqs coreqs antireqs
    rating { liked easy useful filled_count comment_count }
  }
}"""


def course(code: str) -> dict | None:
    code = "".join(code.lower().split())
    r = requests.post("https://uwflow.com/graphql", json={"query": QUERY, "variables": {"code": code}}, timeout=20)
    r.raise_for_status()
    found = r.json()["data"]["course"]
    return found[0] if found else None
