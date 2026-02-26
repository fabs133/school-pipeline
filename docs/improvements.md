# Improvements Plan -- schulpipeline

**Datum:** 2026-02-25
**Basis:** PROJECT_ASSESSMENT.md (alle Fehler behoben), E2E-Validierung bestanden, 185 Tests green
**Aktueller Stand:** Produktionsreif fuer Standard-Pipeline (intake -> plan -> research -> synthesize -> artifact)

---

## Uebersicht

Das Projekt hat ein solides Fundament: 5-Stage-Pipeline, Backend-Routing mit Cascade, Session-Persistenz, Style-System, 185 Tests. Dieser Plan adressiert die naechsten Schritte in vier Tiers nach Prioritaet und Impact.

| Tier | Fokus | Umfang |
|------|-------|--------|
| **Tier 1** | Fehlende Kernfeatures verbinden | 6 Items, ~30h |
| **Tier 2** | Output-Qualitaet & UX | 6 Items, ~40h |
| **Tier 3** | Architektur & Performance | 5 Items, ~35h |
| **Tier 4** | Tooling & Developer Experience | 5 Items, ~15h |

---

## Tier 1: Fehlende Kernfeatures verbinden

### T1-1: Scanner in Pipeline integrieren

**Problem:** `scanner.py` (1063 Zeilen) existiert als vollstaendiges Modul -- Dateiklassifikation, Content-Extraktion, Bundle-Erkennung -- aber ist komplett disconnected von der Pipeline. Schueler muessen Aufgabentexte manuell eingeben, obwohl der Scanner Verzeichnisse automatisch analysieren kann.

**Loesung:**

1. **CLI-Command hinzufuegen:** `schulpipeline scan <dir>`
   - `--json` fuer maschinenlesbare Ausgabe
   - `--verbose` fuer detaillierte Klassifikation
   - Nutzt bestehenden `scan_directory()` + `to_manifest()`

2. **`--scan-input` Flag fuer `run`-Command:**
   ```
   schulpipeline scan ./Aufgaben --json > scan.json
   schulpipeline run --scan-input scan.json --bundle 0
   ```

3. **Intake-Stage erweitern:**
   - `IntakeStage.execute()` erkennt ScanResult-JSON als Input
   - Extrahiert `task_text` aus Bundle-Dateien automatisch
   - Nutzt `info_files` als zusaetzlichen Kontext

**Dateien:**
- `schulpipeline/cli.py` -- neuer `scan` Subcommand
- `schulpipeline/stages/intake.py` -- ScanResult-Handling in `execute()`
- `tests/test_stages.py` -- Tests fuer Intake mit ScanResult

**Aufwand:** ~6h

---

### T1-2: Web-Research aktivieren und absichern

**Problem:** DuckDuckGo-Web-Recherche ist vollstaendig implementiert (`research/web.py`, Caching, async, Quality-Scoring) aber per Default deaktiviert (`config.yaml: use_web: false`). Alle Rechercheergebnisse kommen ausschliesslich aus LLM-Wissen.

**Loesung:**

1. **Error-Handling haerten:**
   - Timeout fuer DDG-Requests (5s)
   - Graceful fallback wenn DDG nicht erreichbar (Schulnetzwerk-Blockaden)
   - BeautifulSoup-Parsing fuer kaputtes HTML absichern
   - Rate-Limiting (max 3 Requests/Sekunde)

2. **Config-Default aendern:**
   ```yaml
   research:
     enabled: true
     use_web: true
     request_delay: 2.0
     max_web_results: 3
     cache_ttl_hours: 24
   ```

3. **Fallback-Strategie:**
   - Wenn Web-Search fehlschlaegt: `sufficient: false` setzen, Pipeline laeuft weiter mit LLM-Wissen
   - Kein harter Fehler bei Netzwerkproblemen

4. **Tests:**
   - Mock-Tests fuer Web-Research-Integration
   - Live-Test mit realer DDG-Abfrage (in `tests/live/`)

