"""get_economic_calendar — universal economic calendar for any stock.

Three layers: stock-specific events (earnings/dividends from yfinance,
Finnhub when a key is configured), country-specific events (central
bank cadence, budget cycle, data releases for the home market), and
global macro events — plus HIGH IMPACT flags keyed to the stock's
sector. Works for any exchange via ticker suffix / exchange / country
/ currency detection.
"""
from datetime import datetime

from langchain_core.tools import tool

from tools.base import safe_call


@tool
def get_economic_calendar(symbol: str) -> str:
    """Get upcoming economic events relevant to any stock on any global
    exchange: next earnings/dividend dates with estimates, the home
    market's central bank and data-release calendar, global macro events,
    and HIGH IMPACT flags for this stock's sector. Input is any ticker,
    e.g. OGDC.KA, AAPL, HSBA.L, RELIANCE.NS, D05.SI, 7203.T."""
    return safe_call(f"get_economic_calendar({symbol})", lambda: _get_calendar(symbol))


def _detect_market(symbol: str, exchange: str, country: str, currency: str) -> dict:
    """Map ticker suffix / exchange / country / currency to a market profile."""
    if symbol.endswith(".KA") or country == "Pakistan":
        return {
            "name": "Pakistan Stock Exchange (PSX)",
            "central_bank": "State Bank of Pakistan (SBP)",
            "events": [
                "SBP Monetary Policy: Every 6-8 weeks (check sbp.org.pk for exact dates)",
                "Federal Budget: Annually in June",
                "PSX Results Season: Jan/Apr/Jul/Oct",
                "KSE-100 Rebalancing: Quarterly",
                "SECP Annual Report: September",
            ],
        }
    if symbol.endswith((".NS", ".BO")) or country == "India":
        return {
            "name": "India (NSE/BSE)",
            "central_bank": "Reserve Bank of India (RBI)",
            "events": [
                "RBI MPC Meeting: Every 2 months (Feb/Apr/Jun/Aug/Oct/Dec)",
                "Union Budget: February 1 annually",
                "India CPI: Monthly, ~12th of each month",
                "India GDP: Quarterly",
                "GST Council Meeting: As scheduled",
            ],
        }
    if symbol.endswith(".L") or country == "United Kingdom" or currency == "GBp":
        return {
            "name": "London Stock Exchange (LSE)",
            "central_bank": "Bank of England (BOE)",
            "events": [
                "BOE MPC Meeting: 8 times per year",
                "UK CPI: Monthly",
                "UK GDP: Quarterly",
                "UK Budget: Usually Autumn",
                "FTSE Rebalancing: Quarterly",
            ],
        }
    if symbol.endswith(".SI") or country == "Singapore" or exchange == "SGX":
        return {
            "name": "Singapore Exchange (SGX)",
            "central_bank": "Monetary Authority of Singapore (MAS)",
            "events": [
                "MAS Policy Review: Twice yearly (April and October)",
                "Singapore Budget: February annually",
                "Singapore CPI: Monthly",
                "Singapore GDP: Quarterly",
            ],
        }
    if symbol.endswith(".T") or country == "Japan" or currency == "JPY":
        return {
            "name": "Tokyo Stock Exchange (TSE)",
            "central_bank": "Bank of Japan (BOJ)",
            "events": [
                "BOJ Policy Meeting: 8 times per year",
                "Japan CPI: Monthly",
                "Japan GDP: Quarterly",
                "Tankan Survey: Quarterly (Mar/Jun/Sep/Dec)",
            ],
        }
    if currency == "EUR":
        return {
            "name": "European Market",
            "central_bank": "European Central Bank (ECB)",
            "events": [
                "ECB Rate Decision: 8 times per year",
                "Eurozone CPI: Monthly",
                "Eurozone GDP: Quarterly",
                "German IFO Business Climate: Monthly",
            ],
        }
    if symbol.endswith(".AX") or country == "Australia" or currency == "AUD":
        return {
            "name": "Australian Securities Exchange (ASX)",
            "central_bank": "Reserve Bank of Australia (RBA)",
            "events": [
                "RBA Board Meeting: 8 times per year",
                "Australia CPI: Quarterly",
                "Australia GDP: Quarterly",
                "Australia Employment: Monthly",
            ],
        }
    if symbol.endswith(".HK") or country == "Hong Kong" or currency == "HKD":
        return {
            "name": "Hong Kong Exchange (HKEX)",
            "central_bank": "Hong Kong Monetary Authority (HKMA)",
            "events": [
                "HKMA follows US Fed — mirrors Fed decisions",
                "China PMI: Monthly (critical for HK stocks)",
                "Hong Kong GDP: Quarterly",
                "Hang Seng Rebalancing: Quarterly",
            ],
        }
    if symbol.endswith((".SS", ".SZ")) or country == "China":
        return {
            "name": "China (Shanghai/Shenzhen)",
            "central_bank": "People's Bank of China (PBOC)",
            "events": [
                "PBOC LPR Decision: Monthly (20th)",
                "China CPI: Monthly",
                "China GDP: Quarterly",
                "China PMI: Monthly (1st of month)",
                "NPC Annual Session: March",
            ],
        }
    if symbol.endswith((".TO", ".V")) or country == "Canada" or currency == "CAD":
        return {
            "name": "Toronto Stock Exchange (TSX)",
            "central_bank": "Bank of Canada (BOC)",
            "events": [
                "BOC Rate Decision: 8 times per year",
                "Canada CPI: Monthly",
                "Canada GDP: Monthly and Quarterly",
                "Canada Employment: Monthly",
            ],
        }
    return {
        "name": "US Markets (NASDAQ/NYSE)",
        "central_bank": "US Federal Reserve (Fed)",
        "events": [
            "FOMC Meeting: 8 times per year",
            "US CPI: Monthly, ~2nd week",
            "US Non-Farm Payrolls: First Friday of month",
            "US GDP: Quarterly",
            "US PPI: Monthly",
            "US Retail Sales: Monthly",
            "US Jobless Claims: Weekly (Thursday)",
        ],
    }


