# Claude Code Fix Plan — schulpipeline Structural Issues

**Target:** 8 identified issues, prioritized by blast radius.  
**Approach:** Fix the root divergence first (Stage-Registry), then everything else slots in cleanly.  
**Tests must stay green throughout.** Run `python -m pytest tests/ --ignore=tests/live -x` after each checkpoint.

---

## Overview

| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| 1 | `SessionRunner`/`Pipeline` stage-list divergence | High | 2h |
| 2 | Post-processing god block in `pipeline.py` | High | 1.5h |
| 3 | `PipelineConfig.DEFAULT_CASCADE` as instance field | Medium | 30min |
| 4 | Double `BackendRouter` init in `cmd_run` | Medium | 30min |
| 5 | `display_title` only checks `plan` stage | Low | 15min |
| 6 | `SessionStore.purge()` has no CLI surface | Low | 30min |
| 7 | `--verbose`/`--json` silent conflict in `scan` | Low | 15min |
| 8 | Agent system dead code — no CLI surface | Low | 1h |

Do them in this order. Issues 1+2 are tightly coupled — do them in one session.

---

## Issue 1 — Stage-Registry + SessionRunner divergence

### Problem

Three places independently define the 5-stage sequence or stage-name lists:

```python
# pipeline.py
self._standard_stages = [IntakeStage(), PlanStage(), ...]     # instance 1

# session.py — SessionRunner.run()
all_stages = [IntakeStage(), PlanStage(), ...]                 # instance 2

# session.py — SessionRunner.retry_from()
stage_order = ["intake", "plan", "research", "synthesize", "artifact"]  # instance 3
```

`_select_stages()` in `Pipeline` handles worksheet/audit/template paths but `SessionRunner`
always uses the 5-stage hardcoded list. Resuming a worksheet session uses wrong stages.

### Fix

**Step 1:** Create a Stage-Registry in `schulpipeline/stages/__init__.py`.

```python
# Add to stages/__init__.py after existing imports

from .artifact import ArtifactStage
from .intake import IntakeStage
from .plan import PlanStage
from .research import ResearchStage
from .synthesize import SynthesizeStage

# Lazy imports for optional stages — avoids import errors if dependencies missing
def _load_worksheet_stages():
    from ..worksheet import DecomposeStage, SolveStage
    return DecomposeStage, SolveStage

def _load_audit_stages():
    from ..audit import AuditStage
    return (AuditStage,)

def _load_document_stages():
    from ..documents import ClassifyDocsStage, FillTemplateStage
    return ClassifyDocsStage, FillTemplateStage

def _load_requirements_stages():
    from ..requirements import AmendmentsStage, ClassifyReportStage
    return ClassifyReportStage, AmendmentsStage


# Core stage registry — maps name → class
STAGE_REGISTRY: dict[str, type] = {
    "intake": IntakeStage,
    "plan": PlanStage,
    "research": ResearchStage,
    "synthesize": SynthesizeStage,
    "artifact": ArtifactStage,
}

# Standard 5-stage sequence (used by Pipeline and SessionRunner as default)
STANDARD_STAGE_SEQUENCE: list[str] = ["intake", "plan", "research", "synthesize", "artifact"]

# Alternative sequences keyed by output_constraints flag
ALTERNATIVE_SEQUENCES: dict[str, list[str]] = {
    "worksheet_mode":       ["intake", "decompose", "solve"],
    "audit_only":           ["intake", "classify_docs", "audit"],
    "template_mode":        ["intake", "classify_docs", "audit", "fill_template"],
    "requirements_report":  ["intake", "classify_docs", "audit", "classify_report", "amendments"],
}


def resolve_stage_sequence(preset=None) -> list[str]:
    """Return the ordered list of stage names for a given preset.

    This is the single source of truth for stage sequencing.
    Both Pipeline and SessionRunner must call this.
    """
    if preset and hasattr(preset, "output_constraints"):
        for flag, sequence in ALTERNATIVE_SEQUENCES.items():
            if preset.output_constraints.get(flag):
                return sequence
    return list(STANDARD_STAGE_SEQUENCE)


def build_stages(sequence: list[str]) -> list:
    """Instantiate stage objects from a sequence of names.

    Loads alternative stage classes lazily on first use.
    Raises ValueError for unknown stage names.
    """
    # Populate registry with optional stages on demand
    _ensure_optional_stages(sequence)

    stages = []
    for name in sequence:
        cls = STAGE_REGISTRY.get(name)
        if cls is None:
            raise ValueError(
                f"Unknown stage '{name}'. Available: {sorted(STAGE_REGISTRY.keys())}"
            )
        stages.append(cls())
    return stages


def _ensure_optional_stages(names: list[str]) -> None:
    """Load optional stage classes into the registry if needed."""
    needs = set(names) - STAGE_REGISTRY.keys()
    if not needs:
        return

    worksheet_names = {"decompose", "solve"}
    if needs & worksheet_names:
        DecomposeStage, SolveStage = _load_worksheet_stages()
        STAGE_REGISTRY["decompose"] = DecomposeStage
        STAGE_REGISTRY["solve"] = SolveStage

    audit_names = {"audit"}
    if needs & audit_names:
        (AuditStage,) = _load_audit_stages()
        STAGE_REGISTRY["audit"] = AuditStage

    doc_names = {"classify_docs", "fill_template"}
    if needs & doc_names:
        ClassifyDocsStage, FillTemplateStage = _load_document_stages()
        STAGE_REGISTRY["classify_docs"] = ClassifyDocsStage
        STAGE_REGISTRY["fill_template"] = FillTemplateStage

    req_names = {"classify_report", "amendments"}
    if needs & req_names:
        ClassifyReportStage, AmendmentsStage = _load_requirements_stages()
        STAGE_REGISTRY["classify_report"] = ClassifyReportStage
        STAGE_REGISTRY["amendments"] = AmendmentsStage
```

