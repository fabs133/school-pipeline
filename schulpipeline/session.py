"""Session system — persistent pipeline state.

A session tracks:
  - Which task is being worked on
  - Which preset was selected
  - What stage we're at
  - Intermediate results from each completed stage
  - The final output path
  - Timing and cost metadata

Sessions are stored as JSON files in a sessions directory.
Resume is trivial: load session, skip completed stages, continue.

Lifecycle:
  create → run stages → (pause/resume) → complete
                ↘ fail → diagnose → retry from failed stage
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# Session Model
# ============================================================

@dataclass
class StageSnapshot:
    """Captured result of a completed stage."""
    name: str
    success: bool
    data: dict[str, Any]
    errors: list[str]
    elapsed_ms: int
    backend_used: str
    completed_at: str  # ISO timestamp


@dataclass
class Session:
    """Persistent pipeline session."""

    # Identity
    id: str
    created_at: str
    updated_at: str

    # Input
    task_input: str                     # Original task text or file path
    input_type: str                     # "text" | "image" | "file"

    # Preset
    preset_key: str | None = None       # Quick-preset key if used
    output_type: str | None = None      # Output preset key
    subject: str | None = None          # Subject preset key
    preset_overrides: dict[str, Any] = field(default_factory=dict)

    # Pipeline state
    status: str = "created"             # created | running | paused | completed | failed
    current_stage: str = ""             # Which stage is currently active
    completed_stages: list[StageSnapshot] = field(default_factory=list)
    failed_stage: str | None = None
    failure_errors: list[str] = field(default_factory=list)

    # Output
    output_path: str | None = None
    output_format: str | None = None

    # Metadata
    total_cost_usd: float = 0.0
    total_elapsed_ms: int = 0
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    # --- Computed properties ---

    @property
    def last_completed_stage(self) -> str | None:
        if self.completed_stages:
            return self.completed_stages[-1].name
        return None

    @property
    def stage_names_completed(self) -> set[str]:
        return {s.name for s in self.completed_stages}

    @property
    def stage_data(self) -> dict[str, dict[str, Any]]:
        """Get all stage outputs as a dict for pipeline context injection."""
        return {s.name: s.data for s in self.completed_stages if s.success}

    @property
    def is_resumable(self) -> bool:
        return self.status in ("paused", "failed", "running")

    @property
    def display_title(self) -> str:
        """Short display title from task or first stage output."""
        if self.completed_stages:
            # Try to get title from plan stage
            for snap in self.completed_stages:
                if snap.name == "plan" and snap.success:
                    return snap.data.get("title", self.task_input[:60])
        return self.task_input[:60]

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "task_input": self.task_input,
            "input_type": self.input_type,
            "preset_key": self.preset_key,
            "output_type": self.output_type,
            "subject": self.subject,
            "preset_overrides": self.preset_overrides,
            "status": self.status,
            "current_stage": self.current_stage,
            "completed_stages": [
                {
                    "name": s.name,
                    "success": s.success,
                    "data": s.data,
                    "errors": s.errors,
                    "elapsed_ms": s.elapsed_ms,
                    "backend_used": s.backend_used,
                    "completed_at": s.completed_at,
                }
                for s in self.completed_stages
            ],
            "failed_stage": self.failed_stage,
            "failure_errors": self.failure_errors,
            "output_path": self.output_path,
            "output_format": self.output_format,
            "total_cost_usd": self.total_cost_usd,
            "total_elapsed_ms": self.total_elapsed_ms,
            "tags": self.tags,
            "notes": self.notes,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Session:
        stages = [
            StageSnapshot(
                name=s["name"],
                success=s["success"],
                data=s["data"],
                errors=s.get("errors", []),
                elapsed_ms=s.get("elapsed_ms", 0),
                backend_used=s.get("backend_used", ""),
                completed_at=s.get("completed_at", ""),
            )
            for s in d.get("completed_stages", [])
        ]
        return cls(
            id=d["id"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            task_input=d["task_input"],
            input_type=d.get("input_type", "text"),
            preset_key=d.get("preset_key"),
            output_type=d.get("output_type"),
            subject=d.get("subject"),
            preset_overrides=d.get("preset_overrides", {}),
            status=d.get("status", "created"),
            current_stage=d.get("current_stage", ""),
            completed_stages=stages,
            failed_stage=d.get("failed_stage"),
            failure_errors=d.get("failure_errors", []),
            output_path=d.get("output_path"),
            output_format=d.get("output_format"),
            total_cost_usd=d.get("total_cost_usd", 0.0),
            total_elapsed_ms=d.get("total_elapsed_ms", 0),
            tags=d.get("tags", []),
            notes=d.get("notes", ""),
        )


# ============================================================
# Session Store — file-based persistence
# ============================================================

class SessionStore:
    """File-based session persistence.

    Layout:
      sessions_dir/
        {session_id}.json
        index.json              # lightweight index for listing
    """

    def __init__(self, sessions_dir: str = ".schulpipeline/sessions"):
        self.dir = Path(sessions_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.dir / "index.json"

    def create(
        self,
        task_input: str,
        input_type: str = "text",
        preset_key: str | None = None,
        output_type: str | None = None,
        subject: str | None = None,
        preset_overrides: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Session:
        """Create a new session."""
        now = datetime.now(tz=__import__("datetime").timezone.utc).isoformat() + "Z"
        session = Session(
            id=_short_id(),
            created_at=now,
            updated_at=now,
            task_input=task_input,
            input_type=input_type,
            preset_key=preset_key,
            output_type=output_type,
            subject=subject,
            preset_overrides=preset_overrides or {},
            tags=tags or [],
        )
        self.save(session)
        self._update_index(session)
        return session

    def save(self, session: Session) -> None:
        """Persist session to disk."""
        session.updated_at = datetime.now(tz=__import__("datetime").timezone.utc).isoformat() + "Z"
        path = self.dir / f"{session.id}.json"
        path.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._update_index(session)

    def load(self, session_id: str) -> Session | None:
        """Load a session by ID."""
        path = self.dir / f"{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Session.from_dict(data)

    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        path = self.dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
            self._remove_from_index(session_id)
            return True
        return False

    def list_sessions(
        self,
        status: str | None = None,
        subject: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List sessions from the index (lightweight, doesn't load full data)."""
        index = self._load_index()
        entries = list(index.values())

        # Filter
        if status:
            entries = [e for e in entries if e.get("status") == status]
        if subject:
            entries = [e for e in entries if e.get("subject") == subject]

        # Sort by updated_at descending
        entries.sort(key=lambda e: e.get("updated_at", ""), reverse=True)

        return entries[:limit]

    def find_latest(self, status: str | None = None) -> Session | None:
        """Find the most recently updated session."""
        entries = self.list_sessions(status=status, limit=1)
        if entries:
            return self.load(entries[0]["id"])
        return None

    def purge(self, max_age_days: int = 30, max_count: int = 50) -> int:
        """Remove old sessions, keeping running ones and respecting limits.

        Returns the number of sessions removed.
        """
        index = self._load_index()
        if not index:
            return 0

        entries = sorted(index.values(), key=lambda e: e.get("updated_at", ""), reverse=True)

        to_delete: list[str] = []
        now = datetime.now(tz=__import__("datetime").timezone.utc)

        for i, entry in enumerate(entries):
            sid = entry["id"]
            # Never purge running sessions
            if entry.get("status") == "running":
                continue

            # Delete if over max_count (after sorting by recency)
            if i >= max_count:
                to_delete.append(sid)
                continue

            # Delete if older than max_age_days
            updated = entry.get("updated_at", "")
            if updated:
                try:
                    ts = datetime.fromisoformat(updated.rstrip("Z")).replace(
                        tzinfo=__import__("datetime").timezone.utc
                    )
                    age = (now - ts).days
                    if age > max_age_days:
                        to_delete.append(sid)
                except (ValueError, TypeError):
                    pass

        for sid in to_delete:
            path = self.dir / f"{sid}.json"
            if path.exists():
                path.unlink()
            index.pop(sid, None)

        if to_delete:
            self._save_index(index)

        return len(to_delete)

    # --- Index management ---

    def _load_index(self) -> dict[str, dict[str, Any]]:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, KeyError):
                pass
        return {}

    def _save_index(self, index: dict[str, dict[str, Any]]) -> None:
        self._index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _update_index(self, session: Session) -> None:
        index = self._load_index()
        index[session.id] = {
            "id": session.id,
            "title": session.display_title,
            "status": session.status,
            "subject": session.subject,
            "output_format": session.output_format,
            "output_path": session.output_path,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "total_cost_usd": session.total_cost_usd,
        }
        self._save_index(index)

    def _remove_from_index(self, session_id: str) -> None:
        index = self._load_index()
        index.pop(session_id, None)
        self._save_index(index)


