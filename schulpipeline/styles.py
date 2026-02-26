"""Style & Visual System — presets, visual slot config, resolution."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any


# ============================================================
# Dataclasses
# ============================================================

@dataclass(frozen=True)
class ColorScheme:
    primary: str       # Headings, title bg
    secondary: str     # Subtitles, light accents
    accent: str        # Highlights, call-to-action
    bg_dark: str       # Dark slide backgrounds
    bg_light: str      # Content slide backgrounds
    text_dark: str     # Body text on light bg
    text_light: str    # Text on dark bg
    text_muted: str    # Secondary info


@dataclass(frozen=True)
class FontConfig:
    heading_family: str     # "Calibri", "Arial", etc.
    body_family: str        # "Calibri", "Arial", etc.
    heading_size_pt: int    # 36 (pptx headings)
    body_size_pt: int       # 18 (pptx body) / 11 (docx body)
    bullet_size_pt: int     # 16 (pptx bullets) / 11 (docx)


@dataclass(frozen=True)
class LayoutConfig:
    slide_ratio: str        # "16:9" | "4:3"
    margin_inches: float    # 0.8 (pptx) / 1.0 (docx)
    line_spacing: float     # 1.15 (docx paragraph spacing)
    title_slide_dark: bool  # True = dark bg title slide


@dataclass(frozen=True)
class ToneConfig:
    register: str           # "formal" | "neutral" | "casual"
    bullet_style: str       # "terse" | "descriptive" | "sentence"
    sentence_length: str    # "short" | "medium" | "elaborate"
    vocabulary_level: str   # "einfach" | "fachlich" | "akademisch"
    instructions: str       # Free-form, injected into synthesize prompt


@dataclass(frozen=True)
class VisualStyle:
    colors: ColorScheme
    fonts: FontConfig
    layout: LayoutConfig


@dataclass(frozen=True)
class StylePreset:
    key: str
    label: str
    visual: VisualStyle
    tone: ToneConfig


@dataclass(frozen=True)
class VisualSlotConfig:
    enabled: bool
    allowed_types: tuple[str, ...]
    default_placement: str       # "right" | "center"
    max_per_slide: int
    placeholder_style: str       # "box" | "outline" | "minimal"
    show_search_hint: bool


@dataclass
class VisualSlot:
    type: str            # "diagram" | "photo" | "icon" | "chart" | "screenshot"
    intent: str          # What the image should show
    placement: str       # "right" | "center"
    search_hint: str     # English search term for future auto-fill


# ============================================================
# Built-in Style Presets
# ============================================================

STYLE_PRESETS: dict[str, StylePreset] = {
    "clean": StylePreset(
        key="clean",
        label="Clean (Navy/White/Coral)",
        visual=VisualStyle(
            colors=ColorScheme(
                primary="#1E2761",
                secondary="#CADCFC",
                accent="#F96167",
                bg_dark="#1E2761",
                bg_light="#F5F7FA",
                text_dark="#212121",
                text_light="#FFFFFF",
                text_muted="#888888",
            ),
            fonts=FontConfig(
                heading_family="Calibri",
                body_family="Calibri",
                heading_size_pt=36,
                body_size_pt=18,
                bullet_size_pt=18,
            ),
            layout=LayoutConfig(
                slide_ratio="16:9",
                margin_inches=0.8,
                line_spacing=1.15,
                title_slide_dark=True,
            ),
        ),
        tone=ToneConfig(
            register="neutral",
            bullet_style="terse",
            sentence_length="short",
            vocabulary_level="fachlich",
            instructions="",
        ),
    ),
    "modern": StylePreset(
        key="modern",
        label="Modern (Charcoal/Teal)",
        visual=VisualStyle(
            colors=ColorScheme(
                primary="#333333",
                secondary="#E0F7F5",
                accent="#2DD4BF",
                bg_dark="#333333",
                bg_light="#F9FAFB",
                text_dark="#1F2937",
                text_light="#FFFFFF",
                text_muted="#6B7280",
            ),
            fonts=FontConfig(
                heading_family="Arial",
                body_family="Arial",
                heading_size_pt=36,
                body_size_pt=18,
                bullet_size_pt=18,
            ),
            layout=LayoutConfig(
                slide_ratio="16:9",
                margin_inches=0.8,
                line_spacing=1.15,
                title_slide_dark=True,
            ),
        ),
        tone=ToneConfig(
            register="neutral",
            bullet_style="sentence",
            sentence_length="medium",
            vocabulary_level="fachlich",
            instructions="",
        ),
    ),
    "minimal": StylePreset(
        key="minimal",
        label="Minimal (Black/White)",
        visual=VisualStyle(
            colors=ColorScheme(
                primary="#000000",
                secondary="#FFFFFF",
                accent="#666666",
                bg_dark="#000000",
                bg_light="#FFFFFF",
                text_dark="#000000",
                text_light="#FFFFFF",
                text_muted="#666666",
            ),
            fonts=FontConfig(
                heading_family="Georgia",
                body_family="Georgia",
                heading_size_pt=36,
                body_size_pt=18,
                bullet_size_pt=18,
            ),
            layout=LayoutConfig(
                slide_ratio="16:9",
                margin_inches=1.0,
                line_spacing=1.3,
                title_slide_dark=True,
            ),
        ),
        tone=ToneConfig(
            register="formal",
            bullet_style="descriptive",
            sentence_length="medium",
            vocabulary_level="akademisch",
            instructions="",
        ),
    ),
    "school": StylePreset(
        key="school",
        label="School (Green/Warm)",
        visual=VisualStyle(
            colors=ColorScheme(
                primary="#2D5F2D",
                secondary="#FFF8E1",
                accent="#FF8A65",
                bg_dark="#2D5F2D",
                bg_light="#FAFAF5",
                text_dark="#212121",
                text_light="#FFFFFF",
                text_muted="#888888",
            ),
            fonts=FontConfig(
                heading_family="Calibri",
                body_family="Calibri",
                heading_size_pt=36,
                body_size_pt=18,
                bullet_size_pt=18,
            ),
            layout=LayoutConfig(
                slide_ratio="16:9",
                margin_inches=0.8,
                line_spacing=1.15,
                title_slide_dark=True,
            ),
        ),
        tone=ToneConfig(
            register="casual",
            bullet_style="terse",
            sentence_length="short",
            vocabulary_level="einfach",
            instructions="",
        ),
    ),
    "corporate": StylePreset(
        key="corporate",
        label="Corporate (Blue/Steel)",
        visual=VisualStyle(
            colors=ColorScheme(
                primary="#1B3A5C",
                secondary="#E8EEF2",
                accent="#E67E22",
                bg_dark="#1B3A5C",
                bg_light="#F4F6F8",
                text_dark="#212121",
                text_light="#FFFFFF",
                text_muted="#7F8C8D",
            ),
            fonts=FontConfig(
                heading_family="Arial",
                body_family="Arial",
                heading_size_pt=36,
                body_size_pt=18,
                bullet_size_pt=18,
            ),
            layout=LayoutConfig(
                slide_ratio="16:9",
                margin_inches=0.8,
                line_spacing=1.15,
                title_slide_dark=True,
            ),
        ),
        tone=ToneConfig(
            register="formal",
            bullet_style="terse",
            sentence_length="medium",
            vocabulary_level="fachlich",
            instructions="",
        ),
    ),
    "dark": StylePreset(
        key="dark",
        label="Dark (Neon/Cyan)",
        visual=VisualStyle(
            colors=ColorScheme(
                primary="#1A1A2E",
                secondary="#E0E0E0",
                accent="#00D4FF",
                bg_dark="#1A1A2E",
                bg_light="#16213E",
                text_dark="#E0E0E0",
                text_light="#FFFFFF",
                text_muted="#888888",
            ),
            fonts=FontConfig(
                heading_family="Consolas",
                body_family="Arial",
                heading_size_pt=36,
                body_size_pt=18,
                bullet_size_pt=18,
            ),
            layout=LayoutConfig(
                slide_ratio="16:9",
                margin_inches=0.8,
                line_spacing=1.15,
                title_slide_dark=True,
            ),
        ),
        tone=ToneConfig(
            register="neutral",
            bullet_style="terse",
            sentence_length="short",
            vocabulary_level="fachlich",
            instructions="",
        ),
    ),
}

DEFAULT_STYLE = STYLE_PRESETS["clean"]

DEFAULT_VISUAL_SLOTS = VisualSlotConfig(
    enabled=True,
    allowed_types=("diagram", "photo", "icon", "chart", "screenshot"),
    default_placement="right",
    max_per_slide=1,
    placeholder_style="box",
    show_search_hint=True,
)

DISABLED_VISUAL_SLOTS = VisualSlotConfig(
    enabled=False,
    allowed_types=(),
    default_placement="right",
    max_per_slide=0,
    placeholder_style="box",
    show_search_hint=False,
)


# ============================================================
# Resolution Functions
# ============================================================

def resolve_style(config: Any, overrides: dict | None = None) -> StylePreset:
    """Resolve style from config + CLI overrides.

    Precedence: CLI --style > config.yaml style: > "clean" default.
    """
    overrides = overrides or {}

    # Determine the style key or dict
    style_spec = overrides.get("style") or getattr(config, "style", "clean") or "clean"

    # Simple string key
    if isinstance(style_spec, str):
        if style_spec not in STYLE_PRESETS:
            raise ValueError(
                f"Unknown style preset: '{style_spec}'. "
                f"Available: {', '.join(STYLE_PRESETS)}"
            )
        return STYLE_PRESETS[style_spec]

    # Dict form: {"base": "clean", "colors": {...}, "tone": {...}}
    if isinstance(style_spec, dict):
        base_key = style_spec.get("base", "clean")
        if base_key not in STYLE_PRESETS:
            raise ValueError(f"Unknown base style: '{base_key}'")
        base = STYLE_PRESETS[base_key]
        return _merge_style(base, style_spec)

    return DEFAULT_STYLE


def resolve_visual_config(config: Any, overrides: dict | None = None) -> VisualSlotConfig:
    """Resolve visual slot config from config + CLI overrides.

    Precedence: CLI --no-visuals > config.yaml visuals: > DEFAULT_VISUAL_SLOTS.
    """
    overrides = overrides or {}

    # CLI --no-visuals wins
    if overrides.get("no_visuals"):
        return DISABLED_VISUAL_SLOTS

    visuals_spec = getattr(config, "visuals", True)

    # Simple bool
    if visuals_spec is False:
        return DISABLED_VISUAL_SLOTS
    if visuals_spec is True:
        base = DEFAULT_VISUAL_SLOTS
    elif isinstance(visuals_spec, dict):
        base = _merge_visual_config(DEFAULT_VISUAL_SLOTS, visuals_spec)
    else:
        base = DEFAULT_VISUAL_SLOTS

    # CLI --visual-placement override
    if overrides.get("visual_placement"):
        base = VisualSlotConfig(
            enabled=base.enabled,
            allowed_types=base.allowed_types,
            default_placement=overrides["visual_placement"],
            max_per_slide=base.max_per_slide,
            placeholder_style=base.placeholder_style,
            show_search_hint=base.show_search_hint,
        )

    return base


# ============================================================
# Color / Helper Functions
# ============================================================

@lru_cache(maxsize=64)
def _to_rgb(hex_str: str):
    """Convert '#RRGGBB' to pptx RGBColor. Cached."""
    from pptx.dml.color import RGBColor
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: '{hex_str}'")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        raise ValueError(f"Invalid hex color: '{hex_str}'")
    return RGBColor(r, g, b)


@lru_cache(maxsize=64)
def _to_docx_rgb(hex_str: str):
    """Convert '#RRGGBB' to docx RGBColor. Cached."""
    from docx.shared import RGBColor
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: '{hex_str}'")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        raise ValueError(f"Invalid hex color: '{hex_str}'")
    return RGBColor(r, g, b)


def _lighten(hex_color: str, amount: float = 0.15) -> str:
    """Lighten a hex color by blending toward white. Returns hex string."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f"#{r:02X}{g:02X}{b:02X}"


