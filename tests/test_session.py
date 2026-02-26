"""Tests for session persistence — serialization, store, and resume."""

import json
from pathlib import Path

import pytest

from schulpipeline.session import Session, StageSnapshot, SessionStore


# ============================================================
# Session model
# ============================================================

def _make_session(**overrides) -> Session:
    defaults = dict(
        id="test1234",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        task_input="Erstelle eine Präsentation",
        input_type="text",
    )
    defaults.update(overrides)
    return Session(**defaults)


def test_session_defaults():
    s = _make_session()
    assert s.status == "created"
    assert s.completed_stages == []
    assert s.is_resumable is False  # "created" is not resumable


def test_session_is_resumable():
    s = _make_session(status="paused")
    assert s.is_resumable is True

    s2 = _make_session(status="failed")
    assert s2.is_resumable is True

    s3 = _make_session(status="completed")
    assert s3.is_resumable is False


def test_session_display_title_from_input():
    s = _make_session(task_input="Erstelle eine Präsentation über Netzwerke")
    assert "Netzwerke" in s.display_title


def test_session_display_title_from_plan():
    snap = StageSnapshot(
        name="plan", success=True,
        data={"title": "Netzwerktechnik Grundlagen"},
        errors=[], elapsed_ms=100, backend_used="mock",
        completed_at="2025-01-01T00:01:00Z",
    )
    s = _make_session(completed_stages=[snap])
    assert s.display_title == "Netzwerktechnik Grundlagen"


def test_session_stage_names_completed():
    snaps = [
        StageSnapshot(name="intake", success=True, data={}, errors=[], elapsed_ms=0, backend_used="", completed_at=""),
        StageSnapshot(name="plan", success=True, data={}, errors=[], elapsed_ms=0, backend_used="", completed_at=""),
    ]
    s = _make_session(completed_stages=snaps)
    assert s.stage_names_completed == {"intake", "plan"}


def test_session_stage_data():
    snaps = [
        StageSnapshot(name="intake", success=True, data={"subject": "IT"}, errors=[], elapsed_ms=0, backend_used="", completed_at=""),
        StageSnapshot(name="plan", success=False, data={}, errors=["err"], elapsed_ms=0, backend_used="", completed_at=""),
    ]
    s = _make_session(completed_stages=snaps)
    stage_data = s.stage_data
    assert "intake" in stage_data
    assert "plan" not in stage_data  # failed stage excluded


# ============================================================
# Serialization round-trip
# ============================================================

def test_session_to_dict_and_back():
    snap = StageSnapshot(
        name="intake", success=True,
        data={"subject": "IT-Sicherheit"},
        errors=[], elapsed_ms=42, backend_used="groq",
        completed_at="2025-01-01T00:00:01Z",
    )
    s = _make_session(
        completed_stages=[snap],
        status="running",
        current_stage="plan",
        tags=["test"],
    )

    d = s.to_dict()
    assert d["id"] == "test1234"
    assert len(d["completed_stages"]) == 1

    s2 = Session.from_dict(d)
    assert s2.id == s.id
    assert s2.status == "running"
    assert s2.completed_stages[0].name == "intake"
    assert s2.completed_stages[0].data["subject"] == "IT-Sicherheit"
    assert s2.tags == ["test"]


def test_session_json_roundtrip():
    s = _make_session(total_cost_usd=0.005, notes="test note")
    text = json.dumps(s.to_dict(), ensure_ascii=False)
    d = json.loads(text)
    s2 = Session.from_dict(d)
    assert s2.total_cost_usd == 0.005
    assert s2.notes == "test note"


# ============================================================
# SessionStore
# ============================================================

def test_store_create_and_load(tmp_path):
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))
    session = store.create(task_input="Test task", input_type="text")

    assert session.id
    assert session.status == "created"

    loaded = store.load(session.id)
    assert loaded is not None
    assert loaded.id == session.id
    assert loaded.task_input == "Test task"


def test_store_load_nonexistent(tmp_path):
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))
    assert store.load("nonexistent") is None


def test_store_save_updates(tmp_path):
    import time
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))
    session = store.create(task_input="Original")
    original_updated = session.updated_at

    time.sleep(0.01)  # ensure distinct timestamps
    session.status = "running"
    store.save(session)

    loaded = store.load(session.id)
    assert loaded.status == "running"
    assert loaded.updated_at != original_updated


def test_store_delete(tmp_path):
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))
    session = store.create(task_input="To delete")

    assert store.delete(session.id) is True
    assert store.load(session.id) is None
    assert store.delete(session.id) is False  # already gone


def test_store_list_sessions(tmp_path):
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))
    store.create(task_input="Task 1")
    store.create(task_input="Task 2")
    store.create(task_input="Task 3")

    sessions = store.list_sessions()
    assert len(sessions) == 3


def test_store_list_with_status_filter(tmp_path):
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))
    s1 = store.create(task_input="Task 1")
    s2 = store.create(task_input="Task 2")

    s1.status = "completed"
    store.save(s1)

    completed = store.list_sessions(status="completed")
    assert len(completed) == 1
    assert completed[0]["id"] == s1.id


def test_store_find_latest(tmp_path):
    import time
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))
    store.create(task_input="First")
    time.sleep(0.01)  # ensure distinct timestamps
    s2 = store.create(task_input="Second")

    latest = store.find_latest()
    assert latest is not None
    assert latest.id == s2.id


def test_store_find_latest_empty(tmp_path):
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))
    assert store.find_latest() is None


# ============================================================
# Session purge
# ============================================================

def test_session_purge_by_count(tmp_path):
    """Purge removes sessions beyond max_count (oldest first)."""
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))
    sessions = []
    for i in range(5):
        s = store.create(task_input=f"Task {i}")
        s.status = "completed"
        store.save(s)
        sessions.append(s)

    removed = store.purge(max_age_days=9999, max_count=3)
    assert removed == 2
    remaining = store.list_sessions()
    assert len(remaining) == 3


def test_session_purge_keeps_running(tmp_path):
    """Running sessions are never purged even if they exceed max_count."""
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))

    for i in range(4):
        s = store.create(task_input=f"Task {i}")
        s.status = "running" if i == 0 else "completed"
        store.save(s)

    removed = store.purge(max_age_days=9999, max_count=2)
    # The running session is protected; only completed sessions beyond count are removed
    remaining = store.list_sessions()
    remaining_ids = {e["id"] for e in remaining}
    running = [e for e in remaining if e.get("status") == "running"]
    assert len(running) == 1  # running session preserved
