# schulpipeline

Spec-driven pipeline that transforms school assignments into submission-ready artifacts.

**Input:** Assignment text or photo → **Output:** PPTX / DOCX / MD

Built on Manifold's spec-validation model. Every stage validates its output before
advancing — the pipeline produces correct results or tells you why it can't.

## 30-Second Setup

```bash
# 1. Clone
git clone <repo-url> && cd schulpipeline

# 2. Install
pip install -e .

# 3. Get free API keys (2 minutes)
#    Groq:   https://console.groq.com → API Keys
#    Gemini: https://aistudio.google.com/apikey
#    Step-by-step guides: docs/guides/

# 4. Set keys (or use a .env file — see .env.example)
export GROQ_API_KEY="gsk_..."
export GEMINI_API_KEY="AI..."

# 5. Run
schulpipeline run "Erstellen Sie eine Präsentation zum Thema IT-Sicherheit (10 Folien)"
```

**Cost: $0.00** — Groq and Gemini free tiers handle everything.

## Usage

```bash
# From text
schulpipeline run "Aufgabenstellung hier..."

# From image (photo of assignment)
schulpipeline run --input aufgabe.jpg

# Force output format
schulpipeline run --input aufgabe.txt --format docx

# Use a preset (subject × output type)
schulpipeline run --preset fiae-praesi-itsec "IT-Sicherheit im Unternehmen"
schulpipeline run --output-type praesentation --subject netzwerktechnik "OSI-Modell"

# Apply a style theme
schulpipeline run --style modern "Aufgabenstellung..."
schulpipeline run --style dark --no-visuals "Aufgabenstellung..."

# Dry run — see the plan
schulpipeline plan "Aufgabenstellung..."

# Cost estimate
schulpipeline cost-estimate "Aufgabenstellung..."

# Check which backends are available
schulpipeline backends

# System diagnostics
schulpipeline doctor

# Debug mode
schulpipeline run --input aufgabe.txt --log-level DEBUG
```

## Document Scanner

Classify a directory of school documents — finds tasks, info material, OneNote exports, duplicates, and empty files:

```bash
# Scan and print summary
schulpipeline scan examples/tasks/

# JSON output
schulpipeline scan examples/tasks/ --json

# Write manifest to file
schulpipeline scan examples/tasks/ -o manifest.yaml

# Verbose (per-file signals)
schulpipeline scan examples/tasks/ --verbose
```

## Presets & Styles

**Presets** combine subject and output type for quick configuration:

```bash
# List all available presets
schulpipeline presets

# Use a quick preset
schulpipeline run --preset fiae-praesi-itsec "Thema..."

# Or combine subject + output type
schulpipeline run --subject it_sicherheit --output-type praesentation "Thema..."
```

**Styles** control the visual appearance of generated artifacts:

| Style | Description |
|-------|-------------|
| `clean` | Default. Neutral colors, clear layout |
| `modern` | Bold accent colors, contemporary feel |
| `minimal` | Reduced elements, lots of whitespace |
| `school` | Traditional, formal school presentation |
| `corporate` | Professional business style |
| `dark` | Dark background, light text |

```bash
schulpipeline run --style dark "Aufgabenstellung..."
schulpipeline run --style modern --no-visuals "Aufgabenstellung..."
```

## Session Management

Every pipeline run creates a session. You can list, inspect, and resume sessions:

```bash
# List recent sessions
schulpipeline sessions

# Show session details
schulpipeline show <session-id>

# Resume a failed session
schulpipeline resume
schulpipeline resume <session-id>
schulpipeline resume <session-id> --from-stage research

# Delete a session
schulpipeline delete <session-id>
```

## Example Data

The `examples/` directory contains **synthetic** school documents for testing — no real student data or copyrighted content. Try it immediately after install:

```bash
schulpipeline scan examples/tasks/
schulpipeline run --yes --input examples/tasks/DE-BSP/IT_B1_A1_Energie.docx
schulpipeline run --yes --input examples/tasks/WI-BSP/Aufgaben_Angebot_Nachfrage.docx --style dark
```

See [examples/README.md](examples/README.md) for details.

## How It Works

