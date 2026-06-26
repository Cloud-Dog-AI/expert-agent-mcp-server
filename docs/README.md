# Documentation Folder

## Purpose

This folder contains all project documentation. Documents here must be **production/deployment ready** - NOT development documentation or interim documents.

## Key Documents

### Core Documentation
- **REQUIREMENTS.md** - Functional and non-functional requirements
- **ARCHITECTURE.md** - System architecture and design
- **PARAMETERS.md** - Configuration parameters and environment variables
- **TASKS.md** - Development tasks with numbering and test mappings
- **TESTS.md** - Comprehensive test plan with numbering by test type

### Server Documentation
- **API_SERVER.md** - API Server specification
- **MCP_SERVER.md** - MCP Server specification
- **A2A_SERVER.md** - A2A Server specification
- **WEB_UI.md** - Web UI Server specification
- **API_DOCUMENTATION.md** - Complete API endpoint documentation

### Operations Documentation
- **DOCKER.md** - Docker build, deployment, configuration guide
- **AGENT_RULES.md** - Agent-specific rules

### Other Documentation
- **SUMMARY.md** - Project summary
- **FOLDER_STRUCTURE.md** - Folder structure documentation

## Rules

Per RULES.md:
- Documents here must remain **production/deployment ready**
- Documents not listed as expected should be:
  - Consolidated into other documents if they add context, OR
  - Moved to `archive/` folder for managing out
- Do NOT expand this folder with interim/working documents

## Related Documentation

- [RULES.md](../RULES.md) - Project rules and folder structure
- [README.md](../README.md) - Project overview

## Notes

- All documentation should be maintained at each release/commit/deploy
- Documents should cross-reference Requirements, Tasks, Architecture, and Tests

