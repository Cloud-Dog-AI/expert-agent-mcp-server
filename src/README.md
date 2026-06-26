# Source Code Folder

## Purpose

This folder contains all source code for the Expert Agent MCP Server.

## Structure

```
src/
  servers/        # Server implementations (API, MCP, A2A, Web UI)
  core/           # Core functionality (sessions, history, prompts, rbac, users, groups)
  llm/            # LLM integration (orchestrator, providers, safety)
  vector/         # Vector database integration (stores, indexing, lifecycle, access)
  database/       # Database layer
  adapters/       # Adapter implementations
  config/         # Configuration management
  security/       # Security components
  utils/          # Utility functions
```

## Code Header Requirements

All source code files must include a header docstring with:
- License: Apache 2.0
- Ownership: Cloud Dog
- Description: What the code does
- Related Requirements: SV1.1, BR1.1, FR1.1, UC1.1
- Related Tasks: T1, T5, T12
- Related Architecture: OV1.1, SA1.2, CC2.1
- Related Tests: UT1.1, IT2.3, AT5.1
- Recent Changes (max 10): Commit hash and description

## Related Documentation

- [RULES.md](../RULES.md) - Project rules and code header format
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) - System architecture
- [docs/REQUIREMENTS.md](../docs/REQUIREMENTS.md) - Requirements

## Notes

- All functions, methods, classes should have documentation
- Code should follow project coding standards
- Tests for code should be in `tests/` folder

