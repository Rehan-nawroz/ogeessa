"""Ogeessa tools — the agent's data sources."""
from tools.announcements import get_announcements
from tools.calendar import get_economic_calendar
from tools.fundamentals import get_fundamentals
from tools.news import get_news
from tools.price import get_price
from tools.technical import get_technicals

ALL_TOOLS = [
    get_price,
    get_technicals,
    get_news,
    get_fundamentals,
    get_announcements,
    get_economic_calendar,
]

__all__ = [
    "get_price",
    "get_technicals",
    "get_news",
    "get_fundamentals",
    "get_announcements",
    "get_economic_calendar",
    "ALL_TOOLS",
]