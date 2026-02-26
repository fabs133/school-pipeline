# Changelog

## v1.0.0 (2026-02-26)

### Features
- 5-stage pipeline: intake → plan → research → synthesize → artifact
- Multi-backend routing: Groq, Gemini, Mistral, OpenAI, Ollama
- PPTX, DOCX, MD output formats
- 6 style themes: clean, modern, minimal, school, corporate, dark
- Visual placeholder system for slides
- Document scanner with heuristic classification (`schulpipeline scan`)
- Session persistence and resume
- Preset system (subject × output type)
- Cost estimation ($0.00 with free tiers)
- Progress display with stage-level timing

### Technical
- JSON Schema validation between all stages
- Rate-limit-aware cascade routing with exponential backoff
- 215+ tests (offline mocks + optional live API tests)
- GitHub Actions CI with pre-commit hooks (ruff)
- Synthetic example data for testing and onboarding
