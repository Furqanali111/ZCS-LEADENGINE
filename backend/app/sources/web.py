"""Polite page fetcher for practice websites. Pure: no database, no settings.
Honors robots.txt and Crawl-delay, spaces requests per domain, skips CAPTCHA pages (never solves them)."""
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "ZCSLeadEngine/1.0 (internal prospecting tool)"
MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3
RETRIES = 2
CAPTCHA_MAX_BYTES = 5_000


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

    def _request(self, url: str, delay: float, *, record: bool = True) -> httpx.Response:
        host = urlsplit(url).netloc
        if host in self._last:
            wait = self._last[host] + delay - self.clock()
            if wait > 0:
                self.sleep(wait)
        try:
            return self.client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=False)
        except httpx.HTTPError as e:
            raise FetchFailed(f"{url}: {e}") from e
        finally:
            if record:  # robots.txt does not count toward page spacing
                self._last[host] = self.clock()

    def _robots_for(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp: RobotFileParser | None = RobotFileParser()
            try:
                resp = self._request(f"{origin}/robots.txt", self.min_interval, record=False)
            except FetchFailed:
                resp = None
            if resp is None or resp.status_code >= 500:
                rp = None
            elif resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp.parse([])  # 4xx: no robots file, everything allowed
            self._robots[origin] = rp
        return self._robots[origin]

    def get(self, url: str) -> Page | None:
        for _ in range(MAX_REDIRECTS + 1):
            rp = self._robots_for(url)
            if rp is None or not rp.can_fetch(USER_AGENT, url):
                self.stats["blocked_by_robots"] += 1
                return None
            delay = max(self.min_interval, float(rp.crawl_delay(USER_AGENT) or 0))
            resp = self._fetch_with_retries(url, delay)
            if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                url = urljoin(url, resp.headers["location"])
                continue
            return self._accept(url, resp)
        self.stats["skipped"] += 1  # redirect chain too long
        return None

    def _fetch_with_retries(self, url: str, delay: float) -> httpx.Response:
        for attempt in range(RETRIES + 1):
            resp = self._request(url, delay)
            if resp.status_code < 500:
                return resp
        raise FetchFailed(f"{url}: HTTP {resp.status_code} after {RETRIES} retries")

    def _accept(self, url: str, resp: httpx.Response) -> Page | None:
        ctype = resp.headers.get("content-type", "").lower()
        body = resp.content
        small_captcha = len(body) < CAPTCHA_MAX_BYTES and b"captcha" in body.lower()
        if (resp.status_code != 200 or not ctype.startswith(("text/html", "application/xhtml"))
                or len(body) > MAX_BYTES or small_captcha):
            self.stats["skipped"] += 1
            return None
        self.stats["pages_fetched"] += 1
        return Page(url, resp.text)
