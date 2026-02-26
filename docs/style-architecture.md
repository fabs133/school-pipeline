# Style & Visual System — Architecture

## Problem

The pipeline produces structurally correct output but:
1. **Visual design** is hardcoded (Navy/Coral colors, Calibri, fixed spacing)
2. **Writing tone** is hardcoded ("sachlich, Berufsschul-Niveau")
3. **Non-text content** doesn't exist — slides are text-only walls

Users can't control how artifacts look, read, or where images belong
without editing code.

## Three Independent Axes

```
StylePreset          VisualSlotConfig         OutputPreset (exists)
├── visual              ├── enabled              ├── format
│   ├── colors          ├── placement            ├── structure
│   ├── fonts           ├── allowed_types        └── constraints
│   └── layout          └── placeholder_style
└── tone
    ├── register
    ├── bullet_style
    └── instructions

         │                    │                       │
         ▼                    ▼                       ▼
   ┌───────────┐    ┌──────────────────┐    ┌────────────────┐
   │ Synthesize │    │ Synthesize       │    │ Plan / Intake  │
   │ (prompt)   │    │ (visual hints)   │    │ (structure)    │
   └─────┬─────┘    └────────┬─────────┘    └────────────────┘
         │                   │
         ▼                   ▼
   ┌─────────────────────────────────┐
   │         Artifact Builders       │
   │  pptx: styled + placeholders   │
   │  docx: styled + placeholders   │
   │  md: text only (unchanged)     │
   └─────────────────────────────────┘
```

These compose freely:
- `style: modern` + `visuals: enabled` → teal-themed slides with placeholders
- `style: minimal` + `visuals: disabled` → black/white text-only
- `style: corporate` + `visuals: enabled` → blue slides with diagram slots

---

## Data Model

### StylePreset (controls look & tone)

```python
@dataclass(frozen=True)
class ColorScheme:
    primary: str      # "#1E2761" — headings, title bg
    secondary: str    # "#CADCFC" — subtitles, light accents
    accent: str       # "#F96167" — highlights, call-to-action
    bg_dark: str      # "#1E2761" — dark slide backgrounds
    bg_light: str     # "#F5F7FA" — content slide backgrounds
    text_dark: str    # "#212121" — body text on light bg
    text_light: str   # "#FFFFFF" — text on dark bg
    text_muted: str   # "#888888" — secondary info

@dataclass(frozen=True)
class FontConfig:
    heading_family: str    # "Calibri"
    body_family: str       # "Calibri"
    heading_size_pt: int   # 36 (pptx) / 16 (docx)
    body_size_pt: int      # 18 (pptx) / 11 (docx)
    bullet_size_pt: int    # 16 (pptx) / 11 (docx)

@dataclass(frozen=True)
class LayoutConfig:
    slide_ratio: str       # "16:9" | "4:3"
    margin_inches: float   # 0.8 (pptx) / 1.0 (docx)
    line_spacing: float    # 1.15 (docx) / 12pt gap (pptx)
    title_slide_dark: bool # True = dark bg title slide

@dataclass(frozen=True)
class ToneConfig:
    register: str          # "formal" | "neutral" | "casual"
    bullet_style: str      # "terse" | "descriptive" | "sentence"
    sentence_length: str   # "short" | "medium" | "elaborate"
    vocabulary_level: str  # "einfach" | "fachlich" | "akademisch"
    instructions: str      # Free-form, injected into synthesize prompt

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
```

### VisualSlotConfig (controls non-text content)

```python
@dataclass(frozen=True)
class VisualSlotConfig:
    enabled: bool                    # Master switch
    allowed_types: list[str]         # ["diagram", "photo", "icon", "chart", "screenshot"]
    default_placement: str           # "right" | "center" | "background"
    max_per_slide: int               # 1 (default) — prevents clutter
    placeholder_style: str           # "box" | "outline" | "minimal"
    show_search_hint: bool           # Include search terms on placeholder
```

