"""Tests for individual pipeline stages with mock backend."""

import json
import pytest

from schulpipeline.stages.base import BaseStage, StageResult, validate_against_spec
from schulpipeline.stages.intake import IntakeStage, _parse_json_response, _infer_format
from schulpipeline.stages.plan import PlanStage
from schulpipeline.stages.research import ResearchStage
from schulpipeline.stages.synthesize import SynthesizeStage
from schulpipeline.stages.artifact import ArtifactStage, _safe_filename
from tests.conftest import DEFAULT_STAGE_RESPONSES


# ============================================================
# stages/base.py
# ============================================================

def test_stage_result_defaults():
    r = StageResult(stage="test", success=True)
    assert r.data == {}
    assert r.errors == []
    assert r.metadata == {}


def test_stage_result_with_data():
    r = StageResult(stage="intake", success=True, data={"key": "val"})
    assert r.data["key"] == "val"


def test_validate_against_spec_nonexistent():
    """Missing spec file returns empty errors (non-fatal)."""
    errors = validate_against_spec({"foo": "bar"}, "specs/nonexistent.json")
    assert errors == []


def test_validate_against_spec_intake_valid():
    data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    errors = validate_against_spec(data, "specs/intake.json")
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_validate_against_spec_intake_invalid():
    errors = validate_against_spec({}, "specs/intake.json")
    assert len(errors) > 0  # missing required fields


def test_validate_against_spec_plan_valid():
    data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    errors = validate_against_spec(data, "specs/plan.json")
    assert errors == []


def test_validate_against_spec_synthesis_valid():
    data = json.loads(DEFAULT_STAGE_RESPONSES["Präsentations-Autor"])
    errors = validate_against_spec(data, "specs/synthesis.json")
    assert errors == []


def test_validate_against_spec_synthesis_content_too_short():
    """Synthesis spec requires content minLength: 10."""
    data = {
        "title": "Test Title Here",
        "sections": [{"section_id": "s1", "heading": "Test", "content": "short"}],
    }
    errors = validate_against_spec(data, "specs/synthesis.json")
    assert any("too short" in e for e in errors)


@pytest.mark.asyncio
async def test_base_stage_wraps_exceptions():
    """BaseStage catches exceptions and returns failed StageResult."""

    class BrokenStage(BaseStage):
        name = "broken"
        spec_path = "specs/nonexistent.json"

        async def execute(self, context, backend, config):
            raise RuntimeError("something broke")

    stage = BrokenStage()
    result = await stage.run({}, None, None)
    assert not result.success
    assert "something broke" in result.errors[0]
    assert result.metadata["elapsed_ms"] >= 0


# ============================================================
# stages/intake.py helpers
# ============================================================

def test_parse_json_response_plain():
    result = _parse_json_response('{"key": "value"}')
    assert result == {"key": "value"}


def test_parse_json_response_with_fences():
    result = _parse_json_response('```json\n{"key": "value"}\n```')
    assert result == {"key": "value"}


def test_parse_json_response_invalid():
    with pytest.raises(ValueError, match="invalid JSON"):
        _parse_json_response("not json at all")


def test_infer_format():
    assert _infer_format("presentation") == "pptx"
    assert _infer_format("document") == "docx"
    assert _infer_format("essay") == "docx"
    assert _infer_format("question_set") == "md"
    assert _infer_format("mixed") == "docx"
    assert _infer_format("unknown") == "md"


# ============================================================
# stages/intake.py
# ============================================================

@pytest.mark.asyncio
async def test_intake_stage_text(mock_router, mock_config):
    stage = IntakeStage()
    context = {"raw_input": "Erstelle eine Präsentation über IT-Sicherheit"}
    result = await stage.run(context, mock_router, mock_config)

    assert result.success
    assert result.stage == "intake"
    assert result.data["subject"] == "IT-Sicherheit"
    assert result.data["task_type"] == "presentation"
    assert result.data["constraints"]["format"] == "pptx"


# ============================================================
# stages/plan.py
# ============================================================

@pytest.mark.asyncio
async def test_plan_stage(mock_router, mock_config):
    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    context = {"raw_input": "test", "intake": intake_data}

    stage = PlanStage()
    result = await stage.run(context, mock_router, mock_config)

    assert result.success
    assert result.stage == "plan"
    assert "title" in result.data
    assert "sections" in result.data
    assert len(result.data["sections"]) >= 3


@pytest.mark.asyncio
async def test_plan_stage_enforces_artifact_type(mock_router, mock_config):
    """Plan stage overrides artifact_type to match intake constraint."""
    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    intake_data["constraints"]["format"] = "docx"
    context = {"raw_input": "test", "intake": intake_data}

    stage = PlanStage()
    result = await stage.run(context, mock_router, mock_config)

    assert result.success
    assert result.data["artifact_type"] == "docx"


# ============================================================
# stages/research.py
# ============================================================

@pytest.mark.asyncio
async def test_research_stage(mock_router, mock_config):
    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    context = {"raw_input": "test", "intake": intake_data, "plan": plan_data}

    stage = ResearchStage()
    result = await stage.run(context, mock_router, mock_config)

    assert result.success
    assert "sections" in result.data
    assert len(result.data["sections"]) >= 1


# ============================================================
# stages/synthesize.py
# ============================================================

@pytest.mark.asyncio
async def test_synthesize_stage(mock_router, mock_config):
    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    research_data = json.loads(DEFAULT_STAGE_RESPONSES["Recherche-Assistent"])
    context = {
        "raw_input": "test",
        "intake": intake_data,
        "plan": plan_data,
        "research": research_data,
    }

    stage = SynthesizeStage()
    result = await stage.run(context, mock_router, mock_config)

    assert result.success
    assert "title" in result.data
    assert "sections" in result.data


# ============================================================
# stages/artifact.py
# ============================================================

@pytest.mark.asyncio
async def test_artifact_stage_pptx(mock_router, mock_config, tmp_path):
    mock_config.output.dir = str(tmp_path)

    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    synthesis_data = json.loads(DEFAULT_STAGE_RESPONSES["Präsentations-Autor"])
    context = {
        "raw_input": "test",
        "intake": intake_data,
        "plan": plan_data,
        "synthesize": synthesis_data,
    }

    stage = ArtifactStage()
    result = await stage.run(context, mock_router, mock_config)

    assert result.success
    assert result.data["artifact_type"] == "pptx"
    assert result.data["file_path"].endswith(".pptx")
    from pathlib import Path
    assert Path(result.data["file_path"]).exists()


@pytest.mark.asyncio
async def test_artifact_stage_md(mock_router, mock_config, tmp_path):
    mock_config.output.dir = str(tmp_path)

    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    plan_data["artifact_type"] = "md"
    synthesis_data = json.loads(DEFAULT_STAGE_RESPONSES["Präsentations-Autor"])
    context = {
        "raw_input": "test",
        "intake": intake_data,
        "plan": plan_data,
        "synthesize": synthesis_data,
    }

    stage = ArtifactStage()
    result = await stage.run(context, mock_router, mock_config)

    assert result.success
    assert result.data["artifact_type"] == "md"
    from pathlib import Path
    assert Path(result.data["file_path"]).exists()


def test_safe_filename():
    assert _safe_filename("IT-Sicherheit im Unternehmen") == "IT-Sicherheit_im_Unternehmen"
    assert _safe_filename("Ärger mit Übungen") == "Aerger_mit_Uebungen"
    assert _safe_filename("") == "output"
    assert len(_safe_filename("a" * 200)) <= 80
