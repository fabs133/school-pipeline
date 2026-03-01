"""Convert synthesis stage output to slideforge Presentation model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from slideforge.models import Presentation, PresentationStyle, Slide

from .slide_registry import classify_presentation

if TYPE_CHECKING:
    from ..presets import ResolvedPreset

# Maps SlideTypeSpec.key → slideforge layout name
_SPEC_TO_LAYOUT: dict[str, str] = {
    "title": "SP_Title",
    "intro": "SP_Intro",
    "content": "SP_Content",
    "closing": "SP_Closing",
    "sources": "SP_Sources",
    "section_break": "SP_SectionBreak",
}

# Maps schulpipeline preset style → slideforge PresentationStyle
_PRESET_STYLE_MAP: dict[str, PresentationStyle] = {
    "bullet-heavy": PresentationStyle.SENTENCES,
    "compact": PresentationStyle.SENTENCES,
    "prose": PresentationStyle.SENTENCES,
}


def synthesis_to_presentation(
    synthesis: dict,
    preset: "ResolvedPreset | None" = None,
    name: str | None = None,
    style: str | None = None,
) -> Presentation:
    """Convert a synthesis dict into a slideforge Presentation.

    Args:
        synthesis: The synthesize stage output dict with keys:
                   title, sections, sources.
        preset:    Optional ResolvedPreset for classification hints.
        name:      Presentation name (defaults to synthesis title).
        style:     Optional style override ("keywords", "sentences", "academic").
                   Falls back to preset style mapping, then "sentences".

    Returns:
        A slideforge Presentation ready for rendering or review.
    """
    sections = synthesis.get("sections", [])
    title = synthesis.get("title", "Präsentation")
    sources = synthesis.get("sources", [])

    classifications = classify_presentation(sections, preset)

    slides: list[Slide] = []
    for section, spec in zip(sections, classifications):
        heading = section.get("heading", "").strip()
        content = section.get("content", "").strip()
        bullets = section.get("bullet_points", [])

        # Skip empty sections
        if not heading and not content and not bullets:
            continue

        layout = _SPEC_TO_LAYOUT.get(spec.key, "SP_Content")

        # Build body as newline-separated string
        if spec.key == "sources":
            all_sources = sources or bullets
            body = "\n".join(all_sources)
        elif spec.key == "title":
            body = content  # subtitle
        else:
            # Prefer bullets, fall back to prose
            if bullets:
                body = "\n".join(bullets)
            else:
                body = content

        slides.append(
            Slide(
                layout=layout,
                title=heading or title,
                body=body,
                notes=section.get("speaker_notes", "") or "",
            )
        )

    # Resolve presentation style
    if style:
        pres_style = PresentationStyle(style)
    elif preset:
        pres_style = _PRESET_STYLE_MAP.get(preset.style, PresentationStyle.SENTENCES)
    else:
        pres_style = PresentationStyle.SENTENCES

    return Presentation(
        name=name or title,
        slides=slides,
        style=pres_style,
    )
