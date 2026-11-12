"""DuckDuckGo fallback through the unofficial `ddgs` library. There is no official API, so this is off until the
owner marks `duckduckgo_search` available. Returns URLs only. A rate limit is reported, never worked around."""
from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException

from app.sources.brave import SearchError


def search(client, api_key, query: str, count: int = 5) -> list[str]:  # client and key unused: same shape as the other providers
    try:
        results = DDGS(timeout=15).text(query, region="us-en", max_results=count)
    except RatelimitException:
        raise SearchError("rate_limited") from None
    except DDGSException:  # "No results found" also lands here
        raise SearchError("failed") from None
    except Exception:
        raise SearchError("failed") from None
    return [r["href"] for r in results if isinstance(r, dict) and isinstance(r.get("href"), str) and r["href"]]
