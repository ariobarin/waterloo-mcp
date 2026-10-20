"""One cookie-backed HTTP session for every service, renewed through UW single sign-on.

Cookies come from `login.py` (a real browser, so you can do Duo). The server never sees a password:
when a service bounces to sign-in, we only replay the SAML hand-off forms, which works while the
UW SSO session is still alive.
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from curl_cffi import requests
from fastmcp.exceptions import ToolError

TRUSTED = (".uwaterloo.ca", ".duosecurity.com", "app.crowdmark.com")
SSO_FIELDS = "input[name=SAMLRequest], input[name=SAMLResponse], input[name=RelayState]"


class SignInRequired(ToolError):
    def __init__(self, service: str):
        super().__init__(f"{service} needs a fresh sign-in: run `python login.py --push <host>:<dir>` (see README).")


def trusted(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or ""
    return parts.scheme == "https" and any(host == t.lstrip(".") or host.endswith(t) for t in TRUSTED)


def text(html: str | None, limit: int | None = None) -> str | None:
    """HTML to plain text."""
    if not html:
        return None
    out = " ".join(BeautifulSoup(html, "html.parser").get_text(" ").split())
    return out[:limit] if limit else out


class Web:
    def __init__(self, cookie_file: Path):
        self.cookie_file = cookie_file
        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session(impersonate="chrome", timeout=30)
        self.lock = threading.Lock()
        self._load()

    def _load(self):
        if not self.cookie_file.exists():
            return
        data = json.loads(self.cookie_file.read_text(encoding="utf-8"))
        for c in data["cookies"] if isinstance(data, dict) else data:
            if 0 < (c.get("expires") or -1) <= time.time():
                continue  # expired
            self.session.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))

    def save(self):
        """Persist cookies atomically. Only called after keepalive, so writes stay rare."""
        cookies = [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path, "expires": c.expires or -1}
            for c in self.session.cookies.jar
        ]
        fd, tmp = tempfile.mkstemp(dir=self.cookie_file.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"cookies": cookies}, f)
        os.replace(tmp, self.cookie_file)

    def request(self, method: str, url: str, **kw):
        with self.lock:
            return self._through_sso(self.session.request(method, url, **kw))

    def stream(self, url: str):
        """Open a download on its own connection (outside the lock) so big files pass through in chunks."""
        r = requests.get(url, cookies=self.session.cookies, impersonate="chrome", stream=True, timeout=60)
        if not r.ok or r.headers.get("content-type", "").startswith("text/html"):
            r.close()
            raise SignInRequired(urlsplit(url).hostname)
        return r

    def get(self, url: str, **kw):
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw):
        return self.request("POST", url, **kw)

    def _through_sso(self, response):
        """Auto-submit SAML hand-off forms on trusted hosts; stop at anything that wants a human."""
        for _ in range(6):
            if "html" not in response.headers.get("content-type", ""):
                return response  # JSON and files never carry SSO forms; skip parsing them
            field = BeautifulSoup(response.text, "html.parser").select_one(SSO_FIELDS)
            form = field and field.find_parent("form")
            if not form:
                return response
            target = urljoin(response.url, form.get("action", ""))
            if not trusted(target):
                return response
            values = {i["name"]: i.get("value", "") for i in form.select("input[name]")}
            response = self.session.post(target, data=values)
        return response
