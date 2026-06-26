---
template-id: T-EXT
template-version: 1.0
applies-to: EXTERNAL-BUILD.md
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

# EXTERNAL-BUILD.md — expert-agent-mcp-server

A self-contained guide for an **external builder** to build, run, and smoke-test
`expert-agent-mcp-server` from a public clone, with **no access to any internal
Cloud-Dog infrastructure** (no Vault, no internal PyPI, no internal registry, no
preprod hosts). Everything you need is in this repository.

This service exposes four surfaces from a single container:

| Surface | Default port | Path probe |
|---------|--------------|------------|
| Web UI  | 8080         | `/`               |
| MCP     | 8081         | `/mcp/health`     |
| A2A     | 8082         | `/health`, `/.well-known/agent.json` |
| API     | 8083         | `/health`         |

Ports come from `defaults.yaml` and can be overridden through the env file
(`CLOUD_DOG__EXPERT__*_SERVER__PORT`). The env-var prefix for every setting is
`CLOUD_DOG__EXPERT__`.

---

## 0. Prerequisites

| Path | Requirements |
|------|-------------|
| Docker build | Docker 24+ with BuildKit enabled. Works on Linux, macOS (Docker Desktop), and Windows (Docker Desktop / WSL2). |
| Pure-source build | Python 3.12+, `pip`, a POSIX shell (`bash`). On Windows use WSL2 or Git Bash. |

You also need an active **public package index** that hosts the Cloud-Dog
platform packages (`cloud-dog-config`, `cloud-dog-logging`, `cloud-dog-api-kit`,
`cloud-dog-idam`, `cloud-dog-llm`, `cloud-dog-db`, `cloud-dog-jobs`,
`cloud-dog-vdb`, `cloud-dog-cache`, `cloud-dog-storage`) plus their transitive
dependencies. By default the build uses `https://pypi.org/simple/`. If the
platform packages are not yet on that index, point the build at the index that
does host them with the `PIP_INDEX_URL` variable (single index only — never an
`--extra-index-url`).

---

## 1. Get the source

```bash
git clone <public-repo-url> expert-agent-mcp-server
cd expert-agent-mcp-server
# Confirm there is exactly one (public) remote and no internal remotes:
git remote -v
```

The clone is self-contained: the web UI is shipped pre-built under `ui/dist/`,
so no sibling UI monorepo is required.

---

## 2. Path A — Docker build (recommended)

The public Docker image is built from `Dockerfile.public` via the variant flag.

```bash
# Default: public PyPI as the single package index.
./docker-build.sh --variant public latest

# Or point at the index that hosts the Cloud-Dog platform packages:
PIP_INDEX_URL=https://your-public-index.example.com/simple/ \
  ./docker-build.sh --variant public latest

# Isolated publication-test tag (skips any registry retag):
PUBLICATION_TAG_SUFFIX=github-test ./docker-build.sh --variant public latest
```

`Dockerfile.public`:

- uses `python:3.12-slim` and the stock public CA trust store (no private CA);
- installs dependencies from the single `PIP_INDEX_URL` (default `pypi.org`);
- contains **no** internal hostnames and **no** `--extra-index-url`;
- exposes ports 8080–8083 and runs as a non-root user.

### Run + smoke

Copy the example env file, then run the published image and probe the surfaces.
Full instructions are in [PUBLICATION-SMOKE.md](PUBLICATION-SMOKE.md):

```bash
cp docker-env.public.example .env
# edit .env to set <your-...-here> placeholders
TAG=latest bash -c "$(sed -n '/```bash/,/```/p' PUBLICATION-SMOKE.md | sed '1d;$d')"
```

A passing smoke prints `RESULT: PASS`. Auth-gated `401/403` and redirects are
acceptable — they prove the surface is up and routing.

---

## 3. Path B — Pure-source / package build (no Docker)

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel

# Install the package + deps from a single public index:
.venv/bin/python -m pip install -e . \
  --index-url https://pypi.org/simple/
# (override the index with --index-url <your-public-index> if the platform
#  packages live elsewhere; never add --extra-index-url)

# Build a distributable wheel + sdist:
.venv/bin/python -m pip install build
.venv/bin/python -m build      # artefacts land in dist/
```

### Run locally

```bash
cp docker-env.public.example .env.local
./server_control.sh --env ./.env.local start all
./server_control.sh --env ./.env.local status all
./server_control.sh --env ./.env.local stop all
```

Configuration precedence: **OS environment → env file → `defaults.yaml`**.

---

## 4. Where evidence goes

Place all build evidence under `build-evidence/` at the repo root:

```
build-evidence/
  docker-build.log        # full output of ./docker-build.sh --variant public
  image-digest.txt        # docker inspect --format '{{.Id}}' <image>
  smoke.log               # output of the PUBLICATION-SMOKE.md block
  pip-install.log         # pure-source install log (Path B)
  build.log               # python -m build log (Path B)
  git-remote.txt          # output of git remote -v (must show only the public remote)
  env.txt                 # docker --version / python --version / uname -a
```

Capture the image digest before any cleanup:

```bash
docker inspect --format '{{.Id}}' expert-agent-mcp-server:latest > build-evidence/image-digest.txt
```

---

## 5. Return a tarball + checksum

Bundle the evidence and the produced artefacts, then checksum the tarball:

```bash
tar czf expert-agent-external-build-$(date -u +%Y%m%dT%H%M%SZ).tgz \
  build-evidence/ dist/
sha256sum expert-agent-external-build-*.tgz > expert-agent-external-build.sha256
```

Return both the `.tgz` and the `.sha256` to the coordinator. The coordinator
verifies with:

```bash
sha256sum -c expert-agent-external-build.sha256
```

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `Could not find a version that satisfies the requirement cloud-dog-config` | The Cloud-Dog platform packages are not on the active index. Point `PIP_INDEX_URL` / `--index-url` at the public index that hosts them. Do **not** add `--extra-index-url`. |
| `certificate signer not trusted` to an external host | A transparent proxy is re-signing TLS. Add your environment's CA to the container's trust store at runtime via `EXPERT_CA_BUNDLE=/app/certs/ca-bundle.crt`. |
| `ui/dist/index.html` missing during Docker build | The publication export must include `ui/dist/`. Re-export from a complete public clone. |
| Smoke probe `FAIL ... -> 000` | The container is still starting (LLM/VDB init). Increase `SMOKE_ATTEMPTS` and re-check `docker logs`. |
