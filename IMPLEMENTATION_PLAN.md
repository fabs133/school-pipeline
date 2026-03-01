# Implementation Plan — Post-Assessment Fixes

**Created:** 2026-03-01
**Scope:** schulpipeline + slide-forge
**Estimated total effort:** ~60-80 hours across all phases

---

## Phase 1: Critical Fixes (Day 1)

*Estimated effort: 2-3 hours. Zero risk of regressions.*

### 1.1 Pin slideforge git dependency

**File:** `pyproject.toml:26`
**Problem:** `slideforge @ git+https://github.com/fabs133/slide-forge.git` installs HEAD with no version lock. Any breaking change in slide-forge breaks CI and user installs.
**Fix:** Tag slide-forge `v1.0.0` and pin:
```toml
"slideforge @ git+https://github.com/fabs133/slide-forge.git@v1.0.0"
```
**Steps:**
1. `cd slide-forge && git tag v1.0.0 && git push origin v1.0.0`
2. Update `pyproject.toml` with `@v1.0.0` suffix
3. Verify: `pip install -e . && python -c "import slideforge"`

### 1.2 Fix temp file leak in slide-forge export

**File:** `slide-forge/slideforge/server.py:107-120`
**Problem:** `NamedTemporaryFile(delete=False)` creates a file that is never cleaned up. Every PPTX export leaks a file in the OS temp directory.
**Fix:** Use FastAPI's `BackgroundTask` to delete the file after the response is sent:
```python
from starlette.background import BackgroundTask
import os

@app.get("/api/projects/{project_id}/export")
def export_pptx(project_id: str):
    ...
    return FileResponse(
        tmp.name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"{pres.name}.pptx",
        background=BackgroundTask(os.unlink, tmp.name),
    )
```
**Test:** Add test in `test_server.py` that verifies the temp file is removed after export.

### 1.3 Sanitize project IDs in slide-forge storage

**File:** `slide-forge/slideforge/storage.py:29`
**Problem:** `project_id` from URL path is used directly in `self._dir / f"{project_id}.json"`. A crafted ID like `../../etc/passwd` could traverse the filesystem.
**Fix:** Validate that the ID contains only safe characters:
```python
import re

def _path(self, project_id: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", project_id):
        raise ValueError(f"Invalid project ID: {project_id}")
    return self._dir / f"{project_id}.json"
```
**Test:** Add test that verifies path-traversal IDs raise `ValueError`.

### 1.4 Fix corrupted slide-forge test files

**Files:** `slide-forge/tests/test_storage.py`, `test_template.py`, `test_renderer.py`
**Problem:** The docgen tool (qwen2.5-coder:7b) inserted nested function definitions and orphaned docstrings inside test functions. These are dead code that pytest never collects.
**Affected locations:**
- `test_storage.py:56-96` — 3 nested dead defs inside `test_get_missing_returns_none`
- `test_storage.py:99-131` — 3 orphaned docstrings inside `test_delete_existing`
- `test_storage.py:148-169` — orphaned docstring inside `test_save_overwrites`
- `test_template.py:31-49` — orphaned docstring inside `test_load_template_valid`
- `test_template.py:65-85` — orphaned docstring inside `test_wrong_version_raises`
- `test_template.py:88-105` — orphaned docstring inside `test_missing_layout_raises`
- `test_template.py:108-131` — nested dead def inside `test_generated_template_has_all_layouts`
- `test_template.py:134-158` — nested dead def inside `test_get_layout_by_name`
- `test_renderer.py:127-148` — orphaned docstring inside `test_render_empty_presentation`
- `test_renderer.py:151-171` — orphaned docstring inside `test_render_unknown_layout_raises`

**Fix:** Remove all nested function definitions and orphaned docstrings from inside test functions. Keep only the actual test logic and its own docstring (if correct).
**Verification:** `pytest tests/ -v` must still pass 38 tests (no test count change — the dead defs were never collected).

---

## Phase 2: slide-forge Server Hardening (Day 2)

*Estimated effort: 3-4 hours.*

### 2.1 Fix relative projects directory

**File:** `slide-forge/slideforge/server.py:17`
**Problem:** `_PROJECTS_DIR = Path("projects")` resolves to CWD. Starting the server from a different directory creates/reads from the wrong location.
**Fix:** Use the package directory as the base:
```python
_PROJECTS_DIR = Path(__file__).parent.parent / "projects"
```
**Test:** Verify server works when started from a different CWD.

### 2.2 Type the create_project endpoint

