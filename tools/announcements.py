"""get_announcements — company announcements for any stock, any exchange.

Three sources, combined: yfinance calendar + news (upcoming events,
headlines), targeted DuckDuckGo searches (board meetings, dividends,
earnings), and yfinance actions (dividend/split history).
"""
from datetime import datetime

import yfinance as yf
from ddgs import DDGS
from langchain_core.tools import tool

from tools.base import json_result, safe_call


@tool
def get_announcements(symbol: str) -> str:
    """Get recent and upcoming company announcements for any stock on any
    exchange: upcoming earnings date and estimates, dividend announcements
    and history, board meeting news, recent official announcements, and
    stock splits. Input is a ticker symbol, e.g. OGDC.KA, AAPL, RELIANCE.NS."""
    return safe_call(f"get_announcements({symbol})", lambda: _get_announcements(symbol))


def _company_name(stock, symbol: str) -> str:
    """longName when available; degrade to the symbol."""
    try:
        info = stock.info or {}
        return info.get("longName") or info.get("shortName") or symbol
    except Exception:
        return symbol


def _upcoming_events(stock) -> dict:
    """Calendar as dict regardless of yfinance version (dict or DataFrame)."""
    cal = stock.calendar
    if isinstance(cal, dict):
        return {k: v for k, v in cal.items() if v}
    if cal is not None and getattr(cal, "empty", True) is False and len(cal) > 0:
        row = cal.iloc[0]
        return {col: row[col] for col in cal.columns if row[col] is not None}
    return {}


def _get_announcements(symbol: str) -> str:
    symbol = symbol.strip().upper()
    stock = yf.Ticker(symbol)
    company_name = _company_name(stock, symbol)
    current_year = datetime.now().year

    # ── SOURCE 1a — yfinance calendar ────────────────────────────────
    try:
        events = _upcoming_events(stock)
    except Exception:
        events = {}

    # ── SOURCE 1b — yfinance news ────────────────────────────────────
    yahoo_news: list[dict] = []
    try:
        for item in (stock.news or [])[:6]:
            title = item.get("title", "")
            if not title:
                continue
            pub_time = item.get("providerPublishTime", 0) or 0
            date_str = (
                datetime.fromtimestamp(int(pub_time)).strftime("%Y-%m-%d")
                if pub_time
                else "unknown date"
            )
            yahoo_news.append({
                "date": date_str,
                "title": title,
                "publisher": item.get("publisher", ""),
            })
    except Exception:
        yahoo_news = []

    # ── SOURCE 3 — yfinance actions: dividends + splits ──────────────
    dividends: list[dict] = []
    trend = None
    try:
        divs = stock.dividends
        if divs is not None and not divs.empty:
            dividends = [
                {"date": str(date)[:10], "amount": round(float(amount), 4)}
                for date, amount in divs.tail(4).items()
            ]
            if len(divs) >= 2:
                last, prev = float(divs.iloc[-1]), float(divs.iloc[-2])
                trend = (
                    "increasing" if last > prev
                    else "decreasing" if last < prev
                    else "stable"
                )
    except Exception:
        dividends = []

    splits: list[dict] = []
    try:
        sp = stock.splits
        if sp is not None and not sp.empty:
            splits = [
                {"date": str(date)[:10], "ratio": f"{float(r):g}:1"}
                for date, r in sp.tail(2).items()
            ]
    except Exception:
        splits = []

    # ── SOURCE 2 — targeted DuckDuckGo searches ──────────────────────
    ddg_results: list[dict] = []
    try:
        queries = [
            f"{company_name} board meeting announcement",
            f"{company_name} dividend announcement {current_year}",
            f"{company_name} earnings results announcement",
        ]
        seen: set[str] = set()
        with DDGS() as ddgs:
            for query in queries:
                try:
                    hits = list(ddgs.news(query, max_results=3, timelimit="m"))
                except Exception:
                    continue
                for r in hits:
                    title = r.get("title", "")
                    if title and title not in seen:
                        seen.add(title)
                        ddg_results.append({
                            "date": str(r.get("date", ""))[:10] or "unknown",
                            "title": title,
                            "source": r.get("source", ""),
                            "query": query,
                        })
    except Exception:
        ddg_results = []

    if not any((events, dividends, splits, yahoo_news, ddg_results)):
        return json_result({
            "error": f"No announcement data found for '{symbol}'. "
                     "Symbol may not be supported.",
        })

    return json_result({
        "symbol": symbol,
        "company": company_name,
        "upcoming_events": {k: str(v) for k, v in events.items()} or None,
        "recent_dividends": dividends,
        "dividend_trend": trend,
        "recent_splits": splits,
        "yahoo_news": yahoo_news,
        "announcement_searches": ddg_results,
        "note": "Report only what appears here; never invent announcements.",
    })