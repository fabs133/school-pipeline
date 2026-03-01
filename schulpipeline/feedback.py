"""Feedback & Telemetry — anonymized data collection for pipeline improvement and research.

After each pipeline run, the user can rate the output. This creates a feedback
record that serves three purposes:

  1. PIPELINE IMPROVEMENT — which presets/backends produce the best results?
     Which stage fails most often? What input patterns cause problems?

  2. RESEARCH DATASET — anonymized, aggregated metrics that document:
     - What percentage of school assignments are solvable by a free pipeline
     - Average quality rating by subject/output type
     - Time saved vs. manual completion
     - Audit findings per assignment (contradiction rate, completeness scores)

  3. USER VALUE — the user sees their own stats: time saved, assignments completed,
     average quality. This isn't gamification, it's transparency.

Privacy model:
  - NO personal data. No names, no school names, no IP addresses.
  - NO assignment content. We store metrics ABOUT the run, not the run itself.
  - Local storage by default (JSON files alongside sessions).
  - Optional: export anonymized aggregate to contribute to the research dataset.
  - The user can delete all their data at any time.
  - Full schema documented below — the user sees exactly what's collected.

Data flow:
  Pipeline run completes
    → User is prompted for feedback (grade, quality, time estimate)
    → Feedback record saved locally
    → Aggregated stats updated
    → Optional: anonymized export for research contribution
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ============================================================
# Feedback Record — what we collect per run
# ============================================================


@dataclass
class FeedbackRecord:
    """One feedback entry per pipeline run. This is the complete schema.

    Everything collected is documented here. Nothing hidden.
    """

    # --- Run metadata (auto-collected) ---
    run_id: str  # Session ID (random, not traceable)
    timestamp: str  # ISO 8601 UTC
    pipeline_flow: str  # "presentation" | "worksheet" | "template" | "audit" | "requirements"
    preset_key: str  # e.g. "fiae-praesi-itsec" (no custom text)
    subject: str  # e.g. "wirtschaft" (from preset, not from input)
    output_format: str  # e.g. "pptx", "docx", "worksheet"

    # --- Pipeline performance (auto-collected) ---
    total_stages: int  # How many stages ran
    failed_stages: int  # How many stages failed
    total_cost_usd: float  # API cost (should be 0.00 for free tier)
    elapsed_ms: int  # Total pipeline duration
    backends_used: list[str]  # Which backends were used (e.g. ["groq", "gemini"])

    # --- Audit metrics (auto-collected, only for audit/requirements flows) ---
    audit_findings_total: int = 0
    audit_blockers: int = 0
    audit_warnings: int = 0
    audit_completeness: float = 0.0  # 0-1
    audit_feasibility: float = 0.0  # 0-1
    requirements_total: int = 0
    requirements_clear: int = 0
    requirements_ambiguous: int = 0
    contradictions_found: int = 0
    deviations_needed: int = 0

    # --- User feedback (user-provided) ---
    grade_received: str = ""  # "1" through "6", or "pending", or ""
    quality_rating: int = 0  # 1-5 stars, 0 = not rated
    usable_without_edits: bool | None = None  # Could you submit this as-is?
    estimated_time_saved_min: int = 0  # How many minutes would this have taken manually?
    feedback_text: str = ""  # Optional free-text (stored locally only, never exported)

    # --- Calculated fields ---
    education_level: str = ""  # "berufsschule" | "gymnasium" | "uni" (from preset)


@dataclass
class AggregateStats:
    """Aggregated statistics across all feedback records.

    This is what gets exported for research — no individual records.
    """

    total_runs: int = 0
    total_time_saved_min: int = 0

    # By flow
    runs_by_flow: dict[str, int] = field(default_factory=dict)
    avg_quality_by_flow: dict[str, float] = field(default_factory=dict)

    # By subject
    runs_by_subject: dict[str, int] = field(default_factory=dict)
    avg_quality_by_subject: dict[str, float] = field(default_factory=dict)

    # Quality distribution
    quality_distribution: dict[int, int] = field(default_factory=dict)  # {1: 3, 2: 5, ...}
    usable_without_edits_pct: float = 0.0
    avg_grade_when_submitted: float = 0.0

    # Audit metrics (the research gold)
    avg_audit_completeness: float = 0.0
    avg_audit_feasibility: float = 0.0
    avg_contradictions_per_assignment: float = 0.0
    avg_blockers_per_assignment: float = 0.0
    pct_assignments_with_blockers: float = 0.0

    # Cost
    total_cost_usd: float = 0.0
    avg_cost_per_run: float = 0.0
    pct_free_runs: float = 0.0

    # Time
    avg_elapsed_ms: float = 0.0
    avg_time_saved_min: float = 0.0


# ============================================================
# Feedback Store — local JSON storage
# ============================================================


class FeedbackStore:
    """Manages feedback records on disk. All data in one directory."""

    def __init__(self, base_dir: str | Path = ".schulpipeline/feedback"):
        """Initialize the FeedbackManager with a base directory.

        :param base_dir: The base directory for storing feedback records and aggregate data.
        :type base_dir: str | Path
        ```

        ```python
        Save a feedback record to the records directory. Returns the file path where the record is saved.

        :param record: The feedback record to save.
        :type record: FeedbackRecord
        :return: The file path of the saved record.
        :rtype: Path
        """
        self.base_dir = Path(base_dir)
        self.records_dir = self.base_dir / "records"
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self._aggregate_path = self.base_dir / "aggregate.json"

    def save_record(self, record: FeedbackRecord) -> Path:
        """Save a feedback record. Returns the file path."""
        path = self.records_dir / f"{record.run_id}.json"
        path.write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Update aggregates
        self._update_aggregates()
        return path

    def load_record(self, run_id: str) -> FeedbackRecord | None:
        """Load a feedback record by run ID."""
        path = self.records_dir / f"{run_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return FeedbackRecord(**data)

    def update_record(self, run_id: str, **updates) -> FeedbackRecord | None:
        """Update fields on an existing record (e.g. add grade after receiving it)."""
        record = self.load_record(run_id)
        if not record:
            return None
        for key, value in updates.items():
            if hasattr(record, key):
                setattr(record, key, value)
        self.save_record(record)
        return record

    def all_records(self) -> list[FeedbackRecord]:
        """Load all feedback records."""
        records = []
        for path in sorted(self.records_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                records.append(FeedbackRecord(**data))
            except (json.JSONDecodeError, TypeError):
                continue
        return records

    def delete_all(self) -> int:
        """Delete all feedback data. Returns count of deleted records."""
        count = 0
        for path in self.records_dir.glob("*.json"):
            path.unlink()
            count += 1
        if self._aggregate_path.exists():
            self._aggregate_path.unlink()
        return count

    def get_aggregates(self) -> AggregateStats:
        """Get current aggregate statistics."""
        if self._aggregate_path.exists():
            try:
                data = json.loads(self._aggregate_path.read_text(encoding="utf-8"))
                return AggregateStats(**data)
            except (json.JSONDecodeError, TypeError):
                pass
        return self._compute_aggregates()

    def _update_aggregates(self) -> AggregateStats:
        """Recompute and save aggregates."""
        stats = self._compute_aggregates()
        self._aggregate_path.write_text(
            json.dumps(asdict(stats), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return stats

    def _compute_aggregates(self) -> AggregateStats:
        """Compute aggregates from all records."""
        records = self.all_records()
        if not records:
            return AggregateStats()

        stats = AggregateStats()
        stats.total_runs = len(records)
        stats.total_cost_usd = sum(r.total_cost_usd for r in records)

        # By flow
        for r in records:
            stats.runs_by_flow[r.pipeline_flow] = stats.runs_by_flow.get(r.pipeline_flow, 0) + 1
            stats.runs_by_subject[r.subject] = stats.runs_by_subject.get(r.subject, 0) + 1

        # Quality ratings
        rated = [r for r in records if r.quality_rating > 0]
        if rated:
            for r in rated:
                stats.quality_distribution[r.quality_rating] = stats.quality_distribution.get(r.quality_rating, 0) + 1

            # Average quality by flow
            by_flow: dict[str, list[int]] = {}
            for r in rated:
                by_flow.setdefault(r.pipeline_flow, []).append(r.quality_rating)
            stats.avg_quality_by_flow = {k: statistics.mean(v) for k, v in by_flow.items()}

            # Average quality by subject
            by_subject: dict[str, list[int]] = {}
            for r in rated:
                by_subject.setdefault(r.subject, []).append(r.quality_rating)
            stats.avg_quality_by_subject = {k: statistics.mean(v) for k, v in by_subject.items()}

        # Usability
        usability_rated = [r for r in records if r.usable_without_edits is not None]
        if usability_rated:
            stats.usable_without_edits_pct = sum(1 for r in usability_rated if r.usable_without_edits) / len(
                usability_rated
            )

        # Grades
        graded = [r for r in records if r.grade_received.isdigit()]
        if graded:
            stats.avg_grade_when_submitted = statistics.mean(int(r.grade_received) for r in graded)

        # Time saved
        time_records = [r for r in records if r.estimated_time_saved_min > 0]
        stats.total_time_saved_min = sum(r.estimated_time_saved_min for r in records)
        if time_records:
            stats.avg_time_saved_min = statistics.mean(r.estimated_time_saved_min for r in time_records)

        # Cost
        stats.avg_cost_per_run = stats.total_cost_usd / stats.total_runs
        stats.pct_free_runs = sum(1 for r in records if r.total_cost_usd == 0) / stats.total_runs

        # Pipeline performance
        stats.avg_elapsed_ms = statistics.mean(r.elapsed_ms for r in records)

        # Audit metrics (the research dataset)
        audited = [r for r in records if r.audit_findings_total > 0]
        if audited:
            stats.avg_audit_completeness = statistics.mean(r.audit_completeness for r in audited)
            stats.avg_audit_feasibility = statistics.mean(r.audit_feasibility for r in audited)
            stats.avg_contradictions_per_assignment = statistics.mean(r.contradictions_found for r in audited)
            stats.avg_blockers_per_assignment = statistics.mean(r.audit_blockers for r in audited)
            stats.pct_assignments_with_blockers = sum(1 for r in audited if r.audit_blockers > 0) / len(audited)

        return stats


# ============================================================
# Record Builder — creates feedback from pipeline results
# ============================================================


def build_feedback_from_result(
    session_id: str,
    pipeline_result: Any,
    preset: Any = None,
) -> FeedbackRecord:
    """Create a feedback record from a pipeline result.

    Auto-fills everything except user feedback fields.
    """
    results = pipeline_result.results if hasattr(pipeline_result, "results") else []

    # Determine flow type
    stage_names = [r.stage for r in results]
    if "decompose" in stage_names:
        flow = "worksheet"
    elif "classify_report" in stage_names:
        flow = "requirements"
    elif "audit" in stage_names and "fill_template" not in stage_names:
        flow = "audit"
    elif "fill_template" in stage_names:
        flow = "template"
    else:
        flow = "presentation"

    # Extract audit metrics
    audit_data = {}
    for r in results:
        if r.stage == "audit" and r.success:
            audit_data = r.data
            break

    audit_summary = audit_data.get("summary", {})

    # Extract requirements metrics
    req_data = {}
    for r in results:
        if r.stage == "classify_report" and r.success:
            req_data = r.data
            break

    req_counts = req_data.get("requirement_count", {})

    # Extract amendment metrics
    for r in results:
        if r.stage == "amendments" and r.success:
            break

    # Collect backends used
    backends = set()
    for r in results:
        meta = r.metadata if hasattr(r, "metadata") else {}
        if isinstance(meta, dict) and meta.get("backend"):
            backends.add(meta["backend"])

    return FeedbackRecord(
        run_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        pipeline_flow=flow,
        preset_key=preset.key if preset and hasattr(preset, "key") else "",
        subject=preset.subject if preset and hasattr(preset, "subject") else "",
        output_format=preset.output_format if preset and hasattr(preset, "output_format") else "",
        education_level=getattr(preset, "difficulty", "") if preset else "",
        total_stages=len(results),
        failed_stages=sum(1 for r in results if not r.success),
        total_cost_usd=getattr(pipeline_result, "total_cost_usd", 0.0),
        elapsed_ms=getattr(pipeline_result, "elapsed_ms", 0),
        backends_used=sorted(backends),
        audit_findings_total=audit_summary.get("total_findings", 0),
        audit_blockers=audit_summary.get("blockers", 0),
        audit_warnings=audit_summary.get("warnings", 0),
        audit_completeness=audit_summary.get("completeness_score", 0.0),
        audit_feasibility=audit_summary.get("feasibility_score", 0.0),
        requirements_total=req_counts.get("total", 0),
        requirements_clear=req_counts.get("clear", 0),
        requirements_ambiguous=req_counts.get("ambiguous", 0),
        contradictions_found=len(
            audit_data.get(
                "findings", [f for f in audit_data.get("findings", []) if f.get("category") == "contradiction"]
            )
        )
        if audit_data
        else 0,
        deviations_needed=0,  # Filled after amendments
    )


# ============================================================
# Research Export — anonymized aggregate only
# ============================================================


def export_for_research(store: FeedbackStore) -> dict[str, Any]:
    """Export anonymized aggregate data for the research dataset.

    This is what goes into the repo under data/. NO individual records.
    Only aggregated statistics that can't be traced to any person.
    """
    stats = store.get_aggregates()

    return {
        "_schema_version": "1.0",
        "_exported_at": datetime.now(timezone.utc).isoformat(),
        "_description": (
            "Anonymisierte, aggregierte Metriken aus der Schulpipeline. "
            "Keine personenbezogenen Daten. Keine Aufgabeninhalte. "
            "Nur Statistiken über Pipeline-Nutzung und Aufgabenqualität."
        ),
        "_instance_id": _generate_instance_id(store),
        "sample_size": stats.total_runs,
        "usage": {
            "runs_by_flow": stats.runs_by_flow,
            "runs_by_subject": stats.runs_by_subject,
            "total_time_saved_hours": round(stats.total_time_saved_min / 60, 1),
            "avg_time_saved_per_run_min": round(stats.avg_time_saved_min, 1),
        },
        "quality": {
            "avg_quality_by_flow": {k: round(v, 2) for k, v in stats.avg_quality_by_flow.items()},
            "avg_quality_by_subject": {k: round(v, 2) for k, v in stats.avg_quality_by_subject.items()},
            "quality_distribution": stats.quality_distribution,
            "usable_without_edits_pct": round(stats.usable_without_edits_pct * 100, 1),
            "avg_grade_when_submitted": round(stats.avg_grade_when_submitted, 2)
            if stats.avg_grade_when_submitted
            else None,
        },
        "audit_findings": {
            "avg_completeness_pct": round(stats.avg_audit_completeness * 100, 1),
            "avg_feasibility_pct": round(stats.avg_audit_feasibility * 100, 1),
            "avg_contradictions_per_assignment": round(stats.avg_contradictions_per_assignment, 2),
            "avg_blockers_per_assignment": round(stats.avg_blockers_per_assignment, 2),
            "pct_assignments_with_blockers": round(stats.pct_assignments_with_blockers * 100, 1),
        },
        "cost": {
            "total_cost_usd": round(stats.total_cost_usd, 4),
            "avg_cost_per_run_usd": round(stats.avg_cost_per_run, 4),
            "pct_free_runs": round(stats.pct_free_runs * 100, 1),
        },
    }


def _generate_instance_id(store: FeedbackStore) -> str:
    """Generate a stable but anonymous instance ID.

    Based on the creation time of the feedback directory — not on any
    user-identifiable information. Two exports from the same installation
    produce the same ID, allowing longitudinal tracking without identification.
    """
    dir_stat = store.base_dir.stat()
    raw = f"{dir_stat.st_ctime_ns}-{store.base_dir.resolve()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


# ============================================================
# CLI Integration Helpers
# ============================================================


def prompt_feedback_cli(run_id: str, store: FeedbackStore) -> FeedbackRecord | None:
    """Interactive CLI prompt for user feedback after a pipeline run.

    Returns the updated record, or None if the user skips.
    """
    record = store.load_record(run_id)
    if not record:
        return None

    print("\n" + "=" * 50)
    print("📊 Feedback (optional, hilft bei der Verbesserung)")
    print("=" * 50)

    # Quality rating
    rating_input = input("\nQualität des Outputs (1-5 Sterne, Enter = überspringen): ").strip()
    if rating_input.isdigit() and 1 <= int(rating_input) <= 5:
        record.quality_rating = int(rating_input)

    # Usable as-is
    usable_input = input("Direkt abgebbar ohne Änderungen? (j/n/Enter = überspringen): ").strip().lower()
    if usable_input in ("j", "ja", "y", "yes"):
        record.usable_without_edits = True
    elif usable_input in ("n", "nein", "no"):
        record.usable_without_edits = False

    # Time saved
    time_input = input("Geschätzte Zeitersparnis in Minuten (Enter = überspringen): ").strip()
    if time_input.isdigit():
        record.estimated_time_saved_min = int(time_input)

    # Grade (can be added later)
    grade_input = input("Note falls bekannt (1-6, Enter = später): ").strip()
    if grade_input.isdigit() and 1 <= int(grade_input) <= 6:
        record.grade_received = grade_input
    elif not grade_input:
        record.grade_received = "pending"

    store.save_record(record)
    print("\n✓ Feedback gespeichert. Danke!")
    return record


def print_user_stats(store: FeedbackStore) -> None:
    """Print the user's personal statistics."""
    stats = store.get_aggregates()

    if stats.total_runs == 0:
        print("Noch keine Daten vorhanden.")
        return

    print("\n📈 Deine Statistiken")
    print("=" * 40)
    print(f"  Runs gesamt:           {stats.total_runs}")
    print(f"  Zeitersparnis gesamt:  {stats.total_time_saved_min} min ({stats.total_time_saved_min / 60:.1f}h)")
    print(f"  Ø Zeitersparnis/Run:   {stats.avg_time_saved_min:.0f} min")
    print(f"  Gesamtkosten:          ${stats.total_cost_usd:.4f}")
    print(f"  Kostenlose Runs:       {stats.pct_free_runs:.0%}")

    if stats.avg_quality_by_flow:
        print("\n  Ø Qualität nach Typ:")
        for flow, avg in stats.avg_quality_by_flow.items():
            stars = "★" * round(avg) + "☆" * (5 - round(avg))
            print(f"    {flow:20s} {stars} ({avg:.1f})")

    if stats.avg_grade_when_submitted:
        print(f"\n  Ø Note (abgegebene):   {stats.avg_grade_when_submitted:.1f}")

    if stats.avg_audit_completeness > 0:
        print("\n  📋 Aufgabenqualität (aus Audits):")
        print(f"    Ø Vollständigkeit:   {stats.avg_audit_completeness:.0%}")
        print(f"    Ø Machbarkeit:       {stats.avg_audit_feasibility:.0%}")
        print(f"    Ø Widersprüche:      {stats.avg_contradictions_per_assignment:.1f} pro Aufgabe")
        print(f"    Aufgaben mit Blocker: {stats.pct_assignments_with_blockers:.0%}")