**Step 2:** Simplify `Pipeline._select_stages()` in `pipeline.py`.

Replace the entire `_select_stages` method with:

```python
def _select_stages(self, context: dict[str, Any]) -> list:
    """Select stage sequence based on preset/mode — single source of truth is the registry."""
    from .stages import build_stages, resolve_stage_sequence
    sequence = resolve_stage_sequence(context.get("preset"))
    return build_stages(sequence)
```

Delete the old if-block chain. The `_standard_stages` instance variable can stay for now
(used by `estimate_cost`) but `_select_stages` must no longer reference it directly.

Also update `estimate_cost` to use `resolve_stage_sequence`:

```python
def estimate_cost(self, stages: list[str] | None = None) -> tuple[float, dict]:
    from .backends.pricing import estimate_pipeline_cost
    from .stages import STANDARD_STAGE_SEQUENCE
    stage_names = stages or STANDARD_STAGE_SEQUENCE
    effective_cascade = {name: self.config.cascade_for(name) for name in stage_names}
    return estimate_pipeline_cost(stage_names, effective_cascade)
```

**Step 3:** Fix `SessionRunner` in `session.py`.

Replace both the `all_stages` list in `run()` and the `stage_order` list in `retry_from()`:

```python
# In SessionRunner.run():
from .stages import build_stages, resolve_stage_sequence

# Remove the hardcoded all_stages list.
# Instead:
sequence = resolve_stage_sequence(preset)
all_stages = build_stages(sequence)
total_stages = len(all_stages)

# In SessionRunner.retry_from():
from .stages import resolve_stage_sequence

# Replace:
#   stage_order = ["intake", "plan", "research", "synthesize", "artifact"]
# With:
stage_order = resolve_stage_sequence(preset)

if stage_name not in stage_order:
    raise ValueError(
        f"Unknown stage '{stage_name}' for this preset. "
        f"Valid stages: {stage_order}"
    )
```

### Acceptance Criteria

- [ ] `resolve_stage_sequence()` returns `["intake", "decompose", "solve"]` for a preset with `worksheet_mode: true`
- [ ] `Pipeline._select_stages()` is ≤5 lines, no if-chains
- [ ] `SessionRunner.run()` has no hardcoded `[IntakeStage(), ...]` list
- [ ] `SessionRunner.retry_from()` has no hardcoded `stage_order` list
- [ ] All 185 existing tests still pass

---

## Issue 2 — Post-processing god block in `pipeline.py`

### Problem

`Pipeline.run()` has ~100 lines of `if is_worksheet / if is_template / if is_audit / if is_req_report`
after the stage loop that assemble output files. This logic belongs inside the stages themselves
(or in output formatter helpers), not bolted on after the loop. The four booleans are
computed redundantly — `_select_stages` already knows which path we're on.

### Fix

The right fix is to make the final stage in each sequence responsible for its own output file,
matching what `ArtifactStage` already does for the standard path.

**Step 1:** Add a `post_run` hook to the stage loop in `pipeline.py`.

