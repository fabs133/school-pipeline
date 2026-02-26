"""Pipeline orchestrator — runs stages sequentially with spec validation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .backends.router import BackendRouter
from .config import PipelineConfig
from .logging_config import set_stage
from .stages.base import StageResult, validate_against_spec
from .stages import IntakeStage, PlanStage, ResearchStage, SynthesizeStage, ArtifactStage

logger = logging.getLogger("schulpipeline.pipeline")


@dataclass
class PipelineResult:
    success: bool
    results: list[StageResult] = field(default_factory=list)
    output_path: str | None = None
    failed_stage: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    elapsed_ms: int = 0


class Pipeline:
    """Runs the 5-stage pipeline: intake → plan → research → synthesize → artifact."""

    def __init__(self, config: PipelineConfig, router: BackendRouter):
        self.config = config
        self.router = router
        self._standard_stages = [
            IntakeStage(),
            PlanStage(),
            ResearchStage(),
            SynthesizeStage(),
            ArtifactStage(),
        ]

    def estimate_cost(self, stages: list[str] | None = None) -> tuple[float, dict]:
        """Estimate the cost of running the pipeline.

        Args:
            stages: List of stage names. If None, uses the standard 5 stages.

        Returns:
            (total_cost_usd, per_stage_breakdown)
        """
        from .backends.pricing import estimate_pipeline_cost

        stage_names = stages or [s.name for s in self._standard_stages]
        effective_cascade = {name: self.config.cascade_for(name) for name in stage_names}
        return estimate_pipeline_cost(stage_names, effective_cascade)

    def _select_stages(self, context: dict[str, Any]) -> list:
        """Select stage sequence based on preset/mode."""
        preset = context.get("preset")

        # Worksheet mode: intake → decompose → solve
        if preset and preset.output_constraints.get("worksheet_mode"):
            from .worksheet import DecomposeStage, SolveStage
            return [IntakeStage(), DecomposeStage(), SolveStage()]

        # Audit-only mode: intake → classify_docs → audit (no filling)
        if preset and preset.output_constraints.get("audit_only"):
            from .documents import ClassifyDocsStage
            from .audit import AuditStage
            return [IntakeStage(), ClassifyDocsStage(), AuditStage()]

        # Full requirements report: intake → classify → audit → classify_report → amendments
        if preset and preset.output_constraints.get("requirements_report"):
            from .documents import ClassifyDocsStage
            from .audit import AuditStage
            from .requirements import ClassifyReportStage, AmendmentsStage
            return [
                IntakeStage(),
                ClassifyDocsStage(),
                AuditStage(),
                ClassifyReportStage(),
                AmendmentsStage(),
            ]

        # Template mode: intake → classify_docs → audit → fill_template
        if preset and preset.output_constraints.get("template_mode"):
            from .documents import ClassifyDocsStage, FillTemplateStage
            from .audit import AuditStage
            return [IntakeStage(), ClassifyDocsStage(), AuditStage(), FillTemplateStage()]

        return self._standard_stages

    async def run(
        self,
        raw_input: str | Path,
        preset: Any = None,
        overrides: dict | None = None,
        on_progress: Any = None,
    ) -> PipelineResult:
        """Execute the full pipeline.

        Args:
            raw_input: Task text or path to image/file.
            preset: Optional ResolvedPreset from the preset system.
            overrides: Optional CLI overrides for style/visuals.
            on_progress: Optional callback(event, stage_name, stage_index, total_stages, **kw).
        """
        t0 = time.monotonic()
        context: dict[str, Any] = {"raw_input": raw_input}
        if preset:
            context["preset"] = preset
        if overrides and overrides.get("subject"):
            context["subject_hint"] = overrides["subject"]

        # Resolve style and visual configuration
        from .styles import resolve_style, resolve_visual_config
        context["style"] = resolve_style(self.config, overrides)
        context["visual_slots"] = resolve_visual_config(self.config, overrides)

        results: list[StageResult] = []

        available = self.router.available_backends
        if not available:
            return PipelineResult(
                success=False,
                failed_stage="init",
                validation_errors=["No backends available. Check config and API keys."],
            )

        logger.info(f"Pipeline starting with backends: {available}")
        logger.info(f"Input: {str(raw_input)[:100]}")

        stages = self._select_stages(context)
        is_worksheet = preset and hasattr(preset, 'output_constraints') and preset.output_constraints.get("worksheet_mode")
        is_template = preset and hasattr(preset, 'output_constraints') and preset.output_constraints.get("template_mode")
        is_audit = preset and hasattr(preset, 'output_constraints') and preset.output_constraints.get("audit_only")
        is_req_report = preset and hasattr(preset, 'output_constraints') and preset.output_constraints.get("requirements_report")

        total_stages = len(stages)
        for i, stage in enumerate(stages):
            stage_name = stage.name
            set_stage(stage_name)
            logger.info(f"=== Stage: {stage_name} ===")

            if on_progress:
                on_progress("stage_start", stage_name, i, total_stages)

            # Run the stage
            result = await stage.run(context, self.router, self.config)
            results.append(result)

            if not result.success:
                elapsed = int((time.monotonic() - t0) * 1000)
                logger.error(f"Stage '{stage_name}' failed: {result.errors}")
                if on_progress:
                    on_progress("stage_error", stage_name, i, total_stages,
                                elapsed_ms=result.metadata.get("elapsed_ms", 0), errors=result.errors)
                return PipelineResult(
                    success=False,
                    results=results,
                    failed_stage=stage_name,
                    total_cost_usd=self.router.total_cost,
                    elapsed_ms=elapsed,
                )

            # Validate output against JSON Schema
            spec_path = Path(stage.spec_path)
            if spec_path.exists():
                errors = validate_against_spec(result.data, spec_path)
                if errors:
                    elapsed = int((time.monotonic() - t0) * 1000)
                    logger.error(f"Stage '{stage_name}' output validation failed: {errors}")
                    return PipelineResult(
                        success=False,
                        results=results,
                        failed_stage=stage_name,
                        validation_errors=errors,
                        total_cost_usd=self.router.total_cost,
                        elapsed_ms=elapsed,
                    )
            else:
                _CORE_STAGES = {"intake", "plan", "research", "synthesize"}
                if stage_name in _CORE_STAGES:
                    elapsed = int((time.monotonic() - t0) * 1000)
                    logger.error(f"Missing spec for core stage '{stage_name}': {spec_path}")
                    return PipelineResult(
                        success=False,
                        results=results,
                        failed_stage=stage_name,
                        validation_errors=[f"Missing spec: {spec_path}"],
                        total_cost_usd=self.router.total_cost,
                        elapsed_ms=elapsed,
                    )
                else:
                    logger.warning(f"No spec found at {spec_path}, skipping validation")

            # Store result in context for next stage
            context[stage_name] = result.data

            if on_progress:
                on_progress("stage_done", stage_name, i, total_stages,
                            elapsed_ms=result.metadata.get("elapsed_ms", 0))

            logger.info(
                f"Stage '{stage_name}' completed in {result.metadata.get('elapsed_ms', '?')}ms"
            )

        elapsed = int((time.monotonic() - t0) * 1000)
        output_path = results[-1].data.get("file_path") if results else None

        # For worksheet mode, generate the output document from solve results
        if is_worksheet and results and results[-1].success:
            solve_data = results[-1].data
            output_dir = Path(self.config.output.dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            from .worksheet import format_worksheet_as_md, format_worksheet_as_docx
            title = solve_data.get("title", "Arbeitsblatt")
            safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in title).strip().replace(" ", "_")[:60]

            # DOCX for formal output, MD as fallback
            try:
                docx_path = output_dir / f"{safe_title}.docx"
                format_worksheet_as_docx(solve_data, docx_path)
                output_path = str(docx_path)
            except Exception as e:
                logger.warning(f"DOCX generation failed, falling back to MD: {e}")
                md_path = output_dir / f"{safe_title}.md"
                md_content = format_worksheet_as_md(solve_data)
                md_path.write_text(md_content, encoding="utf-8")
                output_path = str(md_path)

        # For template mode, apply filled fields to original template files
        if is_template and results and results[-1].success:
            fill_data = results[-1].data
            output_dir = Path(self.config.output.dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            from .documents import apply_to_docx, apply_to_pptx
            for tmpl in fill_data.get("filled_templates", []):
                filename = tmpl.get("template_filename", "output")
                fields = tmpl.get("fields_filled", [])
                # Check if we have the original template file
                template_file = context.get("template_files", {}).get(filename)
                if template_file and Path(template_file).exists():
                    out = output_dir / f"filled_{filename}"
                    if filename.endswith(".pptx"):
                        apply_to_pptx(template_file, fields, out)
                    else:
                        apply_to_docx(template_file, fields, out)
                    output_path = str(out)
                    logger.info(f"Template filled: {out}")

        # For audit mode (standalone or as part of template flow), generate audit report
        audit_data = None
        for r in results:
            if r.stage == "audit" and r.success:
                audit_data = r.data
                break

        if audit_data:
            output_dir = Path(self.config.output.dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            from .audit import format_audit_as_md, format_audit_as_docx
            safe_title = "Vorgaben-Audit"

            try:
                audit_docx = output_dir / f"{safe_title}.docx"
                format_audit_as_docx(audit_data, audit_docx)
                # For audit-only mode, this IS the output
                if is_audit:
                    output_path = str(audit_docx)
                else:
                    logger.info(f"Audit report: {audit_docx}")
            except Exception as e:
                logger.warning(f"Audit DOCX failed, falling back to MD: {e}")
                audit_md = output_dir / f"{safe_title}.md"
                from .audit import format_audit_as_md
                audit_md.write_text(format_audit_as_md(audit_data), encoding="utf-8")
                if is_audit:
                    output_path = str(audit_md)

        # For requirements report mode, build the three-part document
        if is_req_report and results:
            output_dir = Path(self.config.output.dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Collect data from stages
            stage_data = {r.stage: r.data for r in results if r.success}
            classify_report = stage_data.get("classify_report", {})
            amendments = stage_data.get("amendments", {})
            audit_for_report = stage_data.get("audit", {})

            from .requirements import build_full_report, format_report_as_md, format_report_as_docx
            full_report = build_full_report(classify_report, audit_for_report, amendments)

            try:
                docx_path = output_dir / "Anforderungsdokumentation.docx"
                format_report_as_docx(full_report, docx_path)
                output_path = str(docx_path)
            except Exception as e:
                logger.warning(f"Requirements DOCX failed, falling back to MD: {e}")
                md_path = output_dir / "Anforderungsdokumentation.md"
                md_path.write_text(format_report_as_md(full_report), encoding="utf-8")
                output_path = str(md_path)

        logger.info(f"Pipeline completed in {elapsed}ms, cost: ${self.router.total_cost:.4f}")
        if output_path:
            logger.info(f"Output: {output_path}")

        return PipelineResult(
            success=True,
            results=results,
            output_path=output_path,
            total_cost_usd=self.router.total_cost,
            elapsed_ms=elapsed,
        )

    async def plan_only(self, raw_input: str | Path, preset: Any = None, overrides: dict | None = None) -> PipelineResult:
        """Run only intake + plan stages (dry run)."""
        context: dict[str, Any] = {"raw_input": raw_input}
        if preset:
            context["preset"] = preset

        from .styles import resolve_style, resolve_visual_config
        context["style"] = resolve_style(self.config, overrides)
        context["visual_slots"] = resolve_visual_config(self.config, overrides)
        results: list[StageResult] = []

        for stage in self._standard_stages[:2]:  # intake + plan only
            result = await stage.run(context, self.router, self.config)
            results.append(result)

            if not result.success:
                return PipelineResult(success=False, results=results, failed_stage=stage.name)

            context[stage.name] = result.data

        return PipelineResult(success=True, results=results)
