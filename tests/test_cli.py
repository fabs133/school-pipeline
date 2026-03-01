"""Tests for schulpipeline.cli — basic CLI smoke tests."""

from __future__ import annotations

import io
from unittest.mock import patch

from schulpipeline.cli import build_parser, cmd_backends, cmd_presets, cmd_scan
from schulpipeline.config import load_config


def test_build_parser():
    """Parser creates without error and all subcommands are registered."""
    parser = build_parser()
    assert parser is not None
    # Verify key subcommands are present by checking help output
    help_text = parser.format_help()
    for cmd in ["run", "presets", "backends", "scan", "sessions", "doctor"]:
        assert cmd in help_text, f"Subcommand '{cmd}' missing from parser help"


def test_cmd_presets():
    """cmd_presets prints preset info to stdout."""
    parser = build_parser()
    args = parser.parse_args(["presets"])
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        exit_code = cmd_presets(args)
    output = buf.getvalue()
    assert exit_code == 0
    assert "praesentation" in output.lower() or "Praesentation" in output or "praesi" in output.lower()


def test_cmd_presets_json():
    """cmd_presets --json prints valid JSON."""
    import json

    parser = build_parser()
    args = parser.parse_args(["presets", "--json"])
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        exit_code = cmd_presets(args)
    output = buf.getvalue()
    assert exit_code == 0
    data = json.loads(output)
    assert isinstance(data, (dict, list))


def test_cmd_backends():
    """cmd_backends prints backend info."""
    config = load_config(path=None)
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        exit_code = cmd_backends(config)
    output = buf.getvalue()
    assert exit_code == 0
    assert "Backend" in output or "backend" in output.lower()


def test_cmd_sessions_empty():
    """cmd_sessions with no sessions gives clean output."""
    import tempfile

    parser = build_parser()
    args = parser.parse_args(["sessions"])
    config = load_config(path=None)
    # Override sessions dir to empty temp
    with tempfile.TemporaryDirectory() as tmpdir:
        config.sessions_dir = tmpdir
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            from schulpipeline.cli import cmd_sessions

            exit_code = cmd_sessions(args, config)
    assert exit_code == 0


def test_cmd_scan_example_dir():
    """cmd_scan on examples/tasks/ works without error."""
    from pathlib import Path

    examples_dir = Path(__file__).parent.parent / "examples" / "tasks"
    if not examples_dir.is_dir():
        import pytest

        pytest.skip("examples/tasks/ not found")

    parser = build_parser()
    args = parser.parse_args(["scan", str(examples_dir)])
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        exit_code = cmd_scan(args)
    output = buf.getvalue()
    assert exit_code == 0
    assert len(output) > 0


def test_cmd_run_help():
    """'run --help' shows usage without error."""
    parser = build_parser()
    buf = io.StringIO()
    try:
        with patch("sys.stdout", buf):
            parser.parse_args(["run", "--help"])
    except SystemExit as e:
        assert e.code == 0
    output = buf.getvalue()
    assert "run" in output.lower()