**Dateien:**
- `schulpipeline/stages/research.py` -- Error-Handling + Fallback
- `config.yaml` -- Default `use_web: true`
- `tests/test_stages.py` -- Mock-Web-Research-Tests

**Aufwand:** ~4h

---

### T1-3: Prompts externalisieren

**Problem:** 8 System-Prompts sind direkt im Python-Code eingebettet (je 20-50 Zeilen). Prompt-Engineering erfordert Code-Aenderungen und Redeployment. Keine Moeglichkeit, Prompts per Config anzupassen.

**Betroffene Prompts:**
- `INTAKE_SYSTEM_INTRO` + `INTAKE_JSON_SPEC` (intake.py:12-41)
- `PLAN_SYSTEM_INTRO` + `PLAN_JSON_SPEC` (plan.py:11-50)
- `RESEARCH_PROMPT` (research.py:11-40)
- `SYNTHESIZE_PPTX_PROMPT`, `SYNTHESIZE_DOCX_PROMPT`, `SYNTHESIZE_MD_PROMPT` (synthesize.py:11-88)

**Loesung:**

1. **Neues Modul `schulpipeline/prompts.py`:**
   - Prompt-Templates als benannte Strings mit Platzhaltern
   - `load_prompt(name, **variables)` Funktion
   - Default-Prompts im Code, Override via `prompts/` Verzeichnis

2. **Prompt-Verzeichnis `prompts/`:**
   ```
   prompts/
     intake_system.txt
     intake_json_spec.txt
     plan_system.txt
     synthesize_pptx.txt
     synthesize_docx.txt
     synthesize_md.txt
   ```

3. **Config-Integration:**
   ```yaml
   prompts:
     dir: prompts/  # Optional override directory
   ```

4. **Stages aktualisieren:**
   - Ersetze hardcoded Strings durch `load_prompt()` Aufrufe
   - Fallback auf eingebaute Defaults wenn Datei nicht existiert

**Dateien:**
- `schulpipeline/prompts.py` -- neues Modul
- `prompts/*.txt` -- Default-Prompt-Dateien
- `schulpipeline/stages/intake.py`, `plan.py`, `research.py`, `synthesize.py` -- Import-Umstellung

**Aufwand:** ~5h

---

### T1-4: Input-Validierung fuer Stages

**Problem:** Stages greifen auf Context-Keys ohne Validierung zu (`context["synthesize"]` in artifact.py:17). Wenn eine Stage uebersprungen wird oder fehlt, gibt es einen kryptischen `KeyError` statt einer hilfreichen Fehlermeldung.

**Loesung:**

1. **`required_context` Attribut auf BaseStage:**
   ```python
   class ArtifactStage(BaseStage):
       name = "artifact"
       required_context = {"plan", "synthesize"}
   ```

2. **Validierung in `BaseStage.run()`:**
   - Vor `execute()` pruefen ob alle `required_context` Keys im Context vorhanden
   - Klare Fehlermeldung: "Stage 'artifact' requires context keys: ['plan', 'synthesize']. Missing: ['synthesize']"

3. **Alle Stages annotieren:**
   | Stage | required_context |
   |-------|-----------------|
   | intake | `{"raw_input"}` |
   | plan | `{"raw_input", "intake"}` |
   | research | `{"intake", "plan"}` |
   | synthesize | `{"intake", "plan", "research"}` |
   | artifact | `{"plan", "synthesize"}` |

**Dateien:**
- `schulpipeline/stages/base.py` -- `required_context` + Validierung
- `schulpipeline/stages/*.py` -- Attribut setzen
- `tests/test_stages.py` -- Test fuer fehlende Context-Keys

**Aufwand:** ~3h

---

### T1-5: Kosten-Warnung vor Pipeline-Start

