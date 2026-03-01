"""Google Gemini backend — uses the Generative Language API directly."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import requests

from .base import BackendError, LLMResponse, RateLimitError


@dataclass
class GeminiBackend:
    """Converts OpenAI-style messages to Gemini format.

    :param messages: List of dictionaries representing the conversation history.
    :type messages: list[dict[str, Any]]
    :return: Tuple containing the converted message and a list of formatted messages.
    :rtype: tuple[str, list[dict]]
    """

    name: str = "gemini"
    api_key: str = ""
    model: str = "gemini-2.5-flash"
    base_url: str = "https://generativelanguage.googleapis.com"
    is_free: bool = True
    supports_vision: bool = True
    max_context: int = 1_048_576

    def _convert_messages(self, messages: list[dict[str, Any]]) -> tuple[str, list[dict]]:
        """Convert OpenAI-style messages to Gemini format.

        Returns (system_text, contents) where contents is Gemini's format.
        """
        system = ""
        contents = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system = content if isinstance(content, str) else str(content)
                continue

            gemini_role = "model" if role == "assistant" else "user"

            if isinstance(content, str):
                contents.append(
                    {
                        "role": gemini_role,
                        "parts": [{"text": content}],
                    }
                )
            elif isinstance(content, list):
                # Multimodal content (text + images)
                parts = []
                for item in content:
                    if isinstance(item, str):
                        parts.append({"text": item})
                    elif isinstance(item, dict):
                        if item.get("type") == "text":
                            parts.append({"text": item["text"]})
                        elif item.get("type") == "image_url":
                            url = item["image_url"]["url"]
                            if url.startswith("data:"):
                                # data:image/jpeg;base64,... -> inline_data
                                mime, _, b64 = url.partition(";base64,")
                                mime = mime.replace("data:", "")
                                parts.append(
                                    {
                                        "inlineData": {
                                            "mimeType": mime,
                                            "data": b64,
                                        }
                                    }
                                )
                contents.append({"role": gemini_role, "parts": parts})

        return system, contents

    def _sync_generate(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
    ) -> LLMResponse:
        """Sends a request to the language model API to generate a response.

        :param messages: List of message dictionaries.
        :type messages: list[dict[str, Any]]
        :param temperature: Temperature value for controlling randomness in output.
        :type temperature: float
        :param max_tokens: Maximum number of tokens in the generated response.
        :type max_tokens: int
        :param response_format: Optional dictionary specifying the format of the response.
        :type response_format: dict | None
        :return: The generated response from the language model.
        :rtype: LLMResponse
        """
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
        """Asynchronously completes a conversation with the language model.

        :param messages: List of message dictionaries.
        :type messages: list[dict[str, Any]]
        :param temperature: Sampling temperature for text generation.
        :type temperature: float
        :param max_tokens: Maximum number of tokens to generate.
        :type max_tokens: int
        :param response_format: Optional dictionary specifying the format of the response.
        :type response_format: dict | None
        :return: The generated LLMResponse object.
        :rtype: LLMResponse
        """
        return await asyncio.to_thread(self._sync_generate, messages, temperature, max_tokens, response_format)

    async def complete_vision(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Completes a vision task using the provided messages.

        :param messages: List of dictionaries containing message data.
        :type messages: list[dict[str, Any]]
        :param temperature: Temperature value for controlling randomness in output.
        :type temperature: float
        :param max_tokens: Maximum number of tokens to generate.
        :type max_tokens: int
        :return: Response from the language model.
        :rtype: LLMResponse
        """
        return await self.complete(messages, temperature, max_tokens)

    async def close(self):
        """Closes the connection to the Gemini API.

        :raises ConnectionError: If the connection cannot be closed.
        """
        pass


def create_gemini(api_key: str, model: str = "gemini-2.5-flash") -> GeminiBackend:
    """Create a new Gemini backend instance.

    :param api_key: API key for authentication.
    :type api_key: str
    :param model: Model to use, defaults to "gemini-2.5-flash".
    :type model: str
    :return: A new GeminiBackend instance.
    :rtype: GeminiBackend
    """
    return GeminiBackend(api_key=api_key, model=model)
