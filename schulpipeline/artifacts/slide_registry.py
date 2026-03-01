"""Slide type registry — scores and classifies sections into slide layout roles.

The registry maps each section in a synthesis payload to a SlideTypeSpec,
which tells the builder which render function and (eventually) which template
layout to use.

Scoring is two-tier:
  1. Hard position constraints short-circuit the scorer (title at index 0, etc.)
  2. Structure hint from ResolvedPreset gives a flat +8.0 bonus to matching specs.
     Content signals (bullets present, body text length, visual slot) are then
     scored and multiplied by style-specific weight modifiers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..presets import ResolvedPreset


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SlideTypeSpec:
    """Specification for a single slide type in the registry."""

    key: str                           # "title", "content", "sources", etc.
    render_fn: str                     # "title" | "content" | "sources" | "section_break"
    layout_name: str                   # template hint — "blank" for now
    structure_aliases: frozenset[str]  # preset.structure values that map here

    # Content signal weights — positive = prefers trait, negative = avoids
    wants_bullets: float = 0.0
    wants_body_text: float = 0.0
    wants_visual: float = 0.0
    wants_sparse: float = 0.0         # short/empty content, no bullets

    # Position constraints — evaluated BEFORE any scoring
    force_at_first: bool = False      # always wins at index 0
    never_first: bool = False
    never_last: bool = False


# ---------------------------------------------------------------------------
# Registry — the 6 initial slide types
# ---------------------------------------------------------------------------

_REGISTRY: tuple[SlideTypeSpec, ...] = (
    SlideTypeSpec(
        key="title", render_fn="title", layout_name="blank",
        structure_aliases=frozenset({"titel"}),
        wants_bullets=-5.0, wants_body_text=0.0,
        wants_visual=-2.0, wants_sparse=4.0,
        force_at_first=True,
    ),
    SlideTypeSpec(
        key="intro", render_fn="content", layout_name="blank",
        structure_aliases=frozenset({"einleitung"}),
        wants_bullets=1.0, wants_body_text=4.0,
        wants_visual=0.0, wants_sparse=-1.0,
        never_first=True,
    ),
    SlideTypeSpec(
        key="content", render_fn="content", layout_name="blank",
        structure_aliases=frozenset({
            "inhalt", "hauptteil", "kernpunkte",
            "argumentation", "gegenargumentation",
        }),
        wants_bullets=4.0, wants_body_text=1.0,
        wants_visual=2.0, wants_sparse=-2.0,
        never_first=True,
    ),
    SlideTypeSpec(
        key="closing", render_fn="content", layout_name="blank",
        structure_aliases=frozenset({"fazit"}),
        wants_bullets=1.0, wants_body_text=3.0,
        wants_visual=0.0, wants_sparse=1.0,
        never_first=True,
    ),
    SlideTypeSpec(
        key="sources", render_fn="sources", layout_name="blank",
        structure_aliases=frozenset({"quellen", "sources"}),
        wants_bullets=0.0, wants_body_text=0.0,
        wants_visual=-3.0, wants_sparse=3.0,
        never_first=True,
    ),
    SlideTypeSpec(
        key="section_break", render_fn="section_break", layout_name="blank",
        structure_aliases=frozenset({"section_break"}),
        wants_bullets=-4.0, wants_body_text=-4.0,
        wants_visual=-3.0, wants_sparse=6.0,
        never_first=True, never_last=True,
    ),
)


# ---------------------------------------------------------------------------
# Style multipliers
# ---------------------------------------------------------------------------

_STYLE_MULTIPLIERS: dict[str, dict[str, float]] = {
    "bullet-heavy": {"wants_bullets": 1.4, "wants_body_text": 0.6},
    "prose":        {"wants_bullets": 0.6, "wants_body_text": 1.6},
    "compact":      {"wants_bullets": 1.1, "wants_sparse": 1.3},
    "technical":    {"wants_bullets": 1.1, "wants_body_text": 1.1},
    "formal":       {"wants_bullets": 0.8, "wants_body_text": 1.3},
}


# ---------------------------------------------------------------------------
# Sources keyword set (canonical location — pptx_builder imports from here)
# ---------------------------------------------------------------------------

_SOURCES_KEYWORDS: frozenset[str] = frozenset({
    "quellen", "quellenangaben", "referenzen",
    "literaturverzeichnis", "literatur", "sources", "references",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_spec(key: str) -> SlideTypeSpec:
    """Return the SlideTypeSpec with the given key. Raises KeyError if not found."""
    for spec in _REGISTRY:
        if spec.key == key:
            return spec
    raise KeyError(f"No SlideTypeSpec with key '{key}' in registry")


def _extract_signals(section: dict) -> dict[str, float]:
    """Extract normalised content signals from a synthesis section dict.

    Returns a dict with keys matching the wants_* fields of SlideTypeSpec.
    All values are in range [0.0, 1.0].
    """
    bullets = section.get("bullet_points", [])
    content = section.get("content", "") or ""
    visuals = section.get("visuals", [])

    bullet_score = min(len(bullets) / 5.0, 1.0)
    body_score = min(len(content.split()) / 80.0, 1.0)
    visual_score = 1.0 if visuals else 0.0
    sparse_score = 1.0 if (not bullets and len(content.split()) < 20) else 0.0

    return {
        "wants_bullets":   bullet_score,
        "wants_body_text": body_score,
        "wants_visual":    visual_score,
        "wants_sparse":    sparse_score,
    }


def _score_spec(
    spec: SlideTypeSpec,
    signals: dict[str, float],
    structure_hint: str | None,
    style_mults: dict[str, float],
) -> float:
    """Compute a scalar score for one SlideTypeSpec given observed signals."""
    score = 0.0

    # Structure hint bonus
    if structure_hint and structure_hint in spec.structure_aliases:
        score += 8.0

    # Content signal scoring with style multipliers applied
    signal_fields = ("wants_bullets", "wants_body_text", "wants_visual", "wants_sparse")
    for field_name in signal_fields:
        weight = getattr(spec, field_name)
        mult = style_mults.get(field_name, 1.0)
        score += weight * mult * signals[field_name]

    return score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_section(
    section: dict,
    index: int,
    total: int,
    structure_hint: str | None = None,
    style: str = "bullet-heavy",
) -> SlideTypeSpec:
    """Classify one synthesis section into a SlideTypeSpec.

    Args:
        section:        The synthesis section dict (heading, content, bullet_points, ...).
        index:          Zero-based position of this section in the sections list.
        total:          Total number of sections.
        structure_hint: The preset.structure value for this position, if available.
        style:          The preset.style value. Example: "bullet-heavy".

    Returns:
        The winning SlideTypeSpec.
    """
    is_first = index == 0
    is_last = index == total - 1

    # --- Tier 1: Hard position constraints ---
    for spec in _REGISTRY:
        if spec.force_at_first and is_first:
            return spec

    # Disqualify specs that cannot appear at this position
    candidates = [
        spec for spec in _REGISTRY
        if not (spec.never_first and is_first)
        and not (spec.never_last and is_last)
    ]

    if not candidates:
        return _get_spec("content")

    # --- Tier 2: Sources keyword hard override ---
    heading = section.get("heading", "").lower().strip()
    if any(kw in heading for kw in _SOURCES_KEYWORDS):
        sources_spec = _get_spec("sources")
        if sources_spec in candidates:
            return sources_spec

    # --- Tier 3: Scored classification ---
    signals = _extract_signals(section)
    style_mults = _STYLE_MULTIPLIERS.get(style, {})

    scored = [
        (spec, _score_spec(spec, signals, structure_hint, style_mults))
        for spec in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Tie-break: prefer "content" (safe default)
    best_score = scored[0][1]
    winners = [spec for spec, score in scored if score == best_score]
    if len(winners) > 1:
        content_spec = _get_spec("content")
        if content_spec in winners:
            return content_spec

    return scored[0][0]


def classify_presentation(
    sections: list[dict],
    preset: "ResolvedPreset | None" = None,
) -> list[SlideTypeSpec]:
    """Classify all sections in a presentation at once.

    Args:
        sections: The synthesis sections list.
        preset:   Optional ResolvedPreset. When provided, structure hints and
                  style multipliers are applied. When None, only content signals
                  and position constraints are used (backward-compatible mode).

    Returns:
        A list of SlideTypeSpec, one per section, in the same order.
    """
    total = len(sections)
    structure = preset.structure if preset else []
    style = preset.style if preset else "bullet-heavy"

    result = []
    for i, section in enumerate(sections):
        hint = structure[i] if i < len(structure) else None
        spec = classify_section(section, i, total, hint, style)
        result.append(spec)
    return result
