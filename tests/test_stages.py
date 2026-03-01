"""Tests for individual pipeline stages with mock backend."""

import json

import pytest

from schulpipeline.stages.artifact import ArtifactStage, _safe_filename
from schulpipeline.stages.base import BaseStage, MissingContextError, StageResult, validate_against_spec
from schulpipeline.stages.intake import IntakeStage, _infer_format, _parse_json_response
from schulpipeline.stages.plan import PlanStage
from schulpipeline.stages.research import ResearchStage
from schulpipeline.stages.synthesize import SynthesizeStage
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


def test_validate_against_spec_synthesis_content_empty():
    """Synthesis spec requires content minLength: 1 (non-empty)."""
    data = {
        "title": "Test Title Here",
        "sections": [{"section_id": "s1", "heading": "Test", "content": ""}],
    }
    errors = validate_against_spec(data, "specs/synthesis.json")
    assert any("non-empty" in e or "too short" in e for e in errors)


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


def test_parse_json_response_language_variants():
    """Fences with language tags like ```json, ```JSON, ```jsonc all work."""
    for lang in ("json", "JSON", "jsonc", ""):
        result = _parse_json_response(f"```{lang}\n" + '{"ok": true}\n```')
        assert result == {"ok": True}


def test_parse_json_response_surrounding_text():
    """JSON embedded in prose is extracted."""
    result = _parse_json_response('Here is the result:\n{"key": "value"}\nDone.')
    assert result == {"key": "value"}


def test_parse_json_response_unclosed_fence():
    """Unclosed fence falls back to { detection."""
    result = _parse_json_response('```json\n{"key": "value"}')
    assert result == {"key": "value"}


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


@pytest.mark.asyncio
async def test_intake_subject_hint_overrides_llm(mock_router, mock_config):
    """When subject_hint is in context, intake uses it instead of LLM classification."""
    stage = IntakeStage()
    context = {
        "raw_input": "Erstelle eine Präsentation über IT-Sicherheit",
        "subject_hint": "Deutsch",
    }
    result = await stage.run(context, mock_router, mock_config)

    assert result.success
    # LLM would classify as IT-Sicherheit, but hint overrides to Deutsch
    assert result.data["subject"] == "Deutsch"


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


@pytest.mark.asyncio
async def test_research_sanitizes_urls_when_web_disabled(mock_config):
    """When use_web=False, any fabricated URLs in findings are replaced with llm_knowledge."""
    from schulpipeline.backends.router import BackendRouter
    from tests.conftest import MockBackend

    # Mock that returns findings with a fabricated URL
    research_with_urls = json.dumps(
        {
            "sections": [
                {
                    "section_id": "section_02",
                    "findings": [
                        {"content": "Some fact", "source": "https://fake-url.example.com", "relevance": 0.9},
                        {"content": "Another fact", "source": "llm_knowledge", "relevance": 0.8},
                    ],
                    "sufficient": True,
                },
            ]
        }
    )
    mock_backend = MockBackend(responses={"Recherche-Assistent": research_with_urls})

    router = BackendRouter.__new__(BackendRouter)
    router.config = mock_config
    router._backends = {"mock": mock_backend}
    router._cooldowns = {}
    router._call_counts = {"mock": 0}
    router._total_cost = 0.0
    router._stage_costs = {}
    router._stage_tokens = {}

    assert not mock_config.research.use_web

    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    context = {"raw_input": "test", "intake": intake_data, "plan": plan_data}

    stage = ResearchStage()
    result = await stage.run(context, router, mock_config)

    assert result.success
    for section in result.data["sections"]:
        for finding in section["findings"]:
            assert not finding["source"].startswith("http"), f"Found fabricated URL: {finding['source']}"
            assert finding["source"] == "llm_knowledge"


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


def test_safe_filename_accented():
    """Accented characters are decomposed, not stripped."""
    assert _safe_filename("Résumé") == "Resume"
    assert _safe_filename("café") == "cafe"
    assert _safe_filename("naïve señor") == "naive_senor"


# ============================================================
# stages/synthesize.py — Tone & Visual injection
# ============================================================


@pytest.mark.asyncio
async def test_synthesize_tone_from_style(mock_router, mock_config):
    """When style is in context, the tone block appears in the prompt."""
    from schulpipeline.styles import DEFAULT_STYLE, DEFAULT_VISUAL_SLOTS

    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    research_data = json.loads(DEFAULT_STAGE_RESPONSES["Recherche-Assistent"])
    context = {
        "raw_input": "test",
        "intake": intake_data,
        "plan": plan_data,
        "research": research_data,
        "style": DEFAULT_STYLE,
        "visual_slots": DEFAULT_VISUAL_SLOTS,
    }

    stage = SynthesizeStage()
    await stage.run(context, mock_router, mock_config)

    # The mock backend records calls — check system prompt contains tone info
    mock_backend = mock_router._backends["mock"]
    last_call = mock_backend.calls[-1]
    system_prompt = last_call["messages"][0]["content"]
    assert "Stilanweisungen" in system_prompt
    assert "Register:" in system_prompt