def _get_global_events(today: datetime) -> list:
    """Global macro events that affect every market."""
    month = today.strftime("%B %Y")
    return [
        f"US FOMC Meeting: Check federalreserve.gov for {month} schedule",
        "US CPI Release: Monthly (~2nd week) — moves all global markets",
        "US Non-Farm Payrolls: First Friday of month — risk-on/risk-off signal",
        "China PMI: Monthly (1st) — indicator for global commodity demand",
        "Global Oil Inventory (EIA): Weekly Wednesday — critical for energy stocks",
        "OPEC+ Meeting: As scheduled — major mover for oil-linked stocks",
        "US Dollar Index (DXY): Direction affects all emerging market stocks "
        "and commodities",
        f"Earnings Season: Check if {today.strftime('%B')} is Jan/Apr/Jul/Oct "
        "— peak reporting months",
    ]


def _get_sector_flags(sector: str, market: dict) -> list:
    """High-impact event flags for this stock's sector."""
    sector_lower = sector.lower() if sector else ""
    flags = []

    if any(w in sector_lower for w in ("energy", "oil", "gas")):
        flags += [
            "OPEC+ production decisions directly impact revenue",
            "Weekly EIA oil inventory report (Wednesday) — watch closely",
            "Global crude oil price (Brent/WTI) is primary revenue driver",
            "USD strength hurts oil prices — monitor DXY",
        ]
        if "Pakistan" in market["name"]:
            flags.append(
                "SBP circular debt policy directly impacts cash flow collection"
            )
    elif any(w in sector_lower for w in ("bank", "financ", "insurance")):
        flags += [
            f"{market['central_bank']} rate decision directly impacts "
            "net interest margin",
            "US Fed decision affects global banking sentiment even for local banks",
            "Credit rating changes for sovereign debt affect banking stocks",
            "Inflation data — higher inflation usually positive for bank margins",
        ]
    elif any(w in sector_lower for w in ("tech", "software", "semicon")):
        flags += [
            "US Fed rate decisions — tech stocks are rate-sensitive (growth)",
            "US NASDAQ direction sets global tech sentiment",
            "USD strength affects dollar-denominated tech revenues",
            "Major US tech earnings (AAPL/MSFT/NVDA) set sector tone",
        ]
    elif any(w in sector_lower for w in ("fertil", "chemic", "material")):
        flags += [
            "Global natural gas prices — key input cost for fertilizer",
            "Global urea prices — benchmark for fertilizer revenue",
            "Agricultural season — demand driver for fertilizer stocks",
        ]
    elif any(w in sector_lower for w in ("cement", "construct", "real estate")):
        flags += [
            "Interest rate direction — lower rates boost construction activity",
            "Government infrastructure spending announcements",
            "Coal and fuel prices — major input costs for cement",
        ]
    elif any(w in sector_lower for w in ("consumer", "retail", "food")):
        flags += [
            "Inflation data — directly impacts consumer purchasing power",
            "Employment data — jobs = consumer spending",
            "Commodity prices (wheat, palm oil, sugar) — key input costs",
        ]
    elif any(w in sector_lower for w in ("telecom", "communication")):
        flags += [
            "Spectrum auction announcements",
            "Regulatory decisions on tariffs",
            "Interest rates — telecom is capital-intensive and debt-heavy",
        ]

    if not flags:
        flags = [
            f"{market['central_bank']} rate decisions affect cost of capital "
            "for all stocks",
            "US Fed direction sets global risk appetite",
            "Earnings season — check if results are due within 30 days",
        ]
    return flags


