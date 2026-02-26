"""Tests for progress callback integration."""

import pytest

from schulpipeline.pipeline import Pipeline
from schulpipeline.session import SessionRunner, SessionStore


@pytest.mark.asyncio
async def test_pipeline_progress_callback(mock_router, mock_config, tmp_path):
    """Pipeline.run() calls on_progress for each stage."""
    mock_config.output.dir = str(tmp_path)
    pipeline = Pipeline(mock_config, mock_router)

    events = []

    def recorder(event, stage_name, stage_index, total_stages, **kwargs):
        events.append((event, stage_name, stage_index))

    result = await pipeline.run("Test task", on_progress=recorder)

    assert result.success
    starts = [e for e in events if e[0] == "stage_start"]
    dones = [e for e in events if e[0] == "stage_done"]
    assert len(starts) == len(dones)
    assert len(starts) == 5  # standard pipeline has 5 stages


@pytest.mark.asyncio
async def test_pipeline_no_callback(mock_router, mock_config, tmp_path):
    """Pipeline.run() works without on_progress (backward compat)."""
    mock_config.output.dir = str(tmp_path)
    pipeline = Pipeline(mock_config, mock_router)
    result = await pipeline.run("Test task")
    assert result.success


@pytest.mark.asyncio
async def test_pipeline_progress_includes_elapsed(mock_router, mock_config, tmp_path):
    """stage_done events include elapsed_ms."""
    mock_config.output.dir = str(tmp_path)
    pipeline = Pipeline(mock_config, mock_router)

    done_kwargs = []

    def recorder(event, stage_name, stage_index, total_stages, **kwargs):
        if event == "stage_done":
            done_kwargs.append(kwargs)

    await pipeline.run("Test task", on_progress=recorder)

    assert len(done_kwargs) == 5
    for kw in done_kwargs:
        assert "elapsed_ms" in kw
        assert isinstance(kw["elapsed_ms"], int)


@pytest.mark.asyncio
async def test_session_runner_progress(mock_router, mock_config, tmp_path):
    """SessionRunner.run() passes progress events."""
    mock_config.output.dir = str(tmp_path)
    pipeline = Pipeline(mock_config, mock_router)
    store = SessionStore(sessions_dir=str(tmp_path / "sessions"))
    session = store.create(task_input="Test task")
    runner = SessionRunner(store, pipeline, mock_router)

    events = []

    def recorder(event, stage_name, stage_index, total_stages, **kwargs):
        events.append(event)

    session = await runner.run(session, on_progress=recorder)
    assert session.status == "completed"
    assert "stage_start" in events
    assert "stage_done" in events
