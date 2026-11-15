"""Paths and settings. Everything is relative to the repo root (no absolute paths)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
EVAL_DIR = ROOT / "tests" / "eval_set"
RXNAV_CACHE = DATA / "rxnav_cache.json"

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
RXNAV_TIMEOUT = float(os.environ.get("RXNAV_TIMEOUT", "8"))
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "60"))
# Defaults verified against the providers' model docs (Nov 2026). Override with env vars or Streamlit secrets.
#   Anthropic: https://platform.claude.com/docs/en/models/overview  (claude-sonnet-5-5: vision, fast)
#   OpenAI:    https://developers.openai.com/api/docs/models/gpt-6-luna  (gpt-6-luna: text + image input)
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"
DEFAULT_OPENAI_MODEL = "gpt-6-luna"

# OpenAI reasoning effort for this app's simple read/rewrite calls. Override with OPENAI_REASONING_EFFORT (or "" to omit).
DEFAULT_OPENAI_EFFORT = "low"
ACB_HIGH = 3          # project threshold: total ACB >= 3 shown as "high"


def anthropic_model() -> str:
    return secret("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL


def openai_model() -> str:
    return secret("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL


def openai_effort() -> str:
    v = secret("OPENAI_REASONING_EFFORT")
    return DEFAULT_OPENAI_EFFORT if v is None else v.strip()


def secret(name: str) -> str | None:
    """API key from environment, then Streamlit secrets (if running inside Streamlit)."""
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        return None
