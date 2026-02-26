"""Live test fixtures — real API backends, requires .env with keys."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from schulpipeline.backends.router import BackendRouter
from schulpipeline.config import PipelineConfig, load_config


def _load_env():
    """Load .env file into os.environ (minimal dotenv replacement)."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_env()


def _skip_if_no_key(env_var: str, label: str):
    key = os.environ.get(env_var, "")
    if not key:
        pytest.skip(f"No {label} key ({env_var} not set)")


@pytest.fixture
def live_config(tmp_path) -> PipelineConfig:
    """Load real config with API keys from environment."""
    config = load_config(path="config.yaml")
    config.output.dir = str(tmp_path)
    config.research.use_web = False  # don't hit DDG during tests
    return config


@pytest.fixture
def live_router(live_config) -> BackendRouter:
    """Create a real router with discovered backends."""
    return BackendRouter(config=live_config)


@pytest.fixture
def require_groq():
    _skip_if_no_key("GROQ_API_KEY", "Groq")


@pytest.fixture
def require_gemini():
    _skip_if_no_key("GEMINI_API_KEY", "Gemini")