Replace the entire post-loop block (everything from `# For worksheet mode` to the end of
the `is_req_report` block) with a single call:

```python
# After the stage loop succeeds, resolve the output path.
# ArtifactStage writes the file and stores "file_path" in its data.
# For alternative pipelines, their terminal stage must do the same.
output_path = results[-1].data.get("file_path") if results else None
```

**Step 2:** Move the file-writing logic into each terminal stage.

Each alternative terminal stage (`SolveStage`, `AuditStage`, `FillTemplateStage`,
`AmendmentsStage`) needs to write its output file and include `file_path` in its returned
data, just like `ArtifactStage` does.

For `SolveStage` in `worksheet.py`:

```python
async def execute(self, context: dict[str, Any], backend: Any, config: Any) -> dict[str, Any]:
    # ... existing solve logic ...
    result = { "title": ..., "solved_tasks": ..., "unsolvable_tasks": ... }

    # Write output file — mirrors what ArtifactStage does
    output_dir = Path(config.output.dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_title = _safe_filename(result.get("title", "Arbeitsblatt"))

    try:
        out_path = output_dir / f"{safe_title}.docx"
        format_worksheet_as_docx(result, out_path)
    except Exception as e:
        logger = __import__("logging").getLogger("schulpipeline.stages.solve")
        logger.warning(f"DOCX failed, falling back to MD: {e}")
        out_path = output_dir / f"{safe_title}.md"
        out_path.write_text(format_worksheet_as_md(result), encoding="utf-8")

    result["file_path"] = str(out_path)
    return result
```

Apply the same pattern to `AuditStage`, `FillTemplateStage`, and `AmendmentsStage`.
Each must:
1. Write its output file at the end of `execute()`
2. Include `"file_path": str(out_path)` in the returned dict

**Step 3:** Add `_safe_filename()` helper to `worksheet.py` (and import in the other modules):

```python
def _safe_filename(title: str, max_len: int = 60) -> str:
    """Convert a title to a safe filename."""
    replacements = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"}
    for old, new in replacements.items():
        title = title.replace(old, new)
    return "".join(c if c.isalnum() or c in "-_ " else "" for c in title).strip().replace(" ", "_")[:max_len]
```

**Step 4:** Clean up `pipeline.py`.

After the stage loop, `Pipeline.run()` should end simply:

```python
output_path = results[-1].data.get("file_path") if results else None
logger.info(f"Pipeline completed in {elapsed}ms, cost: ${self.router.total_cost:.4f}")
if output_path:
    logger.info(f"Output: {output_path}")

return PipelineResult(
    success=True,
    results=results,
    output_path=output_path,
    total_cost_usd=self.router.total_cost,
    elapsed_ms=elapsed,
)
```

Delete: `is_worksheet`, `is_template`, `is_audit`, `is_req_report` booleans and all
their associated if-blocks.

### Acceptance Criteria

- [ ] `pipeline.py run()` has no `is_worksheet`, `is_template`, `is_audit`, `is_req_report` variables
- [ ] `Pipeline.run()` loop body is ≤60 lines total
- [ ] `SolveStage.execute()` writes its file and returns `file_path`
- [ ] `AuditStage.execute()` writes its file and returns `file_path`
- [ ] `FillTemplateStage.execute()` writes its file and returns `file_path`
- [ ] `AmendmentsStage.execute()` writes its file and returns `file_path`
- [ ] All 185 existing tests still pass

**Note:** If `AuditStage`, `FillTemplateStage`, or `AmendmentsStage` don't yet have a
real `execute()` implementation (they may be stubs), add a minimal one that writes a
placeholder `.md` file. Do not leave them as `raise NotImplementedError`.

---

## Issue 3 — `PipelineConfig.DEFAULT_CASCADE` as instance field

### Problem

In `config.py`, `DEFAULT_CASCADE` is declared as a dataclass field and assigned in
`__post_init__`. It's constant and never varies per instance — wastes memory per instance
and confuses readers.

### Fix

Move it to module level in `config.py`:

```python
# At module level, after the dataclass definitions:
_DEFAULT_CASCADE: dict[str, list[str]] = {
    "intake":          ["gemini", "openai"],
    "plan":            ["groq", "mistral", "gemini"],
    "research":        ["groq", "mistral", "gemini"],
    "synthesize":      ["groq", "gemini", "mistral", "openai"],
    "artifact":        ["groq", "gemini", "mistral", "openai"],
    "decompose":       ["groq", "gemini", "mistral"],
    "solve":           ["groq", "gemini", "mistral", "openai"],
    "classify_docs":   ["groq", "gemini", "mistral"],
    "fill_template":   ["groq", "gemini", "mistral", "openai"],
    "audit":           ["groq", "gemini", "mistral"],
    "classify_report": ["groq", "gemini", "mistral"],
    "amendments":      ["groq", "gemini", "mistral", "openai"],
    "agent_codegen":   ["groq", "gemini", "mistral", "openai"],
}
```

