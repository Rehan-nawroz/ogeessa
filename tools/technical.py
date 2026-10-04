"""get_technicals — RSI, MACD, moving averages, ATR, Bollinger, levels."""
import yfinance as yf
from langchain_core.tools import tool

import pandas_ta_classic as ta  # the republished 0.3.14b0 codebase

from config import HISTORY_PERIOD
from tools.base import json_result, safe_call


@tool
def get_technicals(symbol: str) -> str:
    """Get technical indicators for a stock symbol: RSI(14), MACD(12,26,9),
    SMA 20/50/200, ATR(14), Bollinger Bands, a trend verdict, a momentum
    verdict, and approximate support/resistance levels."""
    return safe_call(f"get_technicals({symbol})", lambda: _technicals(symbol))


def _last(series) -> float | None:
    """Last non-NaN value of a Series, or None."""
    if series is None:
        return None
    try:
        value = series.dropna()
        return float(value.iloc[-1]) if not value.empty else None
    except Exception:
        return None


def _col(df, prefix: str):
    """Find a DataFrame column by prefix (bbands names vary across versions)."""
    if df is None or df.empty:
        return None
    matches = [c for c in df.columns if str(c).startswith(prefix)]
    return df[matches[0]] if matches else None


def _technicals(symbol: str) -> str:
    symbol = symbol.strip()
    df = yf.Ticker(symbol).history(period=HISTORY_PERIOD)
    if df.empty or len(df) < 30:
        return json_result({
            "error": f"Not enough price history for '{symbol}' to compute technicals.",
        })

    close = df["Close"]
    last_close = float(close.iloc[-1])

    rsi = _last(ta.rsi(close, length=14))

    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    macd_val = _last(_col(macd_df, "MACD_"))
    macd_signal = _last(_col(macd_df, "MACDs_"))
    macd_hist = _last(_col(macd_df, "MACDh_"))

    sma20 = _last(ta.sma(close, length=20))
    sma50 = _last(ta.sma(close, length=50))
    sma200 = _last(ta.sma(close, length=200)) if len(df) >= 200 else None

    atr = _last(ta.atr(df["High"], df["Low"], df["Close"], length=14))

    bbands = ta.bbands(close, length=20, std=2)
    bb_lower = _last(_col(bbands, "BBL"))
    bb_upper = _last(_col(bbands, "BBU"))

    # --- support / resistance: recent swing range widened by the bands ----
    window = df.tail(60)
    support = float(window["Low"].min())
    resistance = float(window["High"].max())
    if bb_lower is not None:
        support = min(support, bb_lower)
    if bb_upper is not None:
        resistance = max(resistance, bb_upper)

    # --- trend verdict: price vs available moving averages ----------------
    mas = [m for m in (sma20, sma50, sma200) if m is not None]
    if mas:
        above = sum(1 for m in mas if last_close > m)
        trend = ("bullish" if above == len(mas)
                 else "bearish" if above == 0 else "mixed")
    else:
        trend = "unknown"

    # --- momentum verdict: RSI zone + MACD vs signal -----------------------
    momentum = []
    if rsi is not None:
        if rsi >= 70:
            momentum.append(f"RSI {rsi:.0f} — overbought")
        elif rsi <= 30:
            momentum.append(f"RSI {rsi:.0f} — oversold")
        else:
            momentum.append(f"RSI {rsi:.0f} — neutral")
    if macd_val is not None and macd_signal is not None:
        momentum.append("MACD above signal — bullish momentum"
                        if macd_val > macd_signal
                        else "MACD below signal — bearish momentum")

    return json_result({
        "symbol": symbol.upper(),
        "period": HISTORY_PERIOD,
        "last_close": round(last_close, 2),
        "rsi_14": round(rsi, 1) if rsi is not None else None,
        "macd": {
            "macd": round(macd_val, 3) if macd_val is not None else None,
            "signal": round(macd_signal, 3) if macd_signal is not None else None,
            "hist": round(macd_hist, 3) if macd_hist is not None else None,
        },
        "sma": {
            "sma20": round(sma20, 2) if sma20 is not None else None,
            "sma50": round(sma50, 2) if sma50 is not None else None,
            "sma200": round(sma200, 2) if sma200 is not None else None,
        },
        "atr_14": round(atr, 2) if atr is not None else None,
        "bollinger": {
            "lower": round(bb_lower, 2) if bb_lower is not None else None,
            "upper": round(bb_upper, 2) if bb_upper is not None else None,
        },
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "trend": trend,
        "momentum": momentum,
    })