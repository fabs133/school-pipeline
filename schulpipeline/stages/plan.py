"""Stage 2: Plan — decompose task into sections, define structure."""

from __future__ import annotations

from typing import Any

from .base import BaseStage
from .intake import _parse_json_response

PLAN_SYSTEM_INTRO = """\
Du bist ein Planungsassistent für Schulaufgaben. Basierend auf der analysierten Aufgabe,
erstelle einen strukturierten Plan für das Ergebnis-Artefakt."""

PLAN_JSON_SPEC = """
Antworte ausschließlich mit validem JSON im folgenden Format:
{
  "title": "Titel des Artefakts",
  "artifact_type": "pptx | docx | md",
  "sections": [
    {
      "id": "section_01",
      "title": "Abschnittstitel",
      "purpose": "Was dieser Abschnitt leisten soll",
      "research_queries": ["Suchbegriff 1", "Suchbegriff 2"],
      "estimated_length": "short | medium | long"
    }
  ],
  "style_notes": "Hinweise zum Stil (formal/informell, Stichpunkte, Diagramme, etc.)"
}

Regeln:
- Für Präsentationen (pptx): Jede Section = eine Folie. Erste Folie = Titelfolie, letzte = Quellen.
  Plane die geforderte Folienanzahl ein (Standard: 8-10 wenn nicht angegeben).
- Für Dokumente (docx): Sections = Kapitel. Einleitung + Hauptteil + Fazit Struktur.
- Für Markdown (md): Sections = Überschriften. Kompakt und direkt.
- research_queries: 1-3 kurze, spezifische Suchbegriffe pro Section (deutsch).
  Keine Queries für Titel-/Quellenfolien.
- estimated_length: "short" = 2-3 Stichpunkte/Sätze, "medium" = 4-6, "long" = 7+
- Antworte NUR mit JSON, kein Text davor oder danach
"""


def _build_plan_prompt(preset=None) -> str:
    """Builds a plan prompt based on the provided preset.

    :param preset: Optional preset containing system context and quality instructions.
    :type preset: PlanPreset or None
    :return: A string representing the plan prompt.
    :rtype: str
    """
    parts = [PLAN_SYSTEM_INTRO]
    if preset:
        parts.append(f"\n{preset.system_context}")
        if preset.quality_instructions:
            parts.append(f"\n{preset.quality_instructions}")
    parts.append(PLAN_JSON_SPEC)
    return "\n".join(parts)


class PlanStage(BaseStage):
    """Executes the plan stage.

    :param context: The execution context containing necessary data.
    :type context: dict[str, Any]
    :param backend: The backend service for executing tasks.
    :type backend: Any
    :param config: Configuration settings for the execution.
    :type config: Any
    :return: A dictionary containing the results of the execution.
    :rtype: dict[str, Any]
    """
    name = "plan"
    spec_path = "specs/plan.json"
    required_context = frozenset({"intake"})

    async def execute(self, context: dict[str, Any], backend: Any, config: Any) -> dict[str, Any]:
        """Executes a task based on the provided context.

        :param context: A dictionary containing task details.
        :type context: dict[str, Any]
        :param backend: The backend service to use for execution.
        :type backend: Any
        :param config: Configuration settings for the execution.
        :type config: Any
        :return: A dictionary with the result of the task execution.
        :rtype: dict[str, Any]
        """
        intake = context["intake"]
        preset = context.get("preset")

        task_summary = (
            f"Fach: {intake['subject']}\n"
            f"Aufgabentyp: {intake['task_type']}\n"
            f"Format: {intake['constraints']['format']}\n"
            f"Sprache: {intake['constraints']['language']}\n"
        )

        if intake["constraints"].get("slide_count"):
            task_summary += f"Geforderte Folienanzahl: {intake['constraints']['slide_count']}\n"
        if intake["constraints"].get("page_count"):
            task_summary += f"Geforderte Seitenzahl: {intake['constraints']['page_count']}\n"
        if intake["constraints"].get("specific_requirements"):
            reqs = ", ".join(intake["constraints"]["specific_requirements"])
            task_summary += f"Besondere Anforderungen: {reqs}\n"

        task_summary += f"\nAufgabentext:\n{intake['task_text']}"

        # Build prompt with preset context
        prompt = _build_plan_prompt(preset)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": task_summary},
        ]

        response = await backend.complete(
            stage=self.name,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        data = _parse_json_response(response.content)

        # Ensure artifact_type matches intake constraint
        data["artifact_type"] = intake["constraints"]["format"]

        # Validate section IDs are unique
        ids = [s["id"] for s in data.get("sections", [])]
        if len(ids) != len(set(ids)):
            # Fix duplicate IDs
            for i, section in enumerate(data["sections"]):
                section["id"] = f"section_{i+1:02d}"

        return data
