# Project Assessment — schulpipeline

**Date:** 2026-02-25
**Scope:** Full codebase review after scanner v3 implementation + e2e validation run
**Test suite:** 170 tests, all passing

---

## E2E Run Results

Two end-to-end runs were executed against `IT_M1_A1_Recherche.docx`:

| Run | Output | Size | Duration | Status |
|-----|--------|------|----------|--------|
| Pipeline test (md) | `Recherchewege_und_-moeglichkeiten_zum_Thema_Fair-Trade.md` | 1.5 KB | 15.2s | Success |
| E2E v2 (pptx) | `Recherchewege_und_-moeglichkeiten_zum_Thema_Fair-Trade.pptx` | 52 KB | 18.2s | Generated but **broken/unusable** |

Pipeline stages ran correctly: intake → plan → research → synthesize → artifact.
Backends used: groq + gemini (via cascade). Cost: $0.00 (free tier models).

---

## Known Errors

### ERR-1: PPTX output is broken / unusable

The generated `.pptx` file cannot be opened correctly. Likely causes:

- **Slide dimensions mismatch:** 16:9 mode uses 13.33×7.5 inches instead of standard 10×5.625 (`pptx_builder.py:46-50`)
- **Visual placeholder overlap:** Fixed positioning at `(7.5", 1.8")` with 5" width doesn't account for content overflow (`pptx_builder.py:241-246`)
- **Font availability:** Sets Calibri/Arial without validation — missing fonts cause layout shift (`pptx_builder.py:94-96`)
- **Empty sections:** Sections with missing heading/content/bullet_points still create slides with no visible text
- **Sources slide detection brittle:** Only matches `"quellen"` in heading — misses "Quellenangaben", "Referenzen" (`pptx_builder.py:59`)

### ERR-2: UnicodeEncodeError on Windows console

```
UnicodeEncodeError: 'charmap' codec can't encode characters in position 2-51
```

The e2e script uses box-drawing character `─` which cp1252 (Windows default) cannot encode. The CLI itself also uses Unicode symbols (`✓`, `✗`, `▶`, `⏸`) in `cli.py:121,175-184` that will break on non-UTF8 consoles.

### ERR-3: Ollama backend silently fails

```
Unknown backend 'ollama' — skipping
```

Ollama is defined in `BACKEND_DEFAULTS` (`config.py:27-28`) but **not** in `BACKEND_FACTORIES` (`router.py:30-35`). Configuring ollama in `config.yaml` silently skips it. The `[project.optional-dependencies] ollama = []` in pyproject.toml is a no-op.

---

## Critical Issues

### CRIT-1: JSON markdown fence parsing is fragile

`intake.py:143-152` strips markdown fences but assumes `` ``` `` without language identifier. If an LLM returns `` ```json ``, parsing breaks silently.

### CRIT-2: Hardcoded max_tokens may truncate long presentations

`synthesize.py:208` sets `max_tokens=8192`. For 10+ slides with 4+ bullet points each, this is insufficient and will produce truncated JSON responses.

---

## High Severity

| ID | Location | Issue |
|----|----------|-------|
| HIGH-1 | `pptx_builder.py` | Emoji icons (🎯📷📊) may not render in all fonts/systems |
| HIGH-2 | `cli.py:519` | `read_text(encoding="utf-8")` — no fallback for Latin-1 encoded input files |
| HIGH-3 | `pipeline.py:154` | Spec validation warns but continues silently if spec file missing |
| HIGH-4 | `synthesize.py:216-224` | Fallback sections set `speaker_notes: None` which may violate schema |
| HIGH-5 | `styles.py` / `artifact.py` | Color validation happens at artifact stage — LLM-generated invalid hex crashes late |
| HIGH-6 | `docx_builder.py:87-93` | "Quellen" heading always added even when sources list is empty |

---

## Medium Severity

| ID | Location | Issue |
|----|----------|-------|
| MED-1 | `docx_builder.py:58,69` | Heading levels hardcoded to 0/1 — no deeper hierarchy support |
| MED-2 | `artifact.py:126-129` | Umlaut replacement incomplete — only ä/ö/ü, not ß or accented chars |
| MED-3 | `synthesize.py:110-138` | Visual slot instructions don't sync with `visual_slots.allowed_types` |
| MED-4 | `router.py:178-190` | Router doesn't store which backend handled each stage in results |
| MED-5 | `config.py:63-77` | Cascade order hardcoded — adding a new stage requires code changes |
| MED-6 | `session.py` | No session cleanup / purge of old sessions in `.sessions/` |
| MED-7 | `research.py:75` | No error handling for malformed `_web_research` return data |
| MED-8 | `research.py:30` | `sufficient: false` flag is set but pipeline continues without handling it |
| MED-9 | `md_builder.py` | No nested bullets, no table of contents, no formatting emphasis |
| MED-10 | `pipeline.py:142-152` | Validation errors lack actual-vs-expected context |

---

## Low Severity / Polish

| ID | Location | Issue |
|----|----------|-------|
| LOW-1 | `config.yaml` | `use_web: false` — web research feature wired but disabled |
| LOW-2 | Multiple | German terminology inconsistency ("Quellen" vs "Quellenangaben") |
| LOW-3 | `cli.py` | File path output mixes `/` and `\` on Windows |
| LOW-4 | `cli.py` | `json.dumps(ensure_ascii=False)` may cause issues when piped |
| LOW-5 | `docx_builder.py:106` | Visual placeholder centered but body text left-aligned |

---

## Incomplete Features

| Feature | Status | Location |
|---------|--------|----------|
| Ollama backend | Config exists, factory missing | `config.py`, `router.py` |
| Web research | Code exists, disabled by default | `research/web.py`, `config.yaml` |
| Agent selection | Hardcoded to LocalLLMAgent | `artifact.py:90` |
| Scanner integration | Module exists, not called from pipeline | `scanner.py` |
| Session cleanup | No auto-purge | `session.py` |

---

## Generated Output Quality

The markdown outputs are structurally correct but basic:

- Coherent German content matching the task prompt
- Proper heading hierarchy (H1 title, H2 sections)
- Bullet points present but flat (no nesting)
- Sources section included
- No emphasis formatting, no tables, no internal links
- Generic section headings ("Einleitung", "Fazit")

The PPTX output has the right slide count and structure but is broken on open — this is the highest-priority fix.

---

## Test Coverage

| Area | Tests | Status |
|------|-------|--------|
| Artifact builders (pptx, docx, md) | 23 | All pass |
| Backends + router | 14 | All pass |
| Config loading | 7 | All pass |
| Pipeline e2e (mocked) | 7 | All pass |
| Sessions | 14 | All pass |
| Stages (intake, plan, research, synthesize, artifact) | 22 | All pass |
| Styles | 23 | All pass |
| Scanner (new) | 45 | All pass |
| **Total** | **170** | **All pass** |

Gaps: no tests for Windows encoding edge cases, no tests for font availability, no integration tests with real PPTX validation.

---

## Recommended Next Steps (priority order)

1. **Fix PPTX builder** — debug the broken output, validate with python-pptx's XML, test with standard dimensions
2. **Fix Windows encoding** — wrap CLI output in UTF-8 safe writer, replace box-drawing/emoji with ASCII fallbacks
3. **Wire up ollama backend** — add factory entry in router.py
4. **Harden JSON parsing** — handle `` ```json `` fences, add schema validation of LLM responses
5. **Integrate scanner into pipeline** — connect scan results to task intake
