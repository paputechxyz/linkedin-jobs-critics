"""LLM provider config — reuses the Go CLI's ~/.linkedin-jobs/config.json.

Mirrors the Go CLI's Resolve() for the config-file and env layers so there is a
single source of truth for the API key (no second provider setup).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_openai import ChatOpenAI

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TRACING_PROJECT = "linkedin-jobs-critics"


class NoProviderError(RuntimeError):
    """Raised when no LLM provider is configured."""


def config_dir() -> Path:
    return Path(os.environ.get("LJ_CONFIG_DIR") or (Path.home() / ".linkedin-jobs"))


def _read_go_config() -> dict | None:
    path = config_dir() / "config.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not data.get("api_key"):
        return None
    return data


def load_llm() -> ChatOpenAI:
    """Resolve a ChatOpenAI from the Go CLI config.json, else env.

    Priority: ~/.linkedin-jobs/config.json → LJ_LLM_*/OPENAI_* env.
    """
    cfg = _read_go_config()
    if cfg is not None:
        return ChatOpenAI(
            model=cfg.get("model") or DEFAULT_MODEL,
            base_url=cfg.get("base_url") or DEFAULT_BASE_URL,
            api_key=cfg["api_key"],
        )

    api_key = os.environ.get("LJ_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        base_url = (
            os.environ.get("LJ_LLM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or DEFAULT_BASE_URL
        )
        model = os.environ.get("LJ_LLM_MODEL") or DEFAULT_MODEL
        return ChatOpenAI(model=model, base_url=base_url, api_key=api_key)

    raise NoProviderError(
        "no LLM provider configured: run `linkedin-jobs config llm`, "
        "or set OPENAI_API_KEY / LJ_LLM_API_KEY"
    )


def setup_tracing() -> bool:
    """Enable LangSmith tracing when an API key is present.

    LangChain/LangGraph auto-trace once LANGSMITH_API_KEY is set; this helper
    just fills in sane defaults (project name, tracing on) so a user only has
    to export the key. Idempotent — uses setdefault so explicit env vars win.

    Returns True when tracing will be active, False when no key is configured
    (the app runs normally, just untraced).
    """
    key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    if not key:
        return False
    os.environ.setdefault("LANGSMITH_API_KEY", key)
    os.environ.setdefault("LANGCHAIN_API_KEY", key)  # back-compat for older langchain
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", DEFAULT_TRACING_PROJECT)
    os.environ.setdefault("LANGCHAIN_PROJECT", DEFAULT_TRACING_PROJECT)
    return True