**Problem:** Kosten werden erst nach Abschluss angezeigt. Bei OpenAI-Backend koennen Kosten entstehen, ohne dass der User vorher gewarnt wird. `synthesize.py` kann bis zu 16384 Tokens anfordern.

**Loesung:**

1. **`schulpipeline cost-estimate <task>` Command:**
   - Fuehrt nur Intake + Plan aus (wie `--dry-run`)
   - Berechnet geschaetzte Token-Anzahl pro Stage
   - Zeigt geschaetzte Kosten pro Backend
   - Output: "Geschaetzte Kosten: $0.00 (Groq free tier) / $0.12 (OpenAI gpt-4o)"

2. **Warnung im `run`-Command:**
   - Wenn `total_estimated_cost > 0.01`: Bestaetigung abfragen
   - `--yes` Flag um Bestaetigung zu ueberspringen

3. **Token-Schaetzung:**
   - Intake: ~500 Token in, ~300 out
   - Plan: ~800 Token in, ~500 out
   - Research: ~1000 * section_count in, ~500 * section_count out
   - Synthesize: ~2000 in, ~section_count * 400 out
   - Kosten = Token * Preis/1M (pro Backend)

**Dateien:**
- `schulpipeline/cli.py` -- `cost-estimate` Command + Warnung
- `schulpipeline/backends/base.py` -- `estimate_cost(tokens_in, tokens_out)` auf Backend
- `tests/test_backends.py` -- Kosten-Schaetzungs-Tests

**Aufwand:** ~4h

---

### T1-6: Unvollstaendige Pipeline-Pfade testen

**Problem:** 4 alternative Pipeline-Pfade (worksheet, audit, template, requirements_report) sind im Code angelegt aber untested. `Pipeline._select_stages()` hat 5 hard-coded if-Bloecke (pipeline.py:49-78) die nie in E2E-Tests ausgefuehrt werden.

**Loesung:**

1. **Audit der alternativen Stages:**
   - `worksheet.py`: DecomposeStage + SolveStage pruefen, fehlende `execute()` implementieren
   - `audit.py`: AuditStage pruefen
   - `documents.py`: ClassifyDocsStage + FillTemplateStage pruefen
   - `requirements.py`: ClassifyReportStage + AmendmentsStage pruefen

2. **Mock-Responses fuer alternative Stages:**
   - `conftest.py` erweitern mit Responses fuer Decompose, Solve, Audit, Classify

3. **E2E-Tests pro Pfad:**
   ```python
   test_worksheet_pipeline()      # intake -> decompose -> solve
   test_audit_pipeline()          # intake -> classify -> audit
   test_template_pipeline()       # intake -> classify -> audit -> fill
   test_requirements_pipeline()   # intake -> classify -> audit -> classify_report -> amendments
   ```

4. **Entscheidung:** Unfertige Stages entweder komplett implementieren oder entfernen (kein toter Code).

**Dateien:**
- `schulpipeline/worksheet.py`, `audit.py`, `documents.py`, `requirements.py` -- Implementierung vervollstaendigen oder entfernen
- `tests/conftest.py` -- Mock-Responses
- `tests/test_pipeline_e2e.py` -- 4 neue E2E-Tests

**Aufwand:** ~8h

---

## Tier 2: Output-Qualitaet & UX

### T2-1: Tabellen-Support in PPTX und DOCX

**Problem:** Synthesis kann strukturierte Daten (Vergleiche, Statistiken) liefern, aber die Builder koennen nur Fliesstext und Stichpunkte rendern. Keine Tabellen in PPTX oder DOCX.

**Loesung:**

1. **Synthesis-Schema erweitern:**
   ```json
   {
     "section_id": "s3",
     "heading": "Vergleich",
     "content": "...",
     "table": {
       "headers": ["Kriterium", "Option A", "Option B"],
       "rows": [["Kosten", "10 EUR", "20 EUR"], ...]
     }
   }
   ```

