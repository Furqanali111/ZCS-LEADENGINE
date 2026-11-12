"""Which web search provider enrichment uses: Tavily when its key is set, otherwise Brave."""
from app.config import Settings
from app.sources import brave, tavily


def search_provider(settings: Settings):
    """Returns (source key, search function, api key). The key is None when no provider is configured."""
    if settings.tavily_api_key:
        return "tavily_search", tavily.search, settings.tavily_api_key
    return "brave_search", brave.search, settings.brave_api_key


def with_fallback(primary, fallback):
    """Uses `primary` until it reports that the key or plan is exhausted ("auth"), then `fallback` for the rest of the job."""
    from app.sources.brave import SearchError  # local: keeps the module header minimal

    state = {"exhausted": False}

    def search(client, api_key, query, count=5):
        if not state["exhausted"]:
            try:
                return primary(client, api_key, query, count)
            except SearchError as e:
                if e.kind != "auth":
                    raise
                state["exhausted"] = True
        return fallback(client, api_key, query, count)

    return search
