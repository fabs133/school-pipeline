"""Tests for schulpipeline.review — review server module."""
from __future__ import annotations

from unittest.mock import patch


def test_run_review_import_error():
    """Verify user-friendly message when review extras are missing."""
    # Simulate missing httpx
    with patch.dict("sys.modules", {"httpx": None}):
        # Need to reimport to trigger the ImportError path
        from slideforge.models import Presentation

        import schulpipeline.review as review_mod

        pres = Presentation(id="test", name="Test")
        try:
            review_mod.run_review(pres)
            assert False, "Should have raised ImportError"
        except ImportError as e:
            assert "pip install" in str(e)
            assert "review" in str(e)


def test_find_free_port():
    """_find_free_port returns a valid port number."""
    from schulpipeline.review import _find_free_port

    port = _find_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535


def test_find_free_port_is_unique():
    """Two calls to _find_free_port return different ports (usually)."""
    from schulpipeline.review import _find_free_port

    ports = {_find_free_port() for _ in range(5)}
    # At least 2 different ports out of 5 calls
    assert len(ports) >= 2