def _bullet_instruction(bullet_style: str) -> str:
    """Map bullet_style to German instruction string."""
    return {
        "terse": "Kurz und knapp, max 10 Wörter pro Stichpunkt",
        "descriptive": "Beschreibend, 1-2 Sätze pro Stichpunkt",
        "sentence": "Vollständige Sätze als Stichpunkte",
    }.get(bullet_style, "Kurz und knapp")


def _sentence_instruction(sentence_length: str) -> str:
    """Map sentence_length to German instruction string."""
    return {
        "short": "Kurze Sätze, max 15 Wörter",
        "medium": "Mittellange Sätze",
        "elaborate": "Ausführliche Sätze, Details einbauen",
    }.get(sentence_length, "Mittellange Sätze")


# ============================================================
# Internal merge helpers
# ============================================================

def _merge_style(base: StylePreset, overrides: dict) -> StylePreset:
    """Create a new StylePreset by merging partial overrides into a base."""
    colors = base.visual.colors
    if "colors" in overrides:
        c = overrides["colors"]
        colors = ColorScheme(
            primary=c.get("primary", colors.primary),
            secondary=c.get("secondary", colors.secondary),
            accent=c.get("accent", colors.accent),
            bg_dark=c.get("bg_dark", colors.bg_dark),
            bg_light=c.get("bg_light", colors.bg_light),
            text_dark=c.get("text_dark", colors.text_dark),
            text_light=c.get("text_light", colors.text_light),
            text_muted=c.get("text_muted", colors.text_muted),
        )

    fonts = base.visual.fonts
    if "fonts" in overrides:
        f = overrides["fonts"]
        fonts = FontConfig(
            heading_family=f.get("heading_family", fonts.heading_family),
            body_family=f.get("body_family", fonts.body_family),
            heading_size_pt=f.get("heading_size_pt", fonts.heading_size_pt),
            body_size_pt=f.get("body_size_pt", fonts.body_size_pt),
            bullet_size_pt=f.get("bullet_size_pt", fonts.bullet_size_pt),
        )

    layout = base.visual.layout
    if "layout" in overrides:
        lo = overrides["layout"]
        layout = LayoutConfig(
            slide_ratio=lo.get("slide_ratio", layout.slide_ratio),
            margin_inches=lo.get("margin_inches", layout.margin_inches),
            line_spacing=lo.get("line_spacing", layout.line_spacing),
            title_slide_dark=lo.get("title_slide_dark", layout.title_slide_dark),
        )

    tone = base.tone
    if "tone" in overrides:
        t = overrides["tone"]
        tone = ToneConfig(
            register=t.get("register", tone.register),
            bullet_style=t.get("bullet_style", tone.bullet_style),
            sentence_length=t.get("sentence_length", tone.sentence_length),
            vocabulary_level=t.get("vocabulary_level", tone.vocabulary_level),
            instructions=t.get("instructions", tone.instructions),
        )

    return StylePreset(
        key=f"{base.key}_custom",
        label=f"{base.label} (custom)",
        visual=VisualStyle(colors=colors, fonts=fonts, layout=layout),
        tone=tone,
    )


def _merge_visual_config(base: VisualSlotConfig, overrides: dict) -> VisualSlotConfig:
    """Create a new VisualSlotConfig by merging partial overrides."""
    allowed = overrides.get("allowed_types")
    if allowed is not None:
        allowed = tuple(allowed)
    else:
        allowed = base.allowed_types

    return VisualSlotConfig(
        enabled=overrides.get("enabled", base.enabled),
        allowed_types=allowed,
        default_placement=overrides.get("default_placement", base.default_placement),
        max_per_slide=overrides.get("max_per_slide", base.max_per_slide),
        placeholder_style=overrides.get("placeholder_style", base.placeholder_style),
        show_search_hint=overrides.get("show_search_hint", base.show_search_hint),
    )