**File:** `slide-forge/slideforge/server.py:46-51`
**Problem:** `create_project(body: dict)` accepts unvalidated raw dicts.
**Fix:** Create a Pydantic model for the request body:
```python
class CreateProjectRequest(BaseModel):
    name: str = "Untitled"

@app.post("/api/projects", status_code=201)
def create_project(body: CreateProjectRequest):
    pres = Presentation(name=body.name)
```

### 2.3 Add approval endpoint tests

**File:** `slide-forge/tests/test_server.py`
**Problem:** `POST /approve` and `GET /approved` have zero tests.
**Fix:** Add tests:
- `test_approve_project` — approve and check `/approved` returns `true`
- `test_approve_missing_project_404` — approve a non-existent project
- `test_approved_default_false` — new project is not approved by default

### 2.4 Add prompts.py tests

**File:** `slide-forge/tests/test_prompts.py` (new file)
**Fix:** Test all 3 styles return non-empty strings, and invalid style raises `KeyError`. Consider adding a `.get()` fallback in `get_style_instruction()`.

### 2.5 Fix auto-generated docstrings in slide-forge source modules

**Files:** `slideforge/template_loader.py:71-93`, `slideforge/server.py:149-157`, `slideforge/tools/generate_template.py:349-358`, all test files
**Problem:** Docstrings describe wrong parameters, wrong class names, or contain merged content from adjacent functions.
**Fix:** Review and correct all auto-generated docstrings. Remove `:param:` tags from test functions. Fix class name references (e.g., "SlideManager" → "TemplateLoader").

---

## Phase 3: school-pipeline Code Quality (Day 3)

*Estimated effort: 4-5 hours.*

### 3.1 Fix `__import__("datetime")` antipattern

**File:** `schulpipeline/session.py` — lines 268, 287 (and possibly 352, 538)
**Problem:** Uses `__import__("datetime").timezone.utc` instead of a normal import.
**Fix:** Add `from datetime import timezone` at the top of the file. Replace all occurrences:
```python
# Before
now = datetime.now(tz=__import__("datetime").timezone.utc).isoformat() + "Z"
# After
now = datetime.now(tz=timezone.utc).isoformat() + "Z"
```

### 3.2 Add request timeouts to web research

**File:** `schulpipeline/research/web.py`
**Problem:** `requests.get()` and `requests.post()` calls have no timeout. A slow or unresponsive server will hang the pipeline indefinitely.
**Fix:** Add a module-level constant and apply to all calls:
```python
_REQUEST_TIMEOUT = 15.0  # seconds

# Apply to all requests calls:
resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
resp = requests.post(url, data=data, timeout=_REQUEST_TIMEOUT)
```

### 3.3 Relax synthesis content minLength

**File:** `specs/synthesis.json:17`
**Problem:** `"content": { "type": "string", "minLength": 10 }` is too strict. Title slides with short subtitles like "Fazit" (5 chars) fail validation.
**Fix:** Reduce to `"minLength": 1` (non-empty is sufficient; the LLM is expected to produce meaningful content, and bullet_points carry the real payload).

### 3.4 Make review server port dynamic

**File:** `schulpipeline/review.py:43`
**Problem:** Port 8000 is hardcoded. Fails if already in use.
**Fix:** Find an available port dynamically:
```python
import socket

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

port = _find_free_port()
config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
```
Update the `webbrowser.open()` call to use the dynamic port.

### 3.5 Add user-friendly import error for review extras

**File:** `schulpipeline/review.py:24-28`
**Problem:** If `[review]` extras not installed, user gets raw `ModuleNotFoundError`.
**Fix:** Wrap the imports in a try/except:
```python
def run_review(presentation: Presentation) -> Presentation:
    try:
        import httpx
        import uvicorn
        ...
    except ImportError as e:
        raise ImportError(
            "Review server requires extra dependencies. "
            "Install with: pip install -e '.[review]'"
        ) from e
```

### 3.6 Add timeout to review polling loop

**File:** `schulpipeline/review.py:61-70`
**Problem:** The approval polling loop runs forever if the user never clicks "Fertig".
**Fix:** Add a configurable timeout (default 30 minutes):
```python
deadline = time.monotonic() + 1800  # 30 minutes
while time.monotonic() < deadline:
    ...
raise TimeoutError("Review was not completed within 30 minutes.")
```

---

## Phase 4: CI/CD Improvements (Day 4)

*Estimated effort: 3-4 hours.*

### 4.1 Add pip caching

**File:** `.github/workflows/ci.yml`
**Fix:** Add `cache: 'pip'` to the `setup-python` step:
```yaml
- uses: actions/setup-python@v5
  with:
    python-version: ${{ matrix.python-version }}
    cache: 'pip'
```

### 4.2 Add ruff format check

**File:** `.github/workflows/ci.yml`
**Fix:** Add formatting step after lint:
```yaml
- name: Check formatting
  run: ruff format --check schulpipeline/ tests/
```

