"""Markdown artifact builder — simplest output path."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_md(synthesis: dict[str, Any], output_path: Path) -> None:
    """Build a Markdown document from synthesis data."""
    lines: list[str] = []

    title = synthesis.get("title", "")
    if title:
        lines.append(f"# {title}")
        lines.append("")

    for section in synthesis.get("sections", []):
        heading = section.get("heading", "")
        content = section.get("content", "")
        bullets = section.get("bullet_points", [])

        if heading:
            lines.append(f"## {heading}")
            lines.append("")

        if content:
            lines.append(content)
            lines.append("")

        for bullet in bullets:
            lines.append(f"- {bullet}")
        if bullets:
            lines.append("")

    sources = synthesis.get("sources", [])
    if sources:
        lines.append("## Quellen")
        lines.append("")
        for source in sources:
            lines.append(f"- {source}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
