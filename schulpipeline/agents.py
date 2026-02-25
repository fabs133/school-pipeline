"""Agent system — pluggable execution agents for project-level tasks.

When the pipeline produces a plan for a coding project, the artifact stage
can hand off to an agent that actually builds it. The plan becomes the spec.

Architecture:
  Pipeline stages 1-4 (intake → plan → research → synthesize)
    → produces structured project specification
    → Agent adapter receives spec + executes
    → Output: complete project directory

Agents are optional, credit-based, and the user is always informed of costs
before execution starts.

Supported agents:
  - claude_code:  Anthropic Claude Code CLI (credits)
  - codex:        OpenAI Codex CLI (credits)
  - gemini_code:  Google Gemini Code Assist (API, may have free tier)
  - local_llm:    Generate code via LLM completions (free if using free backends)

Agent selection:
  - Configured in config.yaml under `agents:`
  - Selected via --agent CLI flag or preset
  - local_llm is always available as fallback (uses existing backends)
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("schulpipeline.agents")


# ============================================================
# Agent Protocol
# ============================================================

@dataclass
class AgentResult:
    """Result from an agent execution."""
    success: bool
    output_dir: str                    # Path to generated project
    files_created: list[str]           # List of file paths
    errors: list[str] = field(default_factory=list)
    cost_estimate_usd: float = 0.0     # Estimated cost (shown before execution)
    cost_actual_usd: float = 0.0       # Actual cost after execution
    agent_name: str = ""
    log: str = ""                      # Agent stdout/stderr


@dataclass
class AgentConfig:
    """Configuration for a specific agent."""
    name: str
    enabled: bool = False
    api_key: str = ""
    model: str = ""
    max_cost_usd: float = 1.0         # Safety cap — abort if estimate exceeds this
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if self.name == "local_llm":
            return True  # Always available via pipeline backends
        return bool(self.api_key)


class BaseAgent(ABC):
    """Base class for execution agents."""

    name: str = ""
    is_free: bool = False
    description: str = ""

    @abstractmethod
    async def estimate_cost(self, spec: ProjectSpec) -> float:
        """Estimate cost before execution. Returns USD."""
        ...

    @abstractmethod
    async def execute(self, spec: ProjectSpec, output_dir: Path) -> AgentResult:
        """Execute the project spec, writing files to output_dir."""
        ...


# ============================================================
# Project Spec — the contract between pipeline and agent
# ============================================================

@dataclass
class ProjectSpec:
    """Structured project specification derived from pipeline synthesis.

    This is what gets handed to an agent. It's language/framework aware
    and contains enough detail for an agent to build the project.
    """
    title: str
    description: str
    language: str                      # python, javascript, java, csharp, etc.
    framework: str = ""                # flask, react, spring, etc.
    project_type: str = ""             # cli, web, api, library, fullstack

    # Structure
    modules: list[ModuleSpec] = field(default_factory=list)
    entry_point: str = ""              # e.g. "main.py", "src/index.ts"

    # Requirements
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)

    # Constraints from school assignment
    requirements: list[str] = field(default_factory=list)  # "must include tests", "use MVC pattern"
    max_complexity: str = "berufsschule"  # berufsschule | gymnasium | uni

    # Full text for the agent (the detailed plan)
    full_spec_text: str = ""

    def to_prompt(self) -> str:
        """Convert to a detailed prompt for the agent."""
        lines = [
            f"# Project: {self.title}",
            f"\n{self.description}",
            f"\n## Technical Stack",
            f"- Language: {self.language}",
        ]
        if self.framework:
            lines.append(f"- Framework: {self.framework}")
        if self.project_type:
            lines.append(f"- Type: {self.project_type}")

        if self.modules:
            lines.append("\n## Modules")
            for mod in self.modules:
                lines.append(f"\n### {mod.name}")
                lines.append(f"Purpose: {mod.purpose}")
                if mod.files:
                    lines.append("Files:")
                    for f in mod.files:
                        lines.append(f"  - `{f.path}`: {f.description}")
                        if f.key_functions:
                            for fn in f.key_functions:
                                lines.append(f"    - `{fn}`")

        if self.dependencies:
            lines.append(f"\n## Dependencies")
            for dep in self.dependencies:
                lines.append(f"- {dep}")

        if self.requirements:
            lines.append(f"\n## Requirements")
            for req in self.requirements:
                lines.append(f"- {req}")

        complexity_note = {
            "berufsschule": "Keep it simple, clean, and well-commented. No over-engineering.",
            "gymnasium": "Clean architecture, proper error handling, some tests.",
            "uni": "Production-quality: tests, docs, CI config, proper abstractions.",
        }.get(self.max_complexity, "")
        if complexity_note:
            lines.append(f"\n## Quality Level\n{complexity_note}")

        if self.full_spec_text:
            lines.append(f"\n## Detailed Specification\n{self.full_spec_text}")

        return "\n".join(lines)


@dataclass
class ModuleSpec:
    name: str
    purpose: str
    files: list[FileSpec] = field(default_factory=list)


@dataclass
class FileSpec:
    path: str                          # e.g. "src/models/user.py"
    description: str
    key_functions: list[str] = field(default_factory=list)


# ============================================================
# Agent: Local LLM (free — uses existing pipeline backends)
# ============================================================

class LocalLLMAgent(BaseAgent):
    """Generates code file-by-file using the pipeline's LLM backends.

    Free (uses Groq/Gemini/etc.), but less capable than dedicated
    coding agents. Good enough for Berufsschule projects.
    """

    name = "local_llm"
    is_free = True
    description = "Code-Generierung über Pipeline-Backends (kostenlos)"

    def __init__(self, router):
        self.router = router

    async def estimate_cost(self, spec: ProjectSpec) -> float:
        return 0.0  # Free

    async def execute(self, spec: ProjectSpec, output_dir: Path) -> AgentResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        files_created = []
        errors = []

        # Generate each file
        for module in spec.modules:
            for file_spec in module.files:
                try:
                    content = await self._generate_file(spec, module, file_spec)
                    file_path = output_dir / file_spec.path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(content, encoding="utf-8")
                    files_created.append(str(file_path))
                except Exception as e:
                    errors.append(f"Failed to generate {file_spec.path}: {e}")

        # Generate project config files
        config_files = await self._generate_config_files(spec, output_dir)
        files_created.extend(config_files)

        # Generate README
        readme = await self._generate_readme(spec)
        readme_path = output_dir / "README.md"
        readme_path.write_text(readme, encoding="utf-8")
        files_created.append(str(readme_path))

        return AgentResult(
            success=len(errors) == 0,
            output_dir=str(output_dir),
            files_created=files_created,
            errors=errors,
            agent_name=self.name,
        )

    async def _generate_file(self, spec: ProjectSpec, module: ModuleSpec, file_spec: FileSpec) -> str:
        functions_hint = ""
        if file_spec.key_functions:
            functions_hint = f"\nMuss enthalten: {', '.join(file_spec.key_functions)}"

        prompt = (
            f"Generiere den Code für die Datei `{file_spec.path}` im Projekt '{spec.title}'.\n"
            f"Sprache: {spec.language}\n"
            f"Modul: {module.name} — {module.purpose}\n"
            f"Datei-Zweck: {file_spec.description}{functions_hint}\n\n"
            f"Kontext:\n{spec.to_prompt()}\n\n"
            f"Antworte NUR mit dem Code, keine Erklärungen, keine Markdown-Fences."
        )

        response = await self.router.complete(
            stage="agent_codegen",
            messages=[
                {"role": "system", "content": "Du bist ein Code-Generator. Antworte nur mit Code, ohne Erklärungen."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
        )

        content = response.content.strip()
        # Strip markdown fences if the model added them anyway
        if content.startswith("```"):
            lines = content.split("\n")
            lines = lines[1:]  # Remove opening fence
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)

        return content

    async def _generate_config_files(self, spec: ProjectSpec, output_dir: Path) -> list[str]:
        """Generate project config files (requirements.txt, package.json, etc.)."""
        created = []

        if spec.language == "python" and spec.dependencies:
            req_path = output_dir / "requirements.txt"
            req_path.write_text("\n".join(spec.dependencies) + "\n", encoding="utf-8")
            created.append(str(req_path))

        elif spec.language in ("javascript", "typescript") and spec.dependencies:
            pkg = {
                "name": spec.title.lower().replace(" ", "-"),
                "version": "1.0.0",
                "description": spec.description,
                "dependencies": {d.split("@")[0]: d.split("@")[1] if "@" in d else "*" for d in spec.dependencies},
            }
            pkg_path = output_dir / "package.json"
            pkg_path.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
            created.append(str(pkg_path))

        return created

    async def _generate_readme(self, spec: ProjectSpec) -> str:
        """Generate a README.md for the project."""
        lines = [
            f"# {spec.title}",
            f"\n{spec.description}",
            f"\n## Setup",
        ]
        if spec.language == "python":
            lines.append("```bash\npip install -r requirements.txt\n```")
        elif spec.language in ("javascript", "typescript"):
            lines.append("```bash\nnpm install\n```")

        if spec.entry_point:
            lines.append(f"\n## Run\n```bash\n{_run_command(spec)}\n```")

        return "\n".join(lines)


# ============================================================
# Agent: Claude Code (credits)
# ============================================================

class ClaudeCodeAgent(BaseAgent):
    """Delegates to Claude Code CLI for project generation.

    Requires: `claude` CLI installed + authenticated.
    Cost: Uses Anthropic API credits.
    """

    name = "claude_code"
    is_free = False
    description = "Claude Code CLI — vollständige Projektgenerierung (Credits)"

    def __init__(self, config: AgentConfig):
        self.config = config

    async def estimate_cost(self, spec: ProjectSpec) -> float:
        # Rough estimate: ~$0.10-0.50 per file for Sonnet
        file_count = sum(len(m.files) for m in spec.modules) + 2  # +readme +config
        return file_count * 0.15  # Conservative estimate

    async def execute(self, spec: ProjectSpec, output_dir: Path) -> AgentResult:
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write spec to temp file
        spec_file = output_dir / ".project_spec.md"
        spec_file.write_text(spec.to_prompt(), encoding="utf-8")

        # Build claude code command
        prompt = (
            f"Read the project specification in .project_spec.md and implement "
            f"the complete project in this directory. Create all files, including "
            f"tests and configuration. Language: {spec.language}."
        )

        cmd = [
            "claude", "code",
            "--message", prompt,
            "--directory", str(output_dir),
        ]

        if self.config.model:
            cmd.extend(["--model", self.config.model])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                cwd=str(output_dir),
            )

            files = [str(p) for p in output_dir.rglob("*") if p.is_file() and p.name != ".project_spec.md"]

            return AgentResult(
                success=result.returncode == 0,
                output_dir=str(output_dir),
                files_created=files,
                errors=[result.stderr] if result.returncode != 0 else [],
                agent_name=self.name,
                log=result.stdout,
            )
        except FileNotFoundError:
            return AgentResult(
                success=False,
                output_dir=str(output_dir),
                files_created=[],
                errors=["Claude Code CLI nicht gefunden. Installation: npm install -g @anthropic-ai/claude-code"],
                agent_name=self.name,
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                output_dir=str(output_dir),
                files_created=[],
                errors=["Claude Code Timeout nach 5 Minuten"],
                agent_name=self.name,
            )


# ============================================================
# Agent: OpenAI Codex CLI (credits)
# ============================================================

class CodexAgent(BaseAgent):
    """Delegates to OpenAI Codex CLI for project generation.

    Requires: `codex` CLI installed + OPENAI_API_KEY.
    Cost: Uses OpenAI API credits.
    """

    name = "codex"
    is_free = False
    description = "OpenAI Codex CLI — Projektgenerierung (Credits)"

    def __init__(self, config: AgentConfig):
        self.config = config

    async def estimate_cost(self, spec: ProjectSpec) -> float:
        file_count = sum(len(m.files) for m in spec.modules) + 2
        return file_count * 0.10

    async def execute(self, spec: ProjectSpec, output_dir: Path) -> AgentResult:
        output_dir.mkdir(parents=True, exist_ok=True)

        spec_file = output_dir / ".project_spec.md"
        spec_file.write_text(spec.to_prompt(), encoding="utf-8")

        prompt = (
            f"Implement the project specified in .project_spec.md. "
            f"Create all files including tests. Language: {spec.language}."
        )

        cmd = ["codex", "--message", prompt]

        if self.config.model:
            cmd.extend(["--model", self.config.model])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(output_dir),
            )

            files = [str(p) for p in output_dir.rglob("*") if p.is_file() and p.name != ".project_spec.md"]

            return AgentResult(
                success=result.returncode == 0,
                output_dir=str(output_dir),
                files_created=files,
                errors=[result.stderr] if result.returncode != 0 else [],
                agent_name=self.name,
                log=result.stdout,
            )
        except FileNotFoundError:
            return AgentResult(
                success=False,
                output_dir=str(output_dir),
                files_created=[],
                errors=["Codex CLI nicht gefunden. Installation: npm install -g @openai/codex"],
                agent_name=self.name,
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                output_dir=str(output_dir),
                files_created=[],
                errors=["Codex Timeout nach 5 Minuten"],
                agent_name=self.name,
            )


# ============================================================
# Agent Registry
# ============================================================

AGENT_REGISTRY: dict[str, type] = {
    "local_llm": LocalLLMAgent,
    "claude_code": ClaudeCodeAgent,
    "codex": CodexAgent,
}


def get_available_agents(agent_configs: dict[str, AgentConfig], router=None) -> dict[str, BaseAgent]:
    """Instantiate available agents from config."""
    agents = {}

    for name, config in agent_configs.items():
        if not config.is_available:
            continue

        if name == "local_llm" and router:
            agents[name] = LocalLLMAgent(router)
        elif name in ("claude_code", "codex"):
            cls = AGENT_REGISTRY.get(name)
            if cls:
                agents[name] = cls(config)

    # local_llm is always available if router exists
    if "local_llm" not in agents and router:
        agents["local_llm"] = LocalLLMAgent(router)

    return agents


# ============================================================
# Spec Builder — converts synthesis output to ProjectSpec
# ============================================================

def build_project_spec(synthesis: dict[str, Any], intake: dict[str, Any]) -> ProjectSpec:
    """Convert pipeline synthesis output into a ProjectSpec for agents.

    This bridges the pipeline's structured output with the agent's input format.
    """
    # Extract language/framework from synthesis or intake
    task_text = intake.get("task_text", "").lower()

    language = _detect_language(task_text)
    framework = _detect_framework(task_text, language)
    project_type = _detect_project_type(task_text)

    # Build modules from synthesis sections
    modules = []
    for section in synthesis.get("sections", []):
        if section.get("heading", "").lower() in ("quellen", "sources", "titel"):
            continue

        files = []
        # The synthesis content describes what each module should do
        # We infer file structure from the section
        content = section.get("content", "")
        bullets = section.get("bullet_points", [])

        # Create a file spec for this module
        module_name = _slugify(section.get("heading", "module"))
        files.append(FileSpec(
            path=_infer_file_path(module_name, language),
            description=content or section.get("heading", ""),
            key_functions=[b for b in bullets if len(b) < 60],  # Short bullets → function hints
        ))

        modules.append(ModuleSpec(
            name=section.get("heading", ""),
            purpose=section.get("content", section.get("heading", "")),
            files=files,
        ))

    # Build full spec text from synthesis
    full_text = "\n\n".join(
        f"## {s.get('heading', '')}\n{s.get('content', '')}"
        for s in synthesis.get("sections", [])
    )

    requirements = intake.get("constraints", {}).get("specific_requirements", [])

    return ProjectSpec(
        title=synthesis.get("title", "Projekt"),
        description=full_text[:500],
        language=language,
        framework=framework,
        project_type=project_type,
        modules=modules,
        entry_point=_infer_entry_point(language, project_type),
        dependencies=_infer_dependencies(framework, language),
        requirements=requirements,
        max_complexity=_infer_complexity(intake),
        full_spec_text=full_text,
    )


# ============================================================
# Helpers
# ============================================================

def _detect_language(text: str) -> str:
    """Detect programming language from task text."""
    indicators = {
        "python": ["python", "django", "flask", "fastapi", "pip"],
        "javascript": ["javascript", "node", "react", "express", "npm"],
        "typescript": ["typescript", "angular", "nest", "tsx"],
        "java": ["java", "spring", "maven", "gradle"],
        "csharp": ["c#", "csharp", ".net", "asp.net", "blazor"],
        "php": ["php", "laravel", "symfony"],
        "go": ["golang", " go ", "gin"],
        "rust": ["rust", "cargo"],
    }
    for lang, keywords in indicators.items():
        if any(kw in text for kw in keywords):
            return lang
    return "python"  # Default for FIAE


def _detect_framework(text: str, language: str) -> str:
    frameworks = {
        "python": {"flask": "flask", "django": "django", "fastapi": "fastapi"},
        "javascript": {"react": "react", "express": "express", "vue": "vue", "next": "nextjs"},
        "typescript": {"angular": "angular", "nest": "nestjs", "next": "nextjs"},
        "java": {"spring": "spring-boot"},
    }
    for keyword, framework in frameworks.get(language, {}).items():
        if keyword in text:
            return framework
    return ""


def _detect_project_type(text: str) -> str:
    if any(w in text for w in ["webapp", "web-app", "website", "webseite"]):
        return "web"
    if any(w in text for w in ["api", "rest", "endpoint", "schnittstelle"]):
        return "api"
    if any(w in text for w in ["cli", "kommandozeile", "command"]):
        return "cli"
    if any(w in text for w in ["bibliothek", "library", "modul", "paket"]):
        return "library"
    return "cli"


def _slugify(text: str) -> str:
    replacements = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    for old, new in replacements.items():
        text = text.lower().replace(old, new)
    return "".join(c if c.isalnum() else "_" for c in text).strip("_")[:30]


def _infer_file_path(module_name: str, language: str) -> str:
    ext = {"python": ".py", "javascript": ".js", "typescript": ".ts",
           "java": ".java", "csharp": ".cs", "php": ".php", "go": ".go", "rust": ".rs"}
    return f"src/{module_name}{ext.get(language, '.py')}"


def _infer_entry_point(language: str, project_type: str) -> str:
    entries = {"python": "main.py", "javascript": "src/index.js",
               "typescript": "src/index.ts", "java": "src/Main.java"}
    return entries.get(language, "main.py")


def _infer_dependencies(framework: str, language: str) -> list[str]:
    deps = {
        "flask": ["flask"],
        "django": ["django"],
        "fastapi": ["fastapi", "uvicorn"],
        "react": ["react", "react-dom"],
        "express": ["express"],
        "spring-boot": ["spring-boot-starter-web"],
    }
    return deps.get(framework, [])


def _infer_complexity(intake: dict[str, Any]) -> str:
    # Could be derived from preset difficulty, for now default
    return "berufsschule"


def _run_command(spec: ProjectSpec) -> str:
    cmds = {"python": f"python {spec.entry_point}",
            "javascript": f"node {spec.entry_point}",
            "typescript": f"npx ts-node {spec.entry_point}",
            "java": f"java {spec.entry_point}"}
    return cmds.get(spec.language, f"python {spec.entry_point}")
