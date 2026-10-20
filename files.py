"""Files: small ones go straight to the model; every one gets a one-time download link.

Links stream the file through this server in chunks, so nothing is ever written to disk.
"""

import asyncio
import re
import secrets
import time

from fastmcp.utilities.types import File, Image
from mcp.types import TextContent
from starlette.responses import PlainTextResponse, StreamingResponse

from web import SignInRequired, Web

INLINE_LIMIT = 4_000_000  # bytes of a file to hand to the model directly
LINK_SECONDS = 600  # download links work for 10 minutes


class Files:
    def __init__(self, web: Web, public_url: str | None):
        self.web = web
        self.public_url = public_url
        self.links: dict[str, tuple[str, float]] = {}  # token -> (upstream url, expiry); memory only

    def open(self, url: str, fallback_name: str) -> list:
        """The file's contents if the model can read them (PDF, image, text under 4 MB), plus a download
        link when there's a public URL to serve it from."""
        r = self.web.stream(url)
        try:
            kind = r.headers.get("content-type", "application/octet-stream").split(";")[0]
            size = int(r.headers["content-length"]) if "content-length" in r.headers else None
            found = re.search(r'filename="?([^";]+)', r.headers.get("content-disposition", ""))
            name = found[1] if found else fallback_name
            data = self._read_capped(r) if (size or 0) <= INLINE_LIMIT else None
        finally:
            r.close()

        blocks = [self._link(url, name, kind, size)] if self.public_url else []
        unreadable = [TextContent(type="text", text=f"{name} ({kind}, {size or '?'} bytes) can't be opened here.")]
        if data is None:
            return blocks or unreadable
        if kind.startswith("image/"):
            return [Image(data=data, format=kind.split("/")[1]), *blocks]
        if kind == "application/pdf":
            return [File(data=data, format="pdf", name=name), *blocks]
        if kind.startswith("text/") or kind in ("application/json", "application/xml"):
            return [TextContent(type="text", text=data.decode("utf-8", "replace")), *blocks]
        return blocks or unreadable

    async def serve(self, request):
        """Route handler for /files/{token}: pass the file through, then forget the link."""
        url, expiry = self.links.pop(request.path_params["token"], (None, 0))
        if not url or expiry < time.time():
            return PlainTextResponse("Link expired. Ask Claude for a new one.", status_code=404)
        try:
            upstream = await asyncio.to_thread(self.web.stream, url)
        except SignInRequired as e:
            return PlainTextResponse(str(e), status_code=502)
        headers = {k: v for k, v in upstream.headers.items() if k.lower() in ("content-length", "content-disposition")}
        return StreamingResponse(upstream.iter_content(chunk_size=65536), headers=headers,
                                 media_type=upstream.headers.get("content-type"))

    def _link(self, url: str, name: str, kind: str, size: int | None) -> TextContent:
        now = time.time()
        for token in [t for t, (_, expiry) in self.links.items() if expiry < now]:
            del self.links[token]
        token = secrets.token_urlsafe(24)
        self.links[token] = (url, now + LINK_SECONDS)
        # Plain text rather than a resource_link block: claude.ai doesn't render those yet.
        return TextContent(type="text", text=f"Download {name} ({kind}, {size or '?'} bytes, one use, 10 min): "
                                             f"{self.public_url}/files/{token}")

    @staticmethod
    def _read_capped(response) -> bytes | None:
        """The whole body if it fits under INLINE_LIMIT; stops reading as soon as it doesn't."""
        data = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            data += chunk
            if len(data) > INLINE_LIMIT:
                return None
        return bytes(data)
