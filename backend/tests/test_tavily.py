import httpx
import pytest

from app.config import Settings
from app.sources.brave import SearchError
from app.sources.provider import search_provider
from app.sources.tavily import search

KEY = "tvly-secret-123"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_posts_bearer_and_returns_urls_only():
    seen = {}

    def handler(req):
        seen["req"] = req
        return httpx.Response(200, json={"results": [{"url": "https://a.com", "title": "A", "content": "x", "score": 1},
                                                      {"url": "https://b.com"}, {"title": "no url"}]})

    assert search(_client(handler), KEY, "dr smith tampa", count=3) == ["https://a.com", "https://b.com"]
    req = seen["req"]
    assert req.method == "POST" and req.url.host == "api.tavily.com" and req.url.path == "/search"
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    body = req.read().decode()
    assert '"max_results":3' in body.replace(" ", "") and '"search_depth":"basic"' in body.replace(" ", "")


@pytest.mark.parametrize("status,kind", [(401, "auth"), (432, "auth"), (433, "auth"), (429, "rate_limited"), (500, "failed"), (400, "failed")])
def test_status_maps_to_error_kind(status, kind):
    with pytest.raises(SearchError) as e:
        search(_client(lambda req: httpx.Response(status, json={})), KEY, "q")
    assert e.value.kind == kind and KEY not in str(e.value)


def test_bad_body_and_network_error_fail_without_key():
    for handler in (lambda req: httpx.Response(200, text="not json"), lambda req: httpx.Response(200, json={"results": "x"})):
        with pytest.raises(SearchError) as e:
            search(_client(handler), KEY, "q")
        assert e.value.kind == "failed"

    def boom(req):
        raise httpx.ConnectError(f"cannot reach {KEY}")

    with pytest.raises(SearchError) as e:
        search(_client(boom), KEY, "q")
    assert e.value.kind == "failed" and KEY not in str(e.value) and e.value.__cause__ is None


def test_provider_prefers_tavily_then_brave():
    base = {"database_url": "postgresql://x", "_env_file": None}
    assert search_provider(Settings(**base, tavily_api_key="t", brave_api_key="b"))[::2] == ("tavily_search", "t")
    assert search_provider(Settings(**base, brave_api_key="b"))[::2] == ("brave_search", "b")
    assert search_provider(Settings(**base))[::2] == ("brave_search", None)


def test_fallback_switches_after_auth_error_and_stays_switched():
    from app.sources.provider import with_fallback

    calls = []

    def primary(client, key, query, count=5):
        calls.append("primary")
        raise SearchError("auth")

    def fallback(client, key, query, count=5):
        calls.append("fallback")
        return ["https://x.com"]

    s = with_fallback(primary, fallback)
    assert s(None, "k", "q") == ["https://x.com"] and s(None, "k", "q") == ["https://x.com"]
    assert calls == ["primary", "fallback", "fallback"]


def test_fallback_does_not_hide_rate_limit():
    from app.sources.provider import with_fallback

    def primary(client, key, query, count=5):
        raise SearchError("rate_limited")

    with pytest.raises(SearchError) as e:
        with_fallback(primary, lambda *a, **k: ["https://x.com"])(None, "k", "q")
    assert e.value.kind == "rate_limited"


def test_ddg_returns_hrefs_and_maps_errors(monkeypatch):
    from ddgs.exceptions import DDGSException, RatelimitException

    from app.sources import ddg

    class Fake:
        outcome = [{"href": "https://a.com", "title": "A", "body": "x"}, {"title": "no href"}]

        def __init__(self, **kw): pass

        def text(self, query, **kw):
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

    monkeypatch.setattr(ddg, "DDGS", Fake)
    assert ddg.search(None, None, "q") == ["https://a.com"]
    for exc, kind in ((RatelimitException("x"), "rate_limited"), (DDGSException("No results found"), "failed"), (OSError("x"), "failed")):
        Fake.outcome = exc
        with pytest.raises(SearchError) as e:
            ddg.search(None, None, "q")
        assert e.value.kind == kind