2. **PPTX-Builder:** `_add_table()` mit python-pptx Table-API
   - Dynamische Spaltenbreiten aus slide_width
   - Header-Zeile farblich abgesetzt (Style.colors.primary)
   - Zellen-Padding konfigurierbar

3. **DOCX-Builder:** `_add_table()` mit python-docx Table-API
   - Gleiche Datenstruktur wie PPTX
   - Rahmenlinien + alternating row colors

4. **Prompt-Anpassung:**
   - Synthesize-Prompt erhaelt optionalen "table" Key in Schema
   - Nur wenn Daten vergleichend/tabellarisch sind

**Dateien:**
- `specs/synthesis.json` -- Schema-Update
- `schulpipeline/artifacts/pptx_builder.py` -- `_add_table()`
- `schulpipeline/artifacts/docx_builder.py` -- `_add_table()`
- `schulpipeline/stages/synthesize.py` -- Prompt-Update

**Aufwand:** ~8h

---

### T2-2: Fortschrittsanzeige im CLI

**Problem:** Pipeline laeuft 15-45 Sekunden ohne jegliche Rueckmeldung. User sieht nur die finale Meldung. Kein Indikator welche Stage gerade laeuft oder wie weit der Prozess ist.

**Loesung:**

1. **Stage-Progress-Callback:**
   ```python
   # pipeline.py
   async def run(self, raw_input, preset=None, on_progress=None):
       for stage in stages:
           if on_progress:
               on_progress(stage.name, "started", i, len(stages))
           result = await stage.run(...)
           if on_progress:
               on_progress(stage.name, "completed", i, len(stages))
   ```

2. **CLI-Ausgabe:**
   ```
   [1/5] Intake     ... 1.2s
   [2/5] Plan       ... 3.4s
   [3/5] Research   ... 5.1s
   [4/5] Synthesize ... 8.7s
   [5/5] Artifact   ... 0.9s

   + Fertig in 19.3s
     Datei: output/IT-Sicherheit.pptx
   ```

3. **Session-Runner:** Gleicher Callback in `SessionRunner.run()`

**Dateien:**
- `schulpipeline/pipeline.py` -- `on_progress` Callback
- `schulpipeline/session.py` -- Callback im SessionRunner
- `schulpipeline/cli.py` -- Progress-Formatter

**Aufwand:** ~4h

---

### T2-3: Seitenzahlen, Kopf-/Fusszeilen in DOCX

**Problem:** DOCX-Output hat kein professionelles Layout -- keine Seitenzahlen, keine Kopfzeile mit Thema/Fach, keine Seitenumbrueche zwischen Kapiteln.

**Loesung:**

1. **Seitenzahlen:** Footer mit `PAGE` Field via python-docx XML-Manipulation
2. **Kopfzeile:** Titel + Fach aus Synthesis-Daten
3. **Seitenumbrueche:** `doc.add_page_break()` vor jedem `level=1` Heading (ausser dem ersten)
4. **Style-Integration:** Kopf-/Fusszeile nutzt `visual_style.fonts.body_family` und `colors.text_muted`

**Dateien:**
- `schulpipeline/artifacts/docx_builder.py` -- Header/Footer/Breaks

**Aufwand:** ~5h

---

### T2-4: Foliennummern und Footer in PPTX

**Problem:** PPTX-Slides haben keine Nummerierung. Bei Praesentationen mit 10+ Folien ist die Orientierung schwierig.

**Loesung:**

1. **Foliennummer:** Textbox unten-rechts mit "Folie X / Y"
2. **Footer:** Optional Fach-Name oder Datum unten-links
3. **Konfigurierbar:** Via Style-Config `layout.show_slide_numbers: true`
4. **Nicht auf Titel-/Quellenfolie**

**Dateien:**
- `schulpipeline/artifacts/pptx_builder.py` -- `_add_slide_footer()`
- `schulpipeline/styles.py` -- `show_slide_numbers` Flag

**Aufwand:** ~3h

---

### T2-5: Bildeinbettung in Artifacts

