"""Live end-to-end pipeline tests — full runs producing real files."""

from pathlib import Path

import pytest

from schulpipeline.pipeline import Pipeline


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_pptx_pipeline(live_config, live_router, tmp_path):
    """Full pipeline: real LLM -> PPTX file that opens."""
    live_config.output.dir = str(tmp_path)

    pipeline = Pipeline(live_config, live_router)
    result = await pipeline.run(
        "Erstellen Sie eine Präsentation über IT-Sicherheit, 6 Folien"
    )

    assert result.success, f"Failed at {result.failed_stage}: {result.validation_errors}"
    assert result.output_path is not None
    assert Path(result.output_path).exists()
    assert result.output_path.endswith(".pptx")

    # Verify it's a valid PPTX
    from pptx import Presentation
    prs = Presentation(result.output_path)
    assert len(prs.slides) >= 3

    # Cost should be zero (free tier)
    assert result.total_cost_usd < 0.05


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_docx_pipeline(live_config, live_router, tmp_path):
    """Full pipeline: real LLM -> DOCX document."""
    live_config.output.dir = str(tmp_path)
    live_config.output.default_format = "docx"

    pipeline = Pipeline(live_config, live_router)
    result = await pipeline.run(
        "Schreiben Sie einen kurzen Aufsatz über Datenschutz (1 Seite)"
    )

    assert result.success, f"Failed at {result.failed_stage}: {result.validation_errors}"
    assert result.output_path is not None
    assert Path(result.output_path).exists()
    assert result.output_path.endswith(".docx")


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_plan_only(live_config, live_router):
    """Dry run: intake + plan only, no file generation."""
    pipeline = Pipeline(live_config, live_router)
    result = await pipeline.plan_only(
        "Erstellen Sie eine Präsentation über Netzwerktechnik, 8 Folien"
    )

    assert result.success
    assert len(result.results) == 2

    plan = result.results[-1].data
    assert "title" in plan
    assert len(plan.get("sections", [])) >= 4
