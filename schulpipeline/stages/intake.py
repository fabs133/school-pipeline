"""Stage 1: Intake — parse input, extract task requirements."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from .base import BaseStage

INTAKE_SYSTEM_INTRO = """\
Du bist ein Aufgaben-Parser für Schulaufgaben. Analysiere die folgende Aufgabenstellung
und extrahiere die relevanten Informationen."""

INTAKE_JSON_SPEC = """
Antworte ausschließlich mit validem JSON im folgenden Format:
{
  "task_text": "Die vollständige Aufgabenstellung als Text",
  "subject": "Erkanntes Fach (z.B. IT-Sicherheit, Wirtschaft, Netzwerktechnik, Programmierung, Politik)",
  "task_type": "presentation | document | essay | question_set | mixed",
  "constraints": {
    "page_count": null,
    "slide_count": null,
    "word_count": null,
    "language": "de",
    "format": "pptx",
    "due_date": null,
    "specific_requirements": []
  },
  "raw_input_type": "text"
}

Regeln:
- task_type "presentation" → format "pptx"
- task_type "document" oder "essay" → format "docx"
- task_type "question_set" → format "md"
- Wenn Folienzahl/Seitenzahl genannt wird, extrahiere sie
- specific_requirements: alles was explizit gefordert wird (Quellen, Diagramme, Beispiele, etc.)
- Antworte NUR mit JSON, kein Text davor oder danach
"""


def _build_intake_prompt(preset=None) -> str:
    parts = [INTAKE_SYSTEM_INTRO]
    if preset:
        parts.append(f"\nKontext: {preset.domain_context}")
        parts.append(f"Erwartetes Format: {preset.output_format}")
        if preset.section_count:
            parts.append(f"Erwartete Abschnitte: {preset.section_count}")
    parts.append(INTAKE_JSON_SPEC)
    return "\n".join(parts)


class IntakeStage(BaseStage):
    name = "intake"
    spec_path = "specs/intake.json"

    async def execute(self, context: dict[str, Any], backend: Any, config: Any) -> dict[str, Any]:
        raw_input = context["raw_input"]
        raw_input_str = str(raw_input)
        preset = context.get("preset")  # ResolvedPreset or None

        # Determine input type and build messages
        input_path = Path(raw_input_str) if not raw_input_str.startswith(("{", "[")) else None

        if input_path and input_path.exists() and input_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            data = await self._process_image(input_path, backend, preset)
        else:
            data = await self._process_text(raw_input_str, backend, config, preset)

        # Apply preset overrides if present
        if preset:
            data["constraints"]["format"] = preset.output_format
            data["constraints"]["language"] = preset.language
            if preset.section_count and not data["constraints"].get("slide_count"):
                data["constraints"]["slide_count"] = preset.section_count

        return data

    async def _process_text(self, text: str, backend: Any, config: Any, preset=None) -> dict[str, Any]:
        prompt = _build_intake_prompt(preset)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Aufgabenstellung:\n\n{text}"},
        ]

        response = await backend.complete(
            stage=self.name,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        data = _parse_json_response(response.content)
        data["raw_input_type"] = "text"
        data.setdefault("constraints", {})

        # Apply config defaults
        if not data["constraints"].get("language"):
            data["constraints"]["language"] = config.output.language
        if not data["constraints"].get("format"):
            data["constraints"]["format"] = _infer_format(data.get("task_type", "mixed"))

        return data

    async def _process_image(self, image_path: Path, backend: Any, preset=None) -> dict[str, Any]:
        image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        suffix = image_path.suffix.lower().lstrip(".")
        mime_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(
            suffix, "image/jpeg"
        )

        prompt = _build_intake_prompt(preset)

        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_data}"},
                    },
                    {"type": "text", "text": "Lies und analysiere diese Aufgabenstellung."},
                ],
            },
        ]

        response = await backend.complete(
            stage=self.name,
            messages=messages,
            temperature=0.1,
            require_vision=True,
        )

        data = _parse_json_response(response.content)
        data["raw_input_type"] = "image"
        return data


def _parse_json_response(content: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling markdown fences."""
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last line (fences)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}\nContent: {content[:500]}")


def _infer_format(task_type: str) -> str:
    return {
        "presentation": "pptx",
        "document": "docx",
        "essay": "docx",
        "question_set": "md",
        "mixed": "docx",
    }.get(task_type, "md")
