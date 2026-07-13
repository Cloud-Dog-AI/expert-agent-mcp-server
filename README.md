---
template-id: T-RME
template-version: 1.0
applies-to: README.md
registry: service
required: must-have
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: platform-standards

project: expert-agent-mcp-server
doc-last-updated: 2026-06-18
doc-git-commit: 087c06c37341867986a35a0664c07933a8c53c69
doc-git-branch: main
doc-source-shas: []
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-18T00:00:00Z
---

# Expert Agent MCP Server

`expert-agent-mcp-server` exposes REST, Web UI, MCP, and A2A surfaces for expert routing, knowledge retrieval, and auditable session orchestration.

## Publication Quick Start

Prerequisites:

- Docker 24 or newer with BuildKit enabled
- Python 3.12 if you run the package locally
- A public package index that hosts the Cloud-Dog platform packages (default: `https://pypi.org/simple/`)

Build an isolated publication-test image (public variant):

```bash
PUBLICATION_TAG_SUFFIX=github-test ./docker-build.sh --variant public latest
```

Run the local smoke by executing the shell block in [PUBLICATION-SMOKE.md](PUBLICATION-SMOKE.md) with `TAG=latest-github-test`.

The smoke run uses [env.example](env.example) and probes:

- API: `8083`
- Web: `8080`
- MCP: `8081`
- A2A: `8082`

## Local Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e ".[dev]" --index-url https://pypi.org/simple/
```

If the Cloud-Dog platform packages live on a different public index, point pip at
it with a single `--index-url <your-public-index>` (never an `--extra-index-url`).

Runtime configuration is loaded from the env file passed to `server_control.sh`, then from shell environment variables, then from `defaults.yaml`.

## Documentation

- [EXTERNAL-BUILD.md](EXTERNAL-BUILD.md) — self-contained external-builder guide
- [BUILD.md](BUILD.md)
- [PUBLICATION-SMOKE.md](PUBLICATION-SMOKE.md)
- [env.example](env.example)
- [docker-env.public.example](docker-env.public.example)

## Licence

Apache-2.0 - Copyright (c) 2026 Cloud-Dog, Viewdeck Engineering Limited

## Security & Publication Notes

Authentication and authorisation use the platform IDAM credential/cert model; do not commit secrets.
This public source mirror excludes internal operations material; build artefacts (e.g. the UI bundle) are regenerated at build time.
