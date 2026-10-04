"""Ogeessa — Skynet-red Textual TUI for the stock trading agent.

Layout: ASCII sigil header, system-status rail (left), analysis output
(right), full-width command input, bottom status bar.
agent/core.py is untouched.

Pre-TUI: first-run setup wizard (python main.py --setup forces it), lazy
backend loading (config/agent/tools are imported only after .env is
settled) and a missing-key notice. In-TUI: /help /config /model /reset
/clear /add /remove /watchlist /tools magic commands with red-bordered
panels, plus watchlist.json persistence.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time

from rich.console import Console
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label, RichLog, Static

import pyperclip

# Heavy backends (config → agent → tools) are loaded LAZILY by _load_backend(),
# never at module import time — the setup wizard must be able to inspect and
# even rewrite .env before config.py reads it.
config = None          # type: ignore[assignment]  # set by _load_backend()
StockTraderAgent = None  # type: ignore[assignment,misc]  # set by _load_backend()
ALL_TOOLS: list = []   # empty until _load_backend() runs
_BACKEND_LOADED = False

AGENT_READY = None  # StockTraderAgent once booted

WATCHLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _load_backend() -> None:
    """Import config/agent/tools once, AFTER .env is settled (wizard may rewrite it)."""
    global config, StockTraderAgent, ALL_TOOLS, _BACKEND_LOADED
    if _BACKEND_LOADED:
        return
    import config as _config
    from agent import StockTraderAgent as _Agent
    from tools import ALL_TOOLS as _tools
    config, StockTraderAgent, ALL_TOOLS = _config, _Agent, _tools
    _install_custom_builder()
    _BACKEND_LOADED = True


def _install_custom_builder() -> None:
    """Teach agent.core._build_llm about the custom provider (core.py untouched).

    Wraps the original: unknown providers that have a CUSTOM_BASE_URL fall
    through to a ChatOpenAI(base_url=...) instance, exactly the spec's
    config.py block — just installed at runtime instead of edited in.
    """
    import agent.core as _core
    if getattr(_core._build_llm, "_ogeessa_custom", False):
        return
    _orig = _core._build_llm

    def _patched():
        if config is not None and config.LLM_PROVIDER == "custom" and config.CUSTOM_BASE_URL.strip():
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=config.CUSTOM_MODEL,
                api_key=config.CUSTOM_API_KEY,
                base_url=config.CUSTOM_BASE_URL,
                temperature=0.2,
            )
        return _orig()

    _patched._ogeessa_custom = True  # type: ignore[attr-defined]
    _core._build_llm = _patched

# ── palette ───────────────────────────────────────────────────────────
DARK = "#0d0d0d"
RED = "#ff0000"
DIM = "#8b0000"
GHOST = "#4d0000"
GREEN = "#00cc44"
AMBER = "#ffaa00"
WHITE = "#ffffff"

ASCII_LOGO = (
    " ██████╗  ██████╗ ███████╗███████╗███████╗███████╗ █████╗ \n"
    "██╔═══██╗██╔════╝ ██╔════╝██╔════╝██╔════╝██╔════╝██╔══██╗\n"
    "██║   ██║██║  ███╗█████╗  █████╗  ███████╗███████╗███████║\n"
    "██║   ██║██║   ██║██╔══╝  ██╔══╝  ╚════██║╚════██║██╔══██║\n"
    "╚██████╔╝╚██████╔╝███████╗███████╗███████║███████║██║  ██║\n"
    " ╚═════╝  ╚═════╝ ╚══════╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝"
)
TAGLINE = "UNIVERSAL STOCK TRADING AGENT"

def _status_bar_markup() -> str:
    """Bottom status bar — resolved lazily (config may not be loaded at import)."""
    if config is None:
        return f"[bold {RED}] OGEESSA ONLINE[/]  [{GHOST}]│[/]  [{DIM}]press ctrl+c to exit[/]"
    return (
        f"[bold {RED}] OGEESSA ONLINE[/]  [{GHOST}]│[/]  "
        f"[{DIM}]provider:[/] [{WHITE}]{config.LLM_PROVIDER}[/]  "
        f"[{GHOST}]│[/]  [{DIM}]Tab: switch focus[/]  "
        f"[{GHOST}]│[/]  [{DIM}]Ctrl+V: paste[/]  "
        f"[{GHOST}]│[/]  [{DIM}]Ctrl+C: copy selection[/]  "
        f"[{GHOST}]│[/]  [{DIM}]Ctrl+A: copy all output[/]"
    )

EXIT_WORDS = {"exit", "quit", "q"}
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
TYPING_FRAMES = "▁▂▃▄▅▆▇"
QUERY_BUFFER: list[str] = []
CONFIDENCE_MARKS = {"hig": "🔴", "med": "🟠", "low": "⚪"}

# ══════════════════════════════════════════════════════════════════════
# Analysis rendering — clean the agent's markdown, render a report
# ══════════════════════════════════════════════════════════════════════

# Rule 2: divider color by section keyword.
SECTION_COLOR_RULES: list[tuple[str, str]] = [
    ("INSTRUMENT", WHITE),
    ("MACRO", "#ffcc00"),
    ("SECTOR", "#ffcc00"),
    ("TECHNICAL", "#00bcd4"),
    ("NEWS", "#00bcd4"),
    ("FUNDAMENTAL", GREEN),
    ("RISK", RED),
    ("TRADE SETUP", GREEN),
]

_STEP_RE = re.compile(r"^STEP\s*\d+\s*[:：\-—]\s*(.*)$", re.IGNORECASE)
_VERDICT_RE = re.compile(
    r"^(PATTERN|CONFIDENCE|ALERT TYPE)\s*[:：]\s*(.*)$", re.IGNORECASE
)
_HEADER_RE = re.compile(
    r"^(MACRO SNAPSHOT|KEY SIGNALS|NEWS CATALYST|NEWS & CATALYST|RISKS"
    r"|RISK ASSESSMENT|TRADE SETUP|SUMMARY|FINAL VERDICT)\s*[:：]?\s*$",
    re.IGNORECASE,
)
_LABEL_RE = re.compile(r"^([A-Z0-9][A-Za-z0-9 '/&+.-]{1,20}?)\s*[:：]\s*(.+)$")
_NUM_BULLET_RE = re.compile(r"^\d+[.)]\s+")


def _clean_token(raw: str) -> tuple[str, bool]:
    """Rule 1: strip markdown noise from one line.

    Returns (text, was_bullet). Removes ###/##/# headers, **bold**,
    leading - * • bullets, numbered "1." bullets, and stray tokens.
    """
    t = raw.strip()
    was_bullet = bool(re.match(r"^[-*•]\s+", t)) or bool(_NUM_BULLET_RE.match(t))
    while True:
        before = t
        low = t.lower()
        for token in ("###### ", "##### ", "#### ", "### ", "## ", "# "):
            if low.startswith(token):
                t = t[len(token):].lstrip()
                break
        if t.startswith("**"):
            t = t[2:].lstrip()
        if t.endswith("**"):
            t = t[:-2].rstrip()
        t = t.replace("**", "")
        if t.startswith(("- ", "* ", "• ")):
            t = t[2:].lstrip()
        if _NUM_BULLET_RE.match(t):
            t = _NUM_BULLET_RE.sub("", t).lstrip()
        if t in {"#", "##", "###", "####", "#####", "######", "-", "*", "•"}:
            return "", was_bullet
        if before == t:
            break
    return t.strip(), was_bullet


def esc(text: str) -> str:
    """Escape Rich markup brackets in agent output."""
    return text.replace("[", "\\[")


def _display_width(text: str) -> int:
    """Terminal cell width (emoji count as 2 cells)."""
    return sum(2 if ord(ch) >= 0x2600 else 1 for ch in text)


def _section_color(title: str) -> str:
    up = title.upper()
    for needle, color in SECTION_COLOR_RULES:
        if needle in up:
            return color
    return WHITE


def _divider(title: str) -> str:
    title = esc(title.upper())
    bar = "━" * max(8, 58 - _display_width(title))
    return f"[{_section_color(title)}]━━━ {title} [dim]{bar}[/]"


def _label_row(label: str, value: str) -> str:
    """Rule 4: dim-red label padded to 14 chars, value in white."""
    return f"  [{DIM}]{esc(label.upper())[:14]:<14}[/] [{WHITE}]{esc(value)}[/]"


def _labeled(label: str, value: str) -> tuple[str, int]:
    """Label row plus its display width (for box padding)."""
    return _label_row(label, value), 17 + _display_width(value)




def _box(title: str, rows: list[tuple[str, int]], color: str) -> list[str]:
    """Draw a closed ┌─ TITLE ─┐ box with display-width-correct padding."""
    inner = max([w for _, w in rows] + [len(title) + 2])
    out = [
        f"[bold {color}]┌─ {title} "
        + "─" * max(1, inner - len(title) - 1)
        + "┐[/]"
    ]
    for markup, width in rows:
        out.append(f"[{color}]│[/] " + markup + " " * (inner - width) + f" [{color}]│[/]")
    out.append(f"[bold {color}]└" + "─" * (inner + 2) + "┘[/]")
    return out


def clean_and_render(raw_text: str) -> str:
    """Clean the agent's markdown output and render a formatted report.

    Rule 1 strips markdown noise; rule 2 draws colored ━━━ dividers;
    rule 3 bullets; rule 4 label rows; rule 5 a VERDICT box; rule 6 a
    TRADE SETUP box (green bullish / red bearish); rule 7 an ANALYST
    SUMMARY block; rule 8 a dim tools line at the top. Returns Rich
    markup ready for the output Static widget.
    """
    out: list[str] = []
    verdict_rows: list[str] = []
    setup_pairs: list[tuple[str, str]] = []
    summary_lines: list[str] = []
    tools_line: str | None = None
    mode: str | None = None  # None | "bullets" | "setup" | "summary"
    saw_tools = False

    def _flush_setup() -> None:
        if not setup_pairs:
            return
        low = raw_text.lower()
        color = RED if ("warn" in low or "bear" in low) else GREEN
        rows = [_labeled(l, v) for l, v in setup_pairs]
        out.append("")
        out.extend(_box("TRADE SETUP", rows, color))
        out.append("")
        setup_pairs.clear()

    def _flush_summary() -> None:
        nonlocal summary_lines
        if not summary_lines:
            return
        text = " ".join(s for s in summary_lines if s)
        out.append("")
        out.append(f"[{WHITE}]━━━ ANALYST SUMMARY [dim]{'━' * 44}[/]")
        out.append("")
        out.append(f"[{WHITE}]{esc(text)}[/]")
        out.append("")
        out.append("")
        summary_lines = []

    def _flush_verdict() -> None:
        if not verdict_rows:
            return
        out.append("")
        out.extend(_box("VERDICT", verdict_rows, DIM))
        out.append("")
        verdict_rows.clear()

    for raw_line in re.split(r"\r\n|\r|\n", raw_text):
        text, was_bullet = _clean_token(raw_line)
        if not text:
            if mode == "summary":
                summary_lines.append("")
            continue
        low = text.lower()

        # Rule 8: hoist the tools line (renders dim at the very top).
        if low.startswith("tools used"):
            rest = text[len("tools used"):].strip().lstrip(":：").strip("[] ")
            parts = [p.strip() for p in re.split(r"[,;·]", rest) if p.strip()]
            tools_line = ("Tools used: " + "  ·  ".join(parts)) if parts else None
            saw_tools = True
            continue

        # STEP headers → colored dividers (rule 2).
        sm = _STEP_RE.match(text)
        if sm:
            _flush_summary()
            _flush_verdict()
            _flush_setup()
            mode = None
            title = sm.group(1).strip().strip("-—:：*# ")
            if title:
                out.append("")
                out.append(_divider(title))
                out.append("")
            continue

        # Standalone section headers → dividers / mode switches.
        hm = _HEADER_RE.match(text)
        if hm:
            title = hm.group(1).upper()
            _flush_summary()
            _flush_verdict()
            _flush_setup()
            out.append("")
            if title == "SUMMARY":
                mode = "summary"
                continue
            if title == "FINAL VERDICT":
                mode = None
                out.append(_divider("FINAL VERDICT"))
                out.append("")
                continue
            out.append(_divider(title))
            out.append("")
            mode = "setup" if title == "TRADE SETUP" else "bullets"
            continue

        # Verdict fields → the VERDICT box (rule 5).
        vm = _VERDICT_RE.match(text)
        if vm:
            value = vm.group(2).strip()
            label = vm.group(1)
            if label.upper() == "CONFIDENCE":
                mark = CONFIDENCE_MARKS.get(value.lower()[:3], "")
                value = f"{mark} {value}" if mark else value
            else:
                lv = value.lower()
                for needle, icon in (
                    ("opport", "🚀"), ("warn", "⚠"),
                    ("monitor", "📊"), ("no action", "⛔"),
                ):
                    if needle in lv:
                        value = f"{icon} {value}"
                        break
            verdict_rows.append(_labeled(label, value))
            continue

        if mode == "summary":
            summary_lines.append(text)
            continue

        if mode == "setup":
            if low.startswith(("watch next", "timeframe")):
                _flush_setup()
                mode = None  # fall through to generic label-row rendering
            else:
                lm = _LABEL_RE.match(text)
                if lm:
                    setup_pairs.append((lm.group(1).strip(), lm.group(2).strip()))
                else:
                    setup_pairs.append(("", text))
                continue

        if mode == "bullets":
            out.append(f"  [{RED}]•[/] [{WHITE}]{esc(text)}[/]")
            continue

        # Generic lines: label rows (incl. bulleted bold labels), then
        # bullets, then plain white.
        lm = _LABEL_RE.match(text)
        if lm:
            out.append(_label_row(lm.group(1), lm.group(2).strip()))
        elif was_bullet:
            out.append(f"  [{RED}]•[/] [{WHITE}]{esc(text)}[/]")
        else:
            out.append(f"  [{WHITE}]{esc(text)}[/]")

    _flush_summary()
    _flush_verdict()
    _flush_setup()

    while out and out[-1] == "":
        out.pop()
    while out and out[0] == "":
        out.pop(0)

    header: list[str] = []
    if tools_line:
        header.append(f"[{GHOST}]{esc(tools_line)}[/]")
    elif saw_tools:
        header.append(f"[{GHOST}]Tools used: all four[/]")
    return "\n".join(header + out)


def _alert_class(raw: str) -> str:
    """Panel border class from the verdict: Opportunity green, Warning red,
    Monitor/No Action cyan."""
    low = raw.lower()
    if "opport" in low:
        return "alert-opp"
    if "warn" in low:
        return "alert-warn"
    return "alert-neu"


# ══════════════════════════════════════════════════════════════════════
# Helpers for the status rail
# ══════════════════════════════════════════════════════════════════════


def _model_name() -> str:
    """Short model label for the rail (18 chars max, provider prefix stripped)."""
    if config is None:
        return "—"
    if config.LLM_PROVIDER == "custom":
        raw = config.CUSTOM_MODEL or config.CUSTOM_PROVIDER_NAME or "custom"
        return raw[:17] + "…" if len(raw) > 18 else raw
    provider = config.LLM_PROVIDER
    raw = str(getattr(config, f"{provider.upper()}_MODEL", "") or "gemini-3.1-flash-lite")
    prefix = f"{provider}-"
    name = raw[len(prefix):] if raw.lower().startswith(prefix) else raw
    if len(name) > 18:
        name = name[:17] + "…"
    return name


def _tool_rows() -> str:
    if not ALL_TOOLS:
        return f"[{GHOST}]•[/] [{GHOST}]none loaded[/]"
    rows = []
    for tool in ALL_TOOLS:
        name = getattr(tool, "name", str(tool)).replace("get_", "")
        rows.append(f"[{GHOST}]•[/] [{WHITE}]{name:<11}[/] [{GREEN}]✓[/]")
    return "\n".join(rows)


# ══════════════════════════════════════════════════════════════════════
# .env / API-key helpers for the in-TUI configuration flows
# ══════════════════════════════════════════════════════════════════════

PROVIDER_KEY_VARS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "custom": "CUSTOM_API_KEY",
}
PROVIDER_NAMES = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "groq": "Groq",
    "gemini": "Gemini",
    "ollama": "Ollama",
}
PROVIDER_GET_LINKS = {
    "openai": "platform.openai.com/api-keys",
    "anthropic": "console.anthropic.com",
    "groq": "console.groq.com",
    "gemini": "aistudio.google.com/apikey",
    "finnhub": "finnhub.io → Dashboard → API Key",
}


def _read_env_file() -> dict[str, str]:
    """Parse .env into an ordered dict (comments/blank lines are skipped)."""
    values: dict[str, str] = {}
    try:
        with open(ENV_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                values[k.strip()] = v.strip()
    except OSError:
        pass
    return values


def _env_write_file(updates: dict[str, str]) -> None:
    """Rewrite .env preserving line order and comments, applying updates.
    New keys append at the end. Atomic (tmp file + replace)."""
    lines: list[str] = []
    seen: set[str] = set()
    try:
        with open(ENV_PATH, encoding="utf-8") as fh:
            raw = fh.readlines()
    except OSError:
        raw = []
    for line in raw:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in updates:
                lines.append(f"{k}={updates[k]}\n")
                seen.add(k)
                continue
        lines.append(line if line.endswith("\n") else line + "\n")
    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={v}\n")
    tmp = ENV_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    os.replace(tmp, ENV_PATH)


def _patch_env(updates: dict[str, str]) -> None:
    """Persist to .env, sync os.environ, and refresh the live config module.

    config.py reads os.getenv ONCE at import; without the setattr refresh the
    TUI (and agent.core's patched custom builder) would see stale values.
    """
    _env_write_file(updates)
    for k, v in updates.items():
        os.environ[k] = v
        if config is not None:
            setattr(config, k, v)


def _test_llm_sync(provider: str, api_key: str = "",
                   base_url: str = "", model: str = "") -> tuple[bool, str]:
    """Connection test for the config flows. Returns (ok, error_text)."""
    try:
        if provider == "custom":
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=model or "default",
                api_key=api_key or "fake_key",
                base_url=base_url,
                temperature=0.2,
            )
        elif provider == "ollama":
            from langchain_community.chat_models import ChatOllama
            llm = ChatOllama(model=model or os.getenv("OLLAMA_MODEL", "llama3"),
                             temperature=0.2)
        else:
            llm = _wizard_build_llm(provider, api_key)
        llm.invoke("Reply with only: OK")
        return True, ""
    except Exception as exc:  # noqa: BLE001 — any provider error is user-facing
        return False, str(exc)


def _test_finnhub_sync(key: str) -> tuple[bool, str]:
    """Validate a Finnhub key against a real endpoint ('Testing... ✓ Valid')."""
    try:
        import requests
        resp = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": "AAPL", "token": key},
            timeout=8,
        )
        if resp.status_code in (401, 403):
            return False, "invalid key (rejected by finnhub)"
        resp.raise_for_status()
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _check_ollama_sync() -> tuple[bool, str]:
    """Probe the local Ollama daemon (rules: no key, just must be running)."""
    try:
        import requests
        requests.get("http://localhost:11434", timeout=3)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# ══════════════════════════════════════════════════════════════════════
# Focusable widgets for copy/paste (spec FIXes 1–3, 5)
# ══════════════════════════════════════════════════════════════════════


class OgeessaLog(RichLog):
    """Research log you can click into, select, and copy from (Ctrl+C).

    can_focus=True (a class attribute in this Textual version, not a
    constructor kwarg) enables mouse text selection; Ctrl+C copies the
    selection and Ctrl+A copies the WHOLE log via pyperclip (OSC-52
    fallback when no system clipboard exists).
    """

    can_focus = True

    BINDINGS = [
        Binding("ctrl+c,super+c", "copy_selection", show=False, priority=True),
        Binding("ctrl+a", "copy_all", show=False, priority=True),
        Binding("menu,shift+f10", "open_menu", show=False, priority=True),
    ]

    def all_text(self) -> str:
        """The complete log content as plain text (markup already rendered)."""
        try:
            self.text_select_all()
            text = self.screen.get_selected_text()
            if text:
                return text
        except Exception:  # noqa: BLE001 — selection state can be transient
            pass
        try:
            return "\n".join(strip.text for strip in self.lines)
        except Exception:  # noqa: BLE001 — never let copy crash the TUI
            return ""

    def _copy_text(self, text: str, what: str) -> None:
        try:
            pyperclip.copy(text)
            self.notify(f"✓ {what} copied to clipboard ({len(text)} chars)",
                        timeout=3)
        except Exception:  # noqa: BLE001 — no desktop clipboard (WSL, ssh…)
            self.app.copy_to_clipboard(text)  # OSC-52 escape-code fallback
            self.notify(f"✓ {what} copied (terminal clipboard)", timeout=3)

    def action_copy_all(self) -> None:
        """Ctrl+A — copy the entire output log to the clipboard."""
        text = self.all_text()
        if not text:
            self.notify("Log is empty — nothing to copy", severity="warning",
                        timeout=3)
            return
        self._copy_text(text, "All output")

    def action_copy_selection(self) -> None:
        text = None
        try:
            text = self.screen.get_selected_text()
        except Exception:  # noqa: BLE001 — selection state can be transient
            text = None
        if not text:
            self.notify("Nothing selected — drag over the log, then Ctrl+C"
                        " (or Ctrl+A to copy all)",
                        severity="warning", timeout=3)
            return
        self._copy_text(text, "Selection")

    def action_open_menu(self) -> None:
        """Menu key / Shift+F10 — toggle the small options overlay."""
        app = self.app
        assert isinstance(app, OGEESSAApp)
        existing = app.query("#output-menu")
        if existing:
            app._close_log_menu()
        else:
            app._open_log_menu()


class OgeessaMenu(Static):
    """Small overlay over the output panel: copy all / save to file.

    Focused while open so its own key bindings (C/S/X/Esc) fire before
    anything else; closed by [X] or Escape.
    """

    can_focus = True
    BINDINGS = [
        Binding("c", "copy_all", show=False),
        Binding("s", "save_file", show=False),
        Binding("x,escape", "close_menu", show=False),
        # Menu/Shift+F10 while the overlay is focused toggles it closed
        Binding("menu,shift+f10", "toggle_menu", show=False),
    ]

    def action_toggle_menu(self) -> None:
        app = self.app
        assert isinstance(app, OGEESSAApp)
        app._close_log_menu()

    def action_copy_all(self) -> None:
        app = self.app
        assert isinstance(app, OGEESSAApp)
        app._log_w().action_copy_all()

    def action_save_file(self) -> None:
        app = self.app
        assert isinstance(app, OGEESSAApp)
        app._save_log_to_file()

    def action_close_menu(self) -> None:
        app = self.app
        assert isinstance(app, OGEESSAApp)
        app._close_log_menu()


class OgeessaInput(Input):
    """Command input whose Ctrl+C clears the field (spec FIX 2).

    Textual's Input copies its text on Ctrl+C by default, which would
    shadow the output-log copy shortcut — this keeps the two distinct:
    Ctrl+C clears while typing, copies when the log has focus.
    """

    BINDINGS = [
        Binding("ctrl+c,super+c", "clear_field", show=False, priority=True),
    ]

    def action_clear_field(self) -> None:
        self.value = ""
        self.cursor_position = 0


# ══════════════════════════════════════════════════════════════════════
# The app
# ══════════════════════════════════════════════════════════════════════


class OGEESSAApp(App):
    TITLE = "OGEESSA"

    BINDINGS = [
        # priority: must beat the focused widget's own Tab / Ctrl+V handling
        Binding("ctrl+v,super+v", "paste_from_clipboard", show=False, priority=True),
        Binding("tab", "toggle_focus", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Backend must already be loaded (main() guarantees it) — pull fresh
        # values so /config and the wizard-immediately-then-launch flow agree.
        assert config is not None and StockTraderAgent is not None
        self._provider = config.LLM_PROVIDER
        self._model = _model_name()
        # interactive /config engine state
        self._in_config = False
        self._cfg_view = ""                 # which menu is on screen
        self._cfg_menu: list[tuple[str, str]] = []   # (token, target) choices
        self._cfg_flow: dict | None = None   # active multi-step flow

    def _ensure_agent(self) -> StockTraderAgent:
        """Create the agent on first use (agent/tools imports resolved)."""
        return StockTraderAgent()  # type: ignore[misc]

    CSS = f"""
    Screen {{
        background: {DARK};
    }}
    #header {{
        height: auto;
        padding: 1 0 0 2;
    }}
    #logo {{
        color: {RED};
    }}
    #tagline {{
        color: {DIM};
        text-style: bold;
        margin: 0 0 0 1;
    }}
    #header-rule {{
        color: {GHOST};
        margin-top: 1;
    }}
    #scan {{
        height: 1;
    }}
    #body {{
        height: 1fr;
        margin: 1 1 0 1;
    }}
    #rail {{
        height: 1fr;
        width: 34;
        padding: 0 2;
    }}
    .rail-sec {{
        color: {RED};
        text-style: bold;
        margin-top: 1;
    }}
    .rail-row {{
        height: 1;
    }}
    .rail-label {{
        color: {GHOST};
        width: 12;
    }}
    .rail-val {{
        color: {WHITE};
    }}
    #tool-list {{
        color: {WHITE};
    }}
    #panel {{
        height: 1fr;
        width: 1fr;
        border: round {RED};
        padding: 0 2;
        layers: base topmenu;
    }}
    OgeessaMenu {{
        layer: topmenu;
        dock: bottom;
        width: auto;
        min-width: 24;
        height: auto;
        margin: 0 1 1 1;
        border: round {RED};
        background: {DARK};
        padding: 0 2;
        color: {WHITE};
    }}
    #panel.alert-opp {{
        border: round {GREEN};
    }}
    #panel.alert-warn {{
        border: round {RED};
    }}
    #panel.alert-neu {{
        border: round #00bcd4;
    }}
    #panel-title {{
        color: {RED};
        text-style: bold;
    }}
    #flash {{
        height: 1;
        color: {RED};
    }}
    #output {{
        height: 1fr;
        margin: 0;
        background: {DARK};
    }}
    RichLog {{
        scrollbar-gutter: stable;
    }}
    RichLog > .rich-log--highlight {{
        background: $accent 20%;
    }}
    #input-row {{
        height: 3;
        margin: 1 1 0 1;
    }}
    #prompt {{
        color: {RED};
        width: 2;
        height: 3;
        content-align: center middle;
    }}
    Input#cmd {{
        border: none;
        height: 3;
        background: {DARK};
        color: {WHITE};
    }}
    .input--cursor {{
        background: {RED};
        color: {DARK};
        text-style: bold;
    }}
    .input--placeholder {{
        color: {GHOST};
    }}
    #status {{
        dock: bottom;
        height: 1;
        background: #1a0000;
        padding: 0 1;
    }}
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(ASCII_LOGO, id="logo"),
            Static(TAGLINE, id="tagline"),
            Static("─" * 56, id="header-rule"),
            Static("", id="scan"),
            id="header",
        )
        yield Horizontal(
            Vertical(
                Static("SYSTEM STATUS", classes="rail-sec"),
                Horizontal(
                    Static("Provider", classes="rail-label"),
                    Static(config.LLM_PROVIDER, classes="rail-val", id="v-provider"),
                    classes="rail-row",
                ),
                Horizontal(
                    Static("Model", classes="rail-label"),
                    Static(_model_name(), classes="rail-val", id="v-model"),
                    classes="rail-row",
                ),
                Horizontal(
                    Static("Tools", classes="rail-label"),
                    Static(f"{len(ALL_TOOLS)} loaded", classes="rail-val", id="v-tools"),
                    classes="rail-row",
                ),
                Static("TOOLS ACTIVE", classes="rail-sec"),
                Static(_tool_rows(), id="tool-list"),
                Static("SESSION", classes="rail-sec"),
                Horizontal(
                    Static("Questions", classes="rail-label"),
                    Static("0", classes="rail-val", id="v-qcount"),
                    classes="rail-row",
                ),
                Horizontal(
                    Static("Uptime", classes="rail-label"),
                    Static("00:00", classes="rail-val", id="v-uptime"),
                    classes="rail-row",
                ),
                id="rail",
            ),
            Vertical(
                Static("─ SYSTEM", id="panel-title"),
                Static("", id="flash"),
                OgeessaLog(highlight=True, markup=True, wrap=True, min_width=0,
                           id="output"),
                id="panel",
            ),
            id="body",
        )
        yield Horizontal(
            Label("▶", id="prompt"),
            OgeessaInput(placeholder="booting…", id="cmd"),
            id="input-row",
        )
        # status bar is mounted in on_mount so it docks above everything

    # ── lifecycle ─────────────────────────────────────────────────────
    def on_mount(self) -> None:
        self._t0 = time.time()
        self._qcount = 0
        self._busy = False
        self._spin_timer = None
        self.mount(Static(_status_bar_markup(), id="status"))
        self.set_interval(1.0, self._tick_uptime)
        self._scan()
        self._input_w().focus()

    # ── output helpers ────────────────────────────────────────────────
    def _input_w(self) -> OgeessaInput:
        """The command input widget."""
        return self.query_one("#cmd", OgeessaInput)

    def _log_w(self) -> OgeessaLog:
        """The research-log output widget."""
        return self.query_one("#output", OgeessaLog)

    # ── output-panel copy helpers ─────────────────────────────────────
    def _open_log_menu(self) -> None:
        """Show the [C]opy / [S]ave / [X] overlay and focus it."""
        panel = self.query_one("#panel")
        menu = OgeessaMenu(
            f"  [{WHITE}][C][/] Copy all text\n"
            f"  [{WHITE}][S][/] Save to file\n"
            f"  [{WHITE}][X][/] Close[/]",
            id="output-menu",
        )
        menu.border_title = "OPTIONS"
        panel.mount(menu)
        menu.focus()

    def _close_log_menu(self) -> None:
        """Remove the options overlay and return focus to the log."""
        try:
            self.query_one("#output-menu", OgeessaMenu).remove()
        except Exception:  # noqa: BLE001 — already gone
            pass
        self._log_w().focus()

    def _save_log_to_file(self) -> None:
        """Write the whole log to a timestamped .txt beside main.py."""
        text = self._log_w().all_text()
        if not text:
            self.notify("Log is empty — nothing to save", severity="warning",
                        timeout=3)
            return
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.dirname(ENV_PATH)
        path = os.path.join(out_dir, f"ogeessa_log_{stamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            self.notify(f"Save failed: {exc}", severity="error", timeout=4)
            return
        self.notify(f"✓ Saved to {os.path.basename(path)}", timeout=4)

    def _append(self, markup: str) -> None:
        """Append one entry to the scrollable research log."""
        self.query_one("#output", RichLog).write(markup)

    def _flash(self, markup: str = "") -> None:
        """Set/clear the single spinner line above the log."""
        self.query_one("#flash", Static).update(markup)

    def _tick_uptime(self) -> None:
        mm, ss = divmod(int(time.time() - self._t0), 60)
        try:
            self.query_one("#v-uptime", Static).update(f"{mm:02d}:{ss:02d}")
        except Exception:  # noqa: BLE001 — cosmetic ticker; may tick during teardown
            pass

    # ── clipboard + focus shortcuts ───────────────────────────────────
    def action_paste_from_clipboard(self) -> None:
        """Ctrl+V — insert the clipboard text at the cursor (spec FIX 1)."""
        try:
            text = pyperclip.paste() or ""
        except Exception:  # noqa: BLE001 — clipboard unavailable (ssh, WSL…)
            self.notify("Clipboard unavailable", severity="warning", timeout=3)
            return
        if not text:
            return
        input_w = self._input_w()
        if self.focused is not input_w:
            input_w.focus()
        text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        pos = min(input_w.cursor_position, len(input_w.value))
        input_w.value = input_w.value[:pos] + text + input_w.value[pos:]
        input_w.cursor_position = pos + len(text)

    def action_toggle_focus(self) -> None:
        """Tab — move focus between command input and output log (FIX 5)."""
        input_w, log_w = self._input_w(), self._log_w()
        if self.focused is input_w:
            log_w.focus()
        else:
            input_w.focus()

    # ── boot sequence ─────────────────────────────────────────────────
    def _scan(self) -> None:
        """One motion moment: a red scanline sweeps under the sigil."""
        scan = self.query_one("#scan", Static)
        width = 54
        steps = 40
        state = {"i": 0}

        def step() -> None:
            i = state["i"]
            if i >= steps:
                scan_timer.stop()
                scan.update("")
                self._boot_agent()
                return
            fill = "█" * int(width * i / steps)
            pad = "░" * max(0, width - len(fill) - 1)
            scan.update(f"[{RED}]{fill}▁[/][{GHOST}]{pad}[/]")
            state["i"] += 1

        scan_timer = self.set_interval(0.045, step)

    def _boot_text(self, msg: str) -> None:
        self.query_one("#panel-title", Static).update("─ SYSTEM")
        self._append(f"[{DIM}]{esc(msg)}[/]")
        self._input_w().placeholder = "booting…"

    @work(exclusive=True, group="boot")
    async def _boot_agent(self) -> None:
        self._boot_text("spinning up the agent…")
        try:
            agent = await asyncio.to_thread(self._ensure_agent)
        except Exception as exc:  # noqa: BLE001 — surface any startup failure
            self._show_error(f"agent startup failed: {exc}", fatal=True)
            return
        global AGENT_READY
        AGENT_READY = agent
        self.query_one("#panel-title", Static).update("─ RESEARCH LOG")
        self._append(
            f"[{DIM}]System online. Ask about any symbol — "
            f"e.g. [white]OGDC[/] or [white]NVDA[/].[/]"
        )
        self._input_w().placeholder = ("Type /help for commands · "
                                       "/config to change AI settings")

    # ── input handling ────────────────────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            # In config flows an empty line is meaningful (e.g. the Finnhub
            # prompt offers "press enter on empty line to cancel").
            if self._in_config:
                self._cfg_handle_input("")
            return
        if text.lower() in EXIT_WORDS:
            self.exit()
            return
        if self._in_config:
            # rule 5: ALL input goes to the config handler while a menu/flow
            # is active — never to the agent, never to other commands.
            self._cfg_handle_input(text)
            return
        if text.startswith("/"):
            self._magic_command(text)
            return
        if AGENT_READY is None:
            self.notify("Still booting — one moment.", severity="warning", timeout=3)
            return
        if self._busy:
            self.notify("Analysis in progress — one moment.", severity="warning", timeout=3)
            return
        self._qcount += 1
        self.query_one("#v-qcount", Static).update(str(self._qcount))
        log = self.query_one("#output", RichLog)
        log.write("")
        log.write(f"[dim white]You:[/dim white] [bright_white]{esc(text)}[/bright_white]")
        log.write("")
        QUERY_BUFFER.clear()
        self._run_query(text)

    @work(exclusive=True, group="query")
    async def _run_query(self, question: str) -> None:
        agent = AGENT_READY
        assert agent is not None
        self._busy = True
        self._thinking()
        buffer: list[str] = []
        try:
            def consume() -> None:
                for chunk in agent.ask_stream(question):
                    buffer.append(chunk)

            await asyncio.to_thread(consume)
        except Exception as exc:  # noqa: BLE001 — keep the session alive
            self._show_error(f"analysis failed: {exc}")
            return
        finally:
            self._busy = False
        response = "".join(buffer)
        if response.startswith("Streaming error:"):
            self._show_error(response)
            return
        self._show_analysis(response)

    # ── magic commands ───────────────────────────────────────────────
    @staticmethod
    def help_panel_markup() -> str:
        """SPEC-COPY: /help panel (tests assert on the ``COMMANDS`` section)."""
        help_lines = [
            "  ANALYZE A STOCK",
            "  Just type a ticker or question:",
            "  › OGDC.KA",
            "  › analyze AAPL",
            "  › compare OGDC and PPL",
            "  › what happened to HBL today?",
            "",
            "  COMMANDS",
            "  /help        show this panel",
            "  /config      interactive settings menu",
            "  /model       manage keys and models",
            "  /reset       clear session memory",
            "  /clear       clear screen",
            "  /watchlist   show your saved stocks",
            "  /add TICKER  add stock to watchlist",
            "  /remove X    remove from watchlist",
            "  /tools       show active analysis tools",
            "  exit         quit ogeessa",
            "",
            "  SUPPORTED MARKETS",
            "  PSX: OGDC.KA  |  US: AAPL",
            "  India: RELIANCE.NS  |  UK: HSBA.L",
            "  Singapore: D05.SI  |  Japan: 7203.T",
        ]
        return "\n".join(f"[bold {WHITE}]{ln}[/]" if ln else "" for ln in help_lines)

    # ── interactive /config engine ───────────────────────────────────
    # Conversation-style configuration in the research log: menus render as
    # red-bordered panels; while self._in_config is True every input line is
    # routed here (never to the agent). /config re-enters at the main menu,
    # /cancel leaves config mode.

    def _cfg_active_line(self) -> str:
        """'gemini  (gemini-2.0-flash)  ✓ ready' line for config menus."""
        provider = config.LLM_PROVIDER
        model = _model_name()
        try:
            ready = config.missing_key() is None
        except Exception:  # noqa: BLE001 — never crash a menu on config quirks
            ready = True
        mark = f"[{GREEN}]✓ ready[/]" if ready else f"[{RED}]✗ not ready[/]"
        return f"[{WHITE}]{provider}[/]  [{GHOST}]({model})[/]  {mark}"

    def _cfg_enter(self) -> None:
        """(Re)enter config mode at the main menu — /config again resets here."""
        self._in_config = True
        self._cfg_flow = None
        self._cfg_view = "main"
        self._cfg_menu = [
            ("1", "keys"), ("2", "switch"), ("3", "finnhub"),
            ("4", "custom"), ("5", "cancel"),
        ]
        body = "\n".join([
            "",
            f"  Active:  {self._cfg_active_line()}",
            "",
            f"  [{WHITE}][1][/] Switch provider / manage API keys",
            f"  [{WHITE}][2][/] Change active provider",
            f"  [{WHITE}][3][/] Add Finnhub key (earnings calendar)",
            f"  [{WHITE}][4][/] Add OpenAI-compatible endpoint",
            f"  [{WHITE}][5][/] Cancel",
            "",
            f"  [{GHOST}]Type a number · /cancel exits config mode[/]",
        ])
        self._command_panel("CONFIGURATION", body)

    def _cfg_exit(self) -> None:
        self._in_config = False
        self._cfg_flow = None
        self._cfg_view = ""
        self._append(f"[{GHOST}]Configuration closed. Ask me about any symbol.[/]")

    # ── option [1]: API keys / provider management ──────────────────
    def _stored_key(self, provider: str) -> str:
        var = PROVIDER_KEY_VARS.get(provider, "")
        return str(getattr(config, var, "") or "").strip() if var else ""

    def _cfg_key_status(self, provider: str) -> str:
        if provider == "ollama":
            return f"[{GREEN}]✓ local[/] [{GHOST}](no key needed)[/]"
        if provider == "custom":
            if config.CUSTOM_BASE_URL.strip() and config.CUSTOM_MODEL.strip():
                return f"[{GREEN}]✓ configured[/]"
            return f"[{RED}]✗ not configured[/]"
        return (f"[{GREEN}]✓ key set[/]" if self._stored_key(provider)
                else f"[{RED}]✗ no key[/]")

    def _cfg_show_keys_menu(self) -> None:
        self._cfg_view = "keys"
        self._cfg_flow = None
        self._cfg_menu = []
        rows: list[str] = ["", f"  [{WHITE}]CONFIGURED PROVIDERS:[/]", ""]
        order = ["gemini", "openai", "anthropic", "groq", "ollama", "custom"]
        for i, p in enumerate(order, 1):
            active = "  (ACTIVE)" if p == config.LLM_PROVIDER else ""
            rows.append(
                f"  [{WHITE}][{i}][/] {p:<9} {self._cfg_key_status(p)}"
                f"[{GHOST}]{active}[/]"
            )
            self._cfg_menu.append((str(i), f"detail:{p}"))
        rows += [
            "",
            f"  [{WHITE}]Select a provider to:[/]",
            f"  [{RED}]•[/] [{GHOST}]Set / update its API key[/]",
            f"  [{RED}]•[/] [{GHOST}]Delete its API key[/]",
            f"  [{RED}]•[/] [{GHOST}]Set as active provider[/]",
            "",
            f"  [{WHITE}][7][/] Back",
        ]
        self._cfg_menu.append(("7", "back:main"))
        self._command_panel("API KEYS", "\n".join(rows))

    def _cfg_show_provider_detail(self, provider: str) -> None:
        self._cfg_view = "detail"
        self._cfg_flow = None
        if provider == "ollama":
            model = os.getenv("OLLAMA_MODEL", "llama3")
            self._cfg_menu = [
                ("1", "activate:ollama"), ("2", "model:ollama"),
                ("3", "back:keys"),
            ]
            body = "\n".join([
                "",
                f"  [{WHITE}]Status:[/]  [{GREEN}]✓ local[/]"
                f" [{GHOST}](no key needed)[/]",
                f"  [{WHITE}]Model:  [/] [{WHITE}]{esc(model)}[/]",
                "",
                f"  [{WHITE}][1][/] Use this provider now (set as active)",
                f"  [{WHITE}][2][/] Update model name",
                f"  [{WHITE}][3][/] Back",
                "",
                f"  [{GHOST}]No key needed — the model test pings"
                f" http://localhost:11434[/]",
            ])
            self._command_panel("OLLAMA", body)
            return
        if provider == "custom":
            name = config.CUSTOM_PROVIDER_NAME or "custom"
            self._cfg_menu = [
                ("1", "activate:custom"), ("2", "update:custom"),
                ("3", "delete:custom"), ("4", "back:keys"),
            ]
            configured = bool(config.CUSTOM_BASE_URL.strip()
                              and config.CUSTOM_MODEL.strip())
            status = (f"[{GREEN}]✓ configured[/]" if configured
                      else f"[{RED}]✗ not configured[/]")
            key = config.CUSTOM_API_KEY.strip()
            body = "\n".join([
                "",
                f"  [{WHITE}]Status:  [/] {status}",
                f"  [{WHITE}]Key:     [/]"
                f" [{WHITE}]{esc(key) or '—'}[/]",
                f"  [{WHITE}]Base URL:[/] [{WHITE}]{esc(config.CUSTOM_BASE_URL) or '—'}[/]",
                f"  [{WHITE}]Model:   [/] [{WHITE}]{esc(config.CUSTOM_MODEL) or '—'}[/]",
                "",
                f"  [{WHITE}][1][/] Use this provider now (set as active)",
                f"  [{WHITE}][2][/] Update endpoint (re-run setup)",
                f"  [{WHITE}][3][/] Delete endpoint",
                f"  [{WHITE}][4][/] Back",
            ])
            self._command_panel(name.upper(), body)
            return
        # standard keyed provider (gemini / openai / anthropic / groq)
        name = provider.capitalize()
        key = self._stored_key(provider)
        status = f"[{GREEN}]✓ key set[/]" if key else f"[{RED}]✗ no key[/]"
        self._cfg_menu = [
            ("1", f"activate:{provider}"), ("2", f"update:{provider}"),
            ("3", f"delete:{provider}" if key else "noop"),
            ("4", "back:keys"),
        ]
        rows = [
            "",
            f"  [{WHITE}]Status:[/]  {status}",
            f"  [{WHITE}]Key:  [/]    [{WHITE}]{esc(key) or '—'}[/]",
            "",
            f"  [{WHITE}][1][/] Use this provider now (set as active)",
            f"  [{WHITE}][2][/] Update API key",
            f"  [{WHITE}][3][/] Delete API key",
            f"  [{WHITE}][4][/] Back",
        ]
        if not key:
            rows.append("")
            rows.append(f"  [{GHOST}][1] will ask for a key first · link:"
                        f" {PROVIDER_GET_LINKS.get(provider, '')}[/]")
        self._command_panel(name.upper(), body="\n".join(rows))

    # ── option [2]: change active provider ──────────────────────────
    def _cfg_show_switch_menu(self) -> None:
        self._cfg_view = "switch"
        self._cfg_flow = None
        self._cfg_menu = []
        rows = [
            "",
            f"  Active provider: [{WHITE}]{config.LLM_PROVIDER}[/]",
            "",
            f"  [{WHITE}]Switch to:[/]",
        ]
        i = 1
        for p in ["gemini", "openai", "anthropic", "groq", "ollama", "custom"]:
            if p == config.LLM_PROVIDER:
                continue
            if p == "ollama":
                rows.append(f"  [{WHITE}][{i}][/] ollama     [{GHOST}](local)[/]")
                self._cfg_menu.append((str(i), "activate:ollama"))
                i += 1
            elif p == "custom":
                if config.CUSTOM_BASE_URL.strip() and config.CUSTOM_MODEL.strip():
                    label = config.CUSTOM_PROVIDER_NAME or "custom"
                    rows.append(f"  [{WHITE}][{i}][/] {label:<9} [{GHOST}](endpoint)[/]")
                    self._cfg_menu.append((str(i), "activate:custom"))
                    i += 1
            elif self._stored_key(p):
                rows.append(f"  [{WHITE}][{i}][/] {p:<9} [{GHOST}](key available)[/]")
                self._cfg_menu.append((str(i), f"activate:{p}"))
                i += 1
        if i == 1:
            rows.append(f"  [{GHOST}](no other provider has a key — use [1] to add one)[/]")
        rows.append(f"  [{WHITE}][{i}][/] Back")
        self._cfg_menu.append((str(i), "back:main"))
        self._command_panel("SWITCH PROVIDER", "\n".join(rows))

    # ── shared yes/no confirm flow ──────────────────────────────────
    def _cfg_ask_yes_no(self, prompt_markup: str, on_yes: str, on_no: str,
                        title: str = "CONFIRM") -> None:
        self._cfg_flow = {"kind": "confirm", "on_yes": on_yes, "on_no": on_no}
        body = "\n".join([
            "",
            f"  {prompt_markup}",
            "",
            f"  [{GHOST}]y / n[/]",
        ])
        self._command_panel(title, body)

    # ── option [1] sub-flows: key update / delete / activation ──────
    def _cfg_start_key_update(self, provider: str,
                              then_activate: bool = False) -> None:
        self._cfg_view = "flow"
        self._cfg_flow = {"kind": "key", "provider": provider,
                          "then_activate": then_activate}
        name = self._provider_display(provider)
        link = PROVIDER_GET_LINKS.get(provider, "")
        rows = [
            "",
            f"  [{WHITE}]Enter new {name} API key:[/]",
            f"  [{GHOST}]({link})[/]" if link else "",
            f"  [{GHOST}]paste the key and press enter[/]",
            "",
        ]
        self._command_panel(f"{name.upper()} KEY", "\n".join(rows))

    def _cfg_flow_key_input(self, text: str) -> None:
        flow = self._cfg_flow
        key = text.strip()
        if not key:
            self._append(f"[{RED}]✗ No key entered — paste the key and press enter.[/]")
            return
        provider = flow["provider"]
        then_activate = bool(flow.get("then_activate"))
        self._cfg_flow = None
        self._cfg_test_and_save_key(provider, key, then_activate)

    def _provider_display(self, provider: str) -> str:
        return PROVIDER_NAMES.get(provider, provider.capitalize())

    @work(exclusive=True, group="cfg")
    async def _cfg_test_and_save_key(self, provider: str, key: str,
                                     then_activate: bool) -> None:
        self._flash(f" [{RED}]▍[/] Testing connection...")
        ok, err = await asyncio.to_thread(_test_llm_sync, provider, key)
        self._stop_spinner()
        if not ok:
            self._command_panel("CONNECTION FAILED", "\n".join([
                "",
                f"  [{RED}]✗ Failed: {esc(err[:300])}[/]",
                f"  [{GHOST}]Check your key and try [2] Update API key again.[/]",
                "",
            ]))
            self._cfg_show_provider_detail(provider)
            return
        _patch_env({PROVIDER_KEY_VARS[provider]: key})
        self._command_panel("KEY SAVED", "\n".join([
            "",
            f"  [{GREEN}]✓ Connected[/]",
            f"  [{GREEN}]✓ Key saved.[/]",
            "",
        ]))
        if then_activate:
            self._finish_activation(provider)
            return
        name = self._provider_display(provider)
        self._cfg_ask_yes_no(
            f"[{WHITE}]Set {name} as active provider now?[/] [{GHOST}](y/n)[/]",
            on_yes=f"activate:{provider}", on_no=f"detail:{provider}",
            title="ACTIVATE",
        )

    def _cfg_confirm_delete(self, provider: str) -> None:
        if provider == "custom":
            name = config.CUSTOM_PROVIDER_NAME or "custom endpoint"
        else:
            name = self._provider_display(provider)
        self._cfg_ask_yes_no(
            f"[{WHITE}]Are you sure you want to delete the {name} key?[/]"
            f" [{GHOST}](y/n)[/]",
            on_yes=f"delete-yes:{provider}", on_no=f"detail:{provider}",
            title="DELETE KEY",
        )

    def _cfg_delete_key(self, provider: str) -> None:
        if provider == "custom":
            _patch_env({"CUSTOM_PROVIDER_NAME": "", "CUSTOM_BASE_URL": "",
                        "CUSTOM_API_KEY": "", "CUSTOM_MODEL": ""})
        else:
            _patch_env({PROVIDER_KEY_VARS[provider]: ""})
        was_active = config.LLM_PROVIDER == provider
        self._command_panel("KEY DELETED", "\n".join([
            "",
            f"  [{GREEN}]✓ Key deleted.[/]",
            "",
        ]))
        if was_active:
            # rule 6: force the user into the switch-provider flow
            self._append(f"[{AMBER}]Active provider key deleted."
                         f" Please switch to another provider.[/]")
            self._cfg_show_switch_menu()
        else:
            self._cfg_show_provider_detail(provider)

    # ── activation + live agent reload (rule 4) ─────────────────────
    def _apply_provider(self, provider: str) -> None:
        """Persist active provider, sync env/config/agent.core, rebuild agent."""
        _patch_env({"LLM_PROVIDER": provider})
        import agent.core as _core
        # agent/core.py holds frozen `from config import …` bindings — patch
        # its globals too or its _build_llm sees the OLD provider forever.
        _core.LLM_PROVIDER = provider
        if provider == "ollama":
            _core.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
        elif provider != "custom":
            setattr(_core, f"{provider.upper()}_API_KEY", self._stored_key(provider))
        self._provider = provider
        self._model = _model_name()
        self.query_one("#v-provider", Static).update(provider)
        self.query_one("#v-model", Static).update(self._model)
        self.query_one("#panel-title", Static).update("─ RESEARCH LOG")
        self.query_one("#panel").set_classes("alert-neu")
        try:
            self.query_one("#status", Static).update(_status_bar_markup())
        except Exception:  # noqa: BLE001 — status bar is cosmetic
            pass
        global AGENT_READY
        AGENT_READY = self._ensure_agent()

    def _finish_activation(self, provider: str) -> None:
        try:
            self._apply_provider(provider)
        except Exception as exc:  # noqa: BLE001 — surface any switch failure
            self._show_error(f"provider switch failed: {exc}")
            self._cfg_exit()
            return
        self._in_config = False
        self._cfg_flow = None
        self._append(
            f"[{GREEN}]✓ Now using [/][{WHITE}]{provider}[/]"
            f" [{GHOST}]— agent reloaded, no restart needed[/]"
        )

    def _cfg_activate_provider(self, provider: str) -> None:
        """[1] Use this provider now — straight to key entry when no key."""
        if provider == "custom":
            if not (config.CUSTOM_BASE_URL.strip() and config.CUSTOM_MODEL.strip()):
                self._cfg_start_custom_flow(then_activate=True)
                return
        elif provider != "ollama" and not self._stored_key(provider):
            self._cfg_start_key_update(provider, then_activate=True)
            return
        self._finish_activation(provider)

    # ── option [3]: Finnhub key ─────────────────────────────────────
    def _cfg_start_finnhub(self) -> None:
        self._cfg_view = "flow"
        current = (getattr(config, "FINNHUB_API_KEY", "") or "").strip()
        status = f"[{GREEN}]✓ set[/]" if current else f"[{RED}]✗ not set[/]"
        self._cfg_flow = {"kind": "finnhub"}
        body = "\n".join([
            "",
            f"  [{WHITE}]Finnhub gives you live earnings dates and estimates.[/]",
            f"  [{GHOST}]Get a free key at: finnhub.io → Dashboard → API Key[/]",
            "",
            f"  Current status: {status}",
            "",
            f"  [{WHITE}]Enter Finnhub API key[/]"
            f" [{GHOST}](or press enter on empty line to cancel):[/]",
        ])
        self._command_panel("FINNHUB", body)

    def _cfg_flow_finnhub_input(self, text: str) -> None:
        key = text.strip()
        if not key:
            self._cfg_flow = None
            self._append(f"[{GHOST}]Finnhub setup cancelled.[/]")
            self._cfg_enter()
            return
        self._cfg_flow = None
        self._cfg_test_and_save_finnhub(key)

    @work(exclusive=True, group="cfg")
    async def _cfg_test_and_save_finnhub(self, key: str) -> None:
        self._flash(f" [{RED}]▍[/] Testing...")
        ok, err = await asyncio.to_thread(_test_finnhub_sync, key)
        self._stop_spinner()
        if not ok:
            self._command_panel("CONNECTION FAILED", "\n".join([
                "",
                f"  [{RED}]✗ Failed: {esc(err[:300])}[/]",
                f"  [{GHOST}]Check the key at finnhub.io → Dashboard → API Key[/]",
                "",
            ]))
            self._cfg_enter()
            return
        _patch_env({"FINNHUB_API_KEY": key})
        self._command_panel("FINNHUB SAVED", "\n".join([
            "",
            f"  [{GREEN}]✓ Valid[/]",
            f"  [{GREEN}]✓ Saved. Earnings calendar now enhanced.[/]",
            "",
        ]))
        self._cfg_exit()

    # ── ollama model update (rule 7) ────────────────────────────────
    def _cfg_start_model_update(self) -> None:
        self._cfg_view = "flow"
        current = os.getenv("OLLAMA_MODEL", "llama3")
        self._cfg_flow = {"kind": "model"}
        body = "\n".join([
            "",
            f"  [{WHITE}]Enter Ollama model name (current: {esc(current)}):[/]",
            f"  [{GHOST}]e.g. llama3, mistral, qwen2.5:14b[/]",
            "",
        ])
        self._command_panel("OLLAMA MODEL", body)

    def _cfg_flow_model_input(self, text: str) -> None:
        model = text.strip()
        if not model:
            self._append(f"[{RED}]✗ Model name can't be empty.[/]")
            return
        self._cfg_flow = None
        self._cfg_test_and_save_model(model)

    @work(exclusive=True, group="cfg")
    async def _cfg_test_and_save_model(self, model: str) -> None:
        self._flash(f" [{RED}]▍[/] Checking Ollama...")
        ok, err = await asyncio.to_thread(_check_ollama_sync)
        self._stop_spinner()
        if not ok:
            self._command_panel("OLLAMA NOT RUNNING", "\n".join([
                "",
                f"  [{RED}]✗ Ollama not running[/]",
                f"  [{GHOST}]Start it with: ollama serve[/]",
                "",
            ]))
            self._cfg_show_provider_detail("ollama")
            return
        _patch_env({"OLLAMA_MODEL": model})
        import agent.core as _core
        _core.OLLAMA_MODEL = model
        self._command_panel("MODEL SAVED", "\n".join([
            "",
            f"  [{GREEN}]✓ Ollama running[/]",
            f"  [{GREEN}]✓ Model set to {esc(model)}.[/]",
            "",
        ]))
        if config.LLM_PROVIDER == "ollama":
            self._cfg_ask_yes_no(
                f"[{WHITE}]Reload the agent with the new model now?[/]"
                f" [{GHOST}](y/n)[/]",
                on_yes="activate:ollama", on_no="detail:ollama",
                title="RELOAD",
            )
        else:
            self._cfg_show_provider_detail("ollama")

    # ── option [4]: OpenAI-compatible endpoint wizard ───────────────
    def _cfg_start_custom_flow(self, then_activate: bool = False) -> None:
        self._cfg_view = "flow"
        self._cfg_flow = {"kind": "custom", "step": 1,
                          "data": {"name": "", "base_url": "",
                                   "key": "", "model": ""},
                          "then_activate": then_activate}
        body = "\n".join([
            "",
            f"  [{WHITE}]Add any provider that uses the OpenAI API format:[/]",
            f"  [{GHOST}]LM Studio, Together AI, Mistral, DeepSeek, Perplexity,[/]",
            f"  [{GHOST}]Anyscale, local vllm, Ollama's OpenAI endpoint…[/]",
            "",
            f"  [{WHITE}]Enter a name for this provider:[/]",
            f"  [{GHOST}](e.g. lmstudio, deepseek, mistral)[/]",
        ])
        self._command_panel("CUSTOM ENDPOINT", body)

    def _cfg_flow_custom_input(self, text: str) -> None:
        flow = self._cfg_flow
        step = flow["step"]
        data = flow["data"]
        if step == 1:
            name = text.strip().lower()
            if not re.fullmatch(r"[a-z0-9_-]{2,20}", name):
                self._append(f"[{RED}]✗ Name must be 2–20 chars: a-z, 0-9, - or _[/]")
                return
            data["name"] = name
            flow["step"] = 2
            self._command_panel("CUSTOM ENDPOINT", "\n".join([
                "",
                f"  [{WHITE}]Enter base URL:[/]",
                f"  [{GHOST}](e.g. http://localhost:1234/v1 for LM Studio)[/]",
                f"  [{GHOST}](e.g. https://api.deepseek.com/v1 for DeepSeek)[/]",
            ]))
        elif step == 2:
            url = text.strip()
            if not url.startswith(("http://", "https://")):
                self._append(f"[{RED}]✗ Base URL must start with http:// or https://[/]")
                return
            data["base_url"] = url
            flow["step"] = 3
            self._command_panel("CUSTOM ENDPOINT", "\n".join([
                "",
                f"  [{WHITE}]Enter API key:[/]",
                f"  [{GHOST}](for local models like LM Studio type: fake_key)[/]",
            ]))
        elif step == 3:
            key = text.strip()
            if not key:
                self._append(f"[{RED}]✗ Key can't be empty — for local models"
                             f" type: fake_key[/]")
                return
            data["key"] = key
            flow["step"] = 4
            self._command_panel("CUSTOM ENDPOINT", "\n".join([
                "",
                f"  [{WHITE}]Enter model name:[/]",
                f"  [{GHOST}](e.g. deepseek-chat, mistral-large-latest)[/]",
            ]))
        elif step == 4:
            model = text.strip()
            if not model:
                self._append(f"[{RED}]✗ Model name can't be empty.[/]")
                return
            data["model"] = model
            then_activate = bool(flow.get("then_activate"))
            self._cfg_flow = None
            self._cfg_test_and_save_custom(dict(data), then_activate)

    @work(exclusive=True, group="cfg")
    async def _cfg_test_and_save_custom(self, data: dict,
                                        then_activate: bool) -> None:
        self._flash(f" [{RED}]▍[/] Testing connection...")
        ok, err = await asyncio.to_thread(
            _test_llm_sync, "custom", data["key"], data["base_url"], data["model"]
        )
        self._stop_spinner()
        if not ok:
            self._command_panel("CONNECTION FAILED", "\n".join([
                "",
                f"  [{RED}]✗ Failed: {esc(err[:300])}[/]",
                f"  [{GHOST}]Re-run /config → [4] to retry.[/]",
                "",
            ]))
            self._cfg_enter()
            return
        _patch_env({
            "CUSTOM_PROVIDER_NAME": data["name"],
            "CUSTOM_BASE_URL": data["base_url"],
            "CUSTOM_API_KEY": data["key"],
            "CUSTOM_MODEL": data["model"],
        })
        self._command_panel("ENDPOINT SAVED", "\n".join([
            "",
            f"  [{GREEN}]✓ Connected[/]",
            f"  [{GREEN}]✓ Saved as '{data['name']}' provider.[/]",
            "",
        ]))
        if then_activate:
            self._finish_activation("custom")
            return
        self._cfg_ask_yes_no(
            f"[{WHITE}]Set {data['name']} as active provider now?[/]"
            f" [{GHOST}](y/n)[/]",
            on_yes="activate:custom", on_no="menu:main", title="ACTIVATE",
        )

    # ── config-mode input routing (rule 5) ──────────────────────────
    def _cfg_dispatch(self, token: str) -> None:
        if token.startswith("detail:"):
            self._cfg_show_provider_detail(token.split(":", 1)[1])
        elif token.startswith("activate:"):
            self._cfg_activate_provider(token.split(":", 1)[1])
        elif token.startswith("update:"):
            p = token.split(":", 1)[1]
            if p == "custom":
                self._cfg_start_custom_flow()
            elif p == "ollama":
                self._cfg_start_model_update()
            else:
                self._cfg_start_key_update(p)
        elif token.startswith("delete-yes:"):
            self._cfg_delete_key(token.split(":", 1)[1])
        elif token.startswith("delete:"):
            self._cfg_confirm_delete(token.split(":", 1)[1])
        elif token.startswith("model:"):
            self._cfg_start_model_update()
        elif token == "keys":
            self._cfg_show_keys_menu()
        elif token == "switch":
            self._cfg_show_switch_menu()
        elif token == "finnhub":
            self._cfg_start_finnhub()
        elif token == "custom":
            self._cfg_start_custom_flow()
        elif token == "cancel":
            self._cfg_exit()
        elif token == "back:main":
            self._cfg_enter()
        elif token == "back:keys":
            self._cfg_show_keys_menu()
        elif token == "menu:main":
            self._cfg_enter()
        elif token == "noop":
            self._append(f"[{GHOST}]Nothing to delete — no key stored.[/]")

    def _cfg_menu_pick(self, text: str) -> None:
        token = dict(self._cfg_menu).get(text.strip())
        if token is None:
            self._append(f"[{RED}]✗ Pick a number from the menu"
                         f" (or /cancel to exit).[/]")
            return
        self._cfg_dispatch(token)

    def _cfg_handle_input(self, text: str) -> None:
        low = text.strip().lower()
        if low == "/config":
            self._cfg_enter()          # /config again resets to the main menu
            return
        if low in ("/cancel", "/exit", "/back"):
            self._cfg_exit()
            return
        flow = self._cfg_flow
        if flow is not None:
            kind = flow.get("kind")
            if kind == "key":
                self._cfg_flow_key_input(text)
            elif kind == "custom":
                self._cfg_flow_custom_input(text)
            elif kind == "model":
                self._cfg_flow_model_input(text)
            elif kind == "confirm":
                self._cfg_flow_confirm(text)
            elif kind == "finnhub":
                self._cfg_flow_finnhub_input(text)
            return
        if self._cfg_view in ("main", "keys", "detail", "switch"):
            self._cfg_menu_pick(text)
            return
        self._cfg_enter()

    def _cfg_flow_confirm(self, text: str) -> None:
        flow = self._cfg_flow or {}
        low = text.strip().lower()
        if low in ("y", "yes"):
            action = flow.get("on_yes", "")
        elif low in ("n", "no"):
            action = flow.get("on_no", "")
        else:
            self._append(f"[{DIM}]Please answer y or n.[/]")
            return
        self._cfg_flow = None      # clear BEFORE dispatch: it may set a new flow
        if action:
            self._cfg_dispatch(action)

    @staticmethod
    def tools_panel_markup() -> str:
        """SPEC: /tools panel — every active tool + its status."""
        if not ALL_TOOLS:
            return f"[{RED}]✗ No tools loaded[/]"
        rows = []
        for tool in ALL_TOOLS:
            name = getattr(tool, "name", str(tool))
            desc = str(getattr(tool, "description", "") or "").strip()
            first = desc.splitlines()[0] if desc else ""
            if len(first) > 48:
                first = first[:47] + "…"
            rows.append(
                f"  [{GREEN}]✓[/] [{WHITE}]{name:<22}[/] [{GHOST}]{esc(first)}[/]"
            )
        rows.append("")
        rows.append(f"  [{GHOST}]{len(ALL_TOOLS)} tools active · all systems nominal[/]")
        return "\n".join(rows)

    def _magic_command(self, text: str) -> None:
        """Dispatch ``/``-prefixed input. NEVER forwarded to the agent."""
        cmd, _, arg = text.partition(" ")
        cmd = cmd.lower()
        arg = arg.strip()
        if cmd == "/help":
            self._command_panel("OGEESSA HELP", self.help_panel_markup())
        elif cmd == "/config":
            self._cfg_enter()
        elif cmd == "/model":
            # spec: /model is a shortcut straight to option [1] (API keys /
            # provider management) inside interactive config mode.
            self._in_config = True
            self._cfg_flow = None
            self._cfg_show_keys_menu()
        elif cmd == "/reset":
            if AGENT_READY is not None:
                AGENT_READY.reset()
                self._command_panel(
                    "SESSION RESET", f"[{WHITE}]✓ Session memory cleared.[/]\n"
                    f"[{GHOST}]The agent has forgotten this conversation.[/]"
                )
            else:
                self._command_panel(
                    "SESSION RESET",
                    f"[{DIM}]Agent still booting — nothing to reset yet.[/]",
                )
        elif cmd == "/clear":
            self.query_one("#output", RichLog).clear()
            self._flash()
        elif cmd == "/add":
            if not arg:
                self._command_panel(
                    "WATCHLIST",
                    f"[{RED}]✗ Usage: /add TICKER[/]\n"
                    f"[{GHOST}]Example: /add OGDC.KA[/]",
                )
            else:
                ticker = arg.upper()
                wl = self._load_watchlist()
                if ticker in wl:
                    self._command_panel(
                        "WATCHLIST",
                        f"[{AMBER}]• {esc(ticker)} is already on your watchlist.[/]",
                    )
                else:
                    wl.append(ticker)
                    self._save_watchlist(wl)
                    self._command_panel(
                        "WATCHLIST",
                        f"[{GREEN}]✓ Added {esc(ticker)} to your watchlist.[/]\n"
                        f"[{GHOST}]{len(wl)} saved · /watchlist to view · "
                        f"/remove {esc(ticker)} to undo[/]",
                    )
        elif cmd == "/remove":
            if not arg:
                self._command_panel(
                    "WATCHLIST",
                    f"[{RED}]✗ Usage: /remove TICKER[/]\n"
                    f"[{GHOST}]Example: /remove OGDC.KA[/]",
                )
            else:
                ticker = arg.upper()
                wl = self._load_watchlist()
                if ticker in wl:
                    wl.remove(ticker)
                    self._save_watchlist(wl)
                    self._command_panel(
                        "WATCHLIST",
                        f"[{GREEN}]✓ Removed {esc(ticker)} from your watchlist.[/]",
                    )
                else:
                    self._command_panel(
                        "WATCHLIST",
                        f"[{AMBER}]• {esc(ticker)} is not on your watchlist.[/]\n"
                        f"[{GHOST}]{len(wl)} saved · /watchlist to view[/]",
                    )
        elif cmd == "/watchlist":
            self._show_watchlist()
        elif cmd == "/tools":
            self._command_panel("ACTIVE TOOLS", self.tools_panel_markup())
        else:
            self._command_panel(
                "UNKNOWN COMMAND",
                f"[{RED}]✗ Unknown command: {esc(cmd)}[/]\n"
                f"[{GHOST}]Type /help to see every command.[/]",
            )

    def _command_panel(self, title: str, body: str) -> None:
        """Red-bordered ┌─ TITLE ─┐ panel written straight to the research log.

        Command output is hand-authored (never passed through
        clean_and_render, which would mangle it).
        """
        inner = max(
            (_display_width(re.sub(r"\[[^]]*\]", "", ln)) for ln in body.split("\n")),
            default=0,
        )
        inner = max(inner, _display_width(title) + 2, 40)
        log = self.query_one("#output", RichLog)
        log.write("")
        log.write(
            f"[bold {RED}]┌─ {title} "
            + "─" * max(1, inner - _display_width(title) - 1) + "┐[/]"
        )
        for ln in body.split("\n"):
            visible = _display_width(re.sub(r"\[[^]]*\]", "", ln))
            log.write(f"[{RED}]│[/] " + ln + " " * max(0, inner - visible) + f" [{RED}]│[/]")
        log.write(f"[bold {RED}]└" + "─" * (inner + 2) + "┘[/]")
        log.write("")
        log.scroll_end()

    # ── watchlist persistence (watchlist.json beside main.py) ────────
    @staticmethod
    def _load_watchlist() -> list[str]:
        try:
            with open(WATCHLIST_PATH, encoding="utf-8") as fh:
                data = json.load(fh)
            return [str(t).upper() for t in data] if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _save_watchlist(self, items: list[str]) -> None:
        try:
            with open(WATCHLIST_PATH, "w", encoding="utf-8") as fh:
                json.dump(items, fh, indent=2)
        except OSError as exc:
            self.notify(f"could not save watchlist: {exc}", severity="warning", timeout=4)

    def _show_watchlist(self) -> None:
        wl = self._load_watchlist()
        if not wl:
            body = (
                f"[{GHOST}]Your watchlist is empty.[/]\n"
                f"[{WHITE}]Add one:[/] [{AMBER}]/add OGDC.KA[/]  [{GHOST}]or[/]"
                f"  [{AMBER}]/add AAPL[/]"
            )
        else:
            rows = [f"  [{RED}]•[/] [{WHITE}]{esc(t)}[/]" for t in wl]
            rows += [
                "",
                f"  [{GHOST}]{len(wl)} saved · remove with /remove TICKER[/]",
            ]
            body = "\n".join(rows)
        self._command_panel("YOUR WATCHLIST", body)

    # ── output panel states ───────────────────────────────────────────
    def _thinking(self) -> None:
        self.query_one("#panel-title", Static).update("─ OGEESSA ANALYZING")
        state = {"i": 0}

        def tick() -> None:
            frame = TYPING_FRAMES[state["i"] % len(TYPING_FRAMES)]
            n = len("".join(QUERY_BUFFER))
            self._flash(f" {frame} Analyzing  ·  {n} chars streamed")
            state["i"] += 1

        self._spin_timer = self.set_interval(0.5, tick)

    def _stop_spinner(self) -> None:
        if self._spin_timer is not None:
            self._spin_timer.stop()
            self._spin_timer = None
        self._flash()

    def _show_analysis(self, raw: str) -> None:
        self._stop_spinner()
        self.query_one("#panel").set_classes(_alert_class(raw))
        log = self.query_one("#output", RichLog)
        log.write("[dim red]Ogeessa:[/dim red]")
        log.write(clean_and_render(raw))
        log.write("─" * 80)
        log.scroll_end()

    def _show_error(self, msg: str, fatal: bool = False) -> None:
        self._stop_spinner()
        hint = "" if fatal else " — session kept, ask another question."
        log = self.query_one("#output", RichLog)
        log.write("[dim red]Ogeessa:[/dim red]")
        log.write(f"[bold {RED}]⚠ {esc(msg)}{hint}[/]")
        log.write("─" * 80)
        log.scroll_end()


# ══════════════════════════════════════════════════════════════════════
# First-run setup wizard (pre-TUI; runs before config.py is ever imported)
# ══════════════════════════════════════════════════════════════════════

WIZARD_PROVIDERS: dict[str, tuple[str, str, str, str | None]] = {
    "1": ("gemini",    "Gemini",    "Free tier — aistudio.google.com/apikey", "GEMINI_API_KEY"),
    "2": ("openai",    "OpenAI",    "GPT-4o — platform.openai.com/api-keys",  "OPENAI_API_KEY"),
    "3": ("anthropic", "Anthropic", "Claude — console.anthropic.com",          "ANTHROPIC_API_KEY"),
    "4": ("groq",      "Groq",      "Free & fast — console.groq.com",          "GROQ_API_KEY"),
    "5": ("ollama",    "Ollama",    "Local, no key needed — ollama.ai",        None),
}


def _wizard_build_llm(provider: str, api_key: str):
    """Build one LLM for the wizard's connection test.

    Mirrors agent/core.py::_build_llm instead of importing it: core.py
    reads config constants frozen at ITS import time, while the wizard
    must test the key the user just typed (env already patched by the
    caller).
    """
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=api_key,
            temperature=0.2,
        )
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
            api_key=api_key,
            temperature=0.2,
        )
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            api_key=api_key,
            temperature=0.2,
        )
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite",
            google_api_key=api_key,
        )
    if provider == "ollama":
        from langchain_community.chat_models import ChatOllama

        return ChatOllama(model=os.getenv("OLLAMA_MODEL", "llama3"), temperature=0.2)
    raise ValueError(f"Unknown provider '{provider}'")


