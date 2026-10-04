"""get_fundamentals — valuation and quality metrics via yfinance."""
import yfinance as yf
from langchain_core.tools import tool

from tools.base import json_result, safe_call


@tool
def get_fundamentals(symbol: str) -> str:
    """Get fundamental metrics for a stock symbol: P/E (trailing and forward),
    profit margin, revenue growth, ROE, debt/equity, market cap, dividend
    yield, and sector."""
    return safe_call(f"get_fundamentals({symbol})", lambda: _fundamentals(symbol))


def _fundamentals(symbol: str) -> str:
    symbol = symbol.strip()
    info = yf.Ticker(symbol).info or {}
    if not info.get("symbol") and not info.get("shortName"):
        return json_result({
            "error": f"No fundamental data found for '{symbol}'.",
        })

    return json_result({
        "symbol": symbol.upper(),
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "market_cap": info.get("marketCap"),
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "profit_margin": info.get("profitMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "roe": info.get("returnOnEquity"),
        "debt_to_equity": info.get("debtToEquity"),
        "dividend_yield": info.get("dividendYield"),
    })