Update `PipelineConfig`:

```python
@dataclass
class PipelineConfig:
    backends: dict[str, BackendConfig] = field(default_factory=dict)
    cascade: dict[str, list[str]] = field(default_factory=dict)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    log_level: str = "INFO"
    log_file: str = ".schulpipeline/pipeline.log"
    style: str | dict = "clean"
    visuals: bool | dict = True
    # DEFAULT_CASCADE field removed entirely

    def cascade_for(self, stage: str) -> list[str]:
        order = self.cascade.get(stage, _DEFAULT_CASCADE.get(stage, []))
        return [name for name in order if name in self.backends and self.backends[name].is_available]

    def available_backends(self) -> list[str]:
        return [name for name, cfg in self.backends.items() if cfg.is_available]
```

Remove `__post_init__` entirely (or keep it only if it's doing other work — check first).

### Acceptance Criteria

- [ ] `PipelineConfig` has no `DEFAULT_CASCADE` field
- [ ] No `__post_init__` in `PipelineConfig` (unless needed for other reasons)
- [ ] `_DEFAULT_CASCADE` exists at module level in `config.py`
- [ ] `cascade_for()` returns correct results for known and unknown stages
- [ ] `test_config.py` passes

---

## Issue 4 — Double `BackendRouter` init in `cmd_run`

### Problem

`cmd_run` in `cli.py` creates two separate `BackendRouter` instances:

```python
# Instance 1 — just for the cost estimate
pipeline_check = Pipeline(config, BackendRouter(config))
total_cost, _ = pipeline_check.estimate_cost()
await pipeline_check.router.close()

# ... then later ...

# Instance 2 — actual run
router = BackendRouter(config)
pipeline = Pipeline(config, router)
```

`estimate_cost()` is a pure calculation — it never calls any backend. The router
passed to `Pipeline.__init__` for cost estimation is never actually used.

### Fix

`Pipeline.estimate_cost()` should not require a router at all. Make it a standalone function
or a static method that only needs the config:

```python
# In pipeline.py
def estimate_cost(self, stages: list[str] | None = None) -> tuple[float, dict]:
    """Estimate cost — pure calculation, no network calls."""
    from .backends.pricing import estimate_pipeline_cost
    from .stages import STANDARD_STAGE_SEQUENCE
    stage_names = stages or STANDARD_STAGE_SEQUENCE
    # Use config directly, no router needed
    effective_cascade = {name: self.config.cascade_for(name) for name in stage_names}
    return estimate_pipeline_cost(stage_names, effective_cascade)
```

Update `cmd_run` in `cli.py`:

```python
# Cost warning — no extra router needed
if not getattr(args, "yes", False):
    # Create a temporary pipeline with no router just for cost estimate
    from .pipeline import Pipeline
    pipeline_check = Pipeline(config, None)  # router=None is fine for estimate_cost
    total_cost, _ = pipeline_check.estimate_cost()
    # No router.close() needed

    if total_cost > 0.0:
        print(f"\nGeschaetzte Kosten: ${total_cost:.4f}")
        # ... confirmation prompt ...
```

Update `Pipeline.__init__` to accept `router=None`:

```python
def __init__(self, config: PipelineConfig, router: BackendRouter | None):
    self.config = config
    self.router = router
    self._standard_stages = [...]
```

Add a guard in `Pipeline.run()` so it fails clearly if called without a router:

```python
async def run(self, raw_input, ...):
    if self.router is None:
        raise RuntimeError("Pipeline.run() requires a router. Pass router=BackendRouter(config).")
    ...
```

### Acceptance Criteria

- [ ] `cmd_run` creates exactly one `BackendRouter` instance
- [ ] `Pipeline(config, None).estimate_cost()` works without error
- [ ] `Pipeline(config, None).run(...)` raises `RuntimeError` with a clear message
- [ ] `test_pipeline_e2e.py` passes

---

## Issue 5 — `display_title` only checks `plan` stage

### Problem

`Session.display_title` in `session.py` only looks for a title in the `plan` stage snapshot.
For worksheet (`decompose`), audit, and requirements-report pipelines, `plan` is never run,
so the title always falls back to raw task input.

### Fix

```python
@property
def display_title(self) -> str:
    """Short display title from the first stage that provides one."""
    # Ordered by which stage is most likely to have a meaningful title
    title_stages = ["plan", "decompose", "classify_report", "audit", "synthesize"]
    for stage_name in title_stages:
        for snap in self.completed_stages:
            if snap.name == stage_name and snap.success:
                title = snap.data.get("title")
                if title:
                    return title[:60]
    return self.task_input[:60]
```

### Acceptance Criteria

- [ ] `display_title` returns a meaningful title for worksheet sessions (from `decompose` data)
- [ ] `display_title` still works correctly for standard 5-stage sessions
- [ ] `test_session.py` passes

---

## Issue 6 — `SessionStore.purge()` missing CLI surface

### Problem

`SessionStore.purge()` exists and is well-implemented but is never called. Sessions
accumulate indefinitely. There is no user-facing way to trigger cleanup.

### Fix

**Step 1:** Add a `purge` subcommand in `cli.py`.

In `build_parser()`, add:

```python
# --- purge ---
purge_p = subparsers.add_parser("purge", help="Alte Sessions entfernen")
purge_p.add_argument("--max-age", type=int, default=30,
                     help="Maximales Alter in Tagen (Standard: 30)")
purge_p.add_argument("--max-count", type=int, default=50,
                     help="Maximale Anzahl Sessions (Standard: 50)")
purge_p.add_argument("--dry-run", action="store_true",
                     help="Zeige was geloescht wuerde, ohne zu loeschen")
```

**Step 2:** Add `cmd_purge()`:

```python
def cmd_purge(args, config) -> int:
    from .session import SessionStore

    store = SessionStore()

    if args.dry_run:
        # Show what would be deleted without actually deleting
        entries = store.list_sessions(limit=200)
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        to_delete = []
        for i, e in enumerate(entries):
            if e.get("status") == "running":
                continue
            if i >= args.max_count:
                to_delete.append(e)
                continue
            updated = e.get("updated_at", "")
            if updated:
                try:
                    ts = datetime.fromisoformat(updated.rstrip("Z")).replace(tzinfo=timezone.utc)
                    if (now - ts).days > args.max_age:
                        to_delete.append(e)
                except (ValueError, TypeError):
                    pass

        if not to_delete:
            print("Keine Sessions zum Loeschen gefunden.")
            return 0
        print(f"{len(to_delete)} Sessions wuerden geloescht:")
        for e in to_delete:
            print(f"  {e['id']}  {e.get('status', '?'):10s}  {e.get('title', '')[:40]}")
        return 0

    removed = store.purge(max_age_days=args.max_age, max_count=args.max_count)
    if removed:
        print(f"{removed} Sessions geloescht.")
    else:
        print("Keine Sessions zum Loeschen gefunden.")
    return 0
```

**Step 3:** Wire it into `main()`:

```python
elif args.command == "purge":
    sys.exit(cmd_purge(args, config))
```

### Acceptance Criteria

- [ ] `schulpipeline purge --help` shows usage
- [ ] `schulpipeline purge --dry-run` lists sessions that would be removed without deleting
- [ ] `schulpipeline purge` removes sessions older than 30 days or beyond count 50
- [ ] Running sessions are never purged
- [ ] `test_session.py` has a test for `purge()` with age and count limits

---

## Issue 7 — `--verbose`/`--json` silent conflict in `scan`

### Problem

Passing both `--verbose` and `--json` to `schulpipeline scan` silently ignores `--verbose`.
The user gets no indication their flag was dropped.

### Fix

In `cmd_scan()` in `cli.py`, add an early warning:

```python
def cmd_scan(args) -> int:
    if getattr(args, "verbose", False) and args.json_out:
        print("Hinweis: --verbose wird ignoriert wenn --json aktiv ist.", file=sys.stderr)

    # ... rest of function unchanged ...
```

### Acceptance Criteria

- [ ] `schulpipeline scan . --verbose --json` prints a warning to stderr
- [ ] Output is still valid JSON (warning goes to stderr, not stdout)

---

## Issue 8 — Agent system dead code — no CLI surface

### Problem

`agents.py` is 430 lines of implementation (`LocalLLMAgent`, `ClaudeCodeAgent`,
`CodexAgent`, `ProjectSpec`, `build_project_spec`) with zero CLI surface. No user can
invoke any of it. The `projekt` and `projekt_einfach` output presets in `presets.py`
reference `agent_mode: True` but nothing reads that flag.

### Fix Option A (Recommended): Wire `local_llm` into the `run` command minimally.

This makes the existing code actually reachable without new features.

**Step 1:** In `ArtifactStage.execute()` (in `stages/artifact.py`), detect `agent_mode`:

```python
async def execute(self, context: dict[str, Any], backend: Any, config: Any) -> dict[str, Any]:
    preset = context.get("preset")

    # Agent mode — delegate to code generation agent
    if preset and preset.output_constraints.get("agent_mode"):
        return await self._run_agent_mode(context, backend, config)

    # Standard artifact generation
    # ... existing code ...

async def _run_agent_mode(self, context, backend, config) -> dict[str, Any]:
    from ..agents import LocalLLMAgent, build_project_spec
    spec = build_project_spec(context.get("synthesize", {}), context.get("intake", {}))
    agent = LocalLLMAgent(backend)
    output_dir = Path(config.output.dir) / _safe_filename(spec.title)
    result = await agent.execute(spec, output_dir)
    return {
        "file_path": str(output_dir),
        "artifact_type": "project",
        "files_created": result.files_created,
        "errors": result.errors,
    }
```

**Step 2:** Add `--agent` flag to `run` subcommand in `cli.py` (optional override):

```python
run_p.add_argument("--agent", choices=["local_llm", "claude_code", "codex"],
                   help="Code-Generierungs-Agent (nur fuer Coding-Presets)")
```

If `--agent` is passed, set it in overrides so `ArtifactStage` can pick it up via context.

**Step 3:** Update `docs/` to document which presets trigger agent mode.

### Fix Option B (Conservative): Move to `_future/` and document clearly.

If wiring in even `local_llm` is too risky for this sprint, move `agents.py` to
`schulpipeline/_future/agents.py` and add a comment at the top of the original location:

```python
# agents.py has been moved to _future/agents.py.
# It is not yet connected to the CLI or pipeline.
# See docs/improvements.md T1-6 for integration plan.
```

**Recommendation:** Do Option A for `local_llm` only (it uses existing backends, zero
extra dependencies). Skip `claude_code` and `codex` wiring for now — they require
external CLIs that may not be installed.

### Acceptance Criteria (Option A)

- [ ] `schulpipeline run --preset fiae-projekt-prog "Erstelle ein CLI-Tool..."` runs
      and produces a project directory via `LocalLLMAgent`
- [ ] `ArtifactStage` detects `agent_mode: True` from preset constraints
- [ ] Non-agent presets are unaffected
- [ ] `LocalLLMAgent` errors surface as stage errors (not crashes)

---

## Execution Order for Claude Code

```
1. Start with Issue 3 (config fix) — smallest, no dependencies, warms up the codebase
2. Issue 1 (Stage-Registry) — core structural fix
3. Issue 2 (god block) — depends on Issue 1 being done first
4. Issue 4 (double router) — isolated cli.py + pipeline.py change
5. Issue 5 (display_title) — 10-minute fix
6. Issue 6 (purge CLI) — isolated cli.py addition
7. Issue 7 (verbose/json warning) — one-liner
8. Issue 8 (agent wiring) — do Option A or B depending on time
```

**Run after each issue:**
```bash
python -m pytest tests/ --ignore=tests/live -x -q
```

**Final check:**
```bash
python -m pytest tests/ --ignore=tests/live -v
python -m schulpipeline doctor
python -m schulpipeline backends
python -m schulpipeline presets
```

---

## Files Changed by Issue

| File | Issues |
|------|--------|
| `schulpipeline/stages/__init__.py` | 1 |
| `schulpipeline/pipeline.py` | 1, 2, 4 |
| `schulpipeline/session.py` | 1, 5 |
| `schulpipeline/worksheet.py` | 2 |
| `schulpipeline/audit.py` | 2 |
| `schulpipeline/documents.py` | 2 |
| `schulpipeline/requirements.py` | 2 |
| `schulpipeline/config.py` | 3 |
| `schulpipeline/cli.py` | 4, 6, 7, 8 |
| `schulpipeline/stages/artifact.py` | 8 |
| `tests/test_session.py` | 5, 6 |
| `tests/test_stages.py` | 1, 2 |
| `tests/test_config.py` | 3 |
| `tests/test_pipeline_e2e.py` | 1, 2 |
