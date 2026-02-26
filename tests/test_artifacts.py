"""Tests for artifact builders — PPTX, DOCX, MD file generation."""


from pptx.util import Emu

from schulpipeline.artifacts.docx_builder import build_docx
from schulpipeline.artifacts.md_builder import build_md
from schulpipeline.artifacts.pptx_builder import build_pptx

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


def test_pptx_standard_dimensions_16_9(synthesis_data, tmp_path):
    """16:9 slide dimensions use exact EMU values (not float Inches)."""
    out = tmp_path / "dims.pptx"
    build_pptx(synthesis_data, out)

    from pptx import Presentation
    prs = Presentation(str(out))
    assert prs.slide_width == Emu(12192000)
    assert prs.slide_height == Emu(6858000)


def test_pptx_4_3_dimensions(synthesis_data, tmp_path):
    """4:3 mode uses 9144000 EMU width."""
    from schulpipeline.styles import DEFAULT_STYLE

    style = DEFAULT_STYLE.visual
    # Temporarily override aspect ratio via a copy
    from dataclasses import replace
    layout_4_3 = replace(style.layout, slide_ratio="4:3")
    style_4_3 = replace(style, layout=layout_4_3)

    out = tmp_path / "dims_4_3.pptx"
    build_pptx(synthesis_data, out, style_4_3)

    from pptx import Presentation
    prs = Presentation(str(out))
    assert prs.slide_width == Emu(9144000)


def test_pptx_empty_section_skipped(tmp_path):
    """Sections with no heading, content, or bullets produce no slide."""
    data = {
        "title": "Test",
        "sections": [
            {"section_id": "s1", "heading": "Real Slide", "content": "Content",
             "bullet_points": ["A"], "speaker_notes": None},
            {"section_id": "s2", "heading": "", "content": "",
             "bullet_points": [], "speaker_notes": None},
        ],
        "sources": [],
    }
    out = tmp_path / "skip_empty.pptx"
    build_pptx(data, out)

    from pptx import Presentation
    prs = Presentation(str(out))
    assert len(prs.slides) == 1


def test_pptx_sources_detection_variants(tmp_path):
    """Various sources heading names are all detected as sources slides."""
    for heading in ["Quellen", "Quellenangaben", "Referenzen", "Literaturverzeichnis", "Sources"]:
        data = {
            "title": "Test",
            "sections": [
                {"section_id": "s1", "heading": "Content", "content": "Text here",
                 "bullet_points": ["A"], "speaker_notes": None},
                {"section_id": "s2", "heading": heading, "content": "",
                 "bullet_points": ["Source 1", "Source 2"], "speaker_notes": None},
            ],
            "sources": [],
        }
        out = tmp_path / f"sources_{heading}.pptx"
        build_pptx(data, out)

        from pptx import Presentation
        prs = Presentation(str(out))
        # Should have 2 slides (content + sources), sources detected properly
        assert len(prs.slides) == 2


# ============================================================
# DOCX Builder — Sources Deduplication
# ============================================================

def test_docx_sources_dedup(tmp_path):
    """Sources from inline sections and top-level are deduplicated."""
    data = {
        "title": "Test",
        "sections": [
            {"heading": "Content", "content": "Some text.", "bullet_points": []},
            {"heading": "Quellen", "content": "", "bullet_points": ["Source A", "Source B"]},
        ],
        "sources": ["Source A", "Source C"],
    }
    out = tmp_path / "dedup.docx"
    build_docx(data, out)

    from docx import Document
    doc = Document(str(out))
    all_text = [p.text for p in doc.paragraphs]
    # "Source A" should appear only once (deduplicated)
    assert all_text.count("Source A") == 1
    assert "Source B" in all_text
    assert "Source C" in all_text


def test_docx_no_sources_when_empty(tmp_path):
    """No Quellen heading when there are no sources at all."""
    data = {
        "title": "Bare",
        "sections": [{"heading": "Chapter", "content": "Text.", "bullet_points": []}],
        "sources": [],
    }
    out = tmp_path / "nosources.docx"
    build_docx(data, out)

    from docx import Document
    doc = Document(str(out))
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert "Quellen" not in headings


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


# ============================================================
# PPTX Builder — Style & Visual Tests
# ============================================================

