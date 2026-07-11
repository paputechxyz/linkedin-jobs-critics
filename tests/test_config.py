import json
import os

import pytest

from critics import config


def test_read_go_config_present(monkeypatch, tmp_path):
    cfg = {"base_url": "https://api.z.ai/api/paas/v4", "api_key": "sk-test", "model": "glm-4.5"}
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    (tmp_path / "config.json").write_text(json.dumps(cfg))

    assert config._read_go_config() == cfg


def test_read_go_config_missing_key_is_none(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    (tmp_path / "config.json").write_text(json.dumps({"base_url": "x", "model": "y"}))
    assert config._read_go_config() is None


def test_load_llm_from_go_config(monkeypatch, tmp_path):
    cfg = {"base_url": "https://api.z.ai/api/paas/v4", "api_key": "sk-test", "model": "glm-4.5"}
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    (tmp_path / "config.json").write_text(json.dumps(cfg))

    llm = config.load_llm()
    assert llm.model == "glm-4.5"


def test_load_llm_env_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)  # no config.json present
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.delenv("LJ_LLM_API_KEY", raising=False)
    monkeypatch.delenv("LJ_LLM_MODEL", raising=False)

    llm = config.load_llm()
    assert llm.model == "gpt-4o-mini"


def test_load_llm_raises_when_unconfigured(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    for var in ("OPENAI_API_KEY", "LJ_LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(config.NoProviderError):
        config.load_llm()


# --- LangSmith tracing setup ---


def _clear_tracing_env(monkeypatch):
    for var in (
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING",
        "LANGSMITH_PROJECT",
        "LANGCHAIN_PROJECT",
    ):
        monkeypatch.delenv(var, raising=False)


def test_setup_tracing_off_when_no_key(monkeypatch):
    _clear_tracing_env(monkeypatch)
    assert config.setup_tracing() is False
    assert os.environ.get("LANGSMITH_TRACING") is None


def test_setup_tracing_on_fills_defaults(monkeypatch):
    _clear_tracing_env(monkeypatch)
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-123")

    assert config.setup_tracing() is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_PROJECT"] == "linkedin-jobs-critics"
    # back-compat alias for older langchain releases
    assert os.environ["LANGCHAIN_API_KEY"] == "ls-123"


def test_setup_tracing_respects_explicit_project(monkeypatch):
    _clear_tracing_env(monkeypatch)
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-123")
    monkeypatch.setenv("LANGSMITH_PROJECT", "custom-prod")

    config.setup_tracing()
    assert os.environ["LANGSMITH_PROJECT"] == "custom-prod"


def test_setup_tracing_accepts_legacy_key_alias(monkeypatch):
    _clear_tracing_env(monkeypatch)
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls-legacy")

    assert config.setup_tracing() is True
