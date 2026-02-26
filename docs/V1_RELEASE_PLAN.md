# schulpipeline v1.0.0 Release Plan

**Goal**: Ship a clean, tested, documented v1.0.0 that a classmate could
clone, install, and use in 2 minutes. No dead code, no temp files, no
broken imports, no mystery modules.

**Baseline**: 206 tests passing, E2E verified (DOCX + PPTX), 5 backends
working, scanner module complete, style system complete.

---

## Phase 1: Safety Gate + Bug Fixes

> Phase 1 is the FIRST thing Claude Code runs. Nothing else happens before
> student data is protected. No commits, no pushes, no branch switches —
> .gitignore comes first.

### 1.0 Protect student data (BLOCKER — do this FIRST)

**Problem**: `Data_School_Tasks/` contains original school documents —
teacher-authored content, publisher material (Bildungsverlag EINS, Westermann),
student answers, personal notes. This must NEVER enter git history. Once
committed, it's permanent even after deletion.

**Steps** (in this exact order):

1. Verify `Data_School_Tasks/` is NOT already tracked:
   ```bash
   git ls-files Data_School_Tasks/
   ```
   If output is non-empty → `git rm -r --cached Data_School_Tasks/` before
   anything else.

2. Add to `.gitignore` IMMEDIATELY:
   ```gitignore
   # Student data — NEVER commit (copyright + privacy)
   Data_School_Tasks/
   ```

3. Verify protection:
   ```bash
   git status  # Data_School_Tasks should NOT appear
   git add .gitignore
   git commit -m "safety: gitignore student data before any other changes"
   ```

4. Also add scanner temp outputs:
   ```gitignore
   _manifest.json
   _manifest.yaml
   _scan_result.txt
   ```

**Why this is 1.0 not 2.x**: If ANY other step accidentally runs `git add -A`
or `git add .` before this, student data enters the repo. This is the
hard safety gate. It must be the very first commit.

**Acceptance**: `git ls-files | grep Data_School_Tasks` returns nothing.

### 1.1 dotenv loading ✅ (already done)

`python-dotenv` added to deps, `load_dotenv()` in `cli.py` and `__main__.py`.
Verify: `schulpipeline doctor` finds all 4 API keys.

### 1.2 Intake subject detection

**Problem**: Intake classifies `IT_M1_A1_Recherche.docx` (Deutsch/SMA) as
"Wirtschaft" because Fair-Trade dominates the text. The subject should come
from the folder context or filename, not just content.

**Fix**: When `--subject` or preset provides a subject, intake should use it
and not override. When no subject is given and the task comes from a scanned
bundle, pass `subject_folder` as hint to intake prompt.

**Acceptance**: `schulpipeline run --subject deutsch "..."` → intake output
has `"subject": "Deutsch"`.

### 1.3 Config validation at startup

**Problem**: Typos in `config.yaml` (e.g. `backneds:` instead of `backends:`)
silently produce an empty config. User sees "No backends available" with no
explanation.

**Fix**: Add `validate_config()` in `config.py` that checks:
- At least one backend has a key or is ollama with base_url
- Cascade references only known backends
- Output dir is writable
- Log file parent dir exists

Print clear error messages, not stack traces.

**Acceptance**: Deliberately break config.yaml → helpful error message.

### 1.4 Research stage with use_web: false

**Problem**: Config has `use_web: false` but research stage still runs and
returns content. Quellen section has names but no URLs. Need to verify
research stage behavior is correct when web is disabled (LLM-only research).

**Fix**: Audit `stages/research.py` — if `use_web: false`, research should:
- Still gather LLM knowledge (this seems to work)
- NOT claim web sources it never visited
- Flag in output that sources are LLM-generated

**Acceptance**: Research output with `use_web: false` has no fake URLs.

---

## Phase 2: Repo Hygiene

### 2.1 Delete temp files from root

Files to delete (all `_`-prefixed scripts and outputs from root):
```
_diag.py, _diag_result.txt
_e2e_pptx_stdout.txt, _e2e_result.txt, _e2e_result_pptx.txt, _e2e_stdout.txt
_pip_out.txt
_run_e2e.py, _run_e2e_pptx.py
_run_scanner.py, _run_scanner_v2.py
_analyze_tasks.py, _debug.txt
_doctor_output.txt, _e2e_output.txt, _e2e_v2_error.txt, _e2e_v2_output.txt
_list_tasks.py, _pipeline_test_error.txt, _pipeline_test_output.txt
_run_doctor.py, _run_e2e_test.py, _run_e2e_v2.py, _run_pipeline_test.py
_task_list_output.txt
_tmp.py, _tmp2.py, _tmp3.py
schulpipeline_1.zip
```

