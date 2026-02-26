# Security Policy

## Scope

schulpipeline is a school assignment automation tool. It handles:

- **API keys** for LLM backends (Groq, Gemini, Mistral, OpenAI) via `.env` files
- **School documents** (DOCX input, PPTX/DOCX/MD output)
- **No user accounts, no authentication, no network services**

## Reporting a Vulnerability

If you discover a security issue (e.g., API key exposure, path traversal, command injection), please **do not open a public issue**.

Instead, report it privately:

1. **GitHub**: Use [private vulnerability reporting](https://github.com/fabs133/school-pipeline/security/advisories/new)
2. **Email**: Contact the maintainer directly via their GitHub profile

You should receive a response within 7 days.

## What We Protect

- **API keys**: Stored in `.env` (gitignored), never logged or committed
- **Student data**: `Data_School_Tasks/` is permanently gitignored — original school documents must never enter version control
- **Output files**: Generated in `output/` (gitignored)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| < 1.0   | No        |