**Problem:** Visuelle Platzhalter zeigen nur `[Diagramm]` Text. Keine echten Bilder in PPTX oder DOCX.

**Loesung:**

1. **Unsplash/Pexels-Integration fuer Stock-Fotos:**
   - `search_hint` aus Visual-Slot als Suchbegriff nutzen
   - Kostenlose API (Unsplash: 50 Requests/Stunde)
   - Bilder cachen in `.schulpipeline/images/`

2. **Bild-Einbettung:**
   - PPTX: `slide.shapes.add_picture()` an Platzhalter-Position
   - DOCX: `doc.add_picture()` mit Pillow fuer Resize

3. **Fallback:** Wenn Bild-Download fehlschlaegt, bleibt Text-Platzhalter

4. **Config:**
   ```yaml
   visuals:
     enabled: true
     embed_images: true  # false = nur Platzhalter
     image_source: unsplash  # pexels, local
     api_key_env: UNSPLASH_ACCESS_KEY
   ```

**Dateien:**
- `schulpipeline/images.py` -- neues Modul (Search + Download + Cache)
- `schulpipeline/artifacts/pptx_builder.py` -- `_embed_image()`
- `schulpipeline/artifacts/docx_builder.py` -- `_embed_image()`
- `config.yaml` -- `visuals.embed_images`

**Aufwand:** ~10h

---

### T2-6: Interaktiver Preset-Wizard

**Problem:** Quick-Presets wie `fiae-praesi-itsec` sind schwer zu merken. `--output-type` + `--subject` Kombination ist verbose. Neue User wissen nicht welche Optionen verfuegbar sind.

**Loesung:**

1. **`schulpipeline wizard` Command:**
   ```
   Was soll erstellt werden?
     1. Praesentation (PPTX)
     2. Ausarbeitung (DOCX)
     3. Aufgaben loesen (MD)
     4. Handout (DOCX)

   > 1

   Welches Fach?
     1. IT-Sicherheit
     2. Netzwerktechnik
     3. Programmierung
     4. Wirtschaft
     5. Anderes

   > 2

   Wie viele Folien? [8]
   > 10

   Aufgabentext eingeben (oder Datei-Pfad):
   > Erstelle eine Praesentation ueber das OSI-Modell

   Starte Pipeline mit: praesentation + netzwerktechnik + 10 Folien
   ```

2. **Technisch:** `input()` basiert, kein TUI-Framework noetig

**Dateien:**
- `schulpipeline/cli.py` -- `cmd_wizard()` Funktion + `wizard` Subcommand

**Aufwand:** ~4h

---

## Tier 3: Architektur & Performance

### T3-1: Stage-Auswahl per Config statt Hard-Code

**Problem:** `Pipeline._select_stages()` hat 5 verschachtelte if-Bloecke (pipeline.py:49-78) die Stage-Sequenzen basierend auf Preset-Constraints waehlen. Neue Pipeline-Pfade erfordern Code-Aenderungen.

**Loesung:**

1. **`stage_sequence` Attribut auf ResolvedPreset:**
   ```python
   @dataclass
   class ResolvedPreset:
       stage_sequence: list[str] = None  # ["intake", "plan", "research", "synthesize", "artifact"]
   ```

2. **Stage-Registry:**
   ```python
   STAGE_REGISTRY = {
       "intake": IntakeStage,
       "plan": PlanStage,
       "research": ResearchStage,
       "synthesize": SynthesizeStage,
       "artifact": ArtifactStage,
       "decompose": DecomposeStage,
       "solve": SolveStage,
       "audit": AuditStage,
       "classify_docs": ClassifyDocsStage,
       "fill_template": FillTemplateStage,
   }
   ```

3. **Pipeline._select_stages() vereinfachen:**
   ```python
   def _select_stages(self, context):
       preset = context.get("preset")
       if preset and preset.stage_sequence:
           return [STAGE_REGISTRY[name]() for name in preset.stage_sequence]
       return self._standard_stages
   ```

