"""Tests for the style & visual system — presets, resolution, helpers."""

from dataclasses import FrozenInstanceError

import pytest

from schulpipeline.config import BackendConfig, OutputConfig, PipelineConfig, ResearchConfig
from schulpipeline.styles import (
    DEFAULT_STYLE,
    DEFAULT_VISUAL_SLOTS,
    STYLE_PRESETS,
    _bullet_instruction,
    _lighten,
    _sentence_instruction,
    _to_docx_rgb,
    _to_rgb,
    resolve_style,
    resolve_visual_config,
)

# --- Helpers to build minimal PipelineConfig ---


def _cfg(**kwargs):
    """Build a PipelineConfig with style/visuals overrides."""
    defaults = dict(
        backends={"mock": BackendConfig(name="mock", api_key="k")},
        cascade={},
        research=ResearchConfig(enabled=False),
        output=OutputConfig(),
        style="clean",
        visuals=True,
    )
    defaults.update(kwargs)
    return PipelineConfig(**defaults)


# ============================================================
# resolve_style
# ============================================================


def test_resolve_style_default():
    config = _cfg()
    style = resolve_style(config)
    assert style.key == "clean"
    assert style.visual.colors.primary == "#1E2761"


def test_resolve_style_by_name():
    for key in STYLE_PRESETS:
        config = _cfg(style=key)
        assert resolve_style(config).key == key


def test_resolve_style_unknown_raises():
    config = _cfg(style="nonexistent")
    with pytest.raises(ValueError, match="Unknown style preset"):
        resolve_style(config)


def test_resolve_style_dict_override():
    config = _cfg(style={"base": "clean", "colors": {"primary": "#FF0000"}})
    style = resolve_style(config)
    assert style.visual.colors.primary == "#FF0000"
    # Other colors unchanged from clean
    assert style.visual.colors.secondary == "#CADCFC"
    assert style.key == "clean_custom"


def test_resolve_style_tone_override():
    config = _cfg(style={"base": "clean", "tone": {"register": "casual"}})
    style = resolve_style(config)
    assert style.tone.register == "casual"
    # Other tone fields unchanged
    assert style.tone.bullet_style == "terse"


def test_resolve_style_cli_overrides_config():
    config = _cfg(style="modern")
    style = resolve_style(config, overrides={"style": "dark"})
    assert style.key == "dark"


def test_resolve_style_none_overrides():
    config = _cfg(style="corporate")
    style = resolve_style(config, overrides=None)
    assert style.key == "corporate"


# ============================================================
# resolve_visual_config
# ============================================================


def test_resolve_visual_config_default():
    config = _cfg()
    vc = resolve_visual_config(config)
    assert vc.enabled is True
    assert vc.max_per_slide == 1
    assert "diagram" in vc.allowed_types


def test_resolve_visual_no_visuals_cli():
    config = _cfg()
    vc = resolve_visual_config(config, overrides={"no_visuals": True})
    assert vc.enabled is False
    assert vc.max_per_slide == 0


def test_resolve_visual_config_false():
    config = _cfg(visuals=False)
    vc = resolve_visual_config(config)
    assert vc.enabled is False


def test_resolve_visual_partial_override():
    config = _cfg(visuals={"enabled": True, "max_per_slide": 2})
    vc = resolve_visual_config(config)
    assert vc.enabled is True
    assert vc.max_per_slide == 2
    assert vc.show_search_hint is True  # unchanged default


def test_resolve_visual_placement_override():
    config = _cfg()
    vc = resolve_visual_config(config, overrides={"visual_placement": "center"})
    assert vc.default_placement == "center"


# ============================================================
# _to_rgb / _to_docx_rgb
# ============================================================


def test_to_rgb_valid():
    rgb = _to_rgb("#1E2761")
    assert rgb == _to_rgb("#1E2761")  # cached


def test_to_rgb_no_hash():
    # Should also work without #
    rgb = _to_rgb("1E2761")
    assert rgb is not None


def test_to_rgb_invalid():
    with pytest.raises(ValueError, match="Invalid hex"):
        _to_rgb("not-a-color")


def test_to_rgb_short():
    with pytest.raises(ValueError, match="Invalid hex"):
        _to_rgb("#FFF")


def test_to_docx_rgb_valid():
    rgb = _to_docx_rgb("#888888")
    assert rgb is not None


def test_all_presets_valid_colors():
    """All 6 presets have valid hex colors that convert without error."""
    for key, preset in STYLE_PRESETS.items():
        colors = preset.visual.colors
        for field_name in [
            "primary",
            "secondary",
            "accent",
            "bg_dark",
            "bg_light",
            "text_dark",
            "text_light",
            "text_muted",
        ]:
            hex_val = getattr(colors, field_name)
            _to_rgb(hex_val)  # Should not raise


# ============================================================
# _lighten
# ============================================================


def test_lighten_moves_toward_white():
    lightened = _lighten("#000000", 0.5)
    # Should be roughly #7F7F7F
    assert lightened.startswith("#")
    assert lightened != "#000000"


def test_lighten_white_stays_white():
    assert _lighten("#FFFFFF", 0.5) == "#FFFFFF"


# ============================================================
# Tone instruction helpers
# ============================================================


def test_bullet_instruction_all_styles():
    for style in ("terse", "descriptive", "sentence"):
        result = _bullet_instruction(style)
        assert isinstance(result, str)
        assert len(result) > 5


def test_sentence_instruction_all_lengths():
    for length in ("short", "medium", "elaborate"):
        result = _sentence_instruction(length)
        assert isinstance(result, str)
        assert len(result) > 5


def test_bullet_instruction_unknown_fallback():
    assert _bullet_instruction("unknown") == "Kurz und knapp"


# ============================================================
# Frozen dataclass checks
# ============================================================


def test_style_preset_frozen():
    style = DEFAULT_STYLE
    with pytest.raises(FrozenInstanceError):
        style.key = "changed"


def test_visual_slot_config_frozen():
    vc = DEFAULT_VISUAL_SLOTS
    with pytest.raises(FrozenInstanceError):
        vc.enabled = False


# ============================================================
# Preset completeness
# ============================================================


def test_six_presets_exist():
    expected = {"clean", "modern", "minimal", "school", "corporate", "dark"}
    assert set(STYLE_PRESETS.keys()) == expected


def test_default_style_is_clean():
    assert DEFAULT_STYLE.key == "clean"
