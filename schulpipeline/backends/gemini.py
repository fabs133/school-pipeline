"""Google Gemini backend — uses the Generative Language API directly."""

from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .base import BackendError, LLMResponse, RateLimitError


@dataclass
class GeminiBackend:
    name: str = "gemini"
    api_key: str = ""
    model: str = "gemini-2.0-flash"
    base_url: str = "https://generativelanguage.googleapis.com"
    is_free: bool = True
    supports_vision: bool = True
    max_context: int = 1_048_576

    def _sync_generate(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
    ) -> LLMResponse:
        t0 = time.monotonic()

        system, contents = self._convert_messages(messages)

        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        if response_format and response_format.get("type") == "json_object":
            body["generationConfig"]["responseMimeType"] = "application/json"

        try:
            resp = requests.post(url, json=body, params={"key": self.api_key}, timeout=120)
        except requests.Timeout:
            raise BackendError("Timeout calling Gemini", self.name, retryable=True)
        except requests.ConnectionError:
            raise BackendError("Connection failed to Gemini", self.name, retryable=False)

        latency = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 429:
            raise RateLimitError(self.name, retry_after=60.0)
        if resp.status_code >= 400:
            raise BackendError(
                f"Gemini returned {resp.status_code}: {resp.text[:200]}",
                self.name,
                retryable=resp.status_code >= 500,
            )

        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise BackendError("Gemini returned no candidates", self.name)

        parts = candidates[0].get("content", {}).get("parts", [])
        content = "".join(p.get("text", "") for p in parts)

        usage = data.get("usageMetadata", {})

        return LLMResponse(
            content=content,
            model=self.model,
            tokens_in=usage.get("promptTokenCount", 0),
            tokens_out=usage.get("candidatesTokenCount", 0),
            cost_usd=0.0,
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
            self._sync_generate, messages, temperature, max_tokens, response_format
        )

    async def complete_vision(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return await self.complete(messages, temperature, max_tokens)

    async def close(self):
        pass


def create_gemini(api_key: str, model: str = "gemini-2.0-flash") -> GeminiBackend:
    return GeminiBackend(api_key=api_key, model=model)
