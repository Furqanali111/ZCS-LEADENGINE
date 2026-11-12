"""Tavily Search client. Pure: no database, no settings. Returns result URLs only: titles, snippets and scores
are never returned or stored. The key never enters an error."""
import httpx

from app.sources.brave import SearchError

URL = "https://api.tavily.com/search"


def search(client: httpx.Client, api_key: str, query: str, count: int = 5) -> list[str]:
    try:
        resp = client.post(URL, json={"query": query, "max_results": count, "search_depth": "basic",
                                      "include_answer": False, "include_raw_content": False},
                           headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError:
        raise SearchError("failed") from None  # httpx messages can echo request details
    if resp.status_code in (401, 432, 433):  # 432/433: key or plan limit exceeded, pause the job
        raise SearchError("auth")
    if resp.status_code == 429:
        raise SearchError("rate_limited")
    if resp.status_code != 200:
        raise SearchError("failed")
    try:
        results = resp.json().get("results", [])
    except (ValueError, AttributeError):
        raise SearchError("failed") from None
    if not isinstance(results, list):
        raise SearchError("failed")
    return [r["url"] for r in results if isinstance(r, dict) and isinstance(r.get("url"), str) and r["url"]]
