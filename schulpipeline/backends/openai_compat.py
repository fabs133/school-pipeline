"""OpenAI-compatible backend — covers OpenAI, Groq, and Mistral."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import requests

from .base import BackendError, LLMResponse, RateLimitError


@dataclass
class OpenAICompatibleBackend:
    """Adapter for any OpenAI-compatible chat completions API."""

    name: str
    api_key: str
    model: str
    base_url: str
    is_free: bool = True
    supports_vision: bool = False
    max_context: int = 8192

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _sync_complete(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
    ) -> LLMResponse:
        t0 = time.monotonic()
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            body["response_format"] = response_format

        try:
            resp = requests.post(url, json=body, headers=self._headers(), timeout=120)
        except requests.Timeout:
            raise BackendError(f"Timeout calling {self.name}", self.name, retryable=True)
        except requests.ConnectionError:
            raise BackendError(f"Connection failed to {self.name}", self.name, retryable=False)

        latency = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("retry-after", "60"))
            raise RateLimitError(self.name, retry_after)
        if resp.status_code >= 400:
            raise BackendError(
                f"{self.name} returned {resp.status_code}: {resp.text[:200]}",
                self.name,
                retryable=resp.status_code >= 500,
            )

        data = resp.json()
        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})

        return LLMResponse(
            content=choice.get("content", ""),
            model=data.get("model", self.model),
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            cost_usd=0.0 if self.is_free else self._estimate_cost(usage),
            latency_ms=latency,
            backend_name=self.name,
            raw=data,
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        return await asyncio.to_thread(
            self._sync_complete, messages, temperature, max_tokens, response_format
        )

    async def complete_vision(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        if not self.supports_vision:
            raise BackendError(f"{self.name} does not support vision", self.name)
        return await self.complete(messages, temperature, max_tokens)

    def _estimate_cost(self, usage: dict) -> float:
        """Rough cost estimate for paid backends."""
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        return (tokens_in * 0.15 + tokens_out * 0.6) / 1_000_000

    async def close(self):
        pass


def create_groq(api_key: str, model: str = "llama-3.3-70b-versatile") -> OpenAICompatibleBackend:
    return OpenAICompatibleBackend(
        name="groq",
        api_key=api_key,
        model=model,
        base_url="https://api.groq.com/openai/v1",
        is_free=True,
        supports_vision=False,
        max_context=131_072,
    )


def create_mistral(api_key: str, model: str = "mistral-large-latest") -> OpenAICompatibleBackend:
    return OpenAICompatibleBackend(
        name="mistral",
        api_key=api_key,
        model=model,
        base_url="https://api.mistral.ai/v1",
        is_free=True,
        supports_vision=False,
        max_context=32_768,
    )


def create_openai(api_key: str, model: str = "gpt-4o-mini") -> OpenAICompatibleBackend:
    return OpenAICompatibleBackend(
        name="openai",
        api_key=api_key,
        model=model,
        base_url="https://api.openai.com/v1",
        is_free=False,
        supports_vision=True,
        max_context=128_000,
    )


def create_ollama(
    api_key: str = "",
    model: str = "mistral:7b",
    base_url: str = "http://localhost:11434",
) -> OpenAICompatibleBackend:
    """Create an Ollama backend. api_key is ignored (Ollama has no auth)."""
    return OpenAICompatibleBackend(
        name="ollama",
        api_key="ollama",
        model=model,
        base_url=f"{base_url.rstrip('/')}/v1",
        is_free=True,
        supports_vision=False,
        max_context=32_768,
    )
