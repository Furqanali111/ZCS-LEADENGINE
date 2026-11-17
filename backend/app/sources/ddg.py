"""DuckDuckGo fallback through the unofficial `ddgs` library. There is no official API, so this is off until the
owner marks `duckduckgo_search` available. Returns URLs only. A rate limit is reported, never worked around."""
import re

from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException

from app.sources.brave import SearchError


_GENERIC = {"inc", "llc", "pllc", "the", "and", "medical", "medicine", "clinic", "center", "health", "family", "care",
            "group", "practice", "associates", "services", "physicians", "office", "pllp", "corp"}


def _relevant(r: dict, tokens: list[str]) -> bool:
    # ddgs falls back to Wikipedia/Yahoo fuzzy matching when real engines block us, so results can be unrelated junk
    text = re.sub(r"[^a-z0-9]", "", f"{r.get('href', '')} {r.get('title', '')} {r.get('body', '')}".lower())
    need = min(2, len(tokens))
    return sum(t in text for t in tokens) >= need


def search(client, api_key, query: str, count: int = 5) -> list[str]:  # client and key unused: same shape as the other providers
    try:
        results = DDGS(timeout=15).text(query, region="us-en", max_results=count)
    except RatelimitException:
        raise SearchError("rate_limited") from None
    except DDGSException:  # "No results found" also lands here
        raise SearchError("failed") from None
    except Exception:
        raise SearchError("failed") from None
    # shortcut: tokens come from the whole query (name, city, state), so a city match counts; upgrade if junk still slips through
    tokens = [t for t in re.findall(r"[a-z0-9]{3,}", query.lower()) if t not in _GENERIC]
    return [r["href"] for r in results if isinstance(r, dict) and isinstance(r.get("href"), str) and r["href"]
            and _relevant(r, tokens)]