### VisualSlot (per-section, LLM-generated)

```python
@dataclass
class VisualSlot:
    type: str            # "diagram" | "photo" | "icon" | "chart" | "screenshot"
    intent: str          # "Zeigt den Aufbau des OSI-Modells als Schichtendiagramm"
    placement: str       # "right" | "center" | "background"
    search_hint: str     # "OSI model layers diagram" — for future auto-fill
```

This lands in the synthesis output:

```json
{
  "section_id": "section_03",
  "heading": "Bedrohungen",
  "content": "...",
  "bullet_points": ["...", "..."],
  "speaker_notes": "...",
  "visuals": [
    {
      "type": "diagram",
      "intent": "Übersicht der häufigsten Angriffsarten mit Häufigkeit",
      "placement": "right",
      "search_hint": "cyber attack types infographic"
    }
  ]
}
```

---

## Built-in Style Packs

| Key | Colors | Fonts | Tone | Best For |
|-----|--------|-------|------|----------|
| `clean` | Navy/White/Coral | Calibri | neutral, terse | **Default** |
| `modern` | Charcoal/#2DD4BF teal | Arial | neutral, sentence | Contemporary |
| `minimal` | Black/White/#666 gray | Georgia (serif) | formal, descriptive | Academic |
| `school` | #2D5F2D green/warm | Calibri | casual, short | Informal school |
| `corporate` | #1B3A5C blue/steel/#E67E22 | Arial | formal, fachlich | Business |
| `dark` | #1A1A2E/white/#00D4FF cyan | Consolas heading, Arial body | neutral, terse | Tech/dev |

Default visual slot config:

```python
DEFAULT_VISUAL_SLOTS = VisualSlotConfig(
    enabled=True,
    allowed_types=["diagram", "photo", "icon", "chart", "screenshot"],
    default_placement="right",
    max_per_slide=1,
    placeholder_style="box",
    show_search_hint=True,
)

DISABLED_VISUAL_SLOTS = VisualSlotConfig(
    enabled=False,
    allowed_types=[],
    default_placement="right",
    max_per_slide=0,
    placeholder_style="box",
    show_search_hint=False,
)
```

---

## Config Surface

### CLI

```bash
# Style only
schulpipeline "..." --style modern

# Style + visuals off
schulpipeline "..." --style corporate --no-visuals

# Everything explicit
schulpipeline "..." --style dark --visuals --visual-placement center
```

### config.yaml

```yaml
# Simple: use built-in
style: modern
visuals: true

# Override fields
style:
  base: clean
  colors:
    primary: "#2D5F2D"
  tone:
    register: casual

visuals:
  enabled: true
  max_per_slide: 2
  placeholder_style: outline
  show_search_hint: false
```

---

## Pipeline Integration

### Resolution Order (config precedence)

```
CLI flags  →  config.yaml  →  preset defaults  →  hardcoded defaults
(highest)                                          (lowest)
```

```python
# In Pipeline.run():
style = resolve_style(config, cli_overrides)
visual_slots = resolve_visual_config(config, cli_overrides)
context["style"] = style
context["visual_slots"] = visual_slots
```

### SynthesizeStage

Two injections into the prompt:

**1. Tone suffix** (replaces hardcoded "sachlich, Berufsschul-Niveau"):

```python
tone = context["style"].tone

tone_block = f"""
Stilanweisungen:
- Register: {tone.register}
- Stichpunkte: {_bullet_instruction(tone.bullet_style)}
- Satzlänge: {_sentence_instruction(tone.sentence_length)}
- Vokabular: {tone.vocabulary_level}
{tone.instructions}
"""
```

**2. Visual slot instruction** (only if enabled):

