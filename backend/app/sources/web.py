"""Polite page fetcher for practice websites. Pure: no database, no settings.
Honors robots.txt and Crawl-delay, spaces requests per domain, skips CAPTCHA pages (never solves them)."""
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "ZCSLeadEngine/1.0 (internal prospecting tool)"
MAX_BYTES = 1_000_000
ROBOTS_MAX_BYTES = 512_000
MAX_REDIRECTS = 3
RETRIES = 2
CAPTCHA_MAX_BYTES = 5_000
REDIRECTS = (301, 302, 303, 307, 308)


class FetchFailed(Exception):
    pass


@dataclass
class Page:
    url: str
    html: str


class PoliteFetcher:
    def __init__(self, client: httpx.Client, *, sleep=time.sleep, clock=time.monotonic,
                 min_interval: float = 1.0):
        self.client, self.sleep, self.clock, self.min_interval = client, sleep, clock, min_interval
        self.stats = {"pages_fetched": 0, "blocked_by_robots": 0, "skipped": 0}
        self._robots: dict[str, RobotFileParser | None] = {}  # None means allow nothing
        self._last: dict[str, float] = {}

    def _send(self, url: str, delay: float, cap: int) -> tuple[httpx.Response, bytes | None]:
        """One spaced, streamed GET. Body is None when it exceeds cap (reading stops early)."""
        key = urlsplit(url).netloc.lower()
        if key in self._last:
            wait = self._last[key] + delay - self.clock()
            if wait > 0:
                self.sleep(wait)
        try:
            with self.client.stream("GET", url, headers={"User-Agent": USER_AGENT},
                                    follow_redirects=False) as resp:
                length = resp.headers.get("content-length", "")
                if length.isdigit() and int(length) > cap:
                    return resp, None
                chunks, size = [], 0
                for chunk in resp.iter_bytes():
                    size += len(chunk)
                    if size > cap:
                        return resp, None
                    chunks.append(chunk)
                return resp, b"".join(chunks)
        except (httpx.HTTPError, httpx.InvalidURL, UnicodeError) as e:
            raise FetchFailed(f"{url}: {e}") from e
        finally:
            self._last[key] = self.clock()

    @staticmethod
    def _is_http(url: str) -> bool:
        return urlsplit(url).scheme in ("http", "https")

    def _load_robots(self, origin: str) -> RobotFileParser | None:
        url = f"{origin}/robots.txt"
        for _ in range(MAX_REDIRECTS + 1):
            try:
                resp, body = self._send(url, self.min_interval, ROBOTS_MAX_BYTES)
            except FetchFailed:
                return None
            if resp.status_code in REDIRECTS and resp.headers.get("location"):
                url = urljoin(url, resp.headers["location"])
                if not self._is_http(url):
                    return None
                continue
            if body is None or resp.status_code >= 500 or resp.status_code in (401, 403) + REDIRECTS:
                return None
            rp = RobotFileParser()
            rp.parse(body.decode("utf-8", "replace").splitlines() if resp.status_code == 200 else [])
            return rp  # other 4xx: no robots file, everything allowed
        return None  # redirect loop

    def _robots_for(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc.lower()}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        return self._robots[origin]

    def get(self, url: str) -> Page | None:
        for _ in range(MAX_REDIRECTS + 1):
            if not self._is_http(url):
                self.stats["skipped"] += 1
                return None
            rp = self._robots_for(url)
            if rp is None or not rp.can_fetch(USER_AGENT, url):
                self.stats["blocked_by_robots"] += 1
                return None
            delay = max(self.min_interval, float(rp.crawl_delay(USER_AGENT) or 0))
            resp, body = self._fetch_with_retries(url, delay)
            if resp.status_code in REDIRECTS and resp.headers.get("location"):
                url = urljoin(url, resp.headers["location"])
                continue
            return self._accept(url, resp, body)
        self.stats["skipped"] += 1  # redirect chain too long
        return None

    def _fetch_with_retries(self, url: str, delay: float) -> tuple[httpx.Response, bytes | None]:
        for _ in range(RETRIES + 1):
            resp, body = self._send(url, delay, MAX_BYTES)
            if resp.status_code < 500:
                return resp, body
        raise FetchFailed(f"{url}: HTTP {resp.status_code} after {RETRIES} retries")

    def _accept(self, url: str, resp: httpx.Response, body: bytes | None) -> Page | None:
        ctype = resp.headers.get("content-type", "").lower()
        if (body is None or resp.status_code != 200 or not ctype.startswith(("text/html", "application/xhtml"))
                or (len(body) < CAPTCHA_MAX_BYTES and b"captcha" in body.lower())):
            self.stats["skipped"] += 1
            return None
        self.stats["pages_fetched"] += 1
        return Page(url, body.decode(resp.encoding or "utf-8", "replace"))
