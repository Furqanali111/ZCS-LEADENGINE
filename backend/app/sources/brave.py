"""Brave Search client. Pure: no database, no settings. Returns result URLs only: Brave's terms bar
storing search results, so titles, snippets and ranks are never returned. The key never enters an error."""
from typing import Literal

import httpx

URL = "https://api.search.brave.com/res/v1/web/search"


class SearchError(Exception):
    def __init__(self, kind: Literal["auth", "rate_limited", "failed"]):
        super().__init__(f"Brave search {kind}")
        self.kind = kind


def search(client: httpx.Client, api_key: str, query: str, count: int = 5) -> list[str]:
    try:
        resp = client.get(URL, params={"q": query, "count": count},
                          headers={"X-Subscription-Token": api_key, "Accept": "application/json",
                                   "Cache-Control": "no-cache"})
    except httpx.HTTPError:
        raise SearchError("failed") from None  # httpx messages can echo request details
    if resp.status_code in (401, 402, 403):  # 402: quota or plan exhausted, pause the job
        raise SearchError("auth")
    if resp.status_code == 429:
        raise SearchError("rate_limited")
    if resp.status_code != 200:
        raise SearchError("failed")
    try:
        web = resp.json().get("web")
        results = web.get("results", []) if web is not None else []
    except (ValueError, AttributeError):
        raise SearchError("failed") from None
    if not isinstance(results, list):
        raise SearchError("failed")
    return [r["url"] for r in results if isinstance(r, dict) and isinstance(r.get("url"), str) and r["url"]]
