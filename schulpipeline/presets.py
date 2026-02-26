"""Preset system — student-facing configuration layer.

A student thinks in three dimensions:
  1. Was soll rauskommen?  (Präsentation, Dokument, Antworten)
  2. Was ist die Aufgabe?  (Freitext oder Foto)
  3. Welches Fach?         (IT, Wirtschaft, Politik, ...)

A preset translates these into pipeline configuration:
  - Output format + defaults (slide count, page count, structure)
  - Prompt tuning (domain vocabulary, expected depth, formality)
  - Quality constraints (sources required, diagrams expected, etc.)

Presets are composable: output_type × subject = full config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ============================================================
# Output Types — "Was soll rauskommen?"
# ============================================================

@dataclass(frozen=True)
class OutputPreset:
    """Defines what the final artifact looks like."""
    key: str
    label: str                           # Student-facing name
    format: str                          # pptx | docx | md
    default_section_count: int           # slides or chapters
    structure: list[str]                 # expected section types
    style: str                           # bullet-heavy, prose, compact
    constraints: dict[str, Any] = field(default_factory=dict)


OUTPUT_PRESETS: dict[str, OutputPreset] = {
    # --- Präsentation ---
    "praesentation": OutputPreset(
        key="praesentation",
        label="Präsentation",
        format="pptx",
        default_section_count=10,
        structure=["titel", "inhalt", "inhalt", "inhalt", "inhalt", "inhalt", "inhalt", "inhalt", "fazit", "quellen"],
        style="bullet-heavy",
        constraints={
            "bullets_per_slide": (3, 5),
            "words_per_bullet": (3, 10),
            "speaker_notes": True,
            "sources_required": True,
        },
    ),
    "praesentation_kurz": OutputPreset(
        key="praesentation_kurz",
        label="Kurzpräsentation (5 Folien)",
        format="pptx",
        default_section_count=5,
        structure=["titel", "inhalt", "inhalt", "inhalt", "quellen"],
        style="bullet-heavy",
        constraints={
            "bullets_per_slide": (3, 4),
            "words_per_bullet": (3, 8),
            "speaker_notes": False,
            "sources_required": True,
        },
    ),

    # --- Dokument / Ausarbeitung ---
    "ausarbeitung": OutputPreset(
        key="ausarbeitung",
        label="Ausarbeitung / Bericht",
        format="docx",
        default_section_count=5,
        structure=["einleitung", "hauptteil", "hauptteil", "fazit", "quellen"],
        style="prose",
        constraints={
            "min_words_per_section": 150,
            "formal_register": True,
            "sources_required": True,
        },
    ),
    "handout": OutputPreset(
        key="handout",
        label="Handout (1-2 Seiten)",
        format="docx",
        default_section_count=4,
        structure=["titel", "kernpunkte", "kernpunkte", "quellen"],
        style="compact",
        constraints={
            "max_pages": 2,
            "bullet_heavy": True,
            "sources_required": True,
        },
    ),

    # --- Aufgaben beantworten ---
    "aufgaben": OutputPreset(
        key="aufgaben",
        label="Aufgaben beantworten",
        format="md",
        default_section_count=0,  # dynamic — one per question
        structure=[],             # dynamic
        style="compact",
        constraints={
            "direct_answers": True,
            "show_reasoning": False,
            "sources_required": False,
        },
    ),
    "aufgaben_ausfuehrlich": OutputPreset(
        key="aufgaben_ausfuehrlich",
        label="Aufgaben mit Begründung",
        format="md",
        default_section_count=0,
        structure=[],
        style="compact",
        constraints={
            "direct_answers": True,
            "show_reasoning": True,
            "sources_required": False,
        },
    ),

    # --- Sonstige ---
    "essay": OutputPreset(
        key="essay",
        label="Essay / Erörterung",
        format="docx",
        default_section_count=4,
        structure=["einleitung", "argumentation", "gegenargumentation", "fazit"],
        style="prose",
        constraints={
            "formal_register": True,
            "min_words_total": 500,
            "sources_required": False,
        },
    ),
    "zusammenfassung": OutputPreset(
        key="zusammenfassung",
        label="Zusammenfassung",
        format="md",
        default_section_count=3,
        structure=["kernaussagen", "details", "fazit"],
        style="compact",
        constraints={
            "max_words_total": 500,
            "sources_required": False,
        },
    ),

    # --- Coding-Projekte ---
    "projekt": OutputPreset(
        key="projekt",
        label="Coding-Projekt",
        format="project",                # Special: triggers agent dispatch
        default_section_count=5,
        structure=["setup", "module", "module", "module", "tests"],
        style="technical",
        constraints={
            "include_tests": True,
            "include_readme": True,
            "include_config": True,
            "agent_mode": True,           # Signals artifact stage to use agents
        },
    ),
    "projekt_einfach": OutputPreset(
        key="projekt_einfach",
        label="Einfaches Script/Tool",
        format="project",
        default_section_count=3,
        structure=["main", "helpers", "readme"],
        style="technical",
        constraints={
            "include_tests": False,
            "include_readme": True,
            "include_config": False,
            "agent_mode": True,
            "max_files": 5,
        },
    ),

    # --- Arbeitsblätter ---
    "arbeitsblatt": OutputPreset(
        key="arbeitsblatt",
        label="Arbeitsblatt ausfüllen",
        format="worksheet",              # Special: triggers decompose → solve flow
        default_section_count=0,          # Dynamic — depends on task count
        structure=[],
        style="mirror_input",
        constraints={
            "worksheet_mode": True,
            "show_calculation_steps": True,
            "german_number_format": True,
            "mirror_input_structure": True,
        },
    ),
    "arbeitsblatt_kurz": OutputPreset(
        key="arbeitsblatt_kurz",
        label="Arbeitsblatt (nur Antworten)",
        format="worksheet",
        default_section_count=0,
        structure=[],
        style="compact",
        constraints={
            "worksheet_mode": True,
            "show_calculation_steps": False,
            "german_number_format": True,
        },
    ),

    # --- Vorlagen / Templates ---
    "vorlage": OutputPreset(
        key="vorlage",
        label="Vorlage ausfüllen",
        format="template_fill",           # Special: triggers classify → fill flow
        default_section_count=0,
        structure=[],
        style="preserve_original",
        constraints={
            "template_mode": True,
            "preserve_layout": True,
        },
    ),
    "projektantrag": OutputPreset(
        key="projektantrag",
        label="Projektantrag ausfüllen",
        format="template_fill",
        default_section_count=0,
        structure=[],
        style="formal",
        constraints={
            "template_mode": True,
            "preserve_layout": True,
            "max_pages": 1,               # DIN A4 constraint
            "formal_language": True,
        },
    ),

    # --- Audit ---
    "audit": OutputPreset(
        key="audit",
        label="Vorgaben-Audit",
        format="audit",                   # Special: classify → audit only
        default_section_count=0,
        structure=[],
        style="formal",
        constraints={
            "audit_only": True,
        },
    ),
    "anforderungen": OutputPreset(
        key="anforderungen",
        label="Anforderungsdokumentation",
        format="requirements_report",     # Special: full A/B/C report
        default_section_count=0,
        structure=[],
        style="formal",
        constraints={
            "requirements_report": True,
        },
    ),
}


# ============================================================
# Subjects — "Welches Fach?"
# ============================================================

@dataclass(frozen=True)
class SubjectPreset:
    """Domain context that tunes prompts and research."""
    key: str
    label: str
    domain_context: str              # injected into system prompts
    vocabulary_hints: list[str]      # domain-specific terms the LLM should use
    research_bias: str               # what kind of sources to prefer
    difficulty: str                  # berufsschule | gymnasium | uni
    language: str = "de"


SUBJECT_PRESETS: dict[str, SubjectPreset] = {
    # === Fachinformatiker Anwendungsentwicklung ===
    "it_sicherheit": SubjectPreset(
        key="it_sicherheit",
        label="IT-Sicherheit",
        domain_context="Berufsschule Fachinformatiker Anwendungsentwicklung. "
                       "Themenbereich IT-Sicherheit: Schutzziele, Bedrohungen, Maßnahmen, "
                       "BSI-Grundschutz, Kryptographie, Netzwerksicherheit.",
        vocabulary_hints=["CIA-Triad", "BSI", "Firewall", "VPN", "Ransomware", "Phishing",
                          "Penetrationstest", "DSGVO", "ISO 27001"],
        research_bias="BSI, OWASP, Heise Security, ct-Magazin",
        difficulty="berufsschule",
    ),
    "netzwerktechnik": SubjectPreset(
        key="netzwerktechnik",
        label="Netzwerktechnik",
        domain_context="Berufsschule Fachinformatiker Anwendungsentwicklung. "
                       "Themenbereich Netzwerktechnik: OSI-Modell, TCP/IP, Routing, "
                       "Switching, VLAN, Subnetting, DNS, DHCP.",
        vocabulary_hints=["OSI-Modell", "TCP/IP", "Subnetting", "VLAN", "Router", "Switch",
                          "DNS", "DHCP", "NAT", "Gateway"],
        research_bias="Cisco, Heise Netze, Elektronik-Kompendium",
        difficulty="berufsschule",
    ),
    "programmierung": SubjectPreset(
        key="programmierung",
        label="Programmierung / Softwareentwicklung",
        domain_context="Berufsschule Fachinformatiker Anwendungsentwicklung. "
                       "Themenbereich Softwareentwicklung: OOP, Design Patterns, "
                       "Versionskontrolle, Testing, Datenbanken, Agile Methoden.",
        vocabulary_hints=["OOP", "SOLID", "Git", "Unit Test", "UML", "SQL", "REST API",
                          "Scrum", "Kanban", "CI/CD"],
        research_bias="MDN, Stack Overflow, Clean Code (Robert C. Martin)",
        difficulty="berufsschule",
    ),
    "datenbanken": SubjectPreset(
        key="datenbanken",
        label="Datenbanken",
        domain_context="Berufsschule Fachinformatiker Anwendungsentwicklung. "
                       "Themenbereich Datenbanken: ER-Modell, Normalisierung, SQL, "
                       "Transaktionen, NoSQL, Datenbankdesign.",
        vocabulary_hints=["ER-Modell", "Normalisierung", "SQL", "JOIN", "PRIMARY KEY",
                          "FOREIGN KEY", "ACID", "NoSQL", "Index"],
        research_bias="W3Schools SQL, Elektronik-Kompendium, PostgreSQL Docs",
        difficulty="berufsschule",
    ),
    "wirtschaft": SubjectPreset(
        key="wirtschaft",
        label="Wirtschaft / Geschäftsprozesse",
        domain_context="Berufsschule Fachinformatiker Anwendungsentwicklung. "
                       "Themenbereich Wirtschaft und Geschäftsprozesse: BWL-Grundlagen, "
                       "Kostenrechnung, Vertragsrecht, Projektmanagement, Marketing.",
        vocabulary_hints=["Angebot/Nachfrage", "Deckungsbeitrag", "Fixkosten", "Variable Kosten",
                          "BGB", "HGB", "Gewährleistung", "Lastenheft", "Pflichtenheft"],
        research_bias="IHK, Gabler Wirtschaftslexikon, BWL-Lehrbücher",
        difficulty="berufsschule",
    ),
    "politik": SubjectPreset(
        key="politik",
        label="Politik / Sozialkunde",
        domain_context="Berufsschule. Themenbereich Politik und Gesellschaft: "
                       "Grundgesetz, Staatsaufbau, Sozialversicherung, EU, "
                       "Arbeitsrecht, Tarifverträge, Betriebsrat.",
        vocabulary_hints=["Grundgesetz", "Bundestag", "Bundesrat", "Sozialversicherung",
                          "Tarifvertrag", "Betriebsrat", "EU-Vertrag", "Gewaltenteilung"],
        research_bias="bpb, Bundeszentrale für politische Bildung, Tagesschau",
        difficulty="berufsschule",
    ),
    "englisch": SubjectPreset(
        key="englisch",
        label="Englisch (IT-Kontext)",
        domain_context="Berufsschule Fachinformatiker. Englisch im IT-Kontext: "
                       "Technical writing, IT vocabulary, business communication.",
        vocabulary_hints=["deploy", "implement", "requirements", "stakeholder",
                          "deadline", "sprint", "ticket"],
        research_bias="Cambridge Dictionary, IT-specific glossaries",
        difficulty="berufsschule",
        language="en",
    ),

    # === Allgemein (Gymnasium / andere Schulformen) ===
    "informatik": SubjectPreset(
        key="informatik",
        label="Informatik (allgemein)",
        domain_context="Schulfach Informatik: Algorithmen, Datenstrukturen, "
                       "Programmierung, Automatentheorie, Kryptographie.",
        vocabulary_hints=["Algorithmus", "Datenstruktur", "Komplexität", "Automat",
                          "Verschlüsselung", "Sortierverfahren"],
        research_bias="Informatik-Lehrbücher, Khan Academy, CS50",
        difficulty="gymnasium",
    ),
    "mathematik": SubjectPreset(
        key="mathematik",
        label="Mathematik",
        domain_context="Schulfach Mathematik: Analysis, Algebra, Stochastik, Geometrie.",
        vocabulary_hints=["Ableitung", "Integral", "Wahrscheinlichkeit", "Matrix",
                          "Vektor", "Funktion", "Grenzwert"],
        research_bias="Mathematik-Lehrbücher, Serlo, Mathebibel",
        difficulty="gymnasium",
    ),
    "deutsch": SubjectPreset(
        key="deutsch",
        label="Deutsch",
        domain_context="Schulfach Deutsch: Literaturanalyse, Erörterung, Textanalyse, "
                       "Grammatik, Epochen der Literatur.",
        vocabulary_hints=["Stilmittel", "Epoche", "Erzählperspektive", "These",
                          "Argumentation", "Interpretation"],
        research_bias="Reclam, Lektürehilfen, Deutschunterricht-Materialien",
        difficulty="gymnasium",
    ),
    "geschichte": SubjectPreset(
        key="geschichte",
        label="Geschichte",
        domain_context="Schulfach Geschichte: Epochen, Quellenanalyse, "
                       "politische und soziale Zusammenhänge.",
        vocabulary_hints=["Quelle", "Epoche", "Kausalität", "Perspektive",
                          "Primärquelle", "Sekundärquelle"],
        research_bias="bpb, Geschichtslehrbücher, LeMO (Deutsches Historisches Museum)",
        difficulty="gymnasium",
    ),

    # === Frei / Custom ===
    "custom": SubjectPreset(
        key="custom",
        label="Anderes Fach",
        domain_context="Schulaufgabe. Kontext wird aus der Aufgabenstellung abgeleitet.",
        vocabulary_hints=[],
        research_bias="",
        difficulty="berufsschule",
    ),
}


# ============================================================
# Resolved Preset — what the pipeline actually receives
# ============================================================

@dataclass
class ResolvedPreset:
    """Fully resolved configuration from output + subject presets."""

    # Output config
    output_format: str
    section_count: int
    structure: list[str]
    style: str
    output_constraints: dict[str, Any]

    # Subject config
    subject_key: str
    subject_label: str
    domain_context: str
    vocabulary_hints: list[str]
    research_bias: str
    difficulty: str
    language: str

    # Computed prompt fragments
    system_context: str = ""
    quality_instructions: str = ""

    def __post_init__(self):
        self.system_context = self._build_system_context()
        self.quality_instructions = self._build_quality_instructions()

    def _build_system_context(self) -> str:
        """Build the domain context string injected into all stage prompts."""
        parts = [self.domain_context]
        if self.vocabulary_hints:
            parts.append(f"Verwende Fachbegriffe: {', '.join(self.vocabulary_hints[:10])}")
        if self.research_bias:
            parts.append(f"Bevorzugte Quellen: {self.research_bias}")

        depth = {
            "berufsschule": "Antworte auf Berufsschul-Niveau: klar, sachlich, praxisbezogen.",
            "gymnasium": "Antworte auf Oberstufen-Niveau: differenziert, mit Fachbegriffen.",
            "uni": "Antworte auf akademischem Niveau: präzise, quellenbasiert, kritisch reflektiert.",
        }.get(self.difficulty, "")
        if depth:
            parts.append(depth)

        return "\n".join(parts)

    def _build_quality_instructions(self) -> str:
        """Build quality/formatting instructions from output constraints."""
        instructions = []
        c = self.output_constraints

        if c.get("bullets_per_slide"):
            lo, hi = c["bullets_per_slide"]
            instructions.append(f"Pro Folie {lo}-{hi} Stichpunkte.")
        if c.get("words_per_bullet"):
            lo, hi = c["words_per_bullet"]
            instructions.append(f"Stichpunkte: {lo}-{hi} Wörter, keine ganzen Sätze.")
        if c.get("speaker_notes"):
            instructions.append("Speaker Notes für jede Inhaltsfolie (2-3 Sätze).")
        if c.get("sources_required"):
            instructions.append("Quellenangaben auf der letzten Folie/Seite.")
        if c.get("direct_answers"):
            instructions.append("Direkte Antworten, kein Fülltext.")
        if c.get("show_reasoning"):
            instructions.append("Kurze Begründung nach jeder Antwort.")
        if c.get("formal_register"):
            instructions.append("Formeller Schreibstil, keine Umgangssprache.")
        if c.get("min_words_per_section"):
            instructions.append(f"Mindestens {c['min_words_per_section']} Wörter pro Abschnitt.")
        if c.get("max_pages"):
            instructions.append(f"Maximal {c['max_pages']} Seiten.")

        return "\n".join(instructions)


def resolve_preset(
    output_key: str,
    subject_key: str,
    overrides: dict[str, Any] | None = None,
) -> ResolvedPreset:
    """Combine an output preset with a subject preset into a resolved config.

    Args:
        output_key: Key from OUTPUT_PRESETS (e.g. "praesentation")
        subject_key: Key from SUBJECT_PRESETS (e.g. "it_sicherheit")
        overrides: Optional dict to override specific fields
            - section_count: int
            - language: str
            - difficulty: str
            - additional_context: str (appended to domain_context)

    Returns:
        ResolvedPreset ready for pipeline injection.
    """
    output = OUTPUT_PRESETS.get(output_key)
    if not output:
        raise ValueError(
            f"Unknown output preset '{output_key}'. "
            f"Available: {', '.join(OUTPUT_PRESETS.keys())}"
        )

    subject = SUBJECT_PRESETS.get(subject_key)
    if not subject:
        raise ValueError(
            f"Unknown subject preset '{subject_key}'. "
            f"Available: {', '.join(SUBJECT_PRESETS.keys())}"
        )

    overrides = overrides or {}

    domain_context = subject.domain_context
    if overrides.get("additional_context"):
        domain_context += f"\n{overrides['additional_context']}"

    return ResolvedPreset(
        output_format=output.format,
        section_count=overrides.get("section_count", output.default_section_count),
        structure=list(output.structure),
        style=output.style,
        output_constraints=dict(output.constraints),
        subject_key=subject.key,
        subject_label=subject.label,
        domain_context=domain_context,
        vocabulary_hints=list(subject.vocabulary_hints),
        research_bias=subject.research_bias,
        difficulty=overrides.get("difficulty", subject.difficulty),
        language=overrides.get("language", subject.language),
    )


# ============================================================
# Quick-access aliases for common combinations
# ============================================================

QUICK_PRESETS: dict[str, tuple[str, str]] = {
    # Fachinformatiker AE — die häufigsten Aufgaben
    "fiae-praesi-itsec":     ("praesentation", "it_sicherheit"),
    "fiae-praesi-netzwerk":  ("praesentation", "netzwerktechnik"),
    "fiae-praesi-prog":      ("praesentation", "programmierung"),
    "fiae-praesi-db":        ("praesentation", "datenbanken"),
    "fiae-praesi-wirtschaft":("praesentation", "wirtschaft"),
    "fiae-praesi-politik":   ("praesentation", "politik"),
    "fiae-aufgaben-itsec":   ("aufgaben", "it_sicherheit"),
    "fiae-aufgaben-netzwerk":("aufgaben", "netzwerktechnik"),
    "fiae-aufgaben-prog":    ("aufgaben", "programmierung"),
    "fiae-aufgaben-wirtschaft":("aufgaben", "wirtschaft"),
    "fiae-handout-itsec":    ("handout", "it_sicherheit"),
    "fiae-doku-prog":        ("ausarbeitung", "programmierung"),

    # Fachinformatiker AE — Coding-Projekte
    "fiae-projekt-prog":     ("projekt", "programmierung"),
    "fiae-projekt-db":       ("projekt", "datenbanken"),
    "fiae-projekt-web":      ("projekt", "programmierung"),
    "fiae-script-prog":      ("projekt_einfach", "programmierung"),

    # Fachinformatiker AE — Arbeitsblätter
    "fiae-blatt-wirtschaft":  ("arbeitsblatt", "wirtschaft"),
    "fiae-blatt-itsec":       ("arbeitsblatt", "it_sicherheit"),
    "fiae-blatt-netzwerk":    ("arbeitsblatt", "netzwerktechnik"),
    "fiae-blatt-prog":        ("arbeitsblatt", "programmierung"),
    "fiae-blatt-db":          ("arbeitsblatt", "datenbanken"),
    "fiae-blatt-politik":     ("arbeitsblatt", "politik"),

    # Templates / Vorlagen
    "fiae-vorlage-prog":      ("vorlage", "programmierung"),
    "fiae-vorlage-itsec":     ("vorlage", "it_sicherheit"),
    "fiae-projektantrag":     ("projektantrag", "programmierung"),
    "fiae-audit":             ("audit", "programmierung"),
    "fiae-anforderungen":     ("anforderungen", "programmierung"),

    # Gymnasium — gängig
    "gym-praesi-informatik": ("praesentation", "informatik"),
    "gym-praesi-geschichte": ("praesentation", "geschichte"),
    "gym-essay-deutsch":     ("essay", "deutsch"),
    "gym-aufgaben-mathe":    ("aufgaben", "mathematik"),
    "gym-projekt-informatik":("projekt", "informatik"),
}


def resolve_quick(quick_key: str, overrides: dict[str, Any] | None = None) -> ResolvedPreset:
    """Resolve a quick-access alias."""
    if quick_key not in QUICK_PRESETS:
        raise ValueError(
            f"Unknown quick preset '{quick_key}'. "
            f"Available: {', '.join(sorted(QUICK_PRESETS.keys()))}"
        )
    output_key, subject_key = QUICK_PRESETS[quick_key]
    return resolve_preset(output_key, subject_key, overrides)


def list_presets() -> dict[str, Any]:
    """List all available presets for UI/CLI display."""
    return {
        "output_types": {k: {"label": v.label, "format": v.format} for k, v in OUTPUT_PRESETS.items()},
        "subjects": {k: {"label": v.label, "difficulty": v.difficulty} for k, v in SUBJECT_PRESETS.items()},
        "quick": {k: {"output": v[0], "subject": v[1],
                       "label": f"{OUTPUT_PRESETS[v[0]].label} → {SUBJECT_PRESETS[v[1]].label}"}
                  for k, v in QUICK_PRESETS.items()},
    }