**Dateien:**
- `schulpipeline/stages/__init__.py` -- STAGE_REGISTRY
- `schulpipeline/presets.py` -- `stage_sequence` Attribut
- `schulpipeline/pipeline.py` -- Vereinfachte Stage-Auswahl

**Aufwand:** ~5h

---

### T3-2: Parallele Research-Queries

**Problem:** Research-Stage fuehrt Queries sequentiell aus (research.py:128-137). Bei 5 Sections mit je 2 Queries = 10 serielle LLM-Calls. Web-Search verstaerkt den Effekt.

**Loesung:**

1. **Alle Section-Queries parallel ausfuehren:**
   ```python
   async def _research_section(self, section, backend, config):
       # ... research logic for one section ...

   async def execute(self, context, backend, config):
       tasks = [self._research_section(s, backend, config) for s in plan_sections]
       results = await asyncio.gather(*tasks, return_exceptions=True)
   ```

2. **Concurrency-Limit:** `asyncio.Semaphore(3)` um Backend nicht zu ueberlasten

3. **Web-Research parallel:** Separate Semaphore fuer HTTP-Requests

**Impact:** Research-Stage von 8-15s auf 3-5s reduzierbar

**Dateien:**
- `schulpipeline/stages/research.py` -- asyncio.gather + Semaphore

**Aufwand:** ~4h

---

### T3-3: Streaming-Support fuer Backends

**Problem:** Alle Backend-Calls warten auf die vollstaendige Response. Bei Synthesize (8-16k Tokens) dauert das 8-15 Sekunden ohne Feedback. Kein Partial-Result-Processing.

**Loesung:**

1. **Backend-Protocol erweitern:**
   ```python
   class Backend(Protocol):
       async def complete(self, ...) -> LLMResponse: ...
       async def complete_stream(self, ...) -> AsyncIterator[str]: ...
   ```

2. **Implementierung fuer Groq + OpenAI:**
   - SSE-basiertes Streaming via `requests` mit `stream=True`
   - Chunk-weise Token-Ausgabe

3. **CLI-Integration:**
   - Synthesis-Output live auf stdout streamen
   - Endresultat als JSON sammeln

4. **Fallback:** Backends ohne Streaming-Support nutzen weiterhin `complete()`

**Dateien:**
- `schulpipeline/backends/base.py` -- `complete_stream()` Protocol
- `schulpipeline/backends/openai_compat.py` -- Streaming-Implementierung
- `schulpipeline/backends/router.py` -- `complete_stream()` Routing

**Aufwand:** ~12h

---

### T3-4: Response-Caching

**Problem:** Gleiche Aufgabe zweimal ausgefuehrt = doppelte API-Kosten. Kein Caching fuer LLM-Responses. Web-Research hat Caching, aber LLM-Calls nicht.

**Loesung:**

1. **Content-Hash als Cache-Key:**
   ```python
   cache_key = hashlib.sha256(
       json.dumps(messages, sort_keys=True).encode()
   ).hexdigest()[:16]
   ```

2. **Disk-Cache in `.schulpipeline/cache/llm/`:**
   - TTL: 24h (konfigurierbar)
   - Speichert: Response-Content, Token-Counts, Model
   - Max-Size: 100MB

3. **Cache-Integration im Router:**
   - Vor Backend-Call: Cache pruefen
   - Nach Backend-Call: Response cachen
   - `--no-cache` Flag fuer frische Ergebnisse

**Impact:** Wiederholte Runs kosten 0 Token, ~0ms Latenz

**Dateien:**
- `schulpipeline/cache.py` -- neues Modul
- `schulpipeline/backends/router.py` -- Cache-Layer
- `schulpipeline/cli.py` -- `--no-cache` Flag

**Aufwand:** ~6h

---

### T3-5: Claude/Anthropic Backend

