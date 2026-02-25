"""DOCX artifact builder using python-docx."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


def build_docx(synthesis: dict[str, Any], output_path: Path) -> None:
    """Build a DOCX document from synthesis data."""
    doc = Document()

    # Set default font
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(11)

    # Title
    title = synthesis.get("title", "Dokument")
    heading = doc.add_heading(title, level=0)
    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Sections
    for section in synthesis.get("sections", []):
        heading_text = section.get("heading", "")
        content = section.get("content", "")

        if heading_text:
            doc.add_heading(heading_text, level=1)

        if content:
            doc.add_paragraph(content)

        # Add bullet points if present
        for bullet in section.get("bullet_points", []):
            doc.add_paragraph(bullet, style="List Bullet")

    # Sources
    sources = synthesis.get("sources", [])
    if sources:
        doc.add_heading("Quellen", level=1)
        for source in sources:
            doc.add_paragraph(source, style="List Bullet")

    doc.save(str(output_path))