### 4.3 Extend ruff check to tests/

**File:** `.github/workflows/ci.yml:29`
**Fix:** Change `ruff check schulpipeline/` to:
```yaml
- name: Lint with ruff
  run: ruff check schulpipeline/ tests/
```

### 4.4 Add coverage reporting

**File:** `.github/workflows/ci.yml`
**Fix:** Add `pytest-cov` to dev dependencies and update test step:
```yaml
- name: Run offline tests
  run: pytest tests/ -v --ignore=tests/live -x --cov=schulpipeline --cov-report=term-missing
```
Update `pyproject.toml`:
```toml
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "ruff>=0.4", "pre-commit>=3.5", "pytest-cov>=5.0"]
```

### 4.5 Add build smoke test

**File:** `.github/workflows/ci.yml`
**Fix:** Add step after tests:
```yaml
- name: Verify CLI entry point
  run: schulpipeline --help
```

### 4.6 Set up slide-forge CI

**File:** `slide-forge/.github/workflows/ci.yml` (new file)
**Fix:** Create a basic CI workflow mirroring school-pipeline:
```yaml
name: CI
on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'
      - run: pip install -e ".[dev]"
      - run: ruff check slideforge/ tests/
      - run: ruff format --check slideforge/ tests/
      - run: pytest tests/ -v
```

---

## Phase 5: Test Coverage Expansion (Days 5-7)

*Estimated effort: 20-30 hours. Highest effort phase.*

### 5.1 Migrate worksheet tests from run_tests.py to pytest

**File:** `tests/run_tests.py:925-1130` → `tests/test_worksheet.py` (new file)
**Problem:** 8 worksheet tests exist in `run_tests.py` but are never run by pytest or CI.
**Tests to migrate:**
1. `test_decompose_stage` (line 928) — DecomposeStage with mocked LLM
2. `test_solve_stage` (line 960) — SolveStage with mocked LLM
3. `test_format_worksheet_as_md` (line 985) — Markdown output formatting
4. `test_format_worksheet_as_docx` (line 1023) — DOCX file generation
5. `test_worksheet_preset_resolves` (line 1074) — Preset resolution
6. `test_worksheet_quick_presets` (line 1084) — Quick preset mapping
7. `test_pipeline_selects_worksheet_stages` (line 1093) — Stage selection
8. `test_pipeline_standard_stages_for_presentation` (line 1108) — Standard flow preserved

**Steps:**
1. Create `tests/test_worksheet.py` with the same mock fixtures from `run_tests.py` (lines 24-78, `DEFAULT_RESPONSES`)
2. Convert each `TestWorksheet.test_*` method to a standalone pytest function
3. Verify all 8 pass: `pytest tests/test_worksheet.py -v`
4. Verify total test count increases from 242 to 250

### 5.2 Add basic CLI tests

**File:** `tests/test_cli.py` (new file)
**Problem:** `cli.py` (959 lines) has zero tests. All 12 subcommands untested.
**Priority tests (cover the most-used commands):**
1. `test_build_parser` — parser creates without error, all subcommands registered
2. `test_cmd_presets` — captures stdout, verifies preset table output
3. `test_cmd_backends` — captures stdout, verifies backend listing
4. `test_cmd_sessions_empty` — no sessions, clean output
5. `test_cmd_scan_example_dir` — scans `examples/tasks/`, verifies output
6. `test_cmd_run_dry_run` — `--dry-run` flag with mocked backend
7. `test_cmd_doctor` — system diagnostics output

**Approach:** Use `unittest.mock.patch` on backend calls and `io.StringIO` for stdout capture. Do NOT test actual LLM calls — that's what live tests are for.

### 5.3 Add review server tests

**File:** `tests/test_review.py` (new file)
**Tests:**
1. `test_run_review_starts_server` — mock uvicorn, verify it starts
2. `test_run_review_opens_browser` — mock webbrowser.open, verify URL
3. `test_run_review_cleanup` — verify temp directory is removed on exit
4. `test_run_review_import_error` — verify user-friendly message when extras missing

### 5.4 Add web research tests

**File:** `tests/test_research_web.py` (new file)
**Tests:**
1. `test_disk_cache_put_get` — round-trip cache storage
2. `test_disk_cache_expiry` — expired entries return None
3. `test_search_ddg_mock` — mock requests.post, verify parsing
4. `test_scrape_page_mock` — mock requests.get, verify extraction
5. `test_request_timeout` — verify timeout parameter is passed

---

## Phase 6: Documentation Gaps (Day 8)

*Estimated effort: 4-5 hours.*

### 6.1 Create SECURITY.md

