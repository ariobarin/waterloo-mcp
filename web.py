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


LOGIN_WANTED: Path | None = None  # set when the optional autologin service runs; we add services to it to ask for a sign-in


class SignInRequired(ToolError):
    def __init__(self, service: str):
        if LOGIN_WANTED:
            with LOGIN_WANTED.open("a", encoding="utf-8") as f:
                f.write(service + "\n")
            super().__init__(f"{service} needs a fresh sign-in. The server is signing in again on its own: "
                             "approve the Duo push on your phone if one comes (if it asks for a code, "
                             "sign_in_status shows it), then try again in a minute.")
        else:
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

    def _mtime(self) -> float:
        try:
            return self.cookie_file.stat().st_mtime
        except FileNotFoundError:
            return 0

    def reload_if_changed(self) -> bool:
        """Pick up cookies a fresh sign-in wrote while we were running. True if it did."""
        with self.lock:
            return self._reload_if_changed()

    def _reload_if_changed(self) -> bool:
        if self._mtime() == self.loaded:
            return False
        self.session.cookies.clear()
        self._load()
        return True

    def _load(self):
        self.loaded = self._mtime()
        if not self.loaded:
            return
        data = json.loads(self.cookie_file.read_text(encoding="utf-8"))
        for c in data["cookies"] if isinstance(data, dict) else data:
            if 0 < (c.get("expires") or -1) <= time.time():
                continue  # expired
            self.session.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))

    def save(self):
        """Persist cookies atomically. Only called after keepalive, so writes stay rare."""
        with self.lock:
            if self._reload_if_changed():
                return  # a fresh sign-in landed; never overwrite it with our older cookies
            self._save()

    def _save(self):
        cookies = [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path, "expires": c.expires or -1}
            for c in self.session.cookies.jar
        ]
        fd, tmp = tempfile.mkstemp(dir=self.cookie_file.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"cookies": cookies}, f)
        os.replace(tmp, self.cookie_file)
        self.loaded = self._mtime()

    def request(self, method: str, url: str, **kw):
        with self.lock:
            self._reload_if_changed()
            return self._through_sso(self.session.request(method, url, **kw))

    def stream(self, url: str, service: str):
        """Open a download on its own connection (outside the lock) so big files pass through in chunks.
        An HTML file is a file too: only a refusal, or a bounce to some other page, means signed out."""
        r = requests.get(url, cookies=self.session.cookies, impersonate="chrome", stream=True, timeout=60)
        bounced = urlsplit(r.url).path != urlsplit(url).path and "html" in r.headers.get("content-type", "")
        if r.ok and not bounced:
            return r
        r.close()
        if r.status_code in (401, 403) or bounced:
            raise SignInRequired(service)
        if r.status_code == 404:
            raise ToolError(f"No file there on {service}: it may be a link rather than a file (see its url).")
        raise ToolError(f"{service} refused the download ({r.status_code}).")

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
