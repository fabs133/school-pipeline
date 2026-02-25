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
from .pipeline import Pipeline
from .presets import (
    OUTPUT_PRESETS,
    SUBJECT_PRESETS,
    QUICK_PRESETS,
    resolve_preset,
    resolve_quick,
    list_presets,
)


def setup_logging(level: str, log_file: str | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schulpipeline",
        description="Schulaufgaben automatisieren — Präsentationen, Dokumente, Antworten",
    )
    parser.add_argument("--config", "-c", default="config.yaml", help="Config-Datei")
    parser.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])

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

    # --- presets ---
    presets_p = subparsers.add_parser("presets", help="Verfügbare Presets anzeigen")
    presets_p.add_argument("--json", action="store_true", help="Als JSON ausgeben")

    # --- backends ---
    subparsers.add_parser("backends", help="Verfügbare Backends anzeigen")

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
        session = await runner.run(session, preset=preset)
    finally:
        await router.close()

    if session.status == "completed":
        print(f"\n✓ Fertig in {session.total_elapsed_ms / 1000:.1f}s")
        print(f"  Datei:   {session.output_path}")
        print(f"  Kosten:  ${session.total_cost_usd:.4f}")
        print(f"  Session: {session.id}")
        return 0
    else:
        print(f"\n✗ Fehler in Stage '{session.failed_stage}'", file=sys.stderr)
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
            session = await runner.retry_from(session, args.from_stage, preset=preset)
        else:
            session = await runner.run(session, preset=preset)
    finally:
        await router.close()

    if session.status == "completed":
        print(f"\n✓ Fertig in {session.total_elapsed_ms / 1000:.1f}s")
        print(f"  Datei:   {session.output_path}")
        return 0
    else:
        print(f"\n✗ Fehler in Stage '{session.failed_stage}'", file=sys.stderr)
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
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return 0

    if not entries:
        print("Keine Sessions gefunden.")
        return 0

    # Status symbols
    symbols = {"completed": "✓", "failed": "✗", "running": "▶", "paused": "⏸", "created": "○"}

    print(f"{'ID':10s} {'Status':4s} {'Titel':40s} {'Format':6s} {'Kosten':8s} {'Aktualisiert':20s}")
    print("─" * 90)
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
                print(json.dumps(snap.data, indent=2, ensure_ascii=False))
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
        sym = "✓" if snap.success else "✗"
        print(f"  {sym} {snap.name:12s} {snap.elapsed_ms:6d}ms  {snap.completed_at[:19]}")
        if snap.errors:
            for err in snap.errors:
                print(f"    ✗ {err}")

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
        print(json.dumps(plan_data, indent=2, ensure_ascii=False))
        return 0
    else:
        print(f"Plan fehlgeschlagen: {result.failed_stage}", file=sys.stderr)
        return 1


def cmd_presets(args) -> int:
    if args.json:
        print(json.dumps(list_presets(), indent=2, ensure_ascii=False))
        return 0

    print("═══ Was soll rauskommen? (--output-type) ═══\n")
    for key, preset in OUTPUT_PRESETS.items():
        print(f"  {key:25s} {preset.label:30s} → .{preset.format}")

    print(f"\n═══ Welches Fach? (--subject) ═══\n")
    for key, preset in SUBJECT_PRESETS.items():
        print(f"  {key:25s} {preset.label:30s} [{preset.difficulty}]")

    print(f"\n═══ Quick-Presets (--preset) ═══\n")
    for key, (out_key, sub_key) in sorted(QUICK_PRESETS.items()):
        out_label = OUTPUT_PRESETS[out_key].label
        sub_label = SUBJECT_PRESETS[sub_key].label
        print(f"  {key:30s} {out_label} → {sub_label}")

    print(f"\n═══ Beispiele ═══\n")
    print('  schulpipeline run --preset fiae-praesi-itsec "IT-Sicherheit im Unternehmen"')
    print('  schulpipeline run --output-type praesentation --subject netzwerktechnik "OSI-Modell"')
    print('  schulpipeline run --subject wirtschaft --input aufgaben.jpg')
    print('  schulpipeline run --preset fiae-aufgaben-prog "Stack vs Heap?"')
    return 0


def cmd_backends(config) -> int:
    print("Konfigurierte Backends:\n")
    for name, cfg in config.backends.items():
        status = "✓" if cfg.is_available else "✗"
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


def _get_input(args: argparse.Namespace) -> str | Path | None:
    if hasattr(args, "input") and args.input:
        path = Path(args.input)
        if path.exists():
            if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                return path
            return path.read_text(encoding="utf-8")
        print(f"Warnung: Datei nicht gefunden: {args.input}", file=sys.stderr)
        return None
    if hasattr(args, "task") and args.task:
        return args.task
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return None


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    overrides = {}
    if args.log_level:
        overrides["log_level"] = args.log_level

    config = load_config(args.config, overrides)

    if hasattr(args, "output_dir") and args.output_dir:
        config.output.dir = args.output_dir

    setup_logging(config.log_level, config.log_file)

    if args.command == "presets":
        sys.exit(cmd_presets(args))
    elif args.command == "backends":
        sys.exit(cmd_backends(config))
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
    elif args.command == "resume":
        sys.exit(asyncio.run(cmd_resume(args, config)))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
