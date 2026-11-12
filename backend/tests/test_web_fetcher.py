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
    f.get("https://B.com/")
    assert clock.sleeps == [1.0, 1.0]  # one wait per domain (page after robots), none across domains


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


def test_robots_5xx_cached_then_retried_after_ttl():
    calls = []
    def robots(req):
        calls.append(1)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, text="User-agent: *\nAllow: /")
    f, log, clock = make({"/robots.txt": robots, "/x": ok(), "/y": ok()})
    assert f.get("https://a.com/x") is None and f.get("https://a.com/y") is None
    assert len(calls) == 1  # the failure is remembered, not re-requested per page
    clock.now += 601
    assert f.get("https://a.com/x") is not None
    assert len(calls) == 2


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


def test_robots_redirect_is_followed_and_honored():
    f, _, _ = make({"/robots.txt": httpx.Response(301, headers={"location": "/rules.txt"}),
                    "/rules.txt": httpx.Response(200, text="User-agent: *\nDisallow: /"), "/x": ok()})
    assert f.get("https://a.com/x") is None
    assert f.stats["blocked_by_robots"] == 1


def test_robots_redirect_loop_blocks():
    f, _, _ = make({"/robots.txt": httpx.Response(301, headers={"location": "/robots.txt"}), "/x": ok()})
    assert f.get("https://a.com/x") is None
    assert f.stats["blocked_by_robots"] == 1


@pytest.mark.parametrize("status", [401, 403])
def test_robots_auth_wall_blocks(status):
    f, _, _ = make({"/robots.txt": httpx.Response(status), "/x": ok()})
    assert f.get("https://a.com/x") is None
    assert f.stats["blocked_by_robots"] == 1


def test_robots_404_allows():
    f, _, _ = make({"/x": ok()})  # unknown paths, robots.txt included, are 404
    assert f.get("https://a.com/x") is not None


def test_robots_over_cap_blocks():
    f, _, _ = make({"/robots.txt": httpx.Response(200, content=b"#" * 600_000), "/x": ok()})
    assert f.get("https://a.com/x") is None
    assert f.stats["blocked_by_robots"] == 1


def test_oversized_stream_stops_early():
    sent = []

    def body():
        for _ in range(10):
            sent.append(1)
            yield b"x" * 400_000

    f, _, _ = make({"/x": httpx.Response(200, headers=HTML, content=body())})
    assert f.get("https://a.com/x") is None
    assert f.stats["skipped"] == 1
    assert len(sent) <= 4


def test_three_hop_redirect_succeeds():
    f, _, _ = make({"/a": httpx.Response(301, headers={"location": "/b"}),
                    "/b": httpx.Response(301, headers={"location": "/c"}),
                    "/c": httpx.Response(301, headers={"location": "/d"}), "/d": ok()})
    assert f.get("https://a.com/a").url == "https://a.com/d"


def test_connection_error_raises():
    f, _, _ = make({"/x": httpx.ConnectError("refused")})
    with pytest.raises(FetchFailed):
        f.get("https://a.com/x")


def test_non_http_redirect_target_skipped_not_blocked():
    f, _, _ = make({"/x": httpx.Response(302, headers={"location": "ftp://a.com/file"})})
    assert f.get("https://a.com/x") is None
    assert f.stats["skipped"] == 1
    assert f.stats["blocked_by_robots"] == 0


@pytest.mark.parametrize("target", ["http://127.0.0.1:8000/", "http://169.254.169.254/latest", "http://intranet/",
                                    "https://yelp.com/biz/x"])
def test_redirect_to_non_public_host_refused(target):
    f, log, _ = make({("a.com", "/"): httpx.Response(302, headers={"location": target})})
    assert f.get("https://a.com/") is None
    assert f.stats["skipped"] == 1 and not any(u.startswith(target[:12]) for u in log)


def test_first_url_on_private_host_refused():
    f, log, _ = make({"/": ok()})
    assert f.get("http://10.0.0.5/") is None and log == [] and f.stats["skipped"] == 1


def test_bogus_charset_falls_back_to_utf8():
    f, _, _ = make({"/": httpx.Response(200, headers={"content-type": "text/html; charset=bogus-9"}, content=b"<p>caf\xc3\xa9</p>")})
    assert f.get("https://a.com/").html == "<p>café</p>"