```python
if context["visual_slots"].enabled:
    allowed = ", ".join(context["visual_slots"].allowed_types)
    max_n = context["visual_slots"].max_per_slide

    prompt += f"""
Für jede Folie/Sektion: Überlege ob ein visuelles Element den Inhalt
unterstützen würde. Wenn ja, füge ein "visuals" Array hinzu:

"visuals": [
  {{
    "type": "<{allowed}>",
    "intent": "Was das Bild zeigen soll (1 Satz)",
    "placement": "right|center",
    "search_hint": "Englischer Suchbegriff für Bildersuche"
  }}
]

Regeln:
- Nicht jede Folie braucht ein Visual — nur wo es den Inhalt stärkt
- Titelfolie und Quellenfolie: kein Visual
- Maximal {max_n} Visual(s) pro Folie
- type "diagram" für Prozesse/Abläufe/Strukturen
- type "chart" für Daten/Statistiken/Vergleiche
- type "photo" für reale Objekte/Orte/Personen
- type "icon" für abstrakte Konzepte
- type "screenshot" für Software/UI-Beispiele
"""
```

### ArtifactStage

Passes both configs to builders:

```python
style = context.get("style", DEFAULT_STYLE)
visual_config = context.get("visual_slots", DEFAULT_VISUAL_SLOTS)

if artifact_type == "pptx":
    build_pptx(synthesis, output_path, style.visual, visual_config)
elif artifact_type == "docx":
    build_docx(synthesis, output_path, style.visual, visual_config)
```

### PPTX Builder — Placeholder Rendering

Content slide layout adapts when visual is placed on the right:

```
┌─────────────────────────────────────────────────┐
│  Heading                                         │
│                                                  │
│  • Bullet 1              ┌─────────────────┐    │
│  • Bullet 2              │  📊              │    │
│  • Bullet 3              │  [intent text]   │    │
│  • Bullet 4              │                  │    │
│                           │  🔍 search hint  │    │
│                           └─────────────────┘    │
└─────────────────────────────────────────────────┘
      text area: 6.5"           placeholder: 5.0"
```

Center placement uses full width below the heading:

```
┌─────────────────────────────────────────────────┐
│  Heading                                         │
│                                                  │
│  • Bullet 1    • Bullet 2    • Bullet 3         │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │  📷  [intent text]                       │    │
│  │  🔍  search hint                         │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

Placeholder rendering:

```python
def _add_visual_placeholder(slide, visual, style, config):
    """Styled placeholder box with dashed border."""

    TYPE_ICONS = {
        "diagram": "📊", "photo": "📷", "chart": "📈",
        "icon": "🎯", "screenshot": "🖥️",
    }

    # Position based on placement
    if visual["placement"] == "right":
        left, top = Inches(7.5), Inches(1.8)
        width, height = Inches(5.0), Inches(4.5)
    else:  # center
        left, top = Inches(0.8), Inches(4.0)
        width, height = Inches(11.73), Inches(3.0)

    # Rounded rectangle, dashed border, light fill
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = _lighten(style.colors.bg_light)
    shape.line.color.rgb = _to_rgb(style.colors.text_muted)
    shape.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    shape.line.width = Pt(1.5)

    # Icon + intent + search hint
    icon = TYPE_ICONS.get(visual["type"], "🖼️")
    label = f"{icon}  {visual['intent']}"
    if config.show_search_hint and visual.get("search_hint"):
        label += f"\n\n🔍 {visual['search_hint']}"

    tf = shape.text_frame
    tf.word_wrap = True
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    p = tf.paragraphs[0]
    p.text = label
    p.font.size = Pt(12)
    p.font.color.rgb = _to_rgb(style.colors.text_muted)
