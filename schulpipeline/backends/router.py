"""Backend router — cascade with rate limit tracking and dynamic discovery."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import BackendConfig, PipelineConfig
from .base import Backend, BackendError, LLMResponse, RateLimitError
from .gemini import GeminiBackend, create_gemini
from .openai_compat import (
    OpenAICompatibleBackend,
    create_groq,
    create_mistral,
    create_openai,
)

logger = logging.getLogger("schulpipeline.router")


# Factory registry — maps backend name to constructor
BACKEND_FACTORIES: dict[str, Any] = {
    "groq": lambda cfg: create_groq(cfg.api_key, cfg.model),
    "mistral": lambda cfg: create_mistral(cfg.api_key, cfg.model),
    "gemini": lambda cfg: create_gemini(cfg.api_key, cfg.model),
    "openai": lambda cfg: create_openai(cfg.api_key, cfg.model),
}


@dataclass
class BackendRouter:
    """Routes LLM calls through cascade of backends with rate limit awareness."""

    config: PipelineConfig
    _backends: dict[str, Backend] = field(default_factory=dict, init=False)
    _cooldowns: dict[str, float] = field(default_factory=dict, init=False)  # name -> cooldown_until
    _call_counts: dict[str, int] = field(default_factory=dict, init=False)
    _total_cost: float = field(default=0.0, init=False)

    def __post_init__(self):
        self._discover_backends()

    def _discover_backends(self) -> None:
        """Instantiate backends from config — only those that are available."""
        for name, cfg in self.config.backends.items():
            if not cfg.is_available:
                logger.debug(f"Backend '{name}' not available (disabled or no credentials)")
                continue
            if name not in BACKEND_FACTORIES:
                logger.warning(f"Unknown backend '{name}' — skipping")
                continue

            try:
                backend = BACKEND_FACTORIES[name](cfg)
                self._backends[name] = backend
                self._call_counts[name] = 0
                logger.info(f"Backend '{name}' registered (model={cfg.model})")
            except Exception as e:
                logger.error(f"Failed to create backend '{name}': {e}")

        if not self._backends:
            logger.error("No backends available! Check config and API keys.")

    @property
    def available_backends(self) -> list[str]:
        return list(self._backends.keys())

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def _is_cooled_down(self, name: str) -> bool:
        """Check if a backend is still in rate-limit cooldown."""
        if name not in self._cooldowns:
            return False
        if time.time() >= self._cooldowns[name]:
            del self._cooldowns[name]
            return False
        return True

    async def complete(
        self,
        stage: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
        require_vision: bool = False,
    ) -> LLMResponse:
        """Route a completion through the cascade for the given stage."""
        cascade = self.config.cascade_for(stage)

        if not cascade:
            raise BackendError(
                f"No backends available for stage '{stage}'. "
                f"Available: {self.available_backends}",
                backend="router",
            )

        errors: list[str] = []

        for name in cascade:
            backend = self._backends.get(name)
            if not backend:
                continue

            # Skip if vision required but not supported
            if require_vision and not backend.supports_vision:
                logger.debug(f"Skipping {name} for {stage}: no vision support")
                continue

            # Skip if in cooldown
            if self._is_cooled_down(name):
                remaining = self._cooldowns[name] - time.time()
                logger.debug(f"Skipping {name}: rate limited for {remaining:.0f}s more")
                continue

            try:
                logger.info(f"[{stage}] Trying {name} (model={backend.model if hasattr(backend, 'model') else '?'})")

                if require_vision:
                    result = await backend.complete_vision(messages, temperature, max_tokens)
                else:
                    result = await backend.complete(messages, temperature, max_tokens, response_format)

                self._call_counts[name] = self._call_counts.get(name, 0) + 1
                self._total_cost += result.cost_usd

                logger.info(
                    f"[{stage}] {name} succeeded: "
                    f"{result.tokens_in}+{result.tokens_out} tokens, "
                    f"{result.latency_ms}ms, ${result.cost_usd:.4f}"
                )
                return result

            except RateLimitError as e:
                self._cooldowns[name] = time.time() + e.retry_after
                logger.warning(f"[{stage}] {name} rate limited, cooldown {e.retry_after}s")
                errors.append(f"{name}: rate limited")

            except BackendError as e:
                logger.warning(f"[{stage}] {name} failed: {e}")
                errors.append(f"{name}: {e}")

                if not e.retryable:
                    continue

            except Exception as e:
                logger.error(f"[{stage}] {name} unexpected error: {e}")
                errors.append(f"{name}: {e}")

        raise BackendError(
            f"All backends failed for stage '{stage}': {'; '.join(errors)}",
            backend="router",
        )

    def stats(self) -> dict[str, Any]:
        """Return usage statistics."""
        return {
            "backends_available": self.available_backends,
            "call_counts": dict(self._call_counts),
            "total_cost_usd": self._total_cost,
            "active_cooldowns": {
                name: self._cooldowns[name] - time.time()
                for name in self._cooldowns
                if time.time() < self._cooldowns[name]
            },
        }

    async def close(self):
        """Clean up all backend HTTP clients."""
        for backend in self._backends.values():
            if hasattr(backend, "close"):
                await backend.close()
