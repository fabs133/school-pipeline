"""Pipeline stages — registry and sequence resolution."""

from __future__ import annotations

from typing import Any

from .artifact import ArtifactStage
from .base import MissingContextError
from .intake import IntakeStage
from .plan import PlanStage
from .research import ResearchStage
from .synthesize import SynthesizeStage

__all__ = [
    "MissingContextError",
    "IntakeStage",
    "PlanStage",
    "ResearchStage",
    "SynthesizeStage",
    "ArtifactStage",
    "STAGE_REGISTRY",
    "STANDARD_STAGE_SEQUENCE",
    "ALTERNATIVE_SEQUENCES",
    "resolve_stage_sequence",
    "build_stages",
]

# Core stage registry — maps name → class
STAGE_REGISTRY: dict[str, type] = {
    "intake": IntakeStage,
    "plan": PlanStage,
    "research": ResearchStage,
    "synthesize": SynthesizeStage,
    "artifact": ArtifactStage,
}

# Standard 5-stage sequence (default pipeline path)
STANDARD_STAGE_SEQUENCE: list[str] = [
    "intake", "plan", "research", "synthesize", "artifact",
]

# Alternative sequences keyed by output_constraints flag
ALTERNATIVE_SEQUENCES: dict[str, list[str]] = {
    "worksheet_mode": ["intake", "decompose", "solve"],
    "audit_only": ["intake", "classify_docs", "audit"],
    "requirements_report": [
        "intake", "classify_docs", "audit", "classify_report", "amendments",
    ],
    "template_mode": ["intake", "classify_docs", "audit", "fill_template"],
}


def resolve_stage_sequence(preset: Any = None) -> list[str]:
    """Return the ordered list of stage names for a given preset.

    This is the single source of truth for stage sequencing.
    Both Pipeline and SessionRunner must call this.
    """
    if preset and hasattr(preset, "output_constraints"):
        for flag, sequence in ALTERNATIVE_SEQUENCES.items():
            if preset.output_constraints.get(flag):
                return list(sequence)
    return list(STANDARD_STAGE_SEQUENCE)


def build_stages(sequence: list[str]) -> list:
    """Instantiate stage objects from a sequence of names.

    Loads alternative stage classes lazily on first use.
    Raises ValueError for unknown stage names.
    """
    _ensure_optional_stages(sequence)

    stages = []
    for name in sequence:
        cls = STAGE_REGISTRY.get(name)
        if cls is None:
            raise ValueError(
                f"Unknown stage '{name}'. Available: {sorted(STAGE_REGISTRY.keys())}"
            )
        stages.append(cls())
    return stages


def _ensure_optional_stages(names: list[str]) -> None:
    """Load optional stage classes into the registry if needed."""
    needs = set(names) - STAGE_REGISTRY.keys()
    if not needs:
        return

    if needs & {"decompose", "solve"}:
        from ..worksheet import DecomposeStage, SolveStage
        STAGE_REGISTRY["decompose"] = DecomposeStage
        STAGE_REGISTRY["solve"] = SolveStage

    if "audit" in needs:
        from ..audit import AuditStage
        STAGE_REGISTRY["audit"] = AuditStage

    if needs & {"classify_docs", "fill_template"}:
        from ..documents import ClassifyDocsStage, FillTemplateStage
        STAGE_REGISTRY["classify_docs"] = ClassifyDocsStage
        STAGE_REGISTRY["fill_template"] = FillTemplateStage

    if needs & {"classify_report", "amendments"}:
        from ..requirements import AmendmentsStage, ClassifyReportStage
        STAGE_REGISTRY["classify_report"] = ClassifyReportStage
        STAGE_REGISTRY["amendments"] = AmendmentsStage