**File:** `SECURITY.md` (new file)
**Problem:** README links to `SECURITY.md` (line 303) but it doesn't exist.
**Content:** Standard security policy — how to report vulnerabilities, supported versions, response timeline.

### 6.2 Add `GET /approved` to slide-forge README

**File:** `slide-forge/README.md`
**Problem:** The API endpoints table doesn't include `GET /api/projects/{id}/approved`.
**Fix:** Add it to the table.

### 6.3 Review and fix all auto-generated docstrings

**Scope:** Both projects — all files touched by the Ollama docgen.
**Problem:** Multiple docstrings describe wrong parameters, wrong classes, or contain merged/duplicated content from adjacent functions.
**Approach:**
1. Run `grep -rn ":param " tests/` in slide-forge to find Sphinx params in test functions (they shouldn't have any)
2. Remove all `:param:`, `:type:`, `:return:`, `:rtype:` tags from test functions
3. Fix class name mismatches (e.g., "SlideManager" → "TemplateLoader")
4. Remove docstrings that describe a different function than the one they're in

---

## Phase 7: Nice-to-Have Improvements (Backlog)

*Lower priority. Schedule when time permits.*

### 7.1 Add CORS middleware to slide-forge

**File:** `slide-forge/slideforge/server.py`
**Fix:** Add `CORSMiddleware` for cross-origin API calls when schulpipeline runs on a different port.

### 7.2 Migrate HTTP calls to httpx.AsyncClient

**Files:** `schulpipeline/backends/gemini.py`, `schulpipeline/backends/openai_compat.py`, `schulpipeline/research/web.py`
**Problem:** Synchronous `requests` wrapped in `asyncio.to_thread()` — no connection pooling, thread overhead.
**Fix:** Use `httpx.AsyncClient` with connection pooling and proper async context.

### 7.3 Wire up `Del` keyboard shortcut in slide-forge frontend

**File:** `slide-forge/frontend/app.js` — `handleKeyboard()` function
**Problem:** HTML says `title="Delete slide (Del)"` but the shortcut isn't in the keyboard handler.

### 7.4 Add responsive CSS to slide-forge

**File:** `slide-forge/frontend/style.css`
**Problem:** Sidebar is fixed 240px, no media queries. Breaks on narrow screens.

### 7.5 Add type checking to CI (mypy)

**Files:** `.github/workflows/ci.yml`, `pyproject.toml`
**Fix:** Add mypy step. Start with `--ignore-missing-imports` and fix incrementally.

### 7.6 Make `_PRESET_STYLE_MAP` differentiate styles

**File:** `schulpipeline/artifacts/converter.py:24-28`
**Problem:** All 3 preset styles map to `SENTENCES`. The original `KEYWORDS` mapping caused 2-word bullets — but there should be a way to select `keywords` or `academic` via presets.
**Fix:** Keep `bullet-heavy → SENTENCES` as default. Add CLI flags or preset variants for users who want `keywords` or `academic` explicitly:
```python
_PRESET_STYLE_MAP: dict[str, PresentationStyle] = {
    "bullet-heavy": PresentationStyle.SENTENCES,
    "compact":      PresentationStyle.KEYWORDS,    # handouts can be terse
    "prose":        PresentationStyle.SENTENCES,
    "academic":     PresentationStyle.ACADEMIC,     # new preset style
}
```

---

## Execution Order Summary

| Phase | Scope | Effort | Risk | Priority |
|-------|-------|--------|------|----------|
| 1 | Critical fixes (pin dep, temp leak, path traversal, test corruption) | 2-3h | None | **P0 — Do first** |
| 2 | slide-forge server hardening | 3-4h | Low | P1 |
| 3 | school-pipeline code quality | 4-5h | Low | P1 |
| 4 | CI/CD improvements | 3-4h | None | P1 |
| 5 | Test coverage expansion | 20-30h | Low | P2 |
| 6 | Documentation gaps | 4-5h | None | P2 |
| 7 | Nice-to-have improvements | 10-15h | Medium | P3 — Backlog |

**Total: ~60-80 hours**

---

## Success Criteria

After completing Phases 1-6:
- [ ] All 38 slide-forge tests pass with no dead code in test files
- [ ] All 250+ school-pipeline tests pass (242 existing + 8 migrated worksheet)
- [ ] CI runs ruff check + format check + tests + coverage on both projects
- [ ] slideforge dependency pinned to a release tag
- [ ] No temp file leaks, no path traversal, no hardcoded ports
- [ ] SECURITY.md exists and is linked correctly
- [ ] All auto-generated docstrings reviewed and corrected
- [ ] Coverage report shows >60% for schulpipeline core modules
