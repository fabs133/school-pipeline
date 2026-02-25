"""PPTX artifact builder using python-pptx."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt, Emu


# --- Color scheme ---
COLORS = {
    "primary": RGBColor(0x1E, 0x27, 0x61),      # Navy
    "secondary": RGBColor(0xCA, 0xDC, 0xFC),     # Ice blue
    "accent": RGBColor(0xF9, 0x61, 0x67),        # Coral
    "text_dark": RGBColor(0x21, 0x21, 0x21),     # Near black
    "text_light": RGBColor(0xFF, 0xFF, 0xFF),     # White
    "text_muted": RGBColor(0x88, 0x88, 0x88),    # Gray
    "bg_dark": RGBColor(0x1E, 0x27, 0x61),       # Navy
    "bg_light": RGBColor(0xF5, 0xF7, 0xFA),      # Off-white
}


def build_pptx(synthesis: dict[str, Any], output_path: Path) -> None:
    """Build a PPTX presentation from synthesis data."""
    prs = Presentation()
    prs.slide_width = Inches(13.33)   # 16:9
    prs.slide_height = Inches(7.5)

    sections = synthesis.get("sections", [])
    title = synthesis.get("title", "Präsentation")
    sources = synthesis.get("sources", [])

    for i, section in enumerate(sections):
        if i == 0:
            _add_title_slide(prs, section, title)
        elif i == len(sections) - 1 and "quellen" in section.get("heading", "").lower():
            _add_sources_slide(prs, section, sources)
        else:
            _add_content_slide(prs, section)

    prs.save(str(output_path))


def _add_title_slide(prs: Presentation, section: dict, title: str) -> None:
    """Dark background title slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout

    # Dark background
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = COLORS["bg_dark"]

    # Title
    left, top = Inches(1.0), Inches(2.0)
    width, height = Inches(11.33), Inches(2.0)
    txbox = slide.shapes.add_textbox(left, top, width, height)
    tf = txbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = section.get("heading", title)
    p.font.size = Pt(44)
    p.font.bold = True
    p.font.color.rgb = COLORS["text_light"]
    p.alignment = PP_ALIGN.LEFT

    # Subtitle
    if section.get("content"):
        left, top = Inches(1.0), Inches(4.2)
        width, height = Inches(11.33), Inches(1.5)
        txbox = slide.shapes.add_textbox(left, top, width, height)
        tf = txbox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = section["content"]
        p.font.size = Pt(20)
        p.font.color.rgb = COLORS["secondary"]
        p.alignment = PP_ALIGN.LEFT


def _add_content_slide(prs: Presentation, section: dict) -> None:
    """Content slide with heading and bullet points."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank

    # Light background
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = COLORS["bg_light"]

    # Heading
    left, top = Inches(0.8), Inches(0.5)
    width, height = Inches(11.73), Inches(1.0)
    txbox = slide.shapes.add_textbox(left, top, width, height)
    tf = txbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = section.get("heading", "")
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = COLORS["primary"]
    p.alignment = PP_ALIGN.LEFT

    # Bullet points
    bullets = section.get("bullet_points", [])
    if bullets:
        left, top = Inches(0.8), Inches(1.8)
        width, height = Inches(11.73), Inches(5.0)
        txbox = slide.shapes.add_textbox(left, top, width, height)
        tf = txbox.text_frame
        tf.word_wrap = True

        for j, bullet in enumerate(bullets):
            if j == 0:
                p = tf.paragraphs[0]
            else:
                p = tf.add_paragraph()
            p.text = f"•  {bullet}"
            p.font.size = Pt(18)
            p.font.color.rgb = COLORS["text_dark"]
            p.space_after = Pt(12)
            p.alignment = PP_ALIGN.LEFT

    # Speaker notes
    notes = section.get("speaker_notes")
    if notes:
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = notes


def _add_sources_slide(prs: Presentation, section: dict, sources: list[str]) -> None:
    """Sources/references slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = COLORS["bg_dark"]

    # Heading
    left, top = Inches(0.8), Inches(0.5)
    width, height = Inches(11.73), Inches(1.0)
    txbox = slide.shapes.add_textbox(left, top, width, height)
    tf = txbox.text_frame
    p = tf.paragraphs[0]
    p.text = section.get("heading", "Quellen")
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = COLORS["text_light"]

    # Sources list
    all_sources = sources or section.get("bullet_points", [])
    if all_sources:
        left, top = Inches(0.8), Inches(1.8)
        width, height = Inches(11.73), Inches(5.0)
        txbox = slide.shapes.add_textbox(left, top, width, height)
        tf = txbox.text_frame
        tf.word_wrap = True

        for j, source in enumerate(all_sources):
            if j == 0:
                p = tf.paragraphs[0]
            else:
                p = tf.add_paragraph()
            p.text = source
            p.font.size = Pt(14)
            p.font.color.rgb = COLORS["secondary"]
            p.space_after = Pt(8)