### 2.2 Update .gitignore (full)

Append to the .gitignore from step 1.0:
```gitignore
# Temp scripts (development debugging)
_*.py
_*.txt

# Package artifacts
*.zip
*.egg-info/

# Ruff / Pytest
.ruff_cache/
.pytest_cache/
```

### 2.3 Move docs to docs/

```
IMPROVEMENTS_PLAN.md  → docs/improvements.md
PROJECT_ASSESSMENT.md → docs/assessment.md
SCANNER_PLAN.md       → docs/scanner-plan.md
STYLE_ARCHITECTURE.md → docs/style-architecture.md
```

Keep only `README.md` and `CHANGELOG.md` in root.

### 2.4 Clean output/

Delete all test artifacts in `output/`. Add `output/.gitkeep`.

---

## Phase 3: Example Data

### 3.1 Why synthetic, not anonymized

The original documents contain:
- **Publisher content**: Bildungsverlag EINS, Westermann textbook excerpts,
  copyrighted reading passages (Fischwirt article etc.)
- **Teacher-created material**: GPT-generated Fachtexte, custom worksheets
- **Student answers**: Personal handwritten notes exported from OneNote

Anonymizing (removing names/dates) is NOT sufficient — the publisher text
is still copyrighted and the teacher content is still their intellectual
property. We need fully synthetic examples that replicate the *structure
and patterns* the scanner/pipeline must handle, with zero original content.

### 3.2 Create examples/ directory

```
examples/
├── README.md                    # What this is, how to use it
├── tasks/                       # Input: synthetic school documents
│   ├── DE-BSP/                  # Beispiel-Deutsch (fake subject folder)
│   │   ├── IT_B1_A1_Energie.docx       # Task: clear imperative-Sie patterns
│   │   ├── IT_B1_A1_Energie_Texte.docx # Info: reading material, no tasks
│   │   ├── IT_B1_A1_Energie.docx.pdf   # Duplicate: .docx.pdf pattern
│   │   ├── EnergieOneNote.docx         # OneNote: <<embed>> + student text
│   │   ├── Bewertungsbogen.docx        # Planning: grading criteria
│   │   └── Leer.docx                   # Empty file
│   └── WI-BSP/                  # Beispiel-Wirtschaft
│       ├── Aufgaben_Angebot_Nachfrage.docx  # Task with fill-in table
│       ├── Aufgaben_Angebot_Nachfrage.docx.pdf
│       └── AngebotNachfrageOneNote.docx
├── output/                      # Output: pipeline-generated artifacts
│   ├── Erneuerbare_Energien.pptx       # Generated from Energie task
│   ├── Erneuerbare_Energien.docx       # Same task, DOCX format
│   └── Angebot_und_Nachfrage.pptx      # Generated from WI task
└── manifests/                   # Scanner output examples
    └── example_manifest.yaml
```

### 3.3 Synthetic document content rules

Each synthetic .docx must:
- Use ONLY self-written content (no quotes from textbooks, no real articles)
- Include the structural patterns the scanner relies on:
  - "Aufgabe:", "Formulieren Sie...", "Erstellen Sie..." → task signals
  - "Information", "Grundsätzlich...", "Definition:" → info signals
  - `<<Filename.docx>>` → OneNote embed markers
  - Empty table cells → fill-in worksheet signal
- Be realistic in length (5-30 paragraphs) but obviously synthetic
- Use a fictional school context: "Berufskolleg Beispielstadt"

The OneNote exports should contain the `<<embed>>` pattern plus 3-5 lines
of fake student answers to trigger the answer classification.

### 3.4 Generate example outputs

Run the pipeline against each synthetic task document and include the
generated PPTX/DOCX in `examples/output/`. These are LLM-generated content
so no copyright issues.

```bash
schulpipeline run --input examples/tasks/DE-BSP/IT_B1_A1_Energie.docx --format pptx --yes
schulpipeline run --input examples/tasks/DE-BSP/IT_B1_A1_Energie.docx --format docx --yes
schulpipeline run --input examples/tasks/WI-BSP/Aufgaben_Angebot_Nachfrage.docx --format pptx --yes
```

