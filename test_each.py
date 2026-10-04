"""Standalone tool tests — run BEFORE main.py, always.

    python test_each.py [symbol] [--no-llm]

Every check hits the real data source (no mocks) so the exact broken piece
is identified immediately. Exit code 0 = all pass, 1 = any failure.
"""
import sys

import config
from tools import ALL_TOOLS

PASS, FAIL = "[bold green]PASS[/]", "[bold red]FAIL[/]"
_results = []


def check(name: str, fn):
    console.print(f"  {name:28s}", end="")
    try:
        fn()
        console.print(PASS)
        _results.append(True)
    except Exception as exc:
        console.print(f"{FAIL}  {exc}")
        _results.append(False)


def invoke_tool(tool_, **kwargs):
    """Call a tool and unwrap its JSON, surfacing 'ERROR: ...' strings."""
    import json
    raw = tool_.invoke(kwargs)
    if isinstance(raw, str) and raw.startswith("ERROR:"):
        raise AssertionError(raw)
    return json.loads(raw)


def build_console():
    from rich.console import Console
    return Console()


console = build_console()


# --- 1. config -----------------------------------------------------------
def test_config():
    missing = config.missing_key()
    if missing and not config.LLM_PROVIDER == "ollama":
        # LLM key may be absent on purpose (--no-llm runs); still report it.
        console.print(f"[yellow]note:[/] {missing} not set", end=" ")
    assert config.LLM_PROVIDER in config.PROVIDERS, config.LLM_PROVIDER
    assert config.HISTORY_PERIOD == "6mo"


# --- 2. imports ----------------------------------------------------------
def test_imports():
    import agent.core  # noqa: F401
    import prompts.persona  # noqa: F401
    from tools import (  # noqa: F401
        get_announcements,
        get_economic_calendar,
        get_fundamentals,
        get_news,
        get_price,
        get_technicals,
    )
    assert len(ALL_TOOLS) == 6


# --- 3. get_price --------------------------------------------------------
def make_price_test(symbol):
    def run():
        data = invoke_tool(ALL_TOOLS[0], symbol=symbol)
        assert "error" not in data, data.get("error")
        assert data["last_close"] > 0
        console.print(f"[dim]close={data['last_close']} "
                      f"chg={data['change_pct']}%[/dim] ", end="")
    return run


# --- 4. get_technicals ---------------------------------------------------
def make_technicals_test(symbol):
    def run():
        data = invoke_tool(ALL_TOOLS[1], symbol=symbol)
        assert "error" not in data, data.get("error")
        assert data["trend"] in ("bullish", "bearish", "mixed", "unknown")
        assert data["support"] < data["resistance"]
        console.print(f"[dim]RSI={data['rsi_14']} trend={data['trend']} "
                      f"S/R={data['support']}/{data['resistance']}[/dim] ", end="")
    return run


# --- 5. get_fundamentals -------------------------------------------------
def make_fundamentals_test(symbol):
    def run():
        data = invoke_tool(ALL_TOOLS[3], symbol=symbol)
        assert "error" not in data, data.get("error")
        console.print(f"[dim]name={data.get('name')!r} "
                      f"pe={data.get('pe_trailing')}[/dim] ", end="")
    return run


# --- 6. get_news ---------------------------------------------------------
def make_news_test(query):
    def run():
        data = invoke_tool(ALL_TOOLS[2], query=query)
        assert "error" not in data, data.get("error")
        console.print(f"[dim]{len(data['results'])} headlines[/dim] ", end="")
    return run


# --- 7. get_announcements --------------------------------------------------
def make_announcements_test(symbol):
    def run():
        data = invoke_tool(ALL_TOOLS[4], symbol=symbol)
        assert "error" not in data, data.get("error")
        import json
        result = json.dumps(data)
        assert result and not result.startswith("ERROR")
        console.print(f"[dim]{result[:60]}…[/dim] ", end="")
    return run


# --- 8. get_economic_calendar ----------------------------------------------
def make_calendar_test():
    def run_one(symbol):
        # Plain-text report tool: invoke directly, no JSON unwrap.
        raw = ALL_TOOLS[5].invoke({"symbol": symbol})
        assert raw and not raw.startswith("ERROR"), raw[:120]
        assert "EVENTS" in raw, "missing EVENTS section"
        console.print(f"[dim]{raw[:80]}…[/dim] ", end="")

    def run():
        run_one("OGDC.KA")
        run_one("AAPL")

    return run


# --- 9. LLM connection ---------------------------------------------------
def test_llm():
    from agent.core import _build_llm
    llm = _build_llm()
    reply = llm.invoke("Reply with exactly: OK")
    content = getattr(reply, "content", "")
    assert "OK" in str(content), f"unexpected reply: {content!r}"


def main():
    args = [a for a in sys.argv[1:] if a != "--no-llm"]
    no_llm = "--no-llm" in sys.argv
    symbol = args[0] if args else "OGDC.KA"

    console.print(f"\n[bold cyan]ogeessa tool tests[/] — symbol: [bold]{symbol}[/]\n")

    check("config (.env, provider)", test_config)
    check("imports (all modules)", test_imports)
    check("get_price (yfinance)", make_price_test(symbol))
    check("get_technicals (pandas_ta)", make_technicals_test(symbol))
    check("get_fundamentals (yfinance)", make_fundamentals_test(symbol))
    check("get_news (duckduckgo)", make_news_test(f"{symbol.split('.')[0]} stock"))
    check("get_announcements (yfinance+ddg)", make_announcements_test(symbol))
    check("get_economic_calendar (universal)", make_calendar_test())
    if not no_llm:
        check(f"llm connection ({config.LLM_PROVIDER})", test_llm)
    else:
        console.print(f"  {'llm connection':28s}[yellow]SKIPPED[/]")

    failed = _results.count(False)
    console.print(f"\n{_results.count(True)} passed, {failed} failed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()