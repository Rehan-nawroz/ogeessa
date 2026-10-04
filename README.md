# Ogeessa

**An AI stock-research agent that lives in your terminal.**

Ogeessa is a full-screen terminal app (TUI) built around a LangChain tool-calling
agent. Ask a plain-English question about any stock — *"what happened to HBL
today?"*, *"compare OGDC and PPL"*, *"analyze AAPL"* — and the agent pulls live
market data with its built-in tools (price, technicals, news, fundamentals,
announcements, economic calendar) and streams a structured analysis back into a
research log, complete with a clear verdict.

Bring your own AI: OpenAI, Anthropic, Groq, Google Gemini, a local Ollama model,
or any OpenAI-compatible endpoint (LM Studio, DeepSeek, vLLM, …).

---

## Contents

- [What Ogeessa does](#what-ogeessa-does)
- [Requirements](#requirements)
- [Quick start — how to launch it](#quick-start--how-to-launch-it)
- [First run: the setup wizard](#first-run-the-setup-wizard)
- [Choosing your AI provider](#choosing-your-ai-provider)
- [Manual `.env` configuration](#manual-env-configuration)
- [Using the TUI](#using-the-tui)
- [Slash commands](#slash-commands)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Supported markets](#supported-markets)
- [The data tools](#the-data-tools)
- [Project layout](#project-layout)
- [Diagnostics: testing every tool](#diagnostics-testing-every-tool)
- [Troubleshooting](#troubleshooting)
- [Security notes](#security-notes)
- [Disclaimer](#disclaimer)

---

## What Ogeessa does

- **Natural-language stock research.** Type a ticker or a question; the agent
  decides which tools to call and streams its answer as it forms it.
- **Six live-data tools.** Real quotes, technical indicators, headlines,
  fundamentals, company announcements, and the economic/earnings calendar —
  no mocks, no cached fixtures.
- **A persistent research log.** Every answer is appended to a scrollable,
  selectable log you can copy out with one keystroke.
- **Watchlist.** Save tickers with `/add` and recall them with `/watchlist`.
- **Six LLM providers.** Switch provider or model at any time from the
  interactive `/config` menu — no restart required.
- **Runs anywhere you have a terminal.** Windows, macOS, or Linux.

---

## Requirements

| Requirement | Notes |
|---|---|
| **Python 3.12** | Required by the pinned dependencies (3.13 is not supported yet). |
| **A terminal** | Windows Terminal, PowerShell, cmd, macOS Terminal, or any Linux shell. |
| **Internet access** | For market data (yfinance, DuckDuckGo) and your chosen AI provider. |
| **One AI API key** | Free options exist — Google AI Studio (Gemini) and Groq both hand out free keys. Alternatively run fully local with [Ollama](https://ollama.ai) and no key at all. |
| **Optional: Finnhub key** | Only enriches the earnings/economic calendar; everything else works without it. |

---

## Quick start — how to launch it

The launch is **four commands, in this order**, run inside the folder that holds
`main.py`: create the venv → activate it → install the requirements → start the
agent.

> ⚠️ **A fresh download contains no `venv\` folder — step 1 below creates it.**
> Running `venv\Scripts\activate` before that makes cmd answer
> *"The system cannot find the path specified."* That message always means step 1
> was skipped; nothing is broken and nothing is missing.

**Windows (PowerShell / cmd):**

```bat
python --version                   :: 0. must report Python 3.12
python -m venv venv                :: 1. CREATE the venv (only once, first time)
venv\Scripts\activate             :: 2. enter the venv (do this in every new terminal)
pip install -r requirements.txt   :: 3. install requirements into the venv
python main.py                    :: 4. start the agent
```

**macOS / Linux:**

```bash
python3 --version                 # 0. must report Python 3.12
python3 -m venv venv               # 1. CREATE the venv (only once, first time)
source venv/bin/activate          # 2. enter the venv (do this in every new terminal)
pip install -r requirements.txt   # 3. install requirements into the venv
python main.py                    # 4. start the agent
```

The first-time, step-by-step walkthrough follows.

### 1. Get the code

```bash
git clone https://github.com/Rehan-nawroz/ogeessa.git
cd ogeessa
```

(No git? Download the ZIP from GitHub, extract it, and open the extracted
folder — the one containing `main.py`.)

That folder **is** the application: `main.py`, `requirements.txt`, `agent/`,
`prompts/` and `tools/` all sit in its root, so every command below runs from
there. Check your prompt — it should end in `...ogeessa>` — and `cd` into that
folder if it does not.

A fresh clone contains **no `venv\` folder**; you create it in the next step.

### 2. Create and activate the virtual environment (venv) — do this FIRST

**Always use a venv.** It isolates Ogeessa's packages from your operating
system's own Python: installing into the system interpreter is what makes
`pip` fight with OS-bundled frameworks and system packages (Debian/Ubuntu even
refuse outright with `error: externally-managed-environment`).

**Windows (PowerShell / cmd):**

```bat
python --version
python -m venv venv
venv\Scripts\activate
```

> **Use `python`, never `py`.** The `py` launcher is installed only by the
> python.org installer — Microsoft Store builds and several other distributions
> do not have it, and cmd answers *"'py' is not recognized"* without it. Plain
> `python` works on every machine.
>
> `activate` only ever works **after** `python -m venv venv` created `venv\`.
> Got *"The system cannot find the path specified"*? Create the venv first,
> then activate again.

**macOS / Linux:**

```bash
python3 --version          # must report Python 3.12
python3 -m venv venv
source venv/bin/activate
```

**Your prompt now starts with `(venv)` — that is the sign you are inside it.**
Confirm the interpreter belongs to the venv before installing anything:

```bash
python -c "import sys; print(sys.prefix)"   # must print a path inside venv/
```

> **Rule:** run `pip install` and `python main.py` **only while the venv is
> active**. A new terminal window starts with the venv deactivated — activate
> it again first (`venv\Scripts\activate` on Windows, `source venv/bin/activate`
> on macOS/Linux).

If `python --version` is not recognized at all, install Python 3.12 from
[python.org](https://www.python.org/downloads/) and tick **“Add python.exe to
PATH”** in the installer, then open a fresh terminal.

### 3. Install the requirements into the venv

With the venv active, install everything — each package lands inside `venv/`
and your system Python stays untouched:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> `requirements.txt` pins one internally consistent set — Textual 8 with
> `rich` 15, LangChain 1.x with `langchain-classic`, `ddgs` for news search.
> A resolution error here means something else is being resolved (see
> [Troubleshooting](#troubleshooting)).

### 4. Launch the agent (venv still active)

```bash
python main.py
```

`python` resolves to the venv's interpreter — exactly what step 3 just
installed. That’s it. On the very first launch the setup wizard starts automatically —
pick a provider, paste a key, and Ogeessa writes your `.env` and boots the TUI
(see below).

Other entry points:

| Command | What it does |
|---|---|
| `python main.py` | Start the TUI (runs the setup wizard if `.env` is missing/incomplete). |
| `python main.py --setup` | Force the setup wizard, even if already configured. |
| `python test_each.py` | Test every data tool against the real sources (see [Diagnostics](#diagnostics-testing-every-tool)). |

---

## First run: the setup wizard

If no valid `.env` exists, `python main.py` opens an interactive wizard
instead of the TUI:

1. **Choose a provider** — `openai`, `anthropic`, `groq`, `gemini`, `ollama`,
   or `custom`.
2. **Paste your API key** (skipped for Ollama, which needs no key).
3. The wizard saves everything to `.env` and launches the TUI.

If `.env` exists but the key for the selected provider is empty, Ogeessa
prints where to get one and how to fix it, then exits. Recover at any time
with:

```bash
python main.py --setup
```

---

## Choosing your AI provider

| Provider | Env var for the key | Default model | Get a key |
|---|---|---|---|
| **Gemini** | `GEMINI_API_KEY` | `gemini-3.1-flash-lite` | https://aistudio.google.com/apikey (free) |
| **Groq** | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | https://console.groq.com (free) |
| **OpenAI** | `OPENAI_API_KEY` | `gpt-4o-mini` | https://platform.openai.com/api-keys |
| **Anthropic** | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-latest` | https://console.anthropic.com |
| **Ollama** | *(none — runs locally)* | `llama3` (via `OLLAMA_MODEL`) | https://ollama.ai |
| **Custom** | `CUSTOM_API_KEY` + `CUSTOM_BASE_URL` + `CUSTOM_MODEL` | *(you choose)* | Any OpenAI-compatible endpoint |

- **Model overrides:** set `OPENAI_MODEL`, `ANTHROPIC_MODEL`, `GROQ_MODEL`, or
  `OLLAMA_MODEL` in `.env` to change the default model.
- **Custom endpoints:** anything that speaks the OpenAI API format works —
  LM Studio, Together AI, Mistral, DeepSeek, vLLM, or Ollama’s own OpenAI
  endpoint. `CUSTOM_PROVIDER_NAME` is just a friendly label shown in the UI.
- **Ollama:** install Ollama, pull a model (`ollama pull llama3`), and make
  sure the Ollama server is running before launching Ogeessa.
- **Switch later:** type `/config` inside the TUI — change provider, manage
  keys, add a Finnhub key, or register a custom endpoint, all without
  restarting.

---

## Manual `.env` configuration

Prefer to skip the wizard? Create a file named `.env` in the application
folder:

```ini
# which provider to use: openai | anthropic | groq | gemini | ollama | custom
LLM_PROVIDER=gemini

# the key for that provider (only the one you chose is read)
GEMINI_API_KEY=your_key_here

# optional model overrides
# OPENAI_MODEL=gpt-4o-mini
# ANTHROPIC_MODEL=claude-3-5-sonnet-latest
# GROQ_MODEL=llama-3.3-70b-versatile
# OLLAMA_MODEL=llama3

# optional: custom OpenAI-compatible endpoint (LLM_PROVIDER=custom)
# CUSTOM_PROVIDER_NAME=My local model
# CUSTOM_BASE_URL=http://localhost:1234/v1
# CUSTOM_API_KEY=not-needed-for-local
# CUSTOM_MODEL=my-model

# optional: enriches the earnings / economic calendar
# FINNHUB_API_KEY=
```

Launch again with `python main.py` and you’ll go straight into the TUI.

---

## Using the TUI

- **Ask anything** — type a ticker (`OGDC.KA`, `AAPL`) or a question
  (*“analyze AAPL”*, *“compare OGDC and PPL”*, *“what happened to HBL
  today?”*). The agent streams its analysis into the research log as it works.
- **Session counter** and **watchlist** are shown in the status bar; saved
  tickers persist to `watchlist.json`.
- **Quit** by typing `exit`, `quit`, or `q`.
- While an analysis is running, further input is queued behind a short notice —
  just wait for it to finish.

### Slash commands

| Command | Action |
|---|---|
| `/help` | Show the help panel (examples, commands, supported markets). |
| `/config` | Interactive settings menu: keys, provider switch, Finnhub, custom endpoint. |
| `/model` | Manage keys and models. |
| `/reset` | Clear the agent’s session memory. |
| `/clear` | Clear the screen. |
| `/watchlist` | Show your saved stocks. |
| `/add TICKER` | Add a stock to the watchlist. |
| `/remove X` | Remove a stock from the watchlist. |
| `/tools` | Show the active analysis tools. |
| `/cancel` | Leave config mode. |
| `exit` / `quit` / `q` | Quit Ogeessa. |

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl`+`V` | Paste from the clipboard into the input box. |
| `Ctrl`+`A` | Copy the **entire** research log to the clipboard. |
| `Ctrl`+`C` | Copy the **selected** text (select with the mouse first). |
| `Tab` | Move focus between panels. |
| `Menu` / `Shift`+`F10` | Open the context menu. |

Copy falls back to the terminal’s own clipboard (OSC-52) automatically in
environments without a desktop clipboard, such as WSL or SSH sessions.

---

## Supported markets

Tickers use Yahoo Finance suffixes:

| Market | Example |
|---|---|
| Pakistan (PSX) | `OGDC.KA` |
| United States | `AAPL` |
| India | `RELIANCE.NS` |
| United Kingdom | `HSBA.L` |
| Singapore | `D05.SI` |
| Japan | `7203.T` |

---

## The data tools

The agent reaches the real world through six tools — each one a plain function
in `tools/` that hits a live data source:

| Tool | Source | Provides |
|---|---|---|
| `get_price` | yfinance | Latest quote: price, change, volume. |
| `get_technicals` | yfinance + pandas-ta | RSI, MACD, moving averages, ATR, Bollinger Bands, support/resistance levels. |
| `get_news` | DuckDuckGo | Recent headlines for any symbol or topic. |
| `get_fundamentals` | yfinance | Valuation and quality metrics (P/E, margins, …). |
| `get_announcements` | Exchange disclosures | Company announcements for any stock, any exchange. |
| `get_economic_calendar` | Calendar data (+ optional Finnhub) | Upcoming economic events and earnings dates. |

---

## Project layout

```
ogeessa/                  # repository root — the application lives here
├── main.py               # TUI app, setup wizard, entry point (python main.py)
├── config.py             # .env loader + provider/model configuration
├── test_each.py          # standalone diagnostics for the six tools
├── requirements.txt      # pinned dependencies
├── .env.example          # copy to .env and fill in your key
├── .env                  # your keys — created by the wizard, never share it
├── README.md             # this file
├── agent/
│   └── core.py           # StockTraderAgent — the LangChain tool-calling agent
├── prompts/
│   └── persona.py        # the agent's system persona
├── tools/
│   ├── price.py          # get_price
│   ├── technical.py      # get_technicals
│   ├── news.py           # get_news
│   ├── fundamentals.py   # get_fundamentals
│   ├── announcements.py  # get_announcements
│   ├── calendar.py       # get_economic_calendar
│   ├── base.py           # shared helpers
│   └── __init__.py       # ALL_TOOLS registry
├── venv/                 # your local virtual environment (created in step 2)
└── watchlist.json        # saved tickers (created from /add)
```

---

## Diagnostics: testing every tool

Before blaming the app, ask the tools directly:

```bash
python test_each.py               # test with the default symbol
python test_each.py AAPL          # test a specific symbol
python test_each.py --no-llm      # data tools only, skip the language model
```

Every check hits the **real** data source (no mocks), so the exact broken
piece is identified immediately. Exit code `0` means all pass, `1` means at
least one failed — the failing tool is named in the output.

---

## Troubleshooting

**`venv\Scripts\activate` → "The system cannot find the path specified."**
The `venv\` folder does not exist in a fresh download — step 2 *creates* it, and
the quick start's first command assumes it already exists. Run both lines, in
this order:

```bat
python -m venv venv
venv\Scripts\activate
```

Your prompt then starts with `(venv)`. On macOS/Linux use
`python3 -m venv venv` followed by `source venv/bin/activate`.

**`'py' is not recognized as an internal or external command`.**
You don't have the python.org launcher — that is normal on Microsoft Store and
several other Python builds. Ignore `py` and use plain `python` everywhere:
`python --version`, then `python -m venv venv`.

**`python --version` reports anything older than 3.12.**
Ogeessa's dependencies need 3.12. Install it from
[python.org](https://www.python.org/downloads/) (tick **"Add python.exe to
PATH"**) and re-check.

**`error: externally-managed-environment`, packages landing in your system
Python, or `ModuleNotFoundError` right after a "successful" install.**
The venv is not active, so pip talked to the OS's Python instead. Run
`venv\Scripts\activate` (Windows) or `source venv/bin/activate`
(macOS/Linux), check for the `(venv)` prompt prefix, then repeat
`pip install -r requirements.txt` and `python main.py`.

**`pip install -r requirements.txt` fails with a resolution error
(mentions `rich` and `textual`), or the app won’t start with
`ModuleNotFoundError: No module named 'langchain_classic'` (or `'ddgs'`,
`'langchain_google_genai'`).**
`requirements.txt` pins one internally consistent set — Textual 8 with `rich` 15,
LangChain 1.x with `langchain-classic`, `ddgs` for news search. An error means
something else is being resolved: check that `python --version` reports 3.12,
that the `requirements.txt` on disk matches this repo, and that the venv is
active — then retry after `pip install --upgrade pip`.

**`ModuleNotFoundError: No module named 'langchain_classic'` (or `'ddgs'`,
`'langchain_google-genai'`).**
All three are listed in `requirements.txt`, so the install did not finish or ran
against another interpreter. Confirm the venv is active (`(venv)` in the prompt
and `python -c "import sys; print(sys.prefix)"` prints a path inside `venv\`),
then re-run `pip install -r requirements.txt`.



**“✗ No API key found for provider: …” on launch.**
Your `.env` doesn’t contain a key for the selected provider. Run
`python main.py --setup` or edit `.env` and add the key variable listed in the
[provider table](#choosing-your-ai-provider).

**Garbled emoji / `UnicodeEncodeError` on Windows.**
Run `chcp 65001` first, or use [Windows Terminal](https://aka.ms/windowsterminal)
(modern, UTF-8 by default). From PowerShell you can also launch with:

```powershell
$env:PYTHONIOENCODING="utf-8"; python main.py
```

**Market data comes back empty or fails intermittently.**
Yahoo rate-limits aggressively — wait a moment and retry. Isolate the failing
source with `python test_each.py <SYMBOL>`.

**Ollama: connection refused.**
Start the server (`ollama serve`) and make sure the model is pulled
(`ollama pull llama3`, or set `OLLAMA_MODEL` to a model you have).

**Clipboard copy shows “terminal clipboard” instead of “clipboard”.**
No desktop clipboard is available (WSL/SSH); Ogeessa falls back to OSC-52.
Some terminals don’t support it — copy from the terminal’s own selection
instead.

---

## Security notes

- **Your `.env` contains live API keys.** Never commit it, never paste it into
  an issue or screenshot, and never share your terminal scrollback if it shows
  a key.
- **Revoke and rotate keys** you suspect have been exposed — Gemini keys can
  be recreated at https://aistudio.google.com/apikey at any time.
- Ogeessa itself sends only your prompts and the tool results it fetched — no
  telemetry, no phone-home.

---

## Disclaimer

Ogeessa is a research and education tool. Nothing it prints is financial
advice, and no output should be taken as a recommendation to buy or sell any
security. You are responsible for your own trading decisions.