@pytest.mark.asyncio
async def test_synthesize_fallback_tone(mock_router, mock_config):
    """Without style in context, the old hardcoded tone line is used."""
    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    research_data = json.loads(DEFAULT_STAGE_RESPONSES["Recherche-Assistent"])
    context = {
        "raw_input": "test",
        "intake": intake_data,
        "plan": plan_data,
        "research": research_data,
        # No "style" or "visual_slots" in context
    }

    stage = SynthesizeStage()
    await stage.run(context, mock_router, mock_config)

    mock_backend = mock_router._backends["mock"]
    last_call = mock_backend.calls[-1]
    system_prompt = last_call["messages"][0]["content"]
    assert "sachlich, auf Berufsschul-Niveau" in system_prompt


@pytest.mark.asyncio
async def test_synthesize_visual_instruction(mock_router, mock_config):
    """When visuals are enabled, the visual instruction block is in the prompt."""
    from schulpipeline.styles import DEFAULT_STYLE, DEFAULT_VISUAL_SLOTS

    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    research_data = json.loads(DEFAULT_STAGE_RESPONSES["Recherche-Assistent"])
    context = {
        "raw_input": "test",
        "intake": intake_data,
        "plan": plan_data,
        "research": research_data,
        "style": DEFAULT_STYLE,
        "visual_slots": DEFAULT_VISUAL_SLOTS,
    }

    stage = SynthesizeStage()
    await stage.run(context, mock_router, mock_config)

    mock_backend = mock_router._backends["mock"]
    last_call = mock_backend.calls[-1]
    system_prompt = last_call["messages"][0]["content"]
    assert "visuals" in system_prompt
    assert "diagram" in system_prompt


@pytest.mark.asyncio
async def test_synthesize_no_visual_instruction(mock_router, mock_config):
    """When visuals are disabled, no visual instruction in the prompt."""
    from schulpipeline.styles import DEFAULT_STYLE, DISABLED_VISUAL_SLOTS

    intake_data = json.loads(DEFAULT_STAGE_RESPONSES["Aufgaben-Parser"])
    plan_data = json.loads(DEFAULT_STAGE_RESPONSES["Planungsassistent"])
    research_data = json.loads(DEFAULT_STAGE_RESPONSES["Recherche-Assistent"])
    context = {
        "raw_input": "test",
        "intake": intake_data,
        "plan": plan_data,
        "research": research_data,
        "style": DEFAULT_STYLE,
        "visual_slots": DISABLED_VISUAL_SLOTS,
    }

    stage = SynthesizeStage()
    await stage.run(context, mock_router, mock_config)

    mock_backend = mock_router._backends["mock"]
    last_call = mock_backend.calls[-1]
    system_prompt = last_call["messages"][0]["content"]
    assert "Für jede Folie/Sektion" not in system_prompt


# ============================================================
# Context validation (T1-4)
# ============================================================


@pytest.mark.asyncio
async def test_intake_rejects_empty_context():
    """IntakeStage requires 'raw_input' in context."""
    stage = IntakeStage()
    result = await stage.run({}, None, None)
    assert not result.success
    assert "raw_input" in result.errors[0]


@pytest.mark.asyncio
async def test_plan_rejects_missing_intake():
    """PlanStage requires 'intake' in context."""
    stage = PlanStage()
    result = await stage.run({"raw_input": "test"}, None, None)
    assert not result.success
    assert "intake" in result.errors[0]


@pytest.mark.asyncio
async def test_research_rejects_missing_context():
    """ResearchStage requires 'plan' and 'intake'."""
    stage = ResearchStage()
    result = await stage.run({"raw_input": "test"}, None, None)
    assert not result.success
    assert "plan" in result.errors[0]
    assert "intake" in result.errors[0]


@pytest.mark.asyncio
async def test_synthesize_rejects_missing_context():
    """SynthesizeStage requires plan, research, intake."""
    stage = SynthesizeStage()
    result = await stage.run({"raw_input": "test"}, None, None)
    assert not result.success
    for key in ("plan", "research", "intake"):
        assert key in result.errors[0]


@pytest.mark.asyncio
async def test_artifact_rejects_missing_context():
    """ArtifactStage requires synthesize and plan."""
    stage = ArtifactStage()
    result = await stage.run({"raw_input": "test"}, None, None)
    assert not result.success
    assert "synthesize" in result.errors[0]
    assert "plan" in result.errors[0]


@pytest.mark.asyncio
async def test_validation_passes_with_correct_context(mock_router, mock_config):
    """Normal execution works with required context present."""
    stage = IntakeStage()
    context = {"raw_input": "Test task"}
    result = await stage.run(context, mock_router, mock_config)
    assert result.success


def test_missing_context_error_message():
    """MissingContextError formats a helpful message."""
    err = MissingContextError("synthesize", {"plan", "research"})
    msg = str(err)
    assert "synthesize" in msg
    assert "plan" in msg
    assert "research" in msg
    assert "prior stage" in msg


@pytest.mark.asyncio
async def test_base_stage_no_required_context():
    """A stage with no required_context skips validation."""

    class NoRequirementsStage(BaseStage):
        name = "no_req"
        spec_path = "specs/nonexistent.json"

        async def execute(self, context, backend, config):
            return {"ok": True}

    stage = NoRequirementsStage()
    result = await stage.run({}, None, None)
    assert result.success
