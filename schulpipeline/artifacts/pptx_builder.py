"""PPTX artifact builder — delegates to slideforge renderer."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .converter import synthesis_to_presentation

if TYPE_CHECKING:
    from ..presets import ResolvedPreset


def build_pptx(
    synthesis: dict[str, Any],
    output_path: Path,
    preset: "ResolvedPreset | None" = None,
) -> None:
    """Build a PPTX presentation from synthesis data.

    Converts the synthesis dict to a slideforge Presentation model
    and renders it using slideforge's template-based renderer.
    """
    from slideforge.renderer import render_pptx

    presentation = synthesis_to_presentation(synthesis, preset)
    render_pptx(presentation, output_path)
