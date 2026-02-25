"""Configuration loading with CLI > env > file > defaults precedence."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class BackendConfig:
    name: str
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    enabled: bool = True

    @property
    def is_available(self) -> bool:
        """Backend is available if enabled and has credentials (or is local)."""
        if not self.enabled:
            return False
        if self.name == "ollama":
            return bool(self.base_url)
        return bool(self.api_key)


@dataclass
class ResearchConfig:
    enabled: bool = True
    use_web: bool = True
    cache_dir: str = ".schulpipeline/cache"
    request_delay: float = 1.5


@dataclass
class OutputConfig:
    dir: str = "./output"
    default_format: str = "pptx"
    language: str = "de"


@dataclass
class PipelineConfig:
    backends: dict[str, BackendConfig] = field(default_factory=dict)
    cascade: dict[str, list[str]] = field(default_factory=dict)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    log_level: str = "INFO"
    log_file: str = ".schulpipeline/pipeline.log"

    # --- Defaults applied when config is sparse ---

    DEFAULT_CASCADE: dict[str, list[str]] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.DEFAULT_CASCADE = {
            "intake": ["gemini", "openai"],
            "plan": ["groq", "mistral", "gemini"],
            "research": ["groq", "mistral", "gemini"],
            "synthesize": ["groq", "gemini", "mistral", "openai"],
            "artifact": ["groq", "gemini", "mistral", "openai"],
            "decompose": ["groq", "gemini", "mistral"],
            "solve": ["groq", "gemini", "mistral", "openai"],
            "classify_docs": ["groq", "gemini", "mistral"],
            "fill_template": ["groq", "gemini", "mistral", "openai"],
            "audit": ["groq", "gemini", "mistral"],
            "classify_report": ["groq", "gemini", "mistral"],
            "amendments": ["groq", "gemini", "mistral", "openai"],
            "agent_codegen": ["groq", "gemini", "mistral", "openai"],
        }

    def cascade_for(self, stage: str) -> list[str]:
        """Get cascade order for a stage, filtering to available backends."""
        order = self.cascade.get(stage, self.DEFAULT_CASCADE.get(stage, []))
        return [name for name in order if name in self.backends and self.backends[name].is_available]

    def available_backends(self) -> list[str]:
        return [name for name, cfg in self.backends.items() if cfg.is_available]


# --- Default backend presets ---

BACKEND_DEFAULTS: dict[str, dict[str, Any]] = {
    "groq": {"model": "llama-3.1-70b-versatile", "base_url": "https://api.groq.com/openai/v1"},
    "mistral": {"model": "mistral-large-latest", "base_url": "https://api.mistral.ai/v1"},
    "gemini": {"model": "gemini-2.0-flash", "base_url": "https://generativelanguage.googleapis.com"},
    "openai": {"model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1"},
    "ollama": {"model": "mistral:7b", "base_url": "http://localhost:11434"},
}

# Env var names per backend
ENV_KEY_MAP: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR} with environment variable values."""
    def replacer(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")
    return re.sub(r"\$\{(\w+)\}", replacer, str(value))


def _build_backend_config(name: str, raw: dict[str, Any] | None) -> BackendConfig:
    """Build a BackendConfig from raw YAML data + defaults + env vars."""
    defaults = BACKEND_DEFAULTS.get(name, {})
    raw = raw or {}

    api_key = raw.get("api_key", "")
    if api_key:
        api_key = _resolve_env_vars(api_key)
    elif name in ENV_KEY_MAP:
        api_key = os.environ.get(ENV_KEY_MAP[name], "")

    return BackendConfig(
        name=name,
        api_key=api_key,
        model=raw.get("model", defaults.get("model", "")),
        base_url=raw.get("base_url", defaults.get("base_url", "")),
        enabled=raw.get("enabled", True),
    )


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> PipelineConfig:
    """Load config from YAML file, apply env vars and CLI overrides."""
    raw: dict[str, Any] = {}

    # Load YAML if provided
    if path:
        config_path = Path(path)
        if config_path.exists():
            with open(config_path) as f:
                raw = yaml.safe_load(f) or {}

    # Build backend configs — from file or auto-discover from env vars
    backends: dict[str, BackendConfig] = {}
    raw_backends = raw.get("backends", {})

    # Always try all known backends
    for name in BACKEND_DEFAULTS:
        if name in raw_backends:
            backends[name] = _build_backend_config(name, raw_backends[name])
        else:
            # Auto-discover: if env var is set, enable the backend
            backends[name] = _build_backend_config(name, None)

    # Build cascade config
    cascade = raw.get("cascade", {})

    # Research config
    raw_research = raw.get("research", {})
    research = ResearchConfig(
        enabled=raw_research.get("enabled", True),
        use_web=raw_research.get("use_web", True),
        cache_dir=raw_research.get("cache_dir", ".schulpipeline/cache"),
        request_delay=raw_research.get("request_delay", 1.5),
    )

    # Output config
    raw_output = raw.get("output", {})
    output = OutputConfig(
        dir=raw_output.get("dir", "./output"),
        default_format=raw_output.get("default_format", "pptx"),
        language=raw_output.get("language", "de"),
    )

    # Logging
    raw_logging = raw.get("logging", {})

    config = PipelineConfig(
        backends=backends,
        cascade=cascade,
        research=research,
        output=output,
        log_level=raw_logging.get("level", "INFO"),
        log_file=raw_logging.get("file", ".schulpipeline/pipeline.log"),
    )

    # Apply CLI overrides
    if overrides:
        if "log_level" in overrides:
            config.log_level = overrides["log_level"]
        if "format" in overrides:
            config.output.default_format = overrides["format"]

    return config
