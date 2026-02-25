"""Tests for config loading and backend discovery."""

import os
from pathlib import Path

from schulpipeline.config import load_config, BackendConfig, PipelineConfig


def test_load_empty_config():
    """Config with no file uses defaults + env autodiscovery."""
    config = load_config(path=None)
    assert isinstance(config, PipelineConfig)
    assert config.output.language == "de"
    assert config.output.default_format == "pptx"


def test_backend_autodiscovery_from_env(monkeypatch):
    """Backends are auto-discovered from environment variables."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key-123")
    config = load_config(path=None)
    assert config.backends["groq"].is_available
    assert config.backends["groq"].api_key == "test-key-123"


def test_backend_unavailable_without_key():
    """Backends without API keys are not available."""
    cfg = BackendConfig(name="groq", api_key="", enabled=True)
    assert not cfg.is_available


def test_backend_disabled():
    """Disabled backends are not available even with keys."""
    cfg = BackendConfig(name="groq", api_key="test-key", enabled=False)
    assert not cfg.is_available


def test_cascade_filters_unavailable(mock_config):
    """Cascade only returns available backends."""
    cascade = mock_config.cascade_for("plan")
    assert cascade == ["mock"]


def test_cascade_default_for_unknown_stage(mock_config):
    """Unknown stages return empty cascade."""
    cascade = mock_config.cascade_for("nonexistent")
    assert cascade == []


def test_config_overrides():
    """CLI overrides take precedence."""
    config = load_config(path=None, overrides={"log_level": "DEBUG", "format": "docx"})
    assert config.log_level == "DEBUG"
    assert config.output.default_format == "docx"
