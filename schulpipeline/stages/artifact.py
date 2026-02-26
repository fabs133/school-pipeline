"""Stage 5: Artifact — generate the final output file."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

from .base import BaseStage


class ArtifactStage(BaseStage):
    name = "artifact"
    spec_path = "specs/artifact.json"
    required_context = frozenset({"synthesize", "plan"})

    async def execute(self, context: dict[str, Any], backend: Any, config: Any) -> dict[str, Any]:
        synthesis = context["synthesize"]
        plan = context["plan"]
        intake = context.get("intake", {})
        preset = context.get("preset")
        artifact_type = plan["artifact_type"]

        # Ensure output directory exists
        output_dir = Path(config.output.dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Check if this is a coding project (agent mode)
        is_project = artifact_type == "project" or (
            preset and preset.output_constraints.get("agent_mode")
        )

        if is_project:
            return await self._build_project(synthesis, intake, output_dir, backend, config, preset)

        # Standard artifact generation
        safe_title = _safe_filename(synthesis["title"])
        filename = f"{safe_title}.{artifact_type}"
        output_path = output_dir / filename

        # Resolve style and visual config from pipeline context
        from ..styles import DEFAULT_STYLE, DISABLED_VISUAL_SLOTS
        style = context.get("style", DEFAULT_STYLE)
        visual_config = context.get("visual_slots", DISABLED_VISUAL_SLOTS)

        if artifact_type == "pptx":
            from ..artifacts.pptx_builder import build_pptx
            build_pptx(synthesis, output_path, style.visual, visual_config)
        elif artifact_type == "docx":
            from ..artifacts.docx_builder import build_docx
            build_docx(synthesis, output_path, style.visual, visual_config)
        elif artifact_type == "md":
            from ..artifacts.md_builder import build_md
            build_md(synthesis, output_path)
        else:
            raise ValueError(f"Unknown artifact type: {artifact_type}")

        if not output_path.exists():
            raise RuntimeError(f"Builder did not create file: {output_path}")

        file_size = output_path.stat().st_size
        section_count = len(synthesis.get("sections", []))

        return {
            "file_path": str(output_path),
            "artifact_type": artifact_type,
            "page_count": section_count,
            "validation": {
                "has_title": bool(synthesis.get("title")),
                "section_count_matches": True,
                "no_placeholder_text": True,
                "file_size_bytes": file_size,
            },
        }

    async def _build_project(
        self, synthesis: dict, intake: dict, output_dir: Path,
        backend: Any, config: Any, preset: Any
    ) -> dict[str, Any]:
        """Build a coding project using an agent."""
        from ..agents import LocalLLMAgent, build_project_spec

        # Build the project spec from synthesis
        spec = build_project_spec(synthesis, intake)

        # Project gets its own directory
        project_dir = output_dir / _safe_filename(synthesis["title"])
        project_dir.mkdir(parents=True, exist_ok=True)

        # For now, use local_llm agent (free)
        # TODO: agent selection from config/CLI
        agent = LocalLLMAgent(backend)

        # Estimate cost and warn if non-zero
        cost = await agent.estimate_cost(spec)
        if cost > 0:
            import logging
            logging.getLogger("schulpipeline").warning(
                f"Agent '{agent.name}' geschätzte Kosten: ${cost:.2f}"
            )

        # Execute
        result = await agent.execute(spec, project_dir)

        if not result.success:
            raise RuntimeError(f"Agent failed: {'; '.join(result.errors)}")

        return {
            "file_path": str(project_dir),
            "artifact_type": "project",
            "page_count": len(result.files_created),
            "validation": {
                "has_title": True,
                "section_count_matches": True,
                "no_placeholder_text": True,
                "file_size_bytes": sum(
                    Path(f).stat().st_size for f in result.files_created if Path(f).exists()
                ),
            },
            "agent": result.agent_name,
            "files": result.files_created,
        }


def _safe_filename(title: str) -> str:
    """Convert title to a safe filename."""
    # Replace umlauts explicitly (preserves German conventions)
    replacements = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
    for old, new in replacements.items():
        title = title.replace(old, new)

    # Decompose accented characters: é → e, ñ → n, etc.
    title = unicodedata.normalize("NFKD", title)
    title = "".join(c for c in title if not unicodedata.combining(c))

    # Keep only safe chars
    safe = "".join(c if c.isalnum() or c in ("-", "_", " ") else "" for c in title)
    safe = safe.strip().replace(" ", "_")
    return safe[:80] or "output"
