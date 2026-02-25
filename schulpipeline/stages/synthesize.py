"""Stage 4: Synthesize — merge research findings into structured content."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseStage
from .intake import _parse_json_response

SYNTHESIZE_PPTX_PROMPT = """\
Du bist ein Präsentations-Autor. Erstelle aus dem Plan und den Rechercheergebnissen
den vollständigen Inhalt für eine Präsentation.

Antworte ausschließlich mit validem JSON:
{
  "title": "Präsentationstitel",
  "sections": [
    {
      "section_id": "section_01",
      "heading": "Folientitel",
      "content": "Zusammenfassender Text (2-3 Sätze für Speaker Notes)",
      "bullet_points": ["Stichpunkt 1", "Stichpunkt 2", "Stichpunkt 3"],
      "speaker_notes": "Detaillierte Notizen für den Vortragenden"
    }
  ],
  "sources": ["Quelle 1", "Quelle 2"]
}

Regeln:
- Jede Section aus dem Plan wird zu einer Folie
- bullet_points: 3-5 kurze, prägnante Stichpunkte pro Folie (max 10 Wörter)
- content: Fließtext-Zusammenfassung des Folieninhalts
- speaker_notes: Was man zu dieser Folie sagen würde (2-4 Sätze)
- Titelfolie: nur heading + content, keine bullet_points
- Quellenfolie: bullet_points = Liste der Quellen
- Sprache: Deutsch, sachlich, auf Berufsschul-Niveau
- Antworte NUR mit JSON
"""

SYNTHESIZE_DOCX_PROMPT = """\
Du bist ein Dokument-Autor. Erstelle aus dem Plan und den Rechercheergebnissen
den vollständigen Inhalt für ein Dokument.

Antworte ausschließlich mit validem JSON:
{
  "title": "Dokumenttitel",
  "sections": [
    {
      "section_id": "section_01",
      "heading": "Kapitelüberschrift",
      "content": "Vollständiger Fließtext für dieses Kapitel (mindestens 3-5 Sätze)",
      "bullet_points": [],
      "speaker_notes": null
    }
  ],
  "sources": ["Quelle 1", "Quelle 2"]
}

Regeln:
- content: Vollständige Absätze, kein Stichpunktstil
- Einleitung → Hauptteil → Fazit Struktur einhalten
- Sachlich, klar, auf Berufsschul-Niveau
- Antworte NUR mit JSON
"""

SYNTHESIZE_MD_PROMPT = """\
Du bist ein Aufgaben-Löser. Erstelle aus dem Plan und den Rechercheergebnissen
die vollständige Lösung.

Antworte ausschließlich mit validem JSON:
{
  "title": "Titel",
  "sections": [
    {
      "section_id": "section_01",
      "heading": "Überschrift",
      "content": "Antwort/Inhalt",
      "bullet_points": [],
      "speaker_notes": null
    }
  ],
  "sources": []
}

Regeln:
- Direkte Antworten, kein Fülltext
- Bei Frage-Antwort-Aufgaben: Frage als heading, Antwort als content
- Antworte NUR mit JSON
"""


class SynthesizeStage(BaseStage):
    name = "synthesize"
    spec_path = "specs/synthesis.json"

    async def execute(self, context: dict[str, Any], backend: Any, config: Any) -> dict[str, Any]:
        plan = context["plan"]
        research = context["research"]
        intake = context["intake"]
        preset = context.get("preset")

        # Select prompt based on artifact type
        artifact_type = plan["artifact_type"]
        prompt = {
            "pptx": SYNTHESIZE_PPTX_PROMPT,
            "docx": SYNTHESIZE_DOCX_PROMPT,
            "md": SYNTHESIZE_MD_PROMPT,
        }.get(artifact_type, SYNTHESIZE_MD_PROMPT)

        # Inject preset context
        if preset:
            prompt += f"\n\nKontext: {preset.system_context}"
            if preset.quality_instructions:
                prompt += f"\n\nFormatierung:\n{preset.quality_instructions}"

        # Build context from plan + research
        synthesis_input = f"Titel: {plan['title']}\nFach: {intake['subject']}\n\n"

        for plan_section in plan["sections"]:
            sid = plan_section["id"]
            synthesis_input += f"--- Section: {sid} ---\n"
            synthesis_input += f"Titel: {plan_section['title']}\n"
            synthesis_input += f"Zweck: {plan_section['purpose']}\n"
            synthesis_input += f"Länge: {plan_section.get('estimated_length', 'medium')}\n"

            # Find matching research
            research_section = next(
                (s for s in research.get("sections", []) if s["section_id"] == sid),
                None,
            )
            if research_section:
                synthesis_input += "Rechercheergebnisse:\n"
                for finding in research_section.get("findings", []):
                    synthesis_input += f"  - {finding['content']}\n"
                if not research_section.get("sufficient", True):
                    synthesis_input += "  [HINWEIS: Wenig Material gefunden, nutze dein Wissen]\n"
            synthesis_input += "\n"

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": synthesis_input},
        ]

        response = await backend.complete(
            stage=self.name,
            messages=messages,
            temperature=0.3,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )

        data = _parse_json_response(response.content)

        # Ensure all plan sections are represented
        existing_ids = {s["section_id"] for s in data.get("sections", [])}
        for plan_section in plan["sections"]:
            if plan_section["id"] not in existing_ids:
                data.setdefault("sections", []).append({
                    "section_id": plan_section["id"],
                    "heading": plan_section["title"],
                    "content": plan_section["purpose"],
                    "bullet_points": [],
                    "speaker_notes": None,
                })

        return data
