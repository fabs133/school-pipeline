"""Tests for backend base types and factory functions."""

from schulpipeline.backends.base import Backend, BackendError, LLMResponse, RateLimitError
from schulpipeline.backends.gemini import GeminiBackend, create_gemini
from schulpipeline.backends.openai_compat import (
    OpenAICompatibleBackend,
    create_groq,
    create_mistral,
    create_ollama,
    create_openai,
)
from schulpipeline.backends.router import BACKEND_FACTORIES

# --- LLMResponse ---

def test_llm_response_defaults():
    r = LLMResponse(content="hello", model="test")
    assert r.content == "hello"
    assert r.tokens_in == 0
    assert r.cost_usd == 0.0
    assert r.backend_name == ""


def test_llm_response_full():
    r = LLMResponse(
        content="result",
        model="gpt-4",
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.01,
        latency_ms=500,
        backend_name="openai",
    )
    assert r.tokens_in == 100
    assert r.tokens_out == 50
    assert r.cost_usd == 0.01
    assert r.latency_ms == 500


# --- Error hierarchy ---

def test_backend_error_properties():
    e = BackendError("test failure", "groq", retryable=True)
    assert str(e) == "test failure"
    assert e.backend == "groq"
    assert e.retryable is True


def test_backend_error_not_retryable():
    e = BackendError("permanent", "gemini", retryable=False)
    assert e.retryable is False


def test_rate_limit_error_inherits():
    e = RateLimitError("groq", retry_after=30.0)
    assert isinstance(e, BackendError)
    assert e.retryable is True
    assert e.retry_after == 30.0
    assert e.backend == "groq"


# --- Backend Protocol ---

def test_mock_backend_satisfies_protocol(mock_backend):
    assert isinstance(mock_backend, Backend)


# --- Factory functions ---

def test_create_groq():
    b = create_groq("test-key")
    assert b.name == "groq"
    assert b.api_key == "test-key"
    assert b.is_free is True
    assert b.supports_vision is False
    assert "groq.com" in b.base_url


def test_create_groq_custom_model():
    b = create_groq("key", model="llama-3.2-90b")
    assert b.model == "llama-3.2-90b"


def test_create_mistral():
    b = create_mistral("test-key")
    assert b.name == "mistral"
    assert b.is_free is True
    assert "mistral.ai" in b.base_url


def test_create_openai():
    b = create_openai("sk-test")
    assert b.name == "openai"
    assert b.is_free is False
    assert b.supports_vision is True


def test_create_gemini():
    b = create_gemini("ai-test")
    assert isinstance(b, GeminiBackend)
    assert b.name == "gemini"
    assert b.is_free is True
    assert b.supports_vision is True
    assert b.max_context == 1_048_576


# --- OpenAI-compatible headers ---

def test_openai_compat_headers():
    b = OpenAICompatibleBackend(
        name="test", api_key="sk-abc123", model="m", base_url="http://x"
    )
    h = b._headers()
    assert h["Authorization"] == "Bearer sk-abc123"
    assert h["Content-Type"] == "application/json"


# --- Cost estimation ---

def test_openai_compat_cost_estimation():
    b = create_openai("key")
    cost = b._estimate_cost({"prompt_tokens": 1000, "completion_tokens": 500})
    assert cost > 0
    # (1000 * 0.15 + 500 * 0.6) / 1_000_000 = 0.00045
    assert abs(cost - 0.00045) < 0.0001


# --- Ollama backend ---

def test_create_ollama():
    b = create_ollama()
    assert b.name == "ollama"
    assert b.api_key == "ollama"
    assert b.is_free is True
    assert b.supports_vision is False
    assert "/v1" in b.base_url
    assert b.model == "mistral:7b"


def test_create_ollama_custom():
    b = create_ollama(model="llama3:8b", base_url="http://myhost:11434")
    assert b.model == "llama3:8b"
    assert b.base_url == "http://myhost:11434/v1"


def test_ollama_in_backend_factories():
    assert "ollama" in BACKEND_FACTORIES
