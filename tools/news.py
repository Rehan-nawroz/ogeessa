"""get_news — recent headlines via DuckDuckGo."""
from ddgs import DDGS
from langchain_core.tools import tool

from config import NEWS_RESULTS, NEWS_TIME_WINDOW
from tools.base import json_result, safe_call


@tool
def get_news(query: str) -> str:
    """Search recent news headlines for a company, stock, or market topic.
    Input is a search phrase, e.g. 'OGDC Pakistan oil' or 'HBL bank results'."""
    return safe_call(f"get_news({query!r})", lambda: _news(query))


def _news(query: str) -> str:
    query = query.strip()
    with DDGS() as ddgs:
        hits = list(ddgs.news(
            query,
            max_results=NEWS_RESULTS,
            timelimit=NEWS_TIME_WINDOW,
        ))

    if not hits:
        return json_result({
            "query": query,
            "results": [],
            "note": "No headlines found in the recent window. "
                    "The agent must not invent news.",
        })

    return json_result({
        "query": query,
        "results": [
            {
                "title": h.get("title", ""),
                "source": h.get("source", ""),
                "date": h.get("date", ""),
                "snippet": (h.get("body", "") or "")[:200],
                "url": h.get("url", ""),
            }
            for h in hits
        ],
    })