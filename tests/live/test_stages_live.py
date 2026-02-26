"""Live stage tests — each stage runs against a real LLM and validates against spec."""

import pytest

from schulpipeline.stages.artifact import ArtifactStage
from schulpipeline.stages.base import validate_against_spec
from schulpipeline.stages.intake import IntakeStage
from schulpipeline.stages.plan import PlanStage
from schulpipeline.stages.research import ResearchStage
from schulpipeline.stages.synthesize import SynthesizeStage

TASK_TEXT = "Erstellen Sie eine Präsentation zum Thema IT-Sicherheit mit 6 Folien."


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_intake(live_router, live_config):
    """Intake stage parses real text and validates against spec."""
    stage = IntakeStage()
    context = {"raw_input": TASK_TEXT}
    result = await stage.run(context, live_router, live_config)

    assert result.success, f"Intake failed: {result.errors}"
    assert result.data.get("subject"), "No subject extracted"
    assert result.data.get("task_type"), "No task_type extracted"
    assert result.data.get("constraints"), "No constraints extracted"

    errors = validate_against_spec(result.data, "specs/intake.json")
    assert errors == [], f"Spec validation failed: {errors}"


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_intake_then_plan(live_router, live_config):
    """Intake -> Plan with real LLM, both validate against spec."""
    # Intake
    intake = IntakeStage()
    context = {"raw_input": TASK_TEXT}
    intake_result = await intake.run(context, live_router, live_config)
    assert intake_result.success, f"Intake failed: {intake_result.errors}"

    errors = validate_against_spec(intake_result.data, "specs/intake.json")
    assert errors == [], f"Intake spec failed: {errors}"

    # Plan
    context["intake"] = intake_result.data
    plan = PlanStage()
    plan_result = await plan.run(context, live_router, live_config)
    assert plan_result.success, f"Plan failed: {plan_result.errors}"

    errors = validate_against_spec(plan_result.data, "specs/plan.json")
    assert errors == [], f"Plan spec failed: {errors}"

    assert len(plan_result.data.get("sections", [])) >= 3, "Too few sections planned"


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_full_pipeline_stages(live_router, live_config, tmp_path):
    """Run all 5 stages sequentially, validate each against spec."""
    live_config.output.dir = str(tmp_path)
    context = {"raw_input": TASK_TEXT}

    stages = [
        (IntakeStage(), "specs/intake.json"),
        (PlanStage(), "specs/plan.json"),
        (ResearchStage(), "specs/research.json"),
        (SynthesizeStage(), "specs/synthesis.json"),
        (ArtifactStage(), "specs/artifact.json"),
    ]

    for stage, spec_path in stages:
        result = await stage.run(context, live_router, live_config)
        assert result.success, f"Stage '{stage.name}' failed: {result.errors}"

        errors = validate_against_spec(result.data, spec_path)
        assert errors == [], f"Stage '{stage.name}' spec validation: {errors}"

        context[stage.name] = result.data

    # Verify output file exists
    from pathlib import Path
    output_path = context["artifact"]["file_path"]
    assert Path(output_path).exists(), f"Output not created: {output_path}"
    assert output_path.endswith(".pptx")