# ============================================================
# Session-aware Pipeline Runner
# ============================================================

class SessionRunner:
    """Runs a pipeline with session persistence.

    Saves state after each stage so the pipeline can be resumed
    from any point if interrupted.
    """

    def __init__(self, store: SessionStore, pipeline, router):
        self.store = store
        self.pipeline = pipeline
        self.router = router

    async def run(self, session: Session, preset=None, overrides: dict | None = None, on_progress=None) -> Session:
        """Run (or resume) a session through the pipeline.

        Skips already-completed stages. Saves after each stage.
        """
        from .stages import IntakeStage, PlanStage, ResearchStage, SynthesizeStage, ArtifactStage
        from .stages.base import validate_against_spec

        all_stages = [
            IntakeStage(),
            PlanStage(),
            ResearchStage(),
            SynthesizeStage(),
            ArtifactStage(),
        ]

        # Build context from already-completed stages
        context: dict[str, Any] = {
            "raw_input": session.task_input,
        }
        if preset:
            context["preset"] = preset
        if session.subject:
            context["subject_hint"] = session.subject

        # Resolve style and visual configuration
        from .styles import resolve_style, resolve_visual_config
        context["style"] = resolve_style(self.pipeline.config, overrides)
        context["visual_slots"] = resolve_visual_config(self.pipeline.config, overrides)

        # Inject completed stage data
        for snap in session.completed_stages:
            if snap.success:
                context[snap.name] = snap.data

        session.status = "running"
        self.store.save(session)

        t0 = time.monotonic()
        total_stages = len(all_stages)

        for i, stage in enumerate(all_stages):
            # Skip already-completed stages
            if stage.name in session.stage_names_completed:
                continue

            session.current_stage = stage.name
            self.store.save(session)

            if on_progress:
                on_progress("stage_start", stage.name, i, total_stages)

            # Run the stage
            result = await stage.run(context, self.router, self.pipeline.config)

            # Create snapshot
            snapshot = StageSnapshot(
                name=stage.name,
                success=result.success,
                data=result.data if result.success else {},
                errors=result.errors,
                elapsed_ms=result.metadata.get("elapsed_ms", 0),
                backend_used=result.metadata.get("backend", ""),
                completed_at=datetime.now(tz=__import__("datetime").timezone.utc).isoformat() + "Z",
            )

            if not result.success:
                if on_progress:
                    on_progress("stage_error", stage.name, i, total_stages,
                                elapsed_ms=result.metadata.get("elapsed_ms", 0), errors=result.errors)
                session.status = "failed"
                session.failed_stage = stage.name
                session.failure_errors = result.errors
                session.completed_stages.append(snapshot)
                session.total_elapsed_ms = int((time.monotonic() - t0) * 1000)
                session.total_cost_usd = self.router.total_cost
                self.store.save(session)
                return session

            # Validate
            spec_path = Path(stage.spec_path)
            if spec_path.exists():
                errors = validate_against_spec(result.data, spec_path)
                if errors:
                    session.status = "failed"
                    session.failed_stage = stage.name
                    session.failure_errors = errors
                    session.completed_stages.append(snapshot)
                    session.total_elapsed_ms = int((time.monotonic() - t0) * 1000)
                    self.store.save(session)
                    return session

            # Success — save and continue
            session.completed_stages.append(snapshot)
            context[stage.name] = result.data
            self.store.save(session)

            if on_progress:
                on_progress("stage_done", stage.name, i, total_stages,
                            elapsed_ms=result.metadata.get("elapsed_ms", 0))

        # All stages done
        session.status = "completed"
        session.current_stage = ""
        session.total_elapsed_ms = int((time.monotonic() - t0) * 1000)
        session.total_cost_usd = self.router.total_cost

        # Extract output info from artifact stage
        artifact_snap = next(
            (s for s in session.completed_stages if s.name == "artifact" and s.success),
            None,
        )
        if artifact_snap:
            session.output_path = artifact_snap.data.get("file_path")
            session.output_format = artifact_snap.data.get("artifact_type")

        self.store.save(session)
        return session

    async def retry_from(self, session: Session, stage_name: str, preset=None, overrides: dict | None = None, on_progress=None) -> Session:
        """Re-run a session starting from a specific stage.

        Drops all stage snapshots from `stage_name` onwards and re-runs.
        """
        stage_order = ["intake", "plan", "research", "synthesize", "artifact"]

        if stage_name not in stage_order:
            raise ValueError(f"Unknown stage: {stage_name}")

        idx = stage_order.index(stage_name)

        # Drop stages from this point onwards
        session.completed_stages = [
            s for s in session.completed_stages
            if s.name in stage_order[:idx]
        ]
        session.status = "running"
        session.failed_stage = None
        session.failure_errors = []
        self.store.save(session)

        return await self.run(session, preset=preset, overrides=overrides, on_progress=on_progress)


# ============================================================
# Helpers
# ============================================================

def _short_id() -> str:
    """Generate a short, human-friendly session ID."""
    # 8 chars from uuid4 — collision-resistant enough for local use
    return uuid.uuid4().hex[:8]
