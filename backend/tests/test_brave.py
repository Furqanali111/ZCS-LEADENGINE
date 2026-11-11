import httpx
import pytest

from app.sources.brave import SearchError, search

KEY = "secret-key-123"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _json(body, status=200):
    return lambda req: httpx.Response(status, json=body)


def test_sends_token_and_params_and_returns_urls_only():
    seen = {}

    def handler(req):
        seen["req"] = req
        return httpx.Response(200, json={"web": {"results": [
            {"url": "https://a.com", "title": "A", "description": "x"},
            {"url": "https://b.com"}]}})

    assert search(_client(handler), KEY, "dr smith tampa", count=3) == ["https://a.com", "https://b.com"]
    req = seen["req"]
    assert req.url.host == "api.search.brave.com" and req.url.path == "/res/v1/web/search"
    assert req.url.params["q"] == "dr smith tampa" and req.url.params["count"] == "3"
    assert req.headers["X-Subscription-Token"] == KEY
    assert req.headers["Cache-Control"] == "no-cache"


@pytest.mark.parametrize("body", [{}, {"web": {}}, {"web": {"results": []}}])
def test_empty_or_missing_web_returns_empty(body):
    assert search(_client(_json(body)), KEY, "q") == []


def test_drops_non_string_and_empty_urls():
    body = {"web": {"results": [{"url": "https://a.com"}, {"url": ""}, {"url": 5}, {"title": "x"}, "junk"]}}
    assert search(_client(_json(body)), KEY, "q") == ["https://a.com"]


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth"), (429, "rate_limited"),
                                         (500, "failed"), (503, "failed")])
def test_status_maps_to_kind(status, kind):
    with pytest.raises(SearchError) as e:
        search(_client(_json({}, status)), KEY, "q")
    assert e.value.kind == kind
    assert KEY not in str(e.value) and KEY not in repr(e.value)


@pytest.mark.parametrize("resp", [
    httpx.Response(200, text="<html>nope</html>"),
    httpx.Response(200, json=[1, 2]),
    httpx.Response(200, json={"web": []}),
    httpx.Response(200, json={"web": {"results": {}}}),
])
def test_bad_body_is_failed(resp):
    with pytest.raises(SearchError) as e:
        search(_client(lambda req: resp), KEY, "q")
    assert e.value.kind == "failed"


def test_network_error_is_failed_and_hides_key():
    def handler(req):
        raise httpx.ConnectError(f"boom {req.headers['X-Subscription-Token']}", request=req)

    with pytest.raises(SearchError) as e:
        search(_client(handler), KEY, "q")
    assert e.value.kind == "failed"
    assert KEY not in str(e.value) and KEY not in repr(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__
