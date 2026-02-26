# Contributing to schulpipeline

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/school-pipeline.git
cd school-pipeline

# 2. Install with dev dependencies
pip install -e ".[dev]"

# 3. Set up API keys (at least one pair)
cp .env.example .env
# Edit .env with your Groq and/or Gemini keys

# 4. Verify everything works
schulpipeline doctor
pytest tests/ --ignore=tests/live -q
```

## Running Tests

```bash
# Full offline test suite (230+ tests, ~2s)
pytest tests/ --ignore=tests/live -v

# Single test file
pytest tests/test_scanner.py -v

# Live API tests (requires real keys, not run in CI)
pytest tests/live/ -v
```

## Linting

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check for issues
ruff check schulpipeline/ tests/

# Auto-fix what's possible
ruff check schulpipeline/ tests/ --fix
```

Rules: E (errors), F (pyflakes), W (warnings), I (imports). Line length: 120.

## Making Changes

1. **Create a branch** from `master`:
   ```bash
   git checkout -b feat/your-feature
   ```

2. **Make your changes**. Keep commits focused and atomic.

3. **Run tests and lint** before committing:
   ```bash
   pytest tests/ --ignore=tests/live -q
   ruff check schulpipeline/ tests/
   ```

4. **Commit** with a descriptive message:
   ```
   feat: add support for PDF input files
   fix: scanner misclassifies empty tables as tasks
   docs: add troubleshooting section to README
   chore: update ruff to v0.5
   ```

5. **Open a Pull Request** against `master`.

## Commit Message Conventions

| Prefix | Use for |
|--------|---------|
| `feat:` | New features |
| `fix:` | Bug fixes |
| `docs:` | Documentation only |
| `chore:` | Dependencies, CI, tooling |
| `refactor:` | Code restructuring (no behavior change) |
| `test:` | Adding or updating tests |

## Project Structure

See the [README](README.md#project-structure) for a full overview. Key areas:

- `schulpipeline/stages/` — The 5 pipeline stages
- `schulpipeline/backends/` — LLM backend adapters
- `schulpipeline/artifacts/` — Output file generators (PPTX, DOCX, MD)
- `schulpipeline/scanner.py` — Document classifier
- `tests/` — Offline test suite (mocked backends)
- `examples/` — Synthetic test data

## Reporting Issues

- **Bugs**: Use the [bug report template](https://github.com/fabs133/school-pipeline/issues/new?template=bug_report.yml)
- **Features**: Use the [feature request template](https://github.com/fabs133/school-pipeline/issues/new?template=feature_request.yml)
- **Security**: See [SECURITY.md](SECURITY.md)

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Please be respectful and constructive.
