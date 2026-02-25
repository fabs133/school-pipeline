"""Test fixtures — mock backend and config for offline testing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from schulpipeline.backends.base import LLMResponse, BackendError
from schulpipeline.backends.router import BackendRouter, BACKEND_FACTORIES
from schulpipeline.config import BackendConfig, PipelineConfig, OutputConfig, ResearchConfig


# --- Mock Backend ---

class MockBackend:
    """Deterministic backend for testing — returns pre-configured responses."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.name = "mock"
        self.is_free = True
        self.supports_vision = True
        self.max_context = 128_000
        self.model = "mock-model"
        self.calls: list[dict] = []
        self._responses = responses or {}
        self._default_responses = DEFAULT_STAGE_RESPONSES

    async def complete(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "temperature": temperature})

        # Determine which stage this is for based on system prompt content
        system_msg = messages[0]["content"] if messages else ""
        for stage_key, response in self._responses.items():
            if stage_key in system_msg:
                return LLMResponse(content=response, model="mock", backend_name="mock")

        # Fallback to default responses
        for stage_key, response in self._default_responses.items():
            if stage_key in system_msg:
                return LLMResponse(content=response, model="mock", backend_name="mock")

        return LLMResponse(content="{}", model="mock", backend_name="mock")

    async def complete_vision(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return await self.complete(messages, temperature, max_tokens)

    async def close(self):
        pass


# --- Default mock responses per stage ---

DEFAULT_STAGE_RESPONSES = {
    "Aufgaben-Parser": json.dumps({
        "task_text": "Erstellen Sie eine Präsentation zum Thema IT-Sicherheit mit mindestens 8 Folien.",
        "subject": "IT-Sicherheit",
        "task_type": "presentation",
        "constraints": {
            "page_count": None,
            "slide_count": 8,
            "word_count": None,
            "language": "de",
            "format": "pptx",
            "due_date": None,
            "specific_requirements": ["mindestens 8 Folien", "Quellen angeben"]
        },
        "raw_input_type": "text"
    }),
    "Planungsassistent": json.dumps({
        "title": "IT-Sicherheit im Unternehmen",
        "artifact_type": "pptx",
        "sections": [
            {"id": "section_01", "title": "IT-Sicherheit im Unternehmen", "purpose": "Titelfolie",
             "research_queries": [], "estimated_length": "short"},
            {"id": "section_02", "title": "Was ist IT-Sicherheit?", "purpose": "Definition und Grundbegriffe",
             "research_queries": ["IT-Sicherheit Definition", "Schutzziele CIA"], "estimated_length": "medium"},
            {"id": "section_03", "title": "Bedrohungen", "purpose": "Typische Angriffsvektoren",
             "research_queries": ["Cyberangriffe Arten", "Phishing Ransomware"], "estimated_length": "medium"},
            {"id": "section_04", "title": "Schutzmaßnahmen", "purpose": "Technische und organisatorische Maßnahmen",
             "research_queries": ["IT-Sicherheit Maßnahmen", "Firewall VPN"], "estimated_length": "medium"},
            {"id": "section_05", "title": "Quellen", "purpose": "Quellenangaben",
             "research_queries": [], "estimated_length": "short"},
        ],
        "style_notes": "Sachlich, Stichpunkte, Berufsschul-Niveau"
    }),
    "Recherche-Assistent": json.dumps({
        "sections": [
            {"section_id": "section_01", "findings": [
                {"content": "Titelfolie", "source": "llm_knowledge", "relevance": 1.0}
            ], "sufficient": True},
            {"section_id": "section_02", "findings": [
                {"content": "IT-Sicherheit umfasst den Schutz von Informationen und IT-Systemen vor unbefugtem Zugriff, Manipulation und Ausfall.", "source": "llm_knowledge", "relevance": 0.95},
                {"content": "Die drei Schutzziele sind Vertraulichkeit (Confidentiality), Integrität (Integrity) und Verfügbarkeit (Availability) — das CIA-Triad.", "source": "llm_knowledge", "relevance": 0.95},
            ], "sufficient": True},
            {"section_id": "section_03", "findings": [
                {"content": "Phishing ist die häufigste Angriffsmethode — über 80% aller Cyberangriffe beginnen mit einer Phishing-Mail.", "source": "llm_knowledge", "relevance": 0.9},
                {"content": "Ransomware verschlüsselt Daten und fordert Lösegeld. Bekannte Beispiele: WannaCry, NotPetya.", "source": "llm_knowledge", "relevance": 0.9},
            ], "sufficient": True},
            {"section_id": "section_04", "findings": [
                {"content": "Technische Maßnahmen: Firewalls, VPN, Verschlüsselung, regelmäßige Updates, Backups.", "source": "llm_knowledge", "relevance": 0.9},
                {"content": "Organisatorische Maßnahmen: Schulungen, Zugriffsrechte, Sicherheitsrichtlinien, Incident Response Plan.", "source": "llm_knowledge", "relevance": 0.85},
            ], "sufficient": True},
            {"section_id": "section_05", "findings": [
                {"content": "Quellenfolie", "source": "llm_knowledge", "relevance": 1.0}
            ], "sufficient": True},
        ]
    }),
    "Präsentations-Autor": json.dumps({
        "title": "IT-Sicherheit im Unternehmen",
        "sections": [
            {"section_id": "section_01", "heading": "IT-Sicherheit im Unternehmen",
             "content": "Eine Übersicht über Grundlagen, Bedrohungen und Schutzmaßnahmen",
             "bullet_points": [], "speaker_notes": None},
            {"section_id": "section_02", "heading": "Was ist IT-Sicherheit?",
             "content": "IT-Sicherheit schützt Informationen und Systeme.",
             "bullet_points": ["Schutz von Informationen und IT-Systemen", "CIA-Triad: Vertraulichkeit, Integrität, Verfügbarkeit", "Gesetzliche Grundlage: BSI-Gesetz, DSGVO"],
             "speaker_notes": "Die drei Schutzziele bilden die Grundlage jeder Sicherheitsstrategie."},
            {"section_id": "section_03", "heading": "Bedrohungen",
             "content": "Cyberangriffe nehmen stetig zu.",
             "bullet_points": ["Phishing — häufigste Angriffsmethode", "Ransomware — Datenverschlüsselung und Erpressung", "Social Engineering — Manipulation von Mitarbeitern"],
             "speaker_notes": "Über 80% aller Angriffe beginnen mit einer Phishing-Mail."},
            {"section_id": "section_04", "heading": "Schutzmaßnahmen",
             "content": "Technische und organisatorische Maßnahmen.",
             "bullet_points": ["Firewalls und VPN", "Regelmäßige Updates und Backups", "Mitarbeiterschulungen", "Incident Response Plan"],
             "speaker_notes": "Die beste Technik hilft nichts ohne geschulte Mitarbeiter."},
            {"section_id": "section_05", "heading": "Quellen",
             "content": "Verwendete Quellen und Referenzen zur IT-Sicherheit.",
             "bullet_points": ["BSI — Bundesamt für Sicherheit in der Informationstechnik", "OWASP Top 10"],
             "speaker_notes": None},
        ],
        "sources": ["BSI — Bundesamt für Sicherheit in der Informationstechnik", "OWASP Top 10"]
    }),
}


# --- Fixtures ---

@pytest.fixture
def mock_backend():
    return MockBackend()


@pytest.fixture
def mock_config():
    return PipelineConfig(
        backends={"mock": BackendConfig(name="mock", api_key="test", enabled=True)},
        cascade={
            "intake": ["mock"],
            "plan": ["mock"],
            "research": ["mock"],
            "synthesize": ["mock"],
            "artifact": ["mock"],
        },
        research=ResearchConfig(enabled=False, use_web=False),
        output=OutputConfig(dir="/tmp/schulpipeline_test", default_format="pptx", language="de"),
    )


@pytest.fixture
def mock_router(mock_config, mock_backend):
    """Create a router with the mock backend injected."""
    router = BackendRouter.__new__(BackendRouter)
    router.config = mock_config
    router._backends = {"mock": mock_backend}
    router._cooldowns = {}
    router._call_counts = {"mock": 0}
    router._total_cost = 0.0
    router._stage_costs = {}
    router._stage_tokens = {}
    return router


class FailingBackend:
    """Backend that always raises BackendError."""

    def __init__(self, name: str = "failing"):
        self.name = name
        self.is_free = True
        self.supports_vision = False
        self.max_context = 8192
        self.model = "fail-model"

    async def complete(self, messages, temperature=0.3, max_tokens=4096, response_format=None):
        raise BackendError(f"{self.name} always fails", self.name, retryable=False)

    async def complete_vision(self, messages, temperature=0.3, max_tokens=4096):
        raise BackendError(f"{self.name} no vision", self.name, retryable=False)

    async def close(self):
        pass


@pytest.fixture
def cascade_router(mock_config, mock_backend):
    """Router with two backends: a failing one first, then the working mock."""
    mock_config.cascade = {
        "intake": ["failing", "mock"],
        "plan": ["failing", "mock"],
        "research": ["failing", "mock"],
        "synthesize": ["failing", "mock"],
        "artifact": ["failing", "mock"],
    }
    mock_config.backends["failing"] = BackendConfig(name="failing", api_key="test", enabled=True)

    router = BackendRouter.__new__(BackendRouter)
    router.config = mock_config
    router._backends = {"failing": FailingBackend(), "mock": mock_backend}
    router._cooldowns = {}
    router._call_counts = {"failing": 0, "mock": 0}
    router._total_cost = 0.0
    router._stage_costs = {}
    router._stage_tokens = {}
    return router


@pytest.fixture
def synthesis_data():
    """Pre-parsed synthesis data for artifact builder tests."""
    return json.loads(DEFAULT_STAGE_RESPONSES["Präsentations-Autor"])
