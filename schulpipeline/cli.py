"""CLI entry point for schulpipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .config import load_config
from .backends.router import BackendRouter
from .logging_config import setup_logging, set_run_id
from .pipeline import Pipeline
from .presets import (
    OUTPUT_PRESETS,
    SUBJECT_PRESETS,
    QUICK_PRESETS,
    resolve_preset,
    resolve_quick,
    list_presets,
)


# --- Encoding-safe output helpers ---

def _supports_unicode() -> bool:
    """Check if stdout can handle Unicode output."""
    try:
        enc = getattr(sys.stdout, "encoding", "") or ""
        return enc.lower().replace("-", "") in ("utf8", "utf16", "utf32", "utf8sig")
    except Exception:
        return False


if _supports_unicode():
    SYM_OK, SYM_FAIL, SYM_RUN, SYM_PAUSE, SYM_PENDING = "\u2713", "\u2717", "\u25b6", "\u23f8", "\u25cb"
    SYM_HLINE, SYM_DLINE = "\u2500", "\u2550"
else:
    SYM_OK, SYM_FAIL, SYM_RUN, SYM_PAUSE, SYM_PENDING = "+", "X", ">", "||", "o"
    SYM_HLINE, SYM_DLINE = "-", "="


# Stage name translations for progress display
_STAGE_LABELS: dict[str, str] = {
    "intake": "Aufgabe analysieren",
    "plan": "Plan erstellen",
    "research": "Recherchieren",
    "synthesize": "Inhalt erstellen",
    "artifact": "Datei generieren",
}


def _progress_printer(event: str, stage_name: str, stage_index: int, total_stages: int, **kwargs) -> None:
    """Print real-time progress to stdout."""
    label = _STAGE_LABELS.get(stage_name, stage_name)
    step = f"[{stage_index + 1}/{total_stages}]"

    if event == "stage_start":
        print(f"  {step} {SYM_RUN} {label}...", end="", flush=True)
    elif event == "stage_done":
        elapsed_s = kwargs.get("elapsed_ms", 0) / 1000
        print(f"\r  {step} {SYM_OK} {label} ({elapsed_s:.1f}s)")
    elif event == "stage_error":
        elapsed_s = kwargs.get("elapsed_ms", 0) / 1000
        errors = kwargs.get("errors", [])
        print(f"\r  {step} {SYM_FAIL} {label} ({elapsed_s:.1f}s)")
        for err in errors[:3]:
            print(f"       {err}")


def _json_dumps(obj, **kwargs) -> str:
    """JSON serialization safe for piped output."""
    if not sys.stdout.isatty():
        kwargs.setdefault("ensure_ascii", True)
    else:
        kwargs.setdefault("ensure_ascii", False)
    return json.dumps(obj, **kwargs)


def _read_text_with_fallback(path: Path) -> str:
    """Read a text file, trying UTF-8 first then cp1252 and latin-1."""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schulpipeline",
        description="Schulaufgaben automatisieren — Präsentationen, Dokumente, Antworten",
    )
    parser.add_argument("--config", "-c", default="config.yaml", help="Config-Datei")
    parser.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--json-logs", action="store_true", help="JSON-Format für Log-Ausgabe")

    subparsers = parser.add_subparsers(dest="command", help="Befehle")

    # --- run ---
    run_p = subparsers.add_parser("run", help="Aufgabe bearbeiten")
    run_p.add_argument("task", nargs="?", help="Aufgabentext")
    run_p.add_argument("--input", "-i", help="Eingabedatei (Text, Bild, PDF)")
    run_p.add_argument("--output-dir", "-o", help="Ausgabeverzeichnis")
    run_p.add_argument("--preset", "-p", help="Quick-Preset (z.B. fiae-praesi-itsec)")
    run_p.add_argument("--output-type", help="Ausgabetyp (praesentation, ausarbeitung, aufgaben, ...)")
    run_p.add_argument("--subject", "-s", help="Fach (it_sicherheit, netzwerktechnik, wirtschaft, ...)")
    run_p.add_argument("--format", "-f", choices=["pptx", "docx", "md"], help="Format erzwingen")
    run_p.add_argument("--slides", type=int, help="Folienanzahl")
    run_p.add_argument("--tag", action="append", default=[], help="Tags für die Session")
    run_p.add_argument("--dry-run", action="store_true", help="Nur Plan anzeigen, nicht ausführen")
    run_p.add_argument("--style", help="Style-Preset (clean, modern, minimal, school, corporate, dark)")
    run_p.add_argument("--no-visuals", action="store_true", help="Keine visuellen Platzhalter")
    run_p.add_argument("--visual-placement", choices=["right", "center"], help="Platzierung der Visuals")
    run_p.add_argument("--yes", "-y", action="store_true", help="Kosten-Warnung überspringen")

    # --- resume ---
    resume_p = subparsers.add_parser("resume", help="Letzte/bestimmte Session fortsetzen")
    resume_p.add_argument("session_id", nargs="?", help="Session-ID (leer = letzte)")
    resume_p.add_argument("--from-stage", help="Ab dieser Stage neu starten")

    # --- sessions ---
    sessions_p = subparsers.add_parser("sessions", help="Sessions auflisten")
    sessions_p.add_argument("--status", choices=["created", "running", "paused", "completed", "failed"])
    sessions_p.add_argument("--subject", help="Nach Fach filtern")
    sessions_p.add_argument("--limit", type=int, default=10)
    sessions_p.add_argument("--json", action="store_true")

    # --- show ---
    show_p = subparsers.add_parser("show", help="Session-Details anzeigen")
    show_p.add_argument("session_id", help="Session-ID")
    show_p.add_argument("--stage", help="Nur Daten einer Stage anzeigen")

    # --- delete ---
    del_p = subparsers.add_parser("delete", help="Session löschen")
    del_p.add_argument("session_id", help="Session-ID")

    # --- plan ---
    plan_p = subparsers.add_parser("plan", help="Nur Plan anzeigen (Trockenlauf)")
    plan_p.add_argument("task", nargs="?", help="Aufgabentext")
    plan_p.add_argument("--input", "-i", help="Eingabedatei")
    plan_p.add_argument("--preset", "-p", help="Quick-Preset")
    plan_p.add_argument("--output-type", help="Ausgabetyp")
    plan_p.add_argument("--subject", "-s", help="Fach")
    plan_p.add_argument("--style", help="Style-Preset")

    # --- cost-estimate ---
    cost_p = subparsers.add_parser("cost-estimate", help="Kosten-Schätzung für eine Pipeline-Ausführung")
    cost_p.add_argument("task", nargs="?", help="Aufgabentext")
    cost_p.add_argument("--input", "-i", help="Eingabedatei")
    cost_p.add_argument("--preset", "-p", help="Quick-Preset")
    cost_p.add_argument("--output-type", help="Ausgabetyp")
    cost_p.add_argument("--subject", "-s", help="Fach")

    # --- presets ---
    presets_p = subparsers.add_parser("presets", help="Verfügbare Presets anzeigen")
    presets_p.add_argument("--json", action="store_true", help="Als JSON ausgeben")

    # --- backends ---
    subparsers.add_parser("backends", help="Verfügbare Backends anzeigen")

    # --- doctor ---
    subparsers.add_parser("doctor", help="System-Diagnose: Umgebung, Keys, Backends prüfen")

    return parser


def _resolve_preset_from_args(args: argparse.Namespace):
    """Build a ResolvedPreset from CLI arguments, or None."""
    overrides = {}
    if hasattr(args, "slides") and args.slides:
        overrides["section_count"] = args.slides

    if hasattr(args, "preset") and args.preset:
        return resolve_quick(args.preset, overrides or None)

    output_type = getattr(args, "output_type", None)
    subject = getattr(args, "subject", None)

    if output_type and subject:
        return resolve_preset(output_type, subject, overrides or None)
    if output_type and not subject:
        return resolve_preset(output_type, "custom", overrides or None)
    if subject and not output_type:
        return resolve_preset("aufgaben", subject, overrides or None)

    return None


async def cmd_cost_estimate(args: argparse.Namespace, config) -> int:
    """Show estimated cost for a pipeline run."""
    router = BackendRouter(config)
    pipeline = Pipeline(config, router)

    total, breakdown = pipeline.estimate_cost()
    await router.close()

    print("Kosten-Schaetzung (tatsaechliche Kosten koennen abweichen):\n")
    print(f"  {'Stage':15s} {'Backend':10s} {'Tokens':>12s} {'Kosten':>10s}")
    print(f"  {SYM_HLINE * 50}")

    for stage_name, info in breakdown.items():
        tokens = f"{info['tokens_in']}+{info['tokens_out']}"
        cost = f"${info['cost_usd']:.4f}"
        backend = info["backend"]
        free_marker = " (frei)" if info["cost_usd"] == 0.0 else ""
        print(f"  {stage_name:15s} {backend:10s} {tokens:>12s} {cost:>10s}{free_marker}")

    print(f"  {SYM_HLINE * 50}")
    print(f"  {'GESAMT':15s} {'':10s} {'':>12s} ${total:.4f}")

    if total == 0.0:
        print(f"\n{SYM_OK} Alle Backends sind kostenlos. Keine Kosten erwartet.")
    else:
        print("\n  Hinweis: Schaetzung basierend auf durchschnittlichem Token-Verbrauch.")

    return 0


async def cmd_run(args: argparse.Namespace, config) -> int:
    raw_input = _get_input(args)
    if raw_input is None:
        print("Fehler: Aufgabentext oder --input Datei angeben", file=sys.stderr)
        return 1

    preset = _resolve_preset_from_args(args)
    if preset:
        print(f"Preset: {preset.subject_label} → {preset.output_format.upper()}")

    if hasattr(args, "format") and args.format:
        config.output.default_format = args.format

    # Build style/visual overrides from CLI flags
    style_overrides: dict = {}
    if getattr(args, "style", None):
        style_overrides["style"] = args.style
    if getattr(args, "no_visuals", False):
        style_overrides["no_visuals"] = True
    if getattr(args, "visual_placement", None):
        style_overrides["visual_placement"] = args.visual_placement
    if getattr(args, "subject", None):
        style_overrides["subject"] = args.subject

    if style_overrides.get("style"):
        print(f"Style: {style_overrides['style']}")

    # --dry-run: just show the plan, don't execute full pipeline
    if getattr(args, "dry_run", False):
        args_copy = argparse.Namespace(**vars(args))
        return await cmd_plan(args_copy, config)

    # Cost warning (unless --yes flag)
    if not getattr(args, "yes", False):
        pipeline_check = Pipeline(config, BackendRouter(config))
        total_cost, _ = pipeline_check.estimate_cost()
        await pipeline_check.router.close()
        if total_cost > 0.0:
            print(f"\nGeschaetzte Kosten: ${total_cost:.4f}")
            try:
                answer = input("Fortfahren? [J/n] ").strip().lower()
                if answer and answer not in ("j", "ja", "y", "yes", ""):
                    print("Abgebrochen.")
                    return 0
            except (EOFError, KeyboardInterrupt):
                print("\nAbgebrochen.")
                return 0

    # Create session
    from .session import SessionStore, SessionRunner

    store = SessionStore()
    input_str = str(raw_input)
    input_type = "image" if isinstance(raw_input, Path) else "text"

    session = store.create(
        task_input=input_str,
        input_type=input_type,
        preset_key=getattr(args, "preset", None),
        output_type=getattr(args, "output_type", None),
        subject=getattr(args, "subject", None),
        tags=getattr(args, "tag", []),
    )
    print(f"Session: {session.id}")

    router = BackendRouter(config)
    pipeline = Pipeline(config, router)
    runner = SessionRunner(store, pipeline, router)

    try:
        session = await runner.run(session, preset=preset, overrides=style_overrides or None, on_progress=_progress_printer)
    finally:
        await router.close()

    if session.status == "completed":
        print(f"\n{SYM_OK} Fertig in {session.total_elapsed_ms / 1000:.1f}s")
        print(f"  Datei:   {session.output_path}")
        print(f"  Kosten:  ${session.total_cost_usd:.4f}")
        print(f"  Session: {session.id}")
        return 0
    else:
        print(f"\n{SYM_FAIL} Fehler in Stage '{session.failed_stage}'", file=sys.stderr)
        for error in session.failure_errors:
            print(f"  - {error}", file=sys.stderr)
        print(f"\n  Fortsetzen mit: schulpipeline resume {session.id}", file=sys.stderr)
        return 1


async def cmd_resume(args: argparse.Namespace, config) -> int:
    from .session import SessionStore, SessionRunner

    store = SessionStore()

    # Find session
    if args.session_id:
        session = store.load(args.session_id)
        if not session:
            print(f"Session '{args.session_id}' nicht gefunden", file=sys.stderr)
            return 1
    else:
        session = store.find_latest(status="failed")
        if not session:
            session = store.find_latest(status="paused")
        if not session:
            print("Keine fortsetzbare Session gefunden", file=sys.stderr)
            return 1

    if not session.is_resumable:
        print(f"Session '{session.id}' ist nicht fortsetzbar (Status: {session.status})", file=sys.stderr)
        return 1

    print(f"Session fortsetzen: {session.id}")
    print(f"  Titel:   {session.display_title}")
    print(f"  Status:  {session.status}")
    print(f"  Stages:  {', '.join(session.stage_names_completed) or 'keine'}")

    # Rebuild preset
    preset = None
    if session.preset_key:
        preset = resolve_quick(session.preset_key, session.preset_overrides or None)
    elif session.output_type and session.subject:
        preset = resolve_preset(session.output_type, session.subject, session.preset_overrides or None)

    router = BackendRouter(config)
    pipeline = Pipeline(config, router)
    runner = SessionRunner(store, pipeline, router)

    try:
        if args.from_stage:
            session = await runner.retry_from(session, args.from_stage, preset=preset, on_progress=_progress_printer)
        else:
            session = await runner.run(session, preset=preset, on_progress=_progress_printer)
    finally:
        await router.close()

    if session.status == "completed":
        print(f"\n{SYM_OK} Fertig in {session.total_elapsed_ms / 1000:.1f}s")
        print(f"  Datei:   {session.output_path}")
        return 0
    else:
        print(f"\n{SYM_FAIL} Fehler in Stage '{session.failed_stage}'", file=sys.stderr)
        for error in session.failure_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1


def cmd_sessions(args, config) -> int:
    from .session import SessionStore

    store = SessionStore()
    entries = store.list_sessions(
        status=getattr(args, "status", None),
        subject=getattr(args, "subject", None),
        limit=args.limit,
    )

    if args.json:
        print(_json_dumps(entries, indent=2))
        return 0

    if not entries:
        print("Keine Sessions gefunden.")
        return 0

    # Status symbols
    symbols = {"completed": SYM_OK, "failed": SYM_FAIL, "running": SYM_RUN, "paused": SYM_PAUSE, "created": SYM_PENDING}

    print(f"{'ID':10s} {'Status':4s} {'Titel':40s} {'Format':6s} {'Kosten':8s} {'Aktualisiert':20s}")
    print(SYM_HLINE * 90)
    for e in entries:
        sym = symbols.get(e.get("status", ""), "?")
        title = (e.get("title", "")[:38] + "..") if len(e.get("title", "")) > 40 else e.get("title", "")
        fmt = e.get("output_format", "") or ""
        cost = f"${e.get('total_cost_usd', 0):.4f}"
        updated = e.get("updated_at", "")[:19].replace("T", " ")
        print(f"{e['id']:10s} {sym:4s} {title:40s} {fmt:6s} {cost:8s} {updated:20s}")

    return 0


def cmd_show(args, config) -> int:
    from .session import SessionStore

    store = SessionStore()
    session = store.load(args.session_id)

    if not session:
        print(f"Session '{args.session_id}' nicht gefunden", file=sys.stderr)
        return 1

    if hasattr(args, "stage") and args.stage:
        # Show specific stage data
        for snap in session.completed_stages:
            if snap.name == args.stage:
                print(_json_dumps(snap.data, indent=2))
                return 0
        print(f"Stage '{args.stage}' nicht in Session gefunden", file=sys.stderr)
        return 1

    # Show full session overview
    print(f"Session:   {session.id}")
    print(f"Titel:     {session.display_title}")
    print(f"Status:    {session.status}")
    print(f"Erstellt:  {session.created_at[:19].replace('T', ' ')}")
    print(f"Aktualis.: {session.updated_at[:19].replace('T', ' ')}")

    if session.preset_key:
        print(f"Preset:    {session.preset_key}")
    if session.subject:
        print(f"Fach:      {session.subject}")
    if session.output_path:
        print(f"Output:    {session.output_path}")
    print(f"Kosten:    ${session.total_cost_usd:.4f}")
    print(f"Dauer:     {session.total_elapsed_ms / 1000:.1f}s")

    if session.tags:
        print(f"Tags:      {', '.join(session.tags)}")

    print(f"\nStages:")
    for snap in session.completed_stages:
        sym = SYM_OK if snap.success else SYM_FAIL
        print(f"  {sym} {snap.name:12s} {snap.elapsed_ms:6d}ms  {snap.completed_at[:19]}")
        if snap.errors:
            for err in snap.errors:
                print(f"    {SYM_FAIL} {err}")

    if session.failed_stage:
        print(f"\nFehlgeschlagen: {session.failed_stage}")
        for err in session.failure_errors:
            print(f"  - {err}")
        print(f"\n  Fortsetzen: schulpipeline resume {session.id}")
        print(f"  Neu ab Stage: schulpipeline resume {session.id} --from-stage {session.failed_stage}")

    return 0


def cmd_delete(args, config) -> int:
    from .session import SessionStore

    store = SessionStore()
    if store.delete(args.session_id):
        print(f"Session '{args.session_id}' gelöscht")
        return 0
    else:
        print(f"Session '{args.session_id}' nicht gefunden", file=sys.stderr)
        return 1


async def cmd_plan(args: argparse.Namespace, config) -> int:
    raw_input = _get_input(args)
    if raw_input is None:
        print("Fehler: Aufgabentext oder --input Datei angeben", file=sys.stderr)
        return 1

    preset = _resolve_preset_from_args(args)
    router = BackendRouter(config)
    pipeline = Pipeline(config, router)

    try:
        result = await pipeline.plan_only(raw_input, preset=preset)
    finally:
        await router.close()

    if result.success:
        plan_data = result.results[-1].data
        print(_json_dumps(plan_data, indent=2))
        return 0
    else:
        print(f"Plan fehlgeschlagen: {result.failed_stage}", file=sys.stderr)
        return 1


def cmd_presets(args) -> int:
    if args.json:
        print(_json_dumps(list_presets(), indent=2))
        return 0

    print(f"{SYM_DLINE*3} Was soll rauskommen? (--output-type) {SYM_DLINE*3}\n")
    for key, preset in OUTPUT_PRESETS.items():
        print(f"  {key:25s} {preset.label:30s} → .{preset.format}")

    print(f"\n{SYM_DLINE*3} Welches Fach? (--subject) {SYM_DLINE*3}\n")
    for key, preset in SUBJECT_PRESETS.items():
        print(f"  {key:25s} {preset.label:30s} [{preset.difficulty}]")

    print(f"\n{SYM_DLINE*3} Quick-Presets (--preset) {SYM_DLINE*3}\n")
    for key, (out_key, sub_key) in sorted(QUICK_PRESETS.items()):
        out_label = OUTPUT_PRESETS[out_key].label
        sub_label = SUBJECT_PRESETS[sub_key].label
        print(f"  {key:30s} {out_label} → {sub_label}")

    print(f"\n{SYM_DLINE*3} Beispiele {SYM_DLINE*3}\n")
    print('  schulpipeline run --preset fiae-praesi-itsec "IT-Sicherheit im Unternehmen"')
    print('  schulpipeline run --output-type praesentation --subject netzwerktechnik "OSI-Modell"')
    print('  schulpipeline run --subject wirtschaft --input aufgaben.jpg')
    print('  schulpipeline run --preset fiae-aufgaben-prog "Stack vs Heap?"')
    return 0


def cmd_backends(config) -> int:
    print("Konfigurierte Backends:\n")
    for name, cfg in config.backends.items():
        status = SYM_OK if cfg.is_available else SYM_FAIL
        reason = ""
        if not cfg.enabled:
            reason = " (deaktiviert)"
        elif not cfg.api_key and name != "ollama":
            reason = f" (kein API Key — setze {name.upper()}_API_KEY)"
        print(f"  {status} {name:10s} model={cfg.model}{reason}")

    print(f"\nCascade:")
    for stage in ["intake", "plan", "research", "synthesize", "artifact"]:
        cascade = config.cascade_for(stage)
        print(f"  {stage:12s} → {' → '.join(cascade) if cascade else '(keines verfügbar)'}")
    return 0


async def cmd_doctor(config) -> int:
    """Run system diagnostics: Python version, dependencies, API keys, connectivity."""
    import importlib
    import platform

    print("schulpipeline doctor\n")

    # 1. System info
    print("System:")
    print(f"  Python:   {platform.python_version()}")
    print(f"  Platform: {platform.system()} {platform.release()}")
    print()

    # 2. Dependencies
    print("Dependencies:")
    deps = [
        "requests", "yaml", "jsonschema", "pptx", "docx", "bs4", "PIL",
    ]
    dep_names = {
        "yaml": "pyyaml", "pptx": "python-pptx", "docx": "python-docx",
        "bs4": "beautifulsoup4", "PIL": "Pillow",
    }
    all_ok = True
    for dep in deps:
        try:
            importlib.import_module(dep)
            print(f"  OK  {dep_names.get(dep, dep)}")
        except ImportError:
            print(f"  !!  {dep_names.get(dep, dep)} — NICHT INSTALLIERT")
            all_ok = False
    print()

    # 3. API keys
    print("API Keys:")
    from .config import ENV_KEY_MAP
    import os
    keys_found = 0
    for backend_name, env_var in ENV_KEY_MAP.items():
        val = os.environ.get(env_var, "")
        if val:
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
            print(f"  OK  {env_var} = {masked}")
            keys_found += 1
        else:
            print(f"  --  {env_var} nicht gesetzt")
    if keys_found == 0:
        print("  !!  Kein einziger API Key gefunden. Mindestens GROQ_API_KEY oder GEMINI_API_KEY setzen.")
    print()

    # 4. Backend connectivity
    print("Backend-Konnektivität:")
    available = [n for n, c in config.backends.items() if c.is_available]
    if not available:
        print("  !!  Keine Backends verfügbar — Konnektivitätstest übersprungen")
    else:
        router = BackendRouter(config)
        for name in available:
            try:
                result = await router.complete(
                    stage="plan",
                    messages=[
                        {"role": "system", "content": "Antworte mit einem Wort."},
                        {"role": "user", "content": "Sage 'OK'."},
                    ],
                    temperature=0.0,
                    max_tokens=10,
                )
                print(f"  OK  {name} — {result.latency_ms}ms, model={result.model}")
                break  # one successful call is enough to confirm cascade works
            except Exception as e:
                print(f"  !!  {name} — {e}")
        await router.close()
    print()

    # 5. Specs
    print("Spezifikationen:")
    specs_dir = Path("specs")
    if specs_dir.exists():
        specs = list(specs_dir.glob("*.json"))
        print(f"  OK  {len(specs)} JSON Schemas in specs/")
    else:
        print("  !!  specs/ Verzeichnis nicht gefunden")
        all_ok = False

    # 6. Config file
    print(f"\nKonfiguration:")
    config_path = Path("config.yaml")
    if config_path.exists():
        print(f"  OK  config.yaml gefunden")
    else:
        print(f"  --  config.yaml nicht gefunden (Defaults werden verwendet)")

    print(f"\n{'OK — Alles bereit.' if all_ok and keys_found > 0 else 'Einige Probleme gefunden — siehe oben.'}")
    return 0


def _get_input(args: argparse.Namespace) -> str | Path | None:
    if hasattr(args, "input") and args.input:
        path = Path(args.input)
        if path.exists():
            if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                return path
            return _read_text_with_fallback(path)
        print(f"Warnung: Datei nicht gefunden: {args.input}", file=sys.stderr)
        return None
    if hasattr(args, "task") and args.task:
        return args.task
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return None


def main() -> None:
    # Load .env file into os.environ (API keys etc.)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    overrides = {}
    if args.log_level:
        overrides["log_level"] = args.log_level

    config = load_config(args.config, overrides)

    # Validate config for commands that need working backends
    if args.command in ("run", "plan", "resume", "cost-estimate"):
        from .config import validate_config
        config_errors = validate_config(config)
        if config_errors:
            for err in config_errors:
                print(f"Konfigurationsfehler: {err}", file=sys.stderr)
            sys.exit(1)

    if hasattr(args, "output_dir") and args.output_dir:
        config.output.dir = args.output_dir

    setup_logging(
        level=config.log_level,
        log_file=config.log_file,
        json_logs=getattr(args, "json_logs", False),
    )
    set_run_id()

    if args.command == "presets":
        sys.exit(cmd_presets(args))
    elif args.command == "backends":
        sys.exit(cmd_backends(config))
    elif args.command == "doctor":
        sys.exit(asyncio.run(cmd_doctor(config)))
    elif args.command == "sessions":
        sys.exit(cmd_sessions(args, config))
    elif args.command == "show":
        sys.exit(cmd_show(args, config))
    elif args.command == "delete":
        sys.exit(cmd_delete(args, config))
    elif args.command == "run":
        sys.exit(asyncio.run(cmd_run(args, config)))
    elif args.command == "plan":
        sys.exit(asyncio.run(cmd_plan(args, config)))
    elif args.command == "cost-estimate":
        sys.exit(asyncio.run(cmd_cost_estimate(args, config)))
    elif args.command == "resume":
        sys.exit(asyncio.run(cmd_resume(args, config)))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
