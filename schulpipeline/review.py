"""Embedded slide-forge review server for interactive slide editing."""
from __future__ import annotations

import shutil
import socket
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from slideforge.models import Presentation

_REVIEW_TIMEOUT = 1800  # 30 minutes


def _find_free_port() -> int:
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_review(presentation: Presentation) -> Presentation:
    """Launch slide-forge, wait for approval, return edited presentation.

    1. Starts uvicorn in a background thread serving the slide-forge app
    2. Pushes the presentation to a temporary store
    3. Opens the browser to the editor
    4. Polls /api/projects/{id}/approved every second
    5. On approval, fetches the (possibly edited) presentation
    6. Shuts down the server and returns the result
    """
    try:
        import httpx
        import slideforge.server as srv_module
        import uvicorn
        from slideforge.server import app
        from slideforge.storage import ProjectStore
    except ImportError as e:
        raise ImportError(
            "Review server requires extra dependencies. "
            "Install with: pip install -e '.[review]'"
        ) from e

    # Use a temporary projects directory
    tmp_dir = Path(tempfile.mkdtemp(prefix="schulpipeline_review_"))

    # Set up a temporary store and save the presentation
    review_store = ProjectStore(tmp_dir)
    review_store.save(presentation)

    # Patch the module-level store
    original_store = srv_module.store
    srv_module.store = review_store
    srv_module._approved.clear()

    # Start uvicorn on a dynamic port
    port = _find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be ready
    base = f"http://127.0.0.1:{port}"
    _wait_for_server(base)

    # Open browser to the editor
    editor_url = f"{base}/#project={presentation.id}"
    webbrowser.open(editor_url)
    print(f"  Review: {editor_url}")
    print("  Warte auf 'Fertig' im Browser...")

    # Poll for approval with timeout
    try:
        deadline = time.monotonic() + _REVIEW_TIMEOUT
        with httpx.Client() as client:
            while time.monotonic() < deadline:
                try:
                    resp = client.get(
                        f"{base}/api/projects/{presentation.id}/approved",
                    )
                    if resp.status_code == 200 and resp.json().get("approved"):
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(1.0)
            else:
                raise TimeoutError(
                    f"Review was not completed within {_REVIEW_TIMEOUT // 60} minutes."
                )

            # Fetch the (possibly edited) presentation
            resp = client.get(f"{base}/api/projects/{presentation.id}")
            edited = Presentation.model_validate(resp.json())
    finally:
        # Shutdown
        server.should_exit = True
        thread.join(timeout=5)
        srv_module.store = original_store
        srv_module._approved.clear()
        # Clean up temp files
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return edited


def _wait_for_server(base: str, timeout: float = 10.0) -> None:
    """Block until the server responds or timeout."""
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{base}/api/layouts", timeout=1.0)
            return
        except (httpx.ConnectError, httpx.ReadTimeout):
            time.sleep(0.2)
    raise RuntimeError("Slide-forge server did not start in time")
