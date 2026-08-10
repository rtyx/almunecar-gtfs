"""Shared HTTP fetching, caching and content hashing for source acquisition.

Fetching is deliberately conservative: one request at a time, a real contact
address in the User-Agent, an on-disk cache so re-running extraction does not
re-hit the operator's site, and a normalised content hash used by
``monitor-sources`` to notice when a page changes.

Cached response bodies are written under ``data/cache/``, which is git-ignored.
The repository stores extracted facts, URLs and hashes — not scraped assets.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

USER_AGENT = (
    "almunecar-gtfs/0.1 (+https://github.com/rtoledano/almunecar-gtfs; "
    "open transit data research; contact via repository issues)"
)

#: Minimum seconds between requests to the same host.
POLITE_DELAY_SECONDS = 2.0

DEFAULT_TIMEOUT = httpx.Timeout(30.0)

_last_request_at: dict[str, float] = {}


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    text: str
    retrieved_at: dt.date
    content_sha256: str
    normalized_sha256: str
    cache_path: Path | None = None
    from_cache: bool = False


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
_NONCE_LIKE = re.compile(r"\b(?:nonce|csrf|token|sid|_wpnonce)=[A-Za-z0-9_-]+", re.IGNORECASE)


def normalized_hash(text: str) -> str:
    """Hash of the page's visible text, ignoring markup and per-request noise.

    Source-change monitoring must fire on a changed departure time, not on a
    rotated CSRF token or a reordered analytics tag.
    """
    stripped = _SCRIPT_OR_STYLE.sub(" ", text)
    stripped = _NONCE_LIKE.sub("", stripped)
    stripped = _TAG.sub(" ", stripped)
    stripped = _WHITESPACE.sub(" ", stripped).strip().casefold()
    return hashlib.sha256(stripped.encode("utf-8")).hexdigest()


def _respect_delay(url: str) -> None:
    host = urlparse(url).netloc
    previous = _last_request_at.get(host)
    now = time.monotonic()
    if previous is not None:
        wait = POLITE_DELAY_SECONDS - (now - previous)
        if wait > 0:
            time.sleep(wait)
    _last_request_at[host] = time.monotonic()


def fetch(
    url: str,
    cache_dir: Path | None = None,
    *,
    force: bool = False,
    client: httpx.Client | None = None,
) -> FetchResult:
    """GET ``url``, using the on-disk cache unless ``force`` is set."""
    cache_path = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{cache_key(url)}.html"
        if cache_path.exists() and not force:
            text = cache_path.read_text(encoding="utf-8")
            return FetchResult(
                url=url,
                status_code=200,
                text=text,
                retrieved_at=dt.date.fromtimestamp(cache_path.stat().st_mtime),
                content_sha256=content_hash(text),
                normalized_sha256=normalized_hash(text),
                cache_path=cache_path,
                from_cache=True,
            )

    _respect_delay(url)
    owns_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT, follow_redirects=True
    )
    try:
        response = client.get(url)
    finally:
        if owns_client:
            client.close()

    text = response.text
    if cache_path is not None and response.status_code == 200:
        cache_path.write_text(text, encoding="utf-8")

    return FetchResult(
        url=url,
        status_code=response.status_code,
        text=text,
        retrieved_at=dt.date.today(),
        content_sha256=content_hash(text),
        normalized_sha256=normalized_hash(text),
        cache_path=cache_path,
        from_cache=False,
    )
