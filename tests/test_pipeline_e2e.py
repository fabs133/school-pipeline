"""End-to-end pipeline test with mock backend."""

from pathlib import Path

import pytest

from schulpipeline.backends.router import BackendRouter
from schulpipeline.pipeline import Pipeline


@pytest.mark.asyncio
async def test_full_pipeline_text_to_pptx(mock_config, mock_router, tmp_path):
    """Full pipeline: text input → PPTX output."""
    mock_config.output.dir = str(tmp_path)

    pipeline = Pipeline(mock_config, mock_router)
    result = await pipeline.run(
        "Erstellen Sie eine Präsentation zum Thema IT-Sicherheit mit mindestens 8 Folien."
    )

    assert result.success, f"Pipeline failed: {result.failed_stage}, errors: {result.validation_errors}"
    assert result.output_path is not None
    assert Path(result.output_path).exists()
    assert result.output_path.endswith(".pptx")
    assert len(result.results) == 5  # all 5 stages


@pytest.mark.asyncio
async def test_full_pipeline_text_to_md(mock_config, mock_router, tmp_path):
    """Full pipeline with MD format override."""
    mock_config.output.dir = str(tmp_path)
    mock_config.output.default_format = "md"

    # Override intake response to use md format
    import json

    from tests.conftest import DEFAULT_STAGE_RESPONSES

    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    intake_data["constraints"]["format"] = "md"
    intake_data["task_type"] = "question_set"

    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    plan_data["artifact_type"] = "md"

    mock_backend = mock_router._backends["mock"]
    mock_backend._responses = {
        "Aufgaben-Parser": json.dumps(intake_data),
        "Planungsassistent": json.dumps(plan_data),
        # Synthesize will use the "Aufgaben-Löser" default
        "Aufgaben-Löser": DEFAULT_STAGE_RESPONSES.get("Präsentations-Autor",
            json.dumps({"title": "Test", "sections": [{"section_id": "s1", "heading": "Test", "content": "Test content", "bullet_points": [], "speaker_notes": None}], "sources": []})),
    }

    pipeline = Pipeline(mock_config, mock_router)
    result = await pipeline.run("Was sind die Schutzziele der IT-Sicherheit?")

    assert result.success, f"Failed: {result.failed_stage}, {result.validation_errors}"
    assert result.output_path.endswith(".md")


@pytest.mark.asyncio
async def test_plan_only(mock_config, mock_router):
    """Dry run returns plan without running full pipeline."""
    pipeline = Pipeline(mock_config, mock_router)
    result = await pipeline.plan_only(
        "Erstellen Sie eine Präsentation zum Thema Netzwerktechnik."
    )

    assert result.success
    assert len(result.results) == 2  # intake + plan only
    plan = result.results[-1].data
    assert "title" in plan
    assert "sections" in plan


@pytest.mark.asyncio
async def test_pipeline_reports_stage_failure(mock_config, mock_router):
    """Pipeline reports which stage failed."""
    # Make the mock return invalid JSON for intake
    mock_backend = mock_router._backends["mock"]
    mock_backend._responses = {"Aufgaben-Parser": "not json at all"}

    pipeline = Pipeline(mock_config, mock_router)
    result = await pipeline.run("Test task")

    assert not result.success
    assert result.failed_stage == "intake"


@pytest.mark.asyncio
async def test_full_pipeline_text_to_docx(mock_config, mock_router, tmp_path):
    """Full pipeline: text input -> DOCX output."""
    mock_config.output.dir = str(tmp_path)

    import json

    from tests.conftest import DEFAULT_STAGE_RESPONSES

    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    intake_data["constraints"]["format"] = "docx"
    intake_data["task_type"] = "document"

    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    plan_data["artifact_type"] = "docx"

    # Build synthesis response for DOCX (uses "Dokument-Autor" in system prompt)
    synthesis_data = json.loads(DEFAULT_STAGE_RESPONSES["Präsentations-Autor"])

    mock_backend = mock_router._backends["mock"]
    mock_backend._responses = {
        "Aufgaben-Parser": json.dumps(intake_data),
        "Planungsassistent": json.dumps(plan_data),
        "Dokument-Autor": json.dumps(synthesis_data),
    }

    pipeline = Pipeline(mock_config, mock_router)
    result = await pipeline.run("Schreiben Sie einen Aufsatz über Datenschutz")

    assert result.success, f"Failed: {result.failed_stage}, {result.validation_errors}"
    assert result.output_path.endswith(".docx")
    assert Path(result.output_path).exists()


@pytest.mark.asyncio
async def test_pipeline_cascade_fallback(mock_config, cascade_router, tmp_path):
    """Pipeline succeeds when first backend fails but second works."""
    mock_config.output.dir = str(tmp_path)

    pipeline = Pipeline(mock_config, cascade_router)
    result = await pipeline.run(
        "Erstellen Sie eine Präsentation zum Thema IT-Sicherheit"
    )

    assert result.success, f"Failed: {result.failed_stage}, {result.validation_errors}"
    assert len(result.results) == 5


@pytest.mark.asyncio
async def test_pipeline_no_backends(mock_config):
    """Pipeline fails gracefully when no backends are available."""
    mock_config.backends = {}

    router = BackendRouter.__new__(BackendRouter)
    router.config = mock_config
    router._backends = {}
    router._cooldowns = {}
    router._call_counts = {}
    router._total_cost = 0.0

    pipeline = Pipeline(mock_config, router)
    result = await pipeline.run("Test")

    assert not result.success
    assert result.failed_stage == "init"
    assert "No backends" in result.validation_errors[0]


@pytest.mark.asyncio
async def test_pipeline_tracks_cost(mock_config, mock_router, tmp_path):
    """Pipeline reports total cost from router."""
    mock_config.output.dir = str(tmp_path)

    pipeline = Pipeline(mock_config, mock_router)
    result = await pipeline.run(
        "Erstellen Sie eine Präsentation zum Thema IT-Sicherheit"
    )

    assert result.success
    assert result.total_cost_usd >= 0.0
    assert result.elapsed_ms >= 0
