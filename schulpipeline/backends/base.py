"""Backend protocol — all LLM adapters implement this interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    backend_name: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class BackendError(Exception):
    """Base error for backend failures."""

    def __init__(self, message: str, backend: str, retryable: bool = False):
        super().__init__(message)
        self.backend = backend
        self.retryable = retryable


class RateLimitError(BackendError):
    """Rate limit hit — cascade to next backend."""

    def __init__(self, backend: str, retry_after: float = 60.0):
        super().__init__(f"Rate limited on {backend}", backend, retryable=True)
        self.retry_after = retry_after


@runtime_checkable
class Backend(Protocol):
    name: str
    is_free: bool
    supports_vision: bool
    max_context: int

    async def complete(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse: ...

    async def complete_vision(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...