```
Text/Image → INTAKE → PLAN → RESEARCH → SYNTHESIZE → ARTIFACT → .pptx/.docx/.md
               │        │        │           │            │
               ▼        ▼        ▼           ▼            ▼
            Parse    Decompose  Find      Merge into   Generate
            task     into       facts     structured   final
            reqs     sections   per       content      file
                               section
```

Each stage has a JSON Schema spec. Outputs are validated between stages.
If validation fails, you get a diagnostic — not garbage.

## Configuration

Copy `config.yaml` and edit. Or just set env vars — backends are auto-discovered.

**Minimal (env vars only):**
```bash
export GROQ_API_KEY="..."
export GEMINI_API_KEY="..."
schulpipeline run "..."
```

You can also use a `.env` file (see `.env.example`).

**Custom config:**
```yaml
backends:
  groq:
    api_key: ${GROQ_API_KEY}
    model: "llama-3.1-70b-versatile"
  gemini:
    api_key: ${GEMINI_API_KEY}
    model: "gemini-2.0-flash"

cascade:
  intake:     [gemini]
  plan:       [groq, gemini]
  research:   [groq, gemini]
  synthesize: [groq, gemini]
  artifact:   [groq, gemini]

output:
  dir: "./output"
  default_format: "pptx"
  language: "de"
```

**Adding more backends** (all optional):
```yaml
backends:
  mistral:
    api_key: ${MISTRAL_API_KEY}       # https://console.mistral.ai
    model: "mistral-large-latest"
  openai:
    api_key: ${OPENAI_API_KEY}        # paid, only as fallback
    model: "gpt-4o-mini"
  ollama:                              # local, needs Ollama running
    base_url: "http://localhost:11434"
    model: "mistral:7b"
```

## Backend Cascade

The router tries backends left-to-right per stage. If one hits a rate limit,
it cascades to the next. Cost is always minimized: free first, paid only as fallback.

| Stage | Default | Why |
|-------|---------|-----|
| Intake | gemini | Vision support for image inputs |
| Plan | groq → gemini | Light task, any model works |
| Research | groq → gemini | Many small parallel calls |
| Synthesize | groq → gemini | Needs longer context |
| Artifact | groq → gemini | Structured output generation |

## Tests

```bash
# With pytest (recommended)
pip install -e ".[dev]"
pytest tests/ -v

# Without dev dependencies (standalone)
python tests/run_tests.py
```

## Project Structure

```
schulpipeline/
├── cli.py                  # Entry point (run, scan, sessions, doctor, ...)
├── config.py               # Config loading (YAML + env + CLI)
├── pipeline.py             # 5-stage orchestrator
├── scanner.py              # Document classifier (heuristic scoring)
├── styles.py               # 6 style presets + visual slot system
├── presets.py              # Subject × output type presets
├── session.py              # Session persistence + runner
├── stages/
│   ├── intake.py           # Parse input, extract requirements
│   ├── plan.py             # Decompose into sections
│   ├── research.py         # Gather facts (LLM + web)
│   ├── synthesize.py       # Merge into content
│   └── artifact.py         # Generate PPTX/DOCX/MD
├── backends/
│   ├── router.py           # Cascade routing + rate limits
│   ├── openai_compat.py    # Groq, Mistral, OpenAI adapter
│   └── gemini.py           # Google Gemini adapter
├── artifacts/
│   ├── pptx_builder.py     # Presentation generation
│   ├── docx_builder.py     # Document generation
│   └── md_builder.py       # Markdown generation
└── specs/                  # JSON Schema per stage
```

## Requirements

- Python 3.11+
- requests, pyyaml, python-pptx, python-docx, beautifulsoup4, Pillow, python-dotenv
- At least one API key (Groq or Gemini, both free):
  - [Groq API-Key Anleitung](docs/guides/Groq_API-Key_erstellen_-_Schritt-fuer-Schritt-Anleitung.docx)
  - [Gemini API-Key Anleitung](docs/guides/Gemini_API-Key_erstellen_-_Schritt-fuer-Schritt-Anleitung.docx)

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, coding conventions, and PR workflow.

## Getting Help

- **Bug?** [Open a bug report](https://github.com/fabs133/school-pipeline/issues/new?template=bug_report.yml)
- **Idea?** [Request a feature](https://github.com/fabs133/school-pipeline/issues/new?template=feature_request.yml)
- **Security?** See [SECURITY.md](SECURITY.md)

## License

MIT — see [LICENSE](LICENSE)
