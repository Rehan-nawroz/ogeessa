"""Shared helpers for all ogeessa tools."""
import json
from typing import Any, Callable


def json_result(data: Any) -> str:
    """Serialize tool output to a compact JSON string for the LLM."""
    return json.dumps(data, ensure_ascii=False, default=str)


def safe_call(label: str, fn: Callable[[], str]) -> str:
    """Run a tool body, converting any exception into 'ERROR: ...' text.

    Data sources are flaky (bad symbols, rate limits, network blips). Tools
    must never crash the session — they degrade to an error string the agent
    can read and report honestly.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — deliberate catch-all
        return f"ERROR: {label} failed: {exc}"