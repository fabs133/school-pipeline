"""Tests for artifact builders — PPTX, DOCX, MD file generation."""

from pathlib import Path

from schulpipeline.artifacts.pptx_builder import build_pptx
from schulpipeline.artifacts.docx_builder import build_docx
from schulpipeline.artifacts.md_builder import build_md


# ============================================================
# PPTX Builder
# ============================================================

def test_pptx_creates_file(synthesis_data, tmp_path):
    out = tmp_path / "test.pptx"
    build_pptx(synthesis_data, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_pptx_has_correct_slide_count(synthesis_data, tmp_path):
    out = tmp_path / "slides.pptx"
    build_pptx(synthesis_data, out)

    from pptx import Presentation
    prs = Presentation(str(out))
    assert len(prs.slides) == len(synthesis_data["sections"])


def test_pptx_title_slide_has_heading(synthesis_data, tmp_path):
    out = tmp_path / "title.pptx"
    build_pptx(synthesis_data, out)

    from pptx import Presentation
    prs = Presentation(str(out))
    first_slide = prs.slides[0]
    texts = [shape.text for shape in first_slide.shapes if shape.has_text_frame]
    assert any(synthesis_data["sections"][0]["heading"] in t for t in texts)


def test_pptx_minimal_input(tmp_path):
    """Builder handles minimal synthesis data."""
    data = {
        "title": "Minimal",
        "sections": [
            {"section_id": "s1", "heading": "Only Slide", "content": "Content here",
             "bullet_points": [], "speaker_notes": None}
        ],
        "sources": [],
    }
    out = tmp_path / "minimal.pptx"
    build_pptx(data, out)
    assert out.exists()

    from pptx import Presentation
    prs = Presentation(str(out))
    assert len(prs.slides) == 1


# ============================================================
# DOCX Builder
# ============================================================

def test_docx_creates_file(synthesis_data, tmp_path):
    out = tmp_path / "test.docx"
    build_docx(synthesis_data, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_docx_contains_title(synthesis_data, tmp_path):
    out = tmp_path / "title.docx"
    build_docx(synthesis_data, out)

    from docx import Document
    doc = Document(str(out))
    paragraphs = [p.text for p in doc.paragraphs]
    assert synthesis_data["title"] in paragraphs


def test_docx_contains_sources(synthesis_data, tmp_path):
    out = tmp_path / "sources.docx"
    build_docx(synthesis_data, out)

    from docx import Document
    doc = Document(str(out))
    all_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Quellen" in all_text


def test_docx_minimal_input(tmp_path):
    data = {
        "title": "Minimal Doc",
        "sections": [
            {"heading": "Chapter 1", "content": "Some text here.", "bullet_points": []}
        ],
        "sources": [],
    }
    out = tmp_path / "minimal.docx"
    build_docx(data, out)
    assert out.exists()


# ============================================================
# Markdown Builder
# ============================================================

def test_md_creates_file(synthesis_data, tmp_path):
    out = tmp_path / "test.md"
    build_md(synthesis_data, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_md_has_title_heading(synthesis_data, tmp_path):
    out = tmp_path / "heading.md"
    build_md(synthesis_data, out)

    content = out.read_text(encoding="utf-8")
    assert content.startswith(f"# {synthesis_data['title']}")


def test_md_has_section_headings(synthesis_data, tmp_path):
    out = tmp_path / "sections.md"
    build_md(synthesis_data, out)

    content = out.read_text(encoding="utf-8")
    for section in synthesis_data["sections"]:
        assert f"## {section['heading']}" in content


def test_md_has_bullet_points(synthesis_data, tmp_path):
    out = tmp_path / "bullets.md"
    build_md(synthesis_data, out)

    content = out.read_text(encoding="utf-8")
    # Section 2 has bullet points
    assert "- Schutz von Informationen" in content


def test_md_has_sources(synthesis_data, tmp_path):
    out = tmp_path / "sources.md"
    build_md(synthesis_data, out)

    content = out.read_text(encoding="utf-8")
    assert "## Quellen" in content
    assert "- BSI" in content


def test_md_minimal_input(tmp_path):
    data = {"title": "Minimal", "sections": [], "sources": []}
    out = tmp_path / "minimal.md"
    build_md(data, out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "# Minimal" in content