### 3.5 Generate example manifest

```bash
schulpipeline scan examples/tasks/ -o examples/manifests/example_manifest.yaml
```

### 3.6 examples/README.md

```markdown
# Example Data

This directory contains **synthetic** school documents for testing and
demonstration. No real student data, teacher materials, or copyrighted
publisher content is included.

## Structure

- `tasks/` — Synthetic input documents that mimic real school file dumps
- `output/` — Pipeline-generated artifacts from the example tasks
- `manifests/` — Scanner output showing document classification

## Try it yourself

    # Scan the example directory
    schulpipeline scan examples/tasks/

    # Run the pipeline on an example task
    schulpipeline run --input examples/tasks/DE-BSP/IT_B1_A1_Energie.docx --yes

    # Try different styles
    schulpipeline run --input examples/tasks/WI-BSP/Aufgaben_Angebot_Nachfrage.docx --style dark --yes
```

### 3.7 Tests use examples/

Update `test_scanner.py` to optionally run against `examples/tasks/` as an
integration test (in addition to the existing `.txt` fixtures which stay
for fast unit tests):

```python
@pytest.mark.skipif(not Path("examples/tasks").exists(), reason="examples not available")
def test_scan_example_directory():
    result = scan_directory("examples/tasks")
    assert result.total_files >= 8
    assert any(f.role == "task" for f in result.files)
    assert any(f.role == "onenote_export" for f in result.files)
    assert any(f.role == "duplicate" for f in result.files)
```

---

## Phase 4: Code Quality

### 4.1 ruff lint + fix

```bash
ruff check schulpipeline/ tests/ --fix
ruff format schulpipeline/ tests/
```

**Acceptance**: `make lint` exits 0.

### 4.2 Remove dead / unused code

Audit these modules — for each one, either:
- (a) confirm it's used, has tests → keep
- (b) it's a stub for a future feature → add `# STUB` comment + import test
- (c) it's dead → delete

Modules to audit:
- `agents.py`
- `feedback.py`
- `research/web.py`
- `worksheet.py`
- `documents.py`
- `requirements.py`
- `audit.py`

For each stub kept, add a one-line import test:
```python
def test_module_imports():
    from schulpipeline import agents  # noqa: F401
```

### 4.3 Type hints on public interfaces

Add type hints to all public method signatures in:
- `pipeline.py` — `Pipeline.run()`, `Pipeline.plan_only()`
- `session.py` — `SessionStore`, `SessionRunner`
- `config.py` — `load_config()`
- `scanner.py` — `scan_directory()`, `classify_file()`
- `cli.py` — `main()`

### 4.4 Test suite green

```bash
python -m pytest tests/ --ignore=tests/live -v --tb=short -x
```

Fix any regressions from earlier phases.
**Acceptance**: Exit 0, 200+ tests, 0 failures.

---

## Phase 5: Scanner → CLI

### 5.1 Add `scan` subcommand to CLI

```bash
schulpipeline scan ./examples/tasks
schulpipeline scan ./examples/tasks --json
schulpipeline scan ./examples/tasks -o manifest.yaml
schulpipeline scan ./examples/tasks --verbose
```

Wire `cli.py` → `scanner.scan_directory()` → print summary + write manifest.

### 5.2 Add `run --bundle` flow (optional, stretch)

```bash
schulpipeline run --bundle de-bsp_it_b1_a1_energie --manifest manifest.yaml
```

Reads manifest, finds bundle, extracts task text, passes subject hint.
Mark as stretch — basic `scan` command is the v1 requirement.

### 5.3 Scanner tests in CI

Verify `test_scanner.py` runs in standard `make test` (no special deps —
scanner tests use `.txt` fixtures + optional `examples/` integration).

---

## Phase 6: Documentation

### 6.1 Update README.md

Current README covers basics. Add sections for:
- `.env` file setup (not just `export`)
- Preset system (`--preset`, `schulpipeline presets`)
- Style system (`--style clean|modern|minimal|school|corporate|dark`)
- Scanner (`schulpipeline scan`)
- Example data (`examples/` — try it immediately after install)
- Session management (`schulpipeline sessions`, `resume`)
- Cost estimation (`schulpipeline cost-estimate`)
- `make` targets

### 6.2 Write CHANGELOG.md

