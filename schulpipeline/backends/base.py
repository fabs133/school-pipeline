"""Backend protocol — all LLM adapters implement this interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    """Response from a language model completion call.

    :param content: The generated text.
    :param model: Model identifier used for generation.
    :param tokens_in: Number of input tokens consumed.
    :param tokens_out: Number of output tokens generated.
    :param cost_usd: Estimated cost in USD.
    :param latency_ms: Round-trip latency in milliseconds.
    :param backend_name: Name of the backend that served the request.
    :param raw: Raw response payload for debugging.
    """

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
        """Initialize a backend error.

        :param message: Human-readable error description.
        :param backend: Name of the backend that failed.
        :param retryable: Whether the caller should retry the request.
        """
        super().__init__(message)
        self.backend = backend
        self.retryable = retryable


class RateLimitError(BackendError):
    """Rate limit hit — cascade to next backend."""

    def __init__(self, backend: str, retry_after: float = 60.0):
        """Initialize a rate-limit error.

        :param backend: Name of the backend that hit the rate limit.
        :param retry_after: Seconds to wait before retrying.
        """
        super().__init__(f"Rate limited on {backend}", backend, retryable=True)
        self.retry_after = retry_after


@runtime_checkable
class Backend(Protocol):
    """Protocol that all LLM backends must implement.

    :param name: Backend identifier (e.g. ``"groq"``, ``"gemini"``).
    :param is_free: Whether this backend has a free tier.
    :param supports_vision: Whether the backend accepts image inputs.
    :param max_context: Maximum context window in tokens.
    """

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
    ) -> LLMResponse:
        """Generate a text completion.

        :param messages: Conversation messages in OpenAI format.
        :param temperature: Sampling temperature (0.0–1.0).
        :param max_tokens: Maximum tokens to generate.
        :param response_format: Optional JSON schema for structured output.
        :return: The model's response.
        """
        ...

    async def complete_vision(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a completion from messages that include images.

        :param messages: Conversation messages with image content parts.
        :param temperature: Sampling temperature (0.0–1.0).
        :param max_tokens: Maximum tokens to generate.
        :return: The model's response.
        """
        ...
