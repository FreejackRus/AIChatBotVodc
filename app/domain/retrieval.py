from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

VODC_PAGE_HOSTS = frozenset({"vodc.ru", "www.vodc.ru"})


def canonical_vodc_page_key(value: str) -> str | None:
    """Return a comparison key, never content or metadata supplied by the client."""

    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or host not in VODC_PAGE_HOSTS
        or parsed.username
        or parsed.password
        or port not in {None, 443}
    ):
        return None
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    path = path.rstrip("/")
    return urlunparse(("https", "vodc.ru", path, "", "", ""))