**Problem:** Kein Anthropic-Backend verfuegbar. Claude-Modelle (Sonnet, Haiku) sind kostengeffizient und haben starke Deutsch-Faehigkeiten, werden aber nicht unterstuetzt.

**Loesung:**

1. **`schulpipeline/backends/anthropic.py`:**
   - Messages-API mit `anthropic` Python SDK
   - Vision-Support (Claude 3.5+)
   - Streaming-Support
   - Kosten-Tracking (Input: $3/MTok, Output: $15/MTok fuer Sonnet)

2. **Factory + Router-Integration:**
   ```python
   BACKEND_FACTORIES["anthropic"] = lambda cfg: create_anthropic(cfg.api_key, cfg.model)
   ```

3. **Config:**
   ```yaml
   backends:
     anthropic:
       model: claude-sonnet-4-20250514
       enabled: true
   ```

**Dateien:**
- `schulpipeline/backends/anthropic.py` -- neues Modul
- `schulpipeline/backends/router.py` -- Factory-Eintrag
- `config.yaml` -- Backend-Config
- `pyproject.toml` -- `anthropic` Dependency

**Aufwand:** ~8h

---

## Tier 4: Tooling & Developer Experience

### T4-1: Makefile fuer Common Tasks

**Problem:** Kein Task-Runner. Entwickler muessen sich Befehle merken.

**Loesung:**

```makefile
.PHONY: test lint format typecheck live-test clean

test:
    python -m pytest tests/ --ignore=tests/live -v

live-test:
    python -m pytest tests/live/ -v -m live

lint:
    ruff check schulpipeline/ tests/

format:
    ruff format schulpipeline/ tests/

typecheck:
    mypy schulpipeline/ --ignore-missing-imports

clean:
    rm -rf output/ .schulpipeline/cache/ .pytest_cache/
    find . -name __pycache__ -exec rm -rf {} +

doctor:
    python -m schulpipeline doctor
```

**Aufwand:** ~1h

---

### T4-2: Type-Checking mit mypy

**Problem:** Keine statische Typanalyse. Type-Hints existieren teilweise aber werden nicht geprueft. Potenzielle Runtime-Fehler durch falsche Typen werden erst in Produktion sichtbar.

**Loesung:**

1. **`mypy.ini`:**
   ```ini
   [mypy]
   python_version = 3.11
   warn_return_any = True
   warn_unused_configs = True
   ignore_missing_imports = True
   ```

2. **CI-Integration:** mypy als Step in GitHub Actions
3. **Schrittweise:** Erst `schulpipeline/backends/`, dann `stages/`, dann Rest

**Aufwand:** ~4h (Setup + erste Fixes)

---

### T4-3: Test-Coverage-Tracking

**Problem:** 185 Tests existieren, aber unbekannt welcher Code wie gut abgedeckt ist. Keine Coverage-Metrik in CI.

**Loesung:**

1. **`pytest-cov` installieren:**
   ```toml
   [project.optional-dependencies]
   dev = ["pytest", "pytest-asyncio", "pytest-cov", "ruff"]
   ```

2. **Coverage in CI:**
   ```yaml
   - run: pytest --cov=schulpipeline --cov-report=term-missing tests/
   ```

3. **Coverage-Minimum:** 80% Gesamt, 90% fuer `stages/` und `backends/`

**Aufwand:** ~2h

---

### T4-4: Pre-Commit Hooks

**Problem:** Linting und Formatting werden nur in CI geprueft. Entwickler koennen Code commiten der den Lint-Check nicht besteht.

**Loesung:**

1. **`.pre-commit-config.yaml`:**
   ```yaml
   repos:
     - repo: https://github.com/astral-sh/ruff-pre-commit
       rev: v0.9.0
       hooks:
         - id: ruff
           args: [--fix]
         - id: ruff-format
   ```

2. **Installation:** `pre-commit install` im README dokumentieren

**Aufwand:** ~1h

---

### T4-5: Duplikate konsolidieren

