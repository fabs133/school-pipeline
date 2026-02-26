"""Tests for backend router — cascade logic and error handling."""

import time

import pytest

from schulpipeline.backends.base import BackendError, LLMResponse
from schulpipeline.backends.router import BackendRouter


@pytest.mark.asyncio
async def test_router_completes_with_mock(mock_router):
    """Router successfully routes to mock backend."""
    result = await mock_router.complete(
        stage="plan",
        messages=[{"role": "user", "content": "test"}],
    )
    assert isinstance(result, LLMResponse)
    assert result.backend_name == "mock"


@pytest.mark.asyncio
async def test_router_tracks_call_count(mock_router):
    """Router increments call count."""
    await mock_router.complete(stage="plan", messages=[{"role": "user", "content": "test"}])
    await mock_router.complete(stage="plan", messages=[{"role": "user", "content": "test2"}])
    assert mock_router._call_counts["mock"] == 2


@pytest.mark.asyncio
async def test_router_no_backends_raises(mock_config):
    """Router raises when no backends are available for a stage."""
    mock_config.cascade = {"plan": ["nonexistent"]}
    router = BackendRouter.__new__(BackendRouter)
    router.config = mock_config
    router._backends = {}
    router._cooldowns = {}
    router._call_counts = {}
    router._total_cost = 0.0

    with pytest.raises(BackendError, match="No backends available"):
        await router.complete(stage="plan", messages=[])


@pytest.mark.asyncio
async def test_router_skips_cooled_down_backend(mock_router):
    """Router skips backends in cooldown."""
    mock_router._cooldowns["mock"] = time.time() + 3600  # cooled down for an hour

    with pytest.raises(BackendError, match="All backends failed"):
        await mock_router.complete(stage="plan", messages=[{"role": "user", "content": "test"}])


@pytest.mark.asyncio
async def test_router_cooldown_expires(mock_router):
    """Router uses backend after cooldown expires."""
    mock_router._cooldowns["mock"] = time.time() - 1  # already expired

    result = await mock_router.complete(
        stage="plan",
        messages=[{"role": "user", "content": "test"}],
    )
    assert result.backend_name == "mock"


def test_router_stats(mock_router):
    """Stats returns expected structure."""
    stats = mock_router.stats()
    assert "backends_available" in stats
    assert "call_counts" in stats
    assert "total_cost_usd" in stats
