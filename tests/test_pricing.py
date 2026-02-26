"""Tests for cost estimation and pricing."""

from schulpipeline.backends.pricing import (
    BACKEND_PRICING,
    STAGE_TOKEN_ESTIMATES,
    estimate_pipeline_cost,
    estimate_stage_cost,
)


def test_free_backend_cost_is_zero():
    """Free backends (groq, gemini, mistral, ollama) have zero cost."""
    for backend in ("groq", "gemini", "mistral", "ollama"):
        cost = estimate_stage_cost("synthesize", backend)
        assert cost == 0.0, f"{backend} should be free"


def test_openai_cost_positive():
    """OpenAI backend has non-zero cost."""
    cost = estimate_stage_cost("synthesize", "openai")
    assert cost > 0.0


def test_artifact_cost_zero():
    """Artifact stage has no LLM cost on any backend."""
    for backend in BACKEND_PRICING:
        cost = estimate_stage_cost("artifact", backend)
        assert cost == 0.0


def test_pipeline_cost_all_free():
    """Pipeline with all-free backends costs nothing."""
    stages = ["intake", "plan", "research", "synthesize", "artifact"]
    cascade = {s: ["groq"] for s in stages}
    total, breakdown = estimate_pipeline_cost(stages, cascade)
    assert total == 0.0
    assert len(breakdown) == 5


def test_pipeline_cost_with_openai():
    """Pipeline with OpenAI in cascade has positive cost."""
    stages = ["intake", "plan", "research", "synthesize", "artifact"]
    cascade = {s: ["openai"] for s in stages}
    total, breakdown = estimate_pipeline_cost(stages, cascade)
    assert total > 0.0
    assert breakdown["artifact"]["cost_usd"] == 0.0


def test_pipeline_cost_mixed_cascade():
    """Mixed cascade uses first backend for estimate."""
    stages = ["intake", "plan"]
    cascade = {"intake": ["openai", "groq"], "plan": ["groq", "openai"]}
    total, breakdown = estimate_pipeline_cost(stages, cascade)
    assert breakdown["intake"]["cost_usd"] > 0.0
    assert breakdown["plan"]["cost_usd"] == 0.0


def test_unknown_stage_uses_defaults():
    """Unknown stage gets default token estimate."""
    cost = estimate_stage_cost("unknown_stage", "openai")
    assert cost > 0.0


def test_stage_token_estimates_cover_standard_stages():
    """All standard stages have token estimates."""
    for stage in ("intake", "plan", "research", "synthesize", "artifact"):
        assert stage in STAGE_TOKEN_ESTIMATES


def test_breakdown_contains_all_fields():
    """Each stage breakdown has backend, cost_usd, tokens_in, tokens_out."""
    stages = ["intake", "plan"]
    cascade = {"intake": ["groq"], "plan": ["openai"]}
    _, breakdown = estimate_pipeline_cost(stages, cascade)
    for stage in stages:
        info = breakdown[stage]
        assert "backend" in info
        assert "cost_usd" in info
        assert "tokens_in" in info
        assert "tokens_out" in info