def test_pptx_backward_compat(synthesis_data, tmp_path):
    """build_pptx() without style args still works (defaults)."""
    out = tmp_path / "compat.pptx"
    build_pptx(synthesis_data, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_pptx_with_style(synthesis_data, modern_style, visual_config_disabled, tmp_path):
    """Modern style produces a valid PPTX with correct slide count."""
    out = tmp_path / "modern.pptx"
    build_pptx(synthesis_data, out, modern_style.visual, visual_config_disabled)
    assert out.exists()

    from pptx import Presentation
    prs = Presentation(str(out))
    assert len(prs.slides) == len(synthesis_data["sections"])


def test_pptx_visual_placeholder_right(synthesis_data_with_visuals, clean_style, visual_config_enabled, tmp_path):
    """Visual placeholder adds an extra shape to the content slide."""
    out = tmp_path / "visuals.pptx"
    build_pptx(synthesis_data_with_visuals, out, clean_style.visual, visual_config_enabled)

    from pptx import Presentation
    prs = Presentation(str(out))
    # Section index 2 (third slide) has a visual — should have more shapes than a normal content slide
    visual_slide = prs.slides[2]
    # Normal content slide: heading textbox + bullets textbox = 2 shapes
    # With visual placeholder: + 1 rounded rectangle = 3 shapes (+ possibly notes)
    assert len(visual_slide.shapes) >= 3


def test_pptx_visuals_disabled(synthesis_data_with_visuals, clean_style, visual_config_disabled, tmp_path):
    """When visuals are disabled, no placeholder shapes are added even if data has visuals."""
    out = tmp_path / "no_visuals.pptx"
    build_pptx(synthesis_data_with_visuals, out, clean_style.visual, visual_config_disabled)

    from pptx import Presentation
    prs = Presentation(str(out))
    # Content slide should have at most 2 shapes (heading + bullets)
    content_slide = prs.slides[2]
    assert len(content_slide.shapes) <= 2


def test_pptx_no_visual_on_title_slide(clean_style, visual_config_enabled, tmp_path):
    """Title slide (index 0) never gets visual placeholders."""
    data = {
        "title": "Test",
        "sections": [
            {"section_id": "s1", "heading": "Title", "content": "Sub",
             "bullet_points": [], "speaker_notes": None,
             "visuals": [{"type": "photo", "intent": "test", "placement": "right"}]},
            {"section_id": "s2", "heading": "Content", "content": "Body",
             "bullet_points": ["A", "B"], "speaker_notes": None},
        ],
        "sources": [],
    }
    out = tmp_path / "title_no_visual.pptx"
    build_pptx(data, out, clean_style.visual, visual_config_enabled)

    from pptx import Presentation
    prs = Presentation(str(out))
    title_slide = prs.slides[0]
    # Title slide: title textbox + subtitle textbox = 2 shapes max, no placeholder
    assert len(title_slide.shapes) <= 2


# ============================================================
# DOCX Builder — Style & Visual Tests
# ============================================================

def test_docx_backward_compat(synthesis_data, tmp_path):
    """build_docx() without style args still works (defaults)."""
    out = tmp_path / "compat.docx"
    build_docx(synthesis_data, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_docx_with_style_font(synthesis_data, modern_style, visual_config_disabled, tmp_path):
    """Modern style sets font to Arial."""
    out = tmp_path / "modern.docx"
    build_docx(synthesis_data, out, modern_style.visual, visual_config_disabled)

    from docx import Document
    doc = Document(str(out))
    normal_font = doc.styles["Normal"].font
    assert normal_font.name == "Arial"


def test_docx_visual_placeholder(synthesis_data_with_visuals, clean_style, visual_config_enabled, tmp_path):
    """Visual placeholder renders as an italic paragraph in the document."""
    out = tmp_path / "visuals.docx"
    build_docx(synthesis_data_with_visuals, out, clean_style.visual, visual_config_enabled)

    from docx import Document
    doc = Document(str(out))
    all_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Angriffsarten" in all_text  # The intent text should appear


def test_docx_visuals_disabled(synthesis_data_with_visuals, clean_style, visual_config_disabled, tmp_path):
    """No placeholder when visuals are disabled."""
    out = tmp_path / "no_visuals.docx"
    build_docx(synthesis_data_with_visuals, out, clean_style.visual, visual_config_disabled)

    from docx import Document
    doc = Document(str(out))
    # Check that the placeholder intent text does NOT appear
    italic_paragraphs = [
        p for p in doc.paragraphs
        if p.runs and any(r.italic for r in p.runs)
    ]
    # No italic visual placeholder paragraphs
    assert len(italic_paragraphs) == 0
