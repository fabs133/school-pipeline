"""Smoke tests — verify all modules import cleanly, including future stubs."""


def test_import_agents():
    from schulpipeline import agents  # noqa: F401


def test_import_feedback():
    from schulpipeline import feedback  # noqa: F401


def test_import_worksheet():
    from schulpipeline import worksheet  # noqa: F401


def test_import_documents():
    from schulpipeline import documents  # noqa: F401


def test_import_requirements():
    from schulpipeline import requirements  # noqa: F401


def test_import_audit():
    from schulpipeline import audit  # noqa: F401


def test_import_scanner():
    from schulpipeline import scanner  # noqa: F401


def test_import_pipeline():
    from schulpipeline import pipeline  # noqa: F401


def test_import_cli():
    from schulpipeline import cli  # noqa: F401
