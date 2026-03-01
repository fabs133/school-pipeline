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
from .stages import STANDARD_STAGE_SEQUENCE, build_stages, resolve_stage_sequence
from .stages.base import StageResult, validate_against_spec

logger = logging.getLogger("schulpipeline.pipeline")


@dataclass
class PipelineResult:
    """A class representing the result of a pipeline execution.

    :param success: Indicates whether the pipeline was executed successfully.
    :type success: bool
    :param results: A list of stage results from the pipeline.
    :type results: list[StageResult]
    :param output_path: The path to the output file, if any.
    :type output_path: str | None
    :param failed_stage: The name of the stage that failed, if any.
    :type failed_stage: str | None
    :param validation_errors: A list of validation errors encountered during execution.
    :type validation_errors: list[str]
    :param total_cost_usd: The total cost of the pipeline execution in USD.
    :type total_cost_usd: float
    :param elapsed_ms: The time taken to execute the pipeline in milliseconds.
    :type elapsed_ms: int
    """
    success: bool
    results: list[StageResult] = field(default_factory=list)
    output_path: str | None = None
    failed_stage: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    elapsed_ms: int = 0


class Pipeline:
    """Runs the 5-stage pipeline: intake → plan → research → synthesize → artifact."""

    def __init__(self, config: PipelineConfig, router: BackendRouter | None):
        """Initialize the pipeline with configuration and router.

        :param config: Configuration for the pipeline.
        :type config: PipelineConfig
        :param router: Optional backend router for routing requests.
        :type router: BackendRouter | None
        """
        self.config = config
        self.router = router

    def estimate_cost(self, stages: list[str] | None = None) -> tuple[float, dict]:
        """Estimate the cost of running the pipeline (pure calculation, no network)."""
        from .backends.pricing import estimate_pipeline_cost

        stage_names = stages or STANDARD_STAGE_SEQUENCE
        effective_cascade = {name: self.config.cascade_for(name) for name in stage_names}
        return estimate_pipeline_cost(stage_names, effective_cascade)

    def _select_stages(self, context: dict[str, Any]) -> list:
        """Select stage sequence based on preset/mode — delegates to the stage registry."""
        sequence = resolve_stage_sequence(context.get("preset"))
        return build_stages(sequence)

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
        if self.router is None:
            raise RuntimeError(
                "Pipeline.run() requires a router. "
                "Pass router=BackendRouter(config) to Pipeline()."
            )
        t0 = time.monotonic()
        context: dict[str, Any] = {"raw_input": raw_input}
        if preset:
            context["preset"] = preset
        if overrides and overrides.get("subject"):
            context["subject_hint"] = overrides["subject"]
        if overrides and overrides.get("agent"):
            context["agent"] = overrides["agent"]

        # Make output_dir available to terminal stages for file writing
        context["output_dir"] = str(Path(self.config.output.dir))

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

        for stage in build_stages(["intake", "plan"]):
            result = await stage.run(context, self.router, self.config)
            results.append(result)

            if not result.success:
                return PipelineResult(success=False, results=results, failed_stage=stage.name)

            context[stage.name] = result.data

        return PipelineResult(success=True, results=results)
