"""get_price — latest quote via yfinance."""
import yfinance as yf
from langchain_core.tools import tool

from tools.base import json_result, safe_call


@tool
def get_price(symbol: str) -> str:
    """Get the latest price quote for a stock symbol: last close, day change,
    day range, volume, and 52-week high/low. Works for any Yahoo Finance
    ticker, e.g. OGDC.KA (PSX), HBL.KA, AAPL, MSFT."""
    return safe_call(f"get_price({symbol})", lambda: _price(symbol))


def _price(symbol: str) -> str:
    symbol = symbol.strip()
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5d")
    if hist.empty:
        return json_result({
            "error": f"No price data found for '{symbol}'. "
                     "Check the symbol (PSX names end in .KA).",
        })

    last = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) > 1 else last
    last_close, prev_close = float(last["Close"]), float(prev["Close"])
    change = last_close - prev_close
    pct = (change / prev_close * 100) if prev_close else 0.0

    return json_result({
        "symbol": symbol.upper(),
        "last_close": round(last_close, 2),
        "prev_close": round(prev_close, 2),
        "change": round(change, 2),
        "change_pct": round(pct, 2),
        "day_low": round(float(last["Low"]), 2),
        "day_high": round(float(last["High"]), 2),
        "volume": int(last["Volume"]),
        "week_52_high": _info(ticker).get("fiftyTwoWeekHigh"),
        "week_52_low": _info(ticker).get("fiftyTwoWeekLow"),
        "currency": _info(ticker).get("currency", ""),
    })


def _info(ticker) -> dict:
    """ticker.info can fail on some symbols; degrade to empty."""
    try:
        return ticker.info or {}
    except Exception:
        return {}