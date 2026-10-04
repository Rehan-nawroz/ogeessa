"""Ogeessa configuration — single source of truth.

Everything configurable lives in .env; everything constant lives here.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# --- LLM provider -------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# Model names are overridable via .env, e.g. OPENAI_MODEL=gpt-4o
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# --- Custom OpenAI-compatible endpoint (set via TUI /config → [4]) -------
# Any provider that speaks the OpenAI API format: LM Studio, Together AI,
# Mistral, DeepSeek, Perplexity, Anyscale, local vllm, Ollama's OpenAI
# endpoint, etc. CUSTOM_PROVIDER_NAME is the human-facing label only.
CUSTOM_PROVIDER_NAME = os.getenv("CUSTOM_PROVIDER_NAME", "")
CUSTOM_BASE_URL = os.getenv("CUSTOM_BASE_URL", "")
CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY", "")
CUSTOM_MODEL = os.getenv("CUSTOM_MODEL", "")

# --- Optional data keys ---------------------------------------------------
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

PROVIDERS = ("openai", "anthropic", "groq", "gemini", "ollama", "custom")

# .env ships with a placeholder value; treat it as "missing".
_PLACEHOLDERS = {"", "your_key_here"}


def missing_key() -> str | None:
    """Return the name of the first missing config item, or None if ready."""
    if LLM_PROVIDER not in PROVIDERS:
        return (f"LLM_PROVIDER (unknown value '{LLM_PROVIDER}'; "
                f"use one of: {', '.join(PROVIDERS)})")
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY.strip().lower() in _PLACEHOLDERS:
        return "OPENAI_API_KEY"
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY.strip().lower() in _PLACEHOLDERS:
        return "ANTHROPIC_API_KEY"
    if LLM_PROVIDER == "groq" and GROQ_API_KEY.strip().lower() in _PLACEHOLDERS:
        return "GROQ_API_KEY"
    if LLM_PROVIDER == "gemini" and GEMINI_API_KEY.strip().lower() in _PLACEHOLDERS:
        return "GEMINI_API_KEY"
    if LLM_PROVIDER == "custom":
        if not CUSTOM_BASE_URL.strip():
            return "CUSTOM_BASE_URL"
        if CUSTOM_API_KEY.strip().lower() in _PLACEHOLDERS:
            return "CUSTOM_API_KEY"
        if not CUSTOM_MODEL.strip():
            return "CUSTOM_MODEL"
    return None  # ollama needs no key


# --- Data constants -------------------------------------------------------
HISTORY_PERIOD = "6mo"    # yfinance history window for technicals
NEWS_RESULTS = 5          # DuckDuckGo headlines per call
NEWS_TIME_WINDOW = "w"    # 'd' day, 'w' week, 'm' month