def format_research_export_md(export: dict[str, Any]) -> str:
    """Format research export as readable Markdown for the repo."""
    lines = ["# Schulpipeline — Anonymisierte Nutzungsdaten\n"]
    lines.append(f"*Exportiert: {export['_exported_at'][:10]}*")
    lines.append(f"*Instanz: {export['_instance_id']}*")
    lines.append(f"*Stichprobe: {export['sample_size']} Runs*\n")

    lines.append(export["_description"])
    lines.append("")

    lines.append("## Nutzung")
    usage = export["usage"]
    lines.append(f"- Zeitersparnis gesamt: **{usage['total_time_saved_hours']}h**")
    lines.append(f"- Ø Zeitersparnis pro Run: **{usage['avg_time_saved_per_run_min']} min**")
    if usage.get("runs_by_flow"):
        lines.append(f"- Runs nach Typ: {json.dumps(usage['runs_by_flow'], ensure_ascii=False)}")
    lines.append("")

    lines.append("## Qualität")
    quality = export["quality"]
    lines.append(f"- Direkt abgebbar ohne Änderungen: **{quality['usable_without_edits_pct']}%**")
    if quality.get("avg_grade_when_submitted"):
        lines.append(f"- Ø Note bei Abgabe: **{quality['avg_grade_when_submitted']}**")
    lines.append("")

    lines.append("## Aufgabenqualität (Audit-Ergebnisse)")
    audit = export["audit_findings"]
    lines.append(f"- Ø Vollständigkeit der Vorgaben: **{audit['avg_completeness_pct']}%**")
    lines.append(f"- Ø Machbarkeit: **{audit['avg_feasibility_pct']}%**")
    lines.append(f"- Ø Widersprüche pro Aufgabe: **{audit['avg_contradictions_per_assignment']}**")
    lines.append(f"- Aufgaben mit Blockern: **{audit['pct_assignments_with_blockers']}%**")
    lines.append("")

    lines.append("## Kosten")
    cost = export["cost"]
    lines.append(f"- Gesamtkosten: **${cost['total_cost_usd']}**")
    lines.append(f"- Kostenlose Runs: **{cost['pct_free_runs']}%**")

    return "\n".join(lines)
