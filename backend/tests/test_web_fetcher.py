import httpx
import pytest

from app.sources.web import FetchFailed, Page, PoliteFetcher

HTML = {"content-type": "text/html; charset=utf-8"}


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def make(routes, **kw):
    """routes: path -> httpx.Response or callable; unknown paths 404. Returns fetcher, request log, clock."""
    log, clock = [], Clock()

    def handler(req: httpx.Request) -> httpx.Response:
        log.append(str(req.url))
        r = routes.get((req.url.host, req.url.path)) or routes.get(req.url.path)
        if r is None:
            return httpx.Response(404)
        if isinstance(r, Exception):
            raise r
        return r(req) if callable(r) else r

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PoliteFetcher(client, sleep=clock.sleep, clock=clock.time, **kw), log, clock


def ok(body="<html>hi</html>"):
    return httpx.Response(200, headers=HTML, text=body)


def test_returns_page_and_sends_user_agent():
    seen = []
    f, _, _ = make({"/": lambda r: (seen.append(r.headers["user-agent"]), ok())[1]})
    page = f.get("https://a.com/")
    assert page == Page("https://a.com/", "<html>hi</html>")
    assert seen == ["ZCSLeadEngine/1.0 (internal prospecting tool)"]
    assert f.stats["pages_fetched"] == 1


def test_disallowed_by_robots_not_requested():
    f, log, _ = make({"/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /private"),
                      "/private": ok()})
    assert f.get("https://a.com/private") is None
    assert f.stats["blocked_by_robots"] == 1
    assert "https://a.com/private" not in log


def test_crawl_delay_spaces_requests():
    f, _, clock = make({"/robots.txt": httpx.Response(200, text="User-agent: *\nCrawl-delay: 3"),
                        "/a": ok(), "/b": ok()})
    f.get("https://a.com/a")
    f.get("https://a.com/b")
    assert clock.sleeps and all(s >= 1.0 for s in clock.sleeps)
    assert max(clock.sleeps) >= 3 or sum(clock.sleeps) >= 3


def test_second_page_waits_full_crawl_delay():
    f, _, clock = make({"/robots.txt": httpx.Response(200, text="User-agent: *\nCrawl-delay: 3"),
                        "/a": ok(), "/b": ok()})
    f.get("https://a.com/a")
    clock.sleeps.clear()
    f.get("https://a.com/b")
    assert clock.sleeps == [3]


def test_different_domains_do_not_wait():
    f, _, clock = make({"/": ok()})
    f.get("https://a.com/")
    f.get("https://b.com/")
    assert clock.sleeps == []


@pytest.mark.parametrize("resp", [
    httpx.Response(403), httpx.Response(404),
    httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF"),
    httpx.Response(200, headers=HTML, content=b"x" * 1_000_001),
    httpx.Response(200, headers=HTML, text="<html>Please solve this CAPTCHA</html>"),
])
def test_skipped_responses(resp):
    f, _, _ = make({"/x": resp})
    assert f.get("https://a.com/x") is None
    assert f.stats["skipped"] == 1
    assert f.stats["pages_fetched"] == 0


def test_large_page_mentioning_captcha_is_kept():
    f, _, _ = make({"/x": ok("captcha " + "y" * 6000)})
    assert f.get("https://a.com/x") is not None


def test_500_retries_twice_then_raises():
    calls = []
    f, _, _ = make({"/x": lambda r: (calls.append(1), httpx.Response(500))[1]})
    with pytest.raises(FetchFailed):
        f.get("https://a.com/x")
    assert len(calls) == 3


def test_500_then_success():
    n = []
    f, _, _ = make({"/x": lambda r: ok() if n else (n.append(1), httpx.Response(503))[1]})
    assert f.get("https://a.com/x") is not None


def test_timeout_raises():
    f, _, _ = make({"/x": httpx.ReadTimeout("slow")})
    with pytest.raises(FetchFailed):
        f.get("https://a.com/x")


def test_robots_5xx_allows_nothing():
    f, log, _ = make({"/robots.txt": httpx.Response(503), "/x": ok()})
    assert f.get("https://a.com/x") is None
    assert f.stats["blocked_by_robots"] == 1
    assert "https://a.com/x" not in log


def test_robots_cached_per_domain():
    f, log, _ = make({"/a": ok(), "/b": ok(), "/c": ok()})
    for p in "abc":
        f.get(f"https://a.com/{p}")
    assert sum(u.endswith("/robots.txt") for u in log) == 1


def test_redirect_to_other_domain_returns_final_url():
    f, _, _ = make({("a.com", "/"): httpx.Response(301, headers={"location": "https://b.com/home"}),
                    ("b.com", "/home"): ok()})
    assert f.get("https://a.com/").url == "https://b.com/home"


def test_too_many_redirects_skipped():
    f, _, _ = make({"/": httpx.Response(302, headers={"location": "/"})})
    assert f.get("https://a.com/") is None
    assert f.stats["skipped"] == 1