def _stock_events(stock, today: datetime) -> list:
    """Layer 1 — upcoming stock-specific dates with days-away urgency."""
    lines = []
    try:
        cal = stock.calendar
        rows: dict = {}
        if isinstance(cal, dict):
            rows = {k: v for k, v in cal.items() if v}
        elif cal is not None and getattr(cal, "empty", True) is False and len(cal) > 0:
            row = cal.iloc[0]
            rows = {col: row[col] for col in cal.columns}
        if rows:
            for col, val in rows.items():
                if val is None or str(val) == "NaT":
                    continue
                if hasattr(val, "date"):
                    days = (val.date() - today.date()).days
                    urgency = ""
                    if 0 <= days <= 7:
                        urgency = " ⚠️  THIS WEEK"
                    elif 0 <= days <= 30:
                        urgency = " 📅 WITHIN 30 DAYS"
                    lines.append(f"  {col}: {str(val)[:10]} ({days} days away){urgency}")
                else:
                    lines.append(f"  {col}: {val}")
        else:
            lines.append("  Earnings/dividend dates: Not available for this exchange")
    except Exception:
        lines.append("  Calendar data: Not available")

    # Finnhub earnings calendar when a key is configured (.env, optional)
    try:
        from config import FINNHUB_API_KEY

        if FINNHUB_API_KEY:
            import requests

            resp = requests.get(
                "https://finnhub.io/api/v1/calendar/earnings",
                params={
                    "symbol": stock.ticker or "",
                    "token": FINNHUB_API_KEY,
                },
                timeout=8,
            )
            earnings = (resp.json() or {}).get("earningsCalendar", [])
            if earnings:
                nxt = earnings[0]
                lines.append(
                    f"  Earnings (Finnhub): {nxt.get('date', '?')} | "
                    f"EPS Est: {nxt.get('epsEstimate', '?')} | "
                    f"Rev Est: {nxt.get('revenueEstimate', '?')}"
                )
    except Exception:
        pass
    return lines


def _get_calendar(symbol: str) -> str:
    import yfinance as yf
    from ddgs import DDGS

    symbol = symbol.strip().upper()
    stock = yf.Ticker(symbol)
    try:
        info = stock.info or {}
    except Exception:
        info = {}

    company = info.get("longName") or info.get("shortName") or symbol
    sector = info.get("sector", "Unknown")
    exchange = info.get("exchange", "")
    country = info.get("country", "")
    currency = info.get("currency", "USD")
    market = _detect_market(symbol, exchange, country, currency)
    today = datetime.now()

    sections = []

    # ── LAYER 1: STOCK-SPECIFIC EVENTS ───────────────────────────────
    sections.append("STOCK-SPECIFIC UPCOMING EVENTS")
    sections.append(f"Company: {company}")
    sections.append(f"Sector:  {sector}")
    sections.append(f"Market:  {market['name']}")
    sections.append("")
    sections.extend(_stock_events(stock, today))

    # ── LAYER 2: COUNTRY-SPECIFIC EVENTS ─────────────────────────────
    sections.append("")
    sections.append(f"COUNTRY-SPECIFIC EVENTS — {market['name']}")
    for event in market["events"]:
        sections.append(f"  • {event}")

    try:
        with DDGS() as ddgs:
            query = (
                f"{market['central_bank']} interest rate decision "
                f"{today.strftime('%B %Y')}"
            )
            results = list(ddgs.news(query, max_results=3, timelimit="m"))
            if results:
                sections.append("")
                sections.append(f"  RECENT {market['central_bank']} NEWS:")
                for r in results[:2]:
                    sections.append(
                        f"  [{str(r.get('date', '?'))[:10]}] {r.get('title', '')}"
                    )
    except Exception:
        pass

    # ── LAYER 3: GLOBAL MACRO EVENTS ─────────────────────────────────
    sections.append("")
    sections.append("GLOBAL MACRO EVENTS (affect all markets)")
    for event in _get_global_events(today):
        sections.append(f"  • {event}")

    # ── SECTOR RELEVANCE FLAGS ───────────────────────────────────────
    sections.append("")
    sections.append(f"HIGH IMPACT EVENTS FOR THIS STOCK ({sector})")
    for flag in _get_sector_flags(sector, market):
        sections.append(f"  ⚡ {flag}")

    return "\n".join(sections)