def setup_wizard() -> bool:
    """Interactive first-run provider setup. Returns True when .env was saved."""
    console = Console()

    console.print("""
[bold red]╔══════════════════════════════════════════╗
║      OGEESSA — FIRST TIME SETUP         ║
╚══════════════════════════════════════════╝[/bold red]
""")
    console.print("Welcome. Let's connect your AI in 60 seconds.\n")

    providers = WIZARD_PROVIDERS

    console.print("Which AI provider do you want to use?\n")
    for k, (_, name, hint, _) in providers.items():
        console.print(f"  [[bold]{k}[/bold]] {name} — [dim]{hint}[/dim]")

    console.print("\nEnter number: ", end="")
    choice = input().strip()

    if choice not in providers:
        console.print("[red]Invalid choice. Run again.[/red]")
        return False

    provider, name, hint, key_name = providers[choice]

    api_key = ""
    if key_name:
        console.print(f"\nEnter your {name} API key: ", end="")
        api_key = input().strip()
        if not api_key:
            console.print("[red]No key entered. Run again.[/red]")
            return False

        # Test the connection — patch the env first, then build the LLM fresh.
        console.print("\n[dim]Testing connection...[/dim] ", end="")
        os.environ["LLM_PROVIDER"] = provider
        os.environ[key_name] = api_key
        try:
            llm = _wizard_build_llm(provider, api_key)
            llm.invoke("Reply with only: OK")
            console.print("[bold green]✓ Connected[/bold green]")
        except Exception as e:  # noqa: BLE001 — any provider error is user-facing
            console.print(f"[red]✗ Failed: {e}[/red]")
            console.print("[dim]Check your key and try again.[/dim]")
            return False
    else:
        # Ollama — just check it's running
        console.print("\n[dim]Checking Ollama...[/dim] ", end="")
        try:
            import requests
            requests.get("http://localhost:11434", timeout=3)
            console.print("[bold green]✓ Ollama running[/bold green]")
        except Exception:
            console.print("[red]✗ Ollama not running[/red]")
            console.print("[dim]Start it with: ollama serve[/dim]")
            return False

    # Save to .env
    env_lines = [
        f"LLM_PROVIDER={provider}",
        f"OPENAI_API_KEY={api_key if provider == 'openai' else ''}",
        f"ANTHROPIC_API_KEY={api_key if provider == 'anthropic' else ''}",
        f"GROQ_API_KEY={api_key if provider == 'groq' else ''}",
        f"GEMINI_API_KEY={api_key if provider == 'gemini' else ''}",
        "OLLAMA_MODEL=llama3",
        "FINNHUB_API_KEY=",
    ]

    with open(".env", "w") as f:
        f.write("\n".join(env_lines))

    console.print("\n[green]✓ Saved to .env[/green]")
    console.print("[dim]Launching ogeessa...[/dim]\n")
    return True


