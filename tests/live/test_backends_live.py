"""Live backend connectivity tests — verifies real API calls work."""

import pytest

from schulpipeline.backends.base import LLMResponse


@pytest.mark.live
@pytest.mark.asyncio
async def test_groq_single_completion(live_router, require_groq):
    """Groq responds with valid LLMResponse."""
    result = await live_router.complete(
        stage="plan",
        messages=[
            {"role": "system", "content": "Antworte kurz auf Deutsch."},
            {"role": "user", "content": "Was ist 2+2?"},
        ],
        temperature=0.0,
        max_tokens=50,
    )
    assert isinstance(result, LLMResponse)
    assert len(result.content) > 0
    assert result.tokens_in > 0
    assert result.tokens_out > 0
    assert result.backend_name == "groq"


@pytest.mark.live
@pytest.mark.asyncio
async def test_gemini_single_completion(live_router, require_gemini):
    """Gemini responds with valid LLMResponse."""
    result = await live_router.complete(
        stage="intake",  # intake cascades to gemini first
        messages=[
            {"role": "system", "content": "Antworte kurz auf Deutsch."},
            {"role": "user", "content": "Was ist die Hauptstadt von Deutschland?"},
        ],
        temperature=0.0,
        max_tokens=50,
    )
    assert isinstance(result, LLMResponse)
    assert len(result.content) > 0
    assert "Berlin" in result.content


@pytest.mark.live
@pytest.mark.asyncio
async def test_groq_json_response(live_router, require_groq):
    """Groq returns valid JSON when response_format is set."""
    result = await live_router.complete(
        stage="plan",
        messages=[
            {"role": "system", "content": "Antworte mit JSON: {\"antwort\": \"...\"}"},
            {"role": "user", "content": "Was ist die Farbe des Himmels?"},
        ],
        temperature=0.0,
        max_tokens=100,
        response_format={"type": "json_object"},
    )
    import json
    data = json.loads(result.content)
    assert isinstance(data, dict)


@pytest.mark.live
@pytest.mark.asyncio
async def test_router_reports_available_backends(live_router):
    """Router discovers at least one backend from env."""
    available = live_router.available_backends
    assert len(available) >= 1, f"No backends discovered. Check .env file."