```markdown
# Changelog

## v1.0.0 (2026-02-26)

### Features
- 5-stage pipeline: intake → plan → research → synthesize → artifact
- Multi-backend routing: Groq, Gemini, Mistral, OpenAI, Ollama
- PPTX, DOCX, MD output
- 6 style themes: clean, modern, minimal, school, corporate, dark
- Visual placeholder system for slides
- Document scanner with heuristic + LLM classification
- Session persistence and resume
- Preset system (subject × output type)
- Cost estimation ($0.00 with free tiers)
- Progress display
- Example data for immediate testing

### Technical
- JSON Schema validation between stages
- Rate-limit-aware cascade routing with backoff
- 200+ tests
- GitHub Actions CI
- Pre-commit hooks (ruff)
```

### 6.3 Update .env.example

```env
# Required — at least one pair. Both are free.
GROQ_API_KEY=gsk_your_key_here
GEMINI_API_KEY=AIza_your_key_here

# Optional — paid, used as fallback only
# OPENAI_API_KEY=sk-...
# MISTRAL_API_KEY=...
```

---

## Phase 7: Release

### 7.1 Version bump

- `pyproject.toml` → `version = "1.0.0"`
- `schulpipeline/__init__.py` → `__version__ = "1.0.0"`

### 7.2 Git commits (clean history)

```bash
# 1. Safety gate (must be FIRST commit if not already done)
git add .gitignore
git commit -m "safety: protect student data from git history"

# 2. Cleanup
git add -A  # safe now because .gitignore protects Data_School_Tasks/
git commit -m "chore: delete temp files, organize docs"

# 3. Bug fixes + code quality
git add schulpipeline/ tests/
git commit -m "fix: dotenv, config validation, lint, dead code cleanup"

# 4. Example data
git add examples/
git commit -m "feat: synthetic example data for testing and onboarding"

# 5. Documentation
git add README.md CHANGELOG.md docs/
git commit -m "docs: v1 README, changelog, architecture docs"

# 6. Release
git add pyproject.toml schulpipeline/__init__.py
git commit -m "release: v1.0.0"
git tag v1.0.0
```

### 7.3 Verify clean install

```bash
python -m venv /tmp/sp-test && source /tmp/sp-test/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in real keys
schulpipeline doctor
schulpipeline presets
schulpipeline scan examples/tasks/
schulpipeline run --yes --input examples/tasks/DE-BSP/IT_B1_A1_Energie.docx
ls output/  # verify artifact exists
pytest tests/ --ignore=tests/live -q
```

### 7.4 Post-release verify

```bash
# Confirm no student data leaked
git log --all --name-only | grep -i "Data_School_Tasks" && echo "LEAK!" || echo "Clean"
git ls-files | grep -i "Data_School_Tasks" && echo "TRACKED!" || echo "Safe"
```

---

## Execution Order

```
Phase 1.0 (.gitignore)  ──→  Phase 1.1-1.4 (bugs)
         │
         ▼
Phase 2 (cleanup)  ──→  Phase 3 (examples)  ──→  Phase 4 (code quality)
                                                          │
                                                          ▼
                          Phase 5 (scanner CLI)  ←────────┘
                                   │
                                   ▼
                          Phase 6 (docs)  ──→  Phase 7 (release)
```

**Critical path**: 1.0 → 2 → 3 → 4 → 6 → 7
**Parallel safe**: Phase 5 (scanner CLI) can happen alongside Phase 4.

---

## Acceptance Criteria for v1.0.0

- [ ] `git ls-files | grep Data_School_Tasks` returns NOTHING
- [ ] `make test` → all green, 0 failures
- [ ] `make lint` → 0 warnings
- [ ] `schulpipeline doctor` → all OK with .env
- [ ] `schulpipeline run --yes --input examples/tasks/DE-BSP/IT_B1_A1_Energie.docx` → produces artifact
- [ ] `schulpipeline scan examples/tasks/` → prints summary with correct classifications
- [ ] `examples/` contains synthetic docs + generated outputs + manifest
- [ ] No `_*.py` or `_*.txt` temp files in root
- [ ] README covers all CLI commands incl. examples
- [ ] CHANGELOG.md exists
- [ ] `git tag v1.0.0` set
- [ ] Clean `pip install -e .` in fresh venv works
- [ ] `git log --all --name-only | grep Data_School_Tasks` returns nothing