def missing_key_message(provider: str) -> None:
    """Feature 3 — printed when .env exists but the provider's key is empty."""
    links = {
        "gemini":    ("https://aistudio.google.com/apikey", "GEMINI_API_KEY"),
        "openai":    ("https://platform.openai.com/api-keys", "OPENAI_API_KEY"),
        "anthropic": ("https://console.anthropic.com", "ANTHROPIC_API_KEY"),
        "groq":      ("https://console.groq.com", "GROQ_API_KEY"),
        "ollama":    ("https://ollama.ai", "OLLAMA_MODEL"),
        "custom":    ("your provider's dashboard", "CUSTOM_BASE_URL"),
    }
    link, key_var = links.get(
        provider, ("https://aistudio.google.com/apikey", "GEMINI_API_KEY")
    )
    console = Console()
    console.print(f"\n[red]✗ No API key found for provider: {provider}[/red]")
    console.print(f"\nGet a free {provider} key at:\n{link}")
    console.print("\nThen either:")
    console.print("A) Run setup wizard:  python main.py --setup")
    console.print(f"B) Edit .env directly and add: {key_var}=your_key\n")


def env_configured() -> bool:
    """True when .env exists AND LLM_PROVIDER is valid AND its key is non-empty.

    Parses .env directly — importing config here would freeze values from
    before any wizard run. Ollama needs no key. A key present in the real
    process environment also counts (exported vars win over empty .env lines).
    """
    if not os.path.isfile(".env"):
        return False
    values: dict[str, str] = {}
    try:
        with open(".env", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                values[k.strip()] = v.strip()
    except OSError:
        return False
    valid = {"gemini", "openai", "anthropic", "groq", "ollama", "custom"}
    provider = values.get("LLM_PROVIDER", "").strip().lower()
    if provider not in valid:
        return False
    if provider == "ollama":
        return True
    if provider == "custom":
        return bool(values.get("CUSTOM_BASE_URL", "").strip())
    key_var = f"{provider.upper()}_API_KEY"
    return bool(values.get(key_var, "").strip()) or bool(os.getenv(key_var, "").strip())


def main() -> None:
    """Entry point: wizard → missing-key notice → backend load → TUI."""
    if "--setup" in sys.argv[1:] or not env_configured():
        if not setup_wizard():
            sys.exit(1)
    _load_backend()  # config reads .env only AFTER the wizard has settled it
    if config is not None and config.missing_key() is not None:
        missing_key_message(config.LLM_PROVIDER)
        sys.exit(1)
    OGEESSAApp().run()


if __name__ == "__main__":
    main()