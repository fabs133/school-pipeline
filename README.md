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

# 4. Set keys
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

# Dry run — see the plan
schulpipeline plan "Aufgabenstellung..."

# Check which backends are available
schulpipeline backends

# Debug mode
schulpipeline run --input aufgabe.txt --log-level DEBUG
```

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
# Without dependencies (standalone)
python3 tests/run_tests.py

# With pytest
pip install pytest pytest-asyncio
pytest tests/ -v
```

## Project Structure

```
schulpipeline/
├── cli.py                  # Entry point
├── config.py               # Config loading (YAML + env + CLI)
├── pipeline.py             # Orchestrator
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
- requests, pyyaml, python-pptx, python-docx, beautifulsoup4
- At least one API key (Groq or Gemini, both free)

## License

MIT
