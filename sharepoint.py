"""UW SharePoint and OneDrive: files shared by link, like course schedules and sign-up sheets."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastmcp.exceptions import ToolError

from web import SignInRequired, Web

HOSTS = ("uofwaterloo-my.sharepoint.com", "uofwaterloo.sharepoint.com")
HOME = "https://uofwaterloo-my.sharepoint.com/_api/web/title"


def is_link(url: str | None) -> bool:
    parts = urlsplit(url or "")
    return parts.scheme == "https" and parts.hostname in HOSTS


def ping(web: Web):
    r = web.get(HOME, headers={"Accept": "application/json;odata=nometadata"})
    if not r.ok or "json" not in r.headers.get("content-type", ""):  # bounced to Microsoft sign-in
        raise SignInRequired("SharePoint")


def download_url(url: str) -> str:
    """The sharing link with download=1, which hands over the file itself instead of the web viewer."""
    if not is_link(url):
        raise ToolError("Not a UW SharePoint or OneDrive link (uofwaterloo-my.sharepoint.com).")
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query)) | {"download": "1"}
    return urlunsplit(parts._replace(query=urlencode(query)))