**Problem:** Mehrere Stellen im Code haben identische Logik:
- `_SOURCES_KEYWORDS` in pptx_builder.py UND docx_builder.py
- `_TYPE_ICONS` in pptx_builder.py UND docx_builder.py
- Sources-Deduplizierung in beiden Builders
- Prompt-Schablonen in 4 Stage-Dateien

**Loesung:**

1. **Shared Constants:**
   ```python
   # schulpipeline/artifacts/shared.py
   SOURCES_KEYWORDS = frozenset({...})
   TYPE_ICONS = {...}

   def deduplicate_sources(sections, top_level_sources):
       ...
   ```

2. **Builder importieren aus `shared.py`**

3. **Prompts: siehe T1-3**

**Dateien:**
- `schulpipeline/artifacts/shared.py` -- neues Modul
- `schulpipeline/artifacts/pptx_builder.py` -- Import
- `schulpipeline/artifacts/docx_builder.py` -- Import

**Aufwand:** ~3h

---

## Zusammenfassung nach Aufwand

| # | Item | Tier | Aufwand | Abhaengigkeiten |
|---|------|------|---------|-----------------|
| T1-1 | Scanner-Integration | 1 | 6h | -- |
| T1-2 | Web-Research aktivieren | 1 | 4h | -- |
| T1-3 | Prompts externalisieren | 1 | 5h | -- |
| T1-4 | Input-Validierung | 1 | 3h | -- |
| T1-5 | Kosten-Warnung | 1 | 4h | -- |
| T1-6 | Alternative Pfade testen | 1 | 8h | -- |
| T2-1 | Tabellen-Support | 2 | 8h | -- |
| T2-2 | Fortschrittsanzeige | 2 | 4h | -- |
| T2-3 | DOCX Headers/Footers | 2 | 5h | -- |
| T2-4 | PPTX Foliennummern | 2 | 3h | -- |
| T2-5 | Bildeinbettung | 2 | 10h | T1-2 (Web) |
| T2-6 | Preset-Wizard | 2 | 4h | -- |
| T3-1 | Stage-Registry | 3 | 5h | T1-6 |
| T3-2 | Parallele Research | 3 | 4h | T1-2 |
| T3-3 | Streaming | 3 | 12h | -- |
| T3-4 | Response-Caching | 3 | 6h | -- |
| T3-5 | Anthropic-Backend | 3 | 8h | -- |
| T4-1 | Makefile | 4 | 1h | -- |
| T4-2 | Type-Checking | 4 | 4h | -- |
| T4-3 | Coverage-Tracking | 4 | 2h | -- |
| T4-4 | Pre-Commit Hooks | 4 | 1h | -- |
| T4-5 | Duplikate konsolidieren | 4 | 3h | T1-3 |

**Gesamt: ~120h (22 Items)**

---

## Empfohlene Reihenfolge

**Sprint 1 (Woche 1-2):** T1-4, T1-5, T4-1, T4-4, T2-2
- Input-Validierung, Kosten-Warnung, Makefile, Pre-Commit, Fortschrittsanzeige
- Sofortiger Nutzen, geringes Risiko

**Sprint 2 (Woche 3-4):** T1-1, T1-2, T4-5
- Scanner-Integration, Web-Research, Duplikate aufraemen
- Kernfeatures verbinden

**Sprint 3 (Woche 5-6):** T1-3, T2-3, T2-4, T4-2, T4-3
- Prompts externalisieren, DOCX/PPTX Polish, Type-Checking, Coverage
- Qualitaetsverbesserung

**Sprint 4 (Woche 7-8):** T1-6, T3-1, T3-2
- Alternative Pipeline-Pfade, Stage-Registry, Parallele Research
- Architektur-Cleanup

**Sprint 5+ (Woche 9+):** T2-1, T2-5, T2-6, T3-3, T3-4, T3-5
- Tabellen, Bilder, Wizard, Streaming, Caching, Anthropic
- Advanced Features
