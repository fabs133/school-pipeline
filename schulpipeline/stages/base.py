"""Stage protocol and validation infrastructure."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


@dataclass
class StageResult:
    """Uniform result wrapper for all stages."""

    stage: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def validate_against_spec(data: dict[str, Any], spec_path: str | Path) -> list[str]:
    """Validate stage output against its JSON Schema. Returns list of errors."""
    spec_file = Path(spec_path)
    if not spec_file.exists():
        return []  # Skip validation if spec not found (non-fatal)

    try:
        schema = json.loads(spec_file.read_text())
    except json.JSONDecodeError as e:
        return [f"Invalid JSON in spec {spec_path}: {e}"]

    if HAS_JSONSCHEMA:
        validator = jsonschema.Draft7Validator(schema)
        errors = []
        for error in validator.iter_errors(data):
            path = " → ".join(str(p) for p in error.absolute_path) or "(root)"
            errors.append(f"{path}: {error.message}")
        return errors
    else:
        # Lightweight fallback: check required fields only
        return _validate_required_fields(data, schema)


@runtime_checkable
class Stage(Protocol):
    """Protocol that all pipeline stages must implement."""

    name: str
    spec_path: str

    async def run(
        self,
        context: dict[str, Any],
        backend: Any,  # BackendRouter
        config: Any,  # PipelineConfig
    ) -> StageResult: ...


class MissingContextError(Exception):
    """Raised when required context keys are missing before stage execution."""

    def __init__(self, stage_name: str, missing_keys: set[str]):
        self.stage_name = stage_name
        self.missing_keys = missing_keys
        keys_str = ", ".join(sorted(missing_keys))
        super().__init__(
            f"Stage '{stage_name}' requires context keys [{keys_str}] "
            f"which are not present. A prior stage may not have completed successfully."
        )


class BaseStage:
    """Optional convenience base with timing and error wrapping."""

    name: str = ""
    spec_path: str = ""
    required_context: frozenset[str] = frozenset()

    async def run(self, context: dict[str, Any], backend: Any, config: Any) -> StageResult:
        t0 = time.monotonic()
        try:
            self._validate_context(context)
            data = await self.execute(context, backend, config)
            elapsed = int((time.monotonic() - t0) * 1000)
            return StageResult(
                stage=self.name,
                success=True,
                data=data,
                metadata={"elapsed_ms": elapsed},
            )
        except Exception as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            return StageResult(
                stage=self.name,
                success=False,
                errors=[str(e)],
                metadata={"elapsed_ms": elapsed},
            )

    def _validate_context(self, context: dict[str, Any]) -> None:
        """Check that all required context keys are present."""
        if not self.required_context:
            return
        missing = self.required_context - context.keys()
        if missing:
            raise MissingContextError(self.name, missing)

    async def execute(self, context: dict[str, Any], backend: Any, config: Any) -> dict[str, Any]:
        raise NotImplementedError


def _validate_required_fields(data: dict[str, Any], schema: dict) -> list[str]:
    """Lightweight validation: check required fields exist. Used when jsonschema is not installed."""
    errors = []
    required = schema.get("required", [])
    for field_name in required:
        if field_name not in data:
            errors.append(f"(root): missing required field '{field_name}'")
    return errors
