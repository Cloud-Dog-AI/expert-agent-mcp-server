#!/usr/bin/env bash
# Stage the Expert Agent SPA for the service Docker image.
#
# Publication exports are self-contained: they include ui/dist and do not have
# access to the sibling UI monorepo. Developer checkouts may still rebuild from
# a local UI package or the monorepo when those sources are present.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOCAL_UI_DIR="${REPO_DIR}/ui"
LOCAL_PACKAGE="${LOCAL_UI_DIR}/package.json"
LOCAL_DIST="${LOCAL_UI_DIR}/dist"
UI_MONOREPO="${EXPERT_AGENT_UI_MONOREPO:-${REPO_DIR}/../cloud-dog-ai-ui-monorepo}"
APP_DIR="${UI_MONOREPO}/apps/expert-agent"
APP_DIST="${APP_DIR}/dist"
TARGET_DIST="${REPO_DIR}/ui/dist"

install_npm_deps() {
    local dir="$1"
    if [ -f "${dir}/package-lock.json" ]; then
        npm ci --prefix "${dir}"
    else
        npm install --prefix "${dir}"
    fi
}

if [ -f "${LOCAL_PACKAGE}" ]; then
    echo "Building Expert Agent UI from local package ${LOCAL_UI_DIR}"
    install_npm_deps "${LOCAL_UI_DIR}"
    npm run build --prefix "${LOCAL_UI_DIR}"

    if [ ! -f "${LOCAL_DIST}/index.html" ]; then
        echo "Expected built UI bundle missing at ${LOCAL_DIST}" >&2
        exit 1
    fi
    echo "Expert Agent UI staged in ${LOCAL_DIST}"
    exit 0
fi

if [ -f "${LOCAL_DIST}/index.html" ]; then
    echo "Using bundled Expert Agent UI dist at ${LOCAL_DIST}"
    exit 0
fi

if [ ! -f "${UI_MONOREPO}/package.json" ] || [ ! -f "${APP_DIR}/package.json" ]; then
    echo "Expert Agent UI bundle missing at ${LOCAL_DIST}" >&2
    echo "No local UI package found at ${LOCAL_UI_DIR} and monorepo not found at ${UI_MONOREPO}." >&2
    echo "Ship ui/dist in the publication export or set EXPERT_AGENT_UI_MONOREPO." >&2
    exit 1
fi

echo "Building Expert Agent UI from ${UI_MONOREPO}"
install_npm_deps "${UI_MONOREPO}"
npm run build --workspace @cloud-dog/app-expert-agent --prefix "${UI_MONOREPO}"

if [ ! -f "${APP_DIST}/index.html" ]; then
    echo "Expected built UI bundle missing at ${APP_DIST}" >&2
    exit 1
fi

mkdir -p "${TARGET_DIST}"
find "${TARGET_DIST}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -a "${APP_DIST}/." "${TARGET_DIST}/"

echo "Expert Agent UI staged in ${TARGET_DIST}"
