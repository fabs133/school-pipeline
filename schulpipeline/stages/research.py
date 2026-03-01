"""Stage 3: Research — gather information per section from web or LLM knowledge."""

from __future__ import annotations

from typing import Any

from .base import BaseStage
from .intake import _parse_json_response

RESEARCH_PROMPT = """\
Du bist ein Recherche-Assistent. Für jeden Abschnitt einer Schulaufgabe lieferst du
relevante Fakten, Definitionen und Beispiele.

Du erhältst eine Liste von Abschnitten mit Suchbegriffen. Liefere pro Abschnitt
die wichtigsten Informationen.

Antworte ausschließlich mit validem JSON im folgenden Format:
{
  "sections": [
    {
      "section_id": "section_01",
      "findings": [
        {
          "content": "Relevante Information / Fakt / Definition",
          "source": "llm_knowledge",
          "relevance": 0.9
        }
      ],
      "sufficient": true
    }
  ]
}

Regeln:
- Pro Section mindestens 2-4 Findings
- content: Klare, faktische Aussagen. Keine Füllwörter.
- source: "llm_knowledge" wenn aus deinem Wissen, URL wenn aus Websuche
- relevance: 0.0-1.0, wie relevant der Fund für den Abschnitt ist
- sufficient: false wenn du nicht genug Material für den Abschnitt hast
- Für Titel/Quellenfolien: minimal findings (nur Titel-Vorschläge)
- Sprache: Deutsch
- Antworte NUR mit JSON
"""


class ResearchStage(BaseStage):
    """Executes the research stage of a workflow.

    :param context: The current execution context containing necessary data.
    :type context: dict[str, Any]
    :param backend: The backend service for executing the research.
    :type backend: Any
    :param config: Configuration settings for the research stage.
    :type config: Any
    :return: Updated context with research results.
    :rtype: dict[str, Any]
    :raises ValueError: If required context keys are missing.
    """

    name = "research"
    spec_path = "specs/research.json"
    required_context = frozenset({"plan", "intake"})

    async def execute(self, context: dict[str, Any], backend: Any, config: Any) -> dict[str, Any]:
        """Execute the research plan using the provided backend and configuration.

        :param context: A dictionary containing the research plan and intake data.
        :type context: dict[str, Any]
        :param backend: The backend system to use for executing the research queries.
        :type backend: Any
        :param config: Configuration settings for the research execution.
        :type config: Any
        :return: A dictionary containing the results of the research execution.
        :rtype: dict[str, Any]
        """
        plan = context["plan"]
        intake = context["intake"]

        # Build research request
        sections_summary = []
        for section in plan["sections"]:
            queries = section.get("research_queries", [])
            sections_summary.append(
                f"- Section '{section['id']}': {section['title']}\n"
                f"  Zweck: {section['purpose']}\n"
                f"  Suchbegriffe: {', '.join(queries) if queries else 'keine'}"
            )

        research_request = (
            f"Thema: {plan['title']}\n"
            f"Fach: {intake['subject']}\n"
            f"Kontext: Berufsschule Fachinformatiker Anwendungsentwicklung\n\n"
            f"Abschnitte:\n" + "\n".join(sections_summary)
        )

        # If web search is enabled AND available, use it first
        web_findings = {}
        if config.research.enabled and config.research.use_web:
            web_findings = await self._web_research(plan["sections"], config)

        # LLM research pass — always runs, enriched with web findings
        prompt = RESEARCH_PROMPT
        if not (config.research.enabled and config.research.use_web):
            prompt += (
                "\n\nWICHTIG: Webrecherche ist DEAKTIVIERT. "
                "Verwende KEINE URLs als Quellen. "
                "Alle Quellen muessen als 'llm_knowledge' markiert werden. "
                "Erfinde KEINE URLs."
            )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": research_request},
        ]

        if web_findings:
            web_context = "\n\nZusätzliche Informationen aus Webrecherche:\n"
            for sid, findings in web_findings.items():
                web_context += f"\n[{sid}]:\n"
                for f in findings:
                    web_context += f"  - {f['content'][:200]} (Quelle: {f['source']})\n"
            messages[1]["content"] += web_context

        response = await backend.complete(
            stage=self.name,
            messages=messages,
            temperature=0.2,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )

        data = _parse_json_response(response.content)

        # Sanitize: strip fabricated URLs when web is disabled
        if not (config.research.enabled and config.research.use_web):
            for section in data.get("sections", []):
                for finding in section.get("findings", []):
                    if finding.get("source", "").startswith("http"):
                        finding["source"] = "llm_knowledge"

        # Merge web findings into LLM findings
        if web_findings:
            for section in data.get("sections", []):
                sid = section["section_id"]
                if sid in web_findings:
                    section["findings"].extend(web_findings[sid])

        return data

    async def _web_research(self, sections: list[dict], config: Any) -> dict[str, list[dict]]:
        """Run web research for sections that have queries.

        Returns dict mapping section_id -> list of findings.
        Uses DuckDuckGo search + page scraping with disk caching.
        """
        import asyncio

        from schulpipeline.research.web import DiskCache, search_and_extract

        cache = DiskCache(config.research.cache_dir)
        results: dict[str, list[dict]] = {}

        for section in sections:
            queries = section.get("research_queries", [])
            if not queries:
                continue

            findings: list[dict] = []
            for query in queries[:2]:  # limit queries per section
                search_results = await search_and_extract(query, max_results=2, cache=cache)
                for sr in search_results:
                    if sr.quality in ("high", "medium"):
                        findings.append(
                            {
                                "content": sr.text[:500],
                                "source": sr.url,
                                "relevance": 0.7,
                            }
                        )
                await asyncio.sleep(config.research.request_delay)

            if findings:
                results[section["id"]] = findings

        return results