```

### DOCX Builder — Placeholder Rendering

Lighter approach — styled italic paragraph with border:

```python
def _add_visual_placeholder(doc, visual, style):
    """Gray italic placeholder paragraph."""
    TYPE_ICONS = {"diagram": "📊", "photo": "📷", "chart": "📈",
                  "icon": "🎯", "screenshot": "🖥️"}

    icon = TYPE_ICONS.get(visual["type"], "🖼️")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    run = p.add_run(f"{icon}  [{visual['intent']}]")
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    run.font.italic = True
```

---

## Implementation Steps (single block)

### Step 1: `schulpipeline/styles.py` — NEW
- All dataclasses (ColorScheme through StylePreset, VisualSlotConfig, VisualSlot)
- 6 STYLE_PRESETS + DEFAULT/DISABLED visual configs
- `resolve_style(config, overrides) → StylePreset`
- `resolve_visual_config(config, overrides) → VisualSlotConfig`
- Helpers: `_to_rgb(hex_str) → RGBColor`, tone instruction builders

### Step 2: Refactor `artifacts/pptx_builder.py`
- New signature: `build_pptx(synthesis, path, visual_style, visual_config)`
- Remove global COLORS → use visual_style.colors
- Apply fonts from visual_style.fonts
- Add `_add_visual_placeholder()`
- Narrow text area when visual placement is "right"

### Step 3: Refactor `artifacts/docx_builder.py`
- New signature: `build_docx(synthesis, path, visual_style, visual_config)`
- Apply heading font/color from style
- Add visual placeholder paragraphs between sections

### Step 4: Update `stages/synthesize.py`
- Build tone suffix from ToneConfig
- Add conditional visual slot instruction block
- Update JSON schema example to include optional `visuals`

### Step 5: Update `stages/artifact.py`
- Read style + visual_config from context → pass to builders

### Step 6: Wire `pipeline.py`
- resolve_style() + resolve_visual_config() at run start
- Store both in context dict

### Step 7: Update `config.py`
- Parse `style:` and `visuals:` from config.yaml
- Add fields to PipelineConfig

### Step 8: Update `cli.py`
- `--style`, `--no-visuals`, `--visual-placement` flags

### Step 9: Update `config.yaml` + `specs/synthesis.json`
- Default config values
- Optional `visuals` array in synthesis spec

### Step 10: Tests
- `test_styles.py`: resolution, overrides, hex validation, tone builders
- `test_pptx_builder.py`: placeholder position, colors match, layout adapts
- `test_docx_builder.py`: placeholder rendered, fonts applied
- `test_synthesize.py`: tone suffix in prompt, visual instruction conditional
- Update e2e tests to verify style passthrough

---

## Spec Schema Update

`specs/synthesis.json` — `visuals` is optional per section:

```json
{
  "properties": {
    "sections": {
      "items": {
        "properties": {
          "visuals": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "type": {
                  "enum": ["diagram", "photo", "icon", "chart", "screenshot"]
                },
                "intent": { "type": "string" },
                "placement": { "enum": ["right", "center"] },
                "search_hint": { "type": "string" }
              },
              "required": ["type", "intent"]
            }
          }
        }
      }
    }
  }
}
```

---

## Future Extensions (NOT now)

| Feature | Hook Point | Effort |
|---------|-----------|--------|
| Auto-fill via image search | `search_hint` field | Medium |
| Local asset library | `~/.schulpipeline/assets/` | Low |
| .pptx template import | Alternative to code-built slides | High |
| HTML/CSS themed output | New builder | Medium |
| Per-slide style override | Section metadata | Overkill |

---

## Decision Log

| # | Decision | Choice | Reason |
|---|----------|--------|--------|
| 1 | Three axes (style / visuals / output) | Independent configs | Compose freely, configure independently |
| 2 | Same implementation block | Single integration pass | Two halves break when combined later |
| 3 | LLM decides visual content | `visuals` in synthesis output | LLM knows context; user controls policy |
| 4 | Placeholder not auto-image | Styled box with intent text | Honest, copyright-safe, user keeps control |
| 5 | search_hint for future | Optional field on placeholder | Zero-cost prep for image search |
| 6 | Max 1 visual per slide | Prevents over-decoration | Override to 2 via config |
| 7 | Tone via prompt suffix | No extra LLM call | Free and effective |
| 8 | System-safe fonts only | Calibri, Arial, Georgia, Consolas | Guaranteed to render everywhere |
