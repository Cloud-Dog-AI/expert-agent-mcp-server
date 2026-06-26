#!/bin/bash
# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# docker-build.sh - Build Docker images for Expert Agent MCP Server
# Supports self-signed certificate generation for development environments

set -e

require_main_or_release_branch() {
    local branch
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    case "${branch}" in
        main|release/*)
            return 0
            ;;
    esac

    echo "ERROR: docker-build.sh refuses to build/push from non-main branch. Got '${branch:-unknown}'; checkout main or release/*." >&2
    exit 1
}

require_main_or_release_branch

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
IMAGE_NAME="expert-agent-mcp-server"
IMAGE_TAG="latest"
# Variant selector (PS-97 v1.1 §1.1.3):
#   --variant public  builds Dockerfile.public for external / GitHub-boundary publication
#   --variant dev     builds the internal ./Dockerfile (default — internal registry / CI)
VARIANT="${PUBLICATION_BUILD_VARIANT:-dev}"
DOCKERFILE=""
CONTEXT="."
DOCKER_BUILD_NETWORK="${DOCKER_BUILD_NETWORK:-host}"
SSL_ENABLED=false
SSL_KEY_PATH="./certs/server.key"
SSL_CERT_PATH="./certs/server.crt"
SSL_CA_PATH="./certs/ca.crt"
CUSTOM_CA_CERT=""
PUSH_IMAGE=false
REGISTRY=""
PIP_CONF=".pip.conf.build"
CERT_COUNTRY="US"
CERT_STATE="California"
CERT_CITY="San Francisco"
CERT_ORG="CloudDog"
CERT_CN="localhost"
CERT_DAYS=365

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Build Docker images for Expert Agent MCP Server"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -n, --name NAME         Docker image name (default: expert-agent-mcp-server)"
    echo "  -t, --tag TAG           Docker image tag (default: latest)"
    echo "  -f, --file DOCKERFILE   Path to Dockerfile (default: per --variant)"
    echo "  --variant dev|public    Select Dockerfile.dev (internal, default) or Dockerfile.public (external/GitHub boundary)"
    echo "  -c, --context PATH      Build context path (default: .)"
    echo "  --network NET           Docker build network (default: host; override via DOCKER_BUILD_NETWORK)"
    echo "  --ssl                   Enable SSL certificate generation"
    echo "  --ssl-key PATH          SSL key path (default: ./certs/server.key)"
    echo "  --ssl-cert PATH         SSL certificate path (default: ./certs/server.crt)"
    echo "  --ssl-ca PATH           SSL CA certificate path (default: ./certs/ca.crt)"
    echo "  --custom-ca PATH        Custom CA cert path in build context (copied into trust store)"
    echo "  --registry REGISTRY     Registry prefix for tagging (e.g., ghcr.io/acme)"
    echo "  --push                  Push built image to registry after successful build"
    echo "  --cert-cn CN            Certificate Common Name (default: localhost)"
    echo "  --cert-days DAYS        Certificate validity in days (default: 365)"
    echo "  PUBLICATION_TAG_SUFFIX  Optional env suffix for isolated publication test tags"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Build with default settings"
    echo "  $0 --name my-expert-agent --tag v1.0  # Build with custom name and tag"
    echo "  $0 --ssl                              # Build with self-signed SSL certificates"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -n|--name)
            IMAGE_NAME="$2"
            shift 2
            ;;
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -f|--file)
            DOCKERFILE="$2"
            shift 2
            ;;
        --variant)
            VARIANT="${2:-dev}"
            shift 2
            ;;
        --variant=*)
            VARIANT="${1#*=}"
            shift
            ;;
        -c|--context)
            CONTEXT="$2"
            shift 2
            ;;
        --network)
            DOCKER_BUILD_NETWORK="$2"
            shift 2
            ;;
        --ssl)
            SSL_ENABLED=true
            shift
            ;;
        --ssl-key)
            SSL_KEY_PATH="$2"
            shift 2
            ;;
        --ssl-cert)
            SSL_CERT_PATH="$2"
            shift 2
            ;;
        --ssl-ca)
            SSL_CA_PATH="$2"
            shift 2
            ;;
        --custom-ca)
            CUSTOM_CA_CERT="$2"
            shift 2
            ;;
        --registry)
            REGISTRY="$2"
            shift 2
            ;;
        --push)
            PUSH_IMAGE=true
            shift
            ;;
        --cert-cn)
            CERT_CN="$2"
            shift 2
            ;;
        --cert-days)
            CERT_DAYS="$2"
            shift 2
            ;;
        *)
            if [[ "$1" != -* ]]; then
                IMAGE_TAG="$1"
                shift
            else
                echo -e "${RED}Unknown option: $1${NC}"
                usage
                exit 1
            fi
            ;;
    esac
done

# ── Variant / Dockerfile resolution (PS-97 v1.1 §1.1.3) ──────────────
case "${VARIANT}" in
    dev|public) ;;
    *)
        echo -e "${RED}ERROR: --variant must be 'dev' or 'public' (got: ${VARIANT})${NC}" >&2
        exit 2
        ;;
esac
# An explicit --file overrides the variant-selected Dockerfile.
if [ -z "${DOCKERFILE}" ]; then
    if [ "${VARIANT}" = "public" ]; then
        DOCKERFILE="./Dockerfile.public"
    else
        DOCKERFILE="./Dockerfile"
    fi
fi
if [ ! -f "${DOCKERFILE}" ]; then
    echo -e "${RED}ERROR: ${DOCKERFILE} not found (variant=${VARIANT})${NC}" >&2
    exit 2
fi

PUBLICATION_SUFFIX_BUILD=false
PUBLICATION_TAG_SUFFIX="${PUBLICATION_TAG_SUFFIX:-}"
if [[ -n "${PUBLICATION_TAG_SUFFIX}" ]]; then
    if [[ ! "${PUBLICATION_TAG_SUFFIX}" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
        echo "ERROR: PUBLICATION_TAG_SUFFIX must match ^[a-z0-9]([a-z0-9-]*[a-z0-9])?\$ (got: '${PUBLICATION_TAG_SUFFIX}')" >&2
        exit 2
    fi
    case "${PUBLICATION_TAG_SUFFIX}" in
        latest|dev|prod|release|stable)
            echo "ERROR: PUBLICATION_TAG_SUFFIX '${PUBLICATION_TAG_SUFFIX}' is reserved" >&2
            exit 2
            ;;
    esac
    IMAGE_TAG="${IMAGE_TAG}-${PUBLICATION_TAG_SUFFIX}"
    PUBLICATION_SUFFIX_BUILD=true
    echo "Publication test build: tag suffix '-${PUBLICATION_TAG_SUFFIX}' (latest retag will be skipped)."
fi

# Print header
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Expert Agent MCP Server Docker Build   ${NC}"
echo -e "${GREEN}=========================================${NC}"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
    exit 1
fi

echo -e "${YELLOW}Docker version:$(docker --version)${NC}"

# Create certificates directory if SSL is enabled
if [ "$SSL_ENABLED" = true ]; then
    echo -e "${YELLOW}SSL enabled. Creating certificates...${NC}"
    CERTS_DIR=$(dirname "$SSL_KEY_PATH")
    mkdir -p "$CERTS_DIR"
    
    # Check if certificates already exist
    if [ ! -f "$SSL_KEY_PATH" ] || [ ! -f "$SSL_CERT_PATH" ]; then
        echo -e "${YELLOW}Generating self-signed SSL certificates...${NC}"
        
        # Generate private key
        openssl genrsa -out "$SSL_KEY_PATH" 2048
        
        # Generate certificate
        openssl req -x509 -nodes -days "$CERT_DAYS" -newkey rsa:2048 \
            -key "$SSL_KEY_PATH" \
            -out "$SSL_CERT_PATH" \
            -subj "/C=$CERT_COUNTRY/ST=$CERT_STATE/L=$CERT_CITY/O=$CERT_ORG/CN=$CERT_CN"
        
        # Copy certificate to CA path as well
        cp "$SSL_CERT_PATH" "$SSL_CA_PATH"
        
        echo -e "${GREEN}SSL certificates generated:${NC}"
        echo -e "  Private Key: $SSL_KEY_PATH"
        echo -e "  Certificate: $SSL_CERT_PATH"
        echo -e "  CA Certificate: $SSL_CA_PATH"
    else
        echo -e "${YELLOW}SSL certificates already exist. Skipping generation.${NC}"
    fi
fi

# Build Docker image
echo -e "${YELLOW}Building Docker image: $IMAGE_NAME:$IMAGE_TAG${NC}"
echo -e "${YELLOW}Using Dockerfile: $DOCKERFILE${NC}"
echo -e "${YELLOW}Build context: $CONTEXT${NC}"
echo -e "${YELLOW}Build network: $DOCKER_BUILD_NETWORK${NC}"

if [ "${EXPERT_AGENT_SKIP_UI_DIST_SYNC:-0}" != "1" ]; then
    bash "${SCRIPT_DIR}/build-ui-dist.sh"
else
    echo -e "${YELLOW}Skipping Expert Agent UI dist sync because EXPERT_AGENT_SKIP_UI_DIST_SYNC=1${NC}"
fi

BUILD_ARGS=""
if [ "$SSL_ENABLED" = true ]; then
    BUILD_ARGS="--build-arg SSL_ENABLED=true"
fi
if [ -n "$CUSTOM_CA_CERT" ]; then
    BUILD_ARGS="$BUILD_ARGS --build-arg CUSTOM_CA_CERT=$CUSTOM_CA_CERT"
fi

# EA10 (W28M-FIX-1617): build provenance — computed on the HOST (the image has no
# .git tree or git binary) and passed as build args so the Dockerfile can write
# /app/VERSION + /app/.git-commit + /app/.git-branch + /app/build-info.json.
PROV_GIT_DIR="${SCRIPT_DIR}/.."
PROV_GIT_COMMIT="$(git -C "$PROV_GIT_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
PROV_GIT_BRANCH="$(git -C "$PROV_GIT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
PROV_BUILD_VERSION="$(grep -m1 '^version' "${PROV_GIT_DIR}/pyproject.toml" 2>/dev/null | sed -E 's/.*"(.*)".*/\1/' || echo unknown)"
PROV_BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BUILD_ARGS="$BUILD_ARGS --build-arg GIT_COMMIT=${PROV_GIT_COMMIT} --build-arg GIT_BRANCH=${PROV_GIT_BRANCH} --build-arg BUILD_VERSION=${PROV_BUILD_VERSION} --build-arg BUILD_TIME=${PROV_BUILD_TIME}"
echo -e "${GREEN}Build provenance: version=${PROV_BUILD_VERSION} commit=${PROV_GIT_COMMIT} branch=${PROV_GIT_BRANCH}${NC}"

# Optional extra build args (e.g. --build-arg INCLUDE_BROWSER_TOOLS=1)
EXTRA_BUILD_ARGS="${DOCKER_BUILD_ARGS:-}"

# ── Package-index strategy by variant (PS-97 v1.1 §3.3 / §4) ─────────
PIP_CONF_SECRET_ARG=""
trap 'rm -f "$PIP_CONF"' EXIT

if [ "${VARIANT}" = "public" ]; then
    # External / GitHub boundary: single index supplied by the build environment,
    # defaulting to the public PyPI. NO internal host default, NO --extra-index-url,
    # NO credentials baked in (PS-97 §3.3 / §4). The index passes to Dockerfile.public
    # as the PIP_INDEX_URL build ARG.
    PUBLIC_INDEX_URL="${PIP_INDEX_URL:-${PYPI_URL:-https://pypi.org/simple/}}"
    case "${PUBLIC_INDEX_URL}" in
        *cloud-dog.net*|*.vpc*|*.dmz*)
            echo -e "${RED}ERROR: public build index must not point at an internal Cloud-Dog host (got: ${PUBLIC_INDEX_URL}).${NC}" >&2
            echo -e "${RED}       Supply PIP_INDEX_URL pointing at a public/boundary index.${NC}" >&2
            exit 2
            ;;
    esac
    echo -e "${GREEN}Public build: single package index (no extra-index): ${PUBLIC_INDEX_URL}${NC}"
    BUILD_ARGS="$BUILD_ARGS --build-arg PIP_INDEX_URL=${PUBLIC_INDEX_URL}"
    # Proxy passthrough for transparent-proxy environments.
    BUILD_ARGS="$BUILD_ARGS --build-arg HTTP_PROXY=${HTTP_PROXY:-} --build-arg HTTPS_PROXY=${HTTPS_PROXY:-} --build-arg NO_PROXY=${NO_PROXY:-}"
    BUILD_ARGS="$BUILD_ARGS --build-arg http_proxy=${http_proxy:-} --build-arg https_proxy=${https_proxy:-} --build-arg no_proxy=${no_proxy:-}"
else
    # Internal / dev boundary: the internal build supplies its own package index
    # via the PYPI_URL environment variable (internal CI / Vault-credentialled).
    # No internal hostname is baked into this script (PS-97 §1.1.2 — keep the
    # publishable tree free of internal topology).
    PYPI_URL_ARG="${PYPI_URL:-}"
    PYPI_USERNAME_ARG="${PYPI_USERNAME:-}"
    PYPI_PASSWORD_ARG="${PYPI_PASSWORD:-}"
    if [ -z "$PYPI_URL_ARG" ]; then
        echo -e "${RED}ERROR: dev variant requires PYPI_URL to be set (internal package index).${NC}" >&2
        echo -e "${RED}       Set PYPI_URL, or use --variant public for the external build.${NC}" >&2
        exit 2
    fi
    PYPI_HOST_ARG="$(python3 -c "from urllib.parse import urlsplit; print(urlsplit('${PYPI_URL_ARG}').hostname or '')")"
    if [ -z "$PYPI_USERNAME_ARG" ] || [ -z "$PYPI_PASSWORD_ARG" ]; then
        echo -e "${YELLOW}WARNING: PYPI credentials not supplied.${NC}" >&2
        echo -e "${YELLOW}  PYPI_URL=${PYPI_URL_ARG}${NC}" >&2
        echo -e "${YELLOW}  PYPI_USERNAME=$([ -n "$PYPI_USERNAME_ARG" ] && echo '<set>' || echo '<empty>')${NC}" >&2
        echo -e "${YELLOW}  PYPI_PASSWORD=$([ -n "$PYPI_PASSWORD_ARG" ] && echo '<set>' || echo '<empty>')${NC}" >&2
        echo -e "${YELLOW}  Build will proceed using anonymous package-index access.${NC}" >&2
    fi

    if [ -n "$PYPI_USERNAME_ARG" ] && [ -n "$PYPI_PASSWORD_ARG" ]; then
        cat > "$PIP_CONF" << EOF
[global]
extra-index-url = https://${PYPI_USERNAME_ARG}:${PYPI_PASSWORD_ARG}@${PYPI_URL_ARG#https://}
trusted-host = ${PYPI_HOST_ARG}
               files.pythonhosted.org
EOF
        echo -e "${GREEN}pip.conf generated with authenticated PyPI access.${NC}"
    else
        cat > "$PIP_CONF" << EOF
[global]
extra-index-url = ${PYPI_URL_ARG}
trusted-host = ${PYPI_HOST_ARG}
               files.pythonhosted.org
EOF
        echo -e "${YELLOW}pip.conf generated with anonymous PyPI access.${NC}"
    fi
    chmod 600 "$PIP_CONF"
    PIP_CONF_SECRET_ARG="--secret id=pip_conf,src=${PIP_CONF}"
fi

# Execute docker build
if DOCKER_BUILDKIT=1 docker build --network="$DOCKER_BUILD_NETWORK" -t "$IMAGE_NAME:$IMAGE_TAG" \
    -f "$DOCKERFILE" \
    $PIP_CONF_SECRET_ARG \
    $BUILD_ARGS \
    $EXTRA_BUILD_ARGS \
    "$CONTEXT"; then

    echo -e "${GREEN}Docker image built successfully!${NC}"
    echo -e "${GREEN}Image: $IMAGE_NAME:$IMAGE_TAG${NC}"
    
    # Show image size
    IMAGE_SIZE=$(docker images "$IMAGE_NAME:$IMAGE_TAG" --format "{{.Size}}")
    echo -e "${GREEN}Image size: $IMAGE_SIZE${NC}"
    FULL_IMAGE="$IMAGE_NAME:$IMAGE_TAG"
    if [ -n "$REGISTRY" ]; then
        FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
        echo -e "${YELLOW}Tagging image for registry: $FULL_IMAGE${NC}"
        docker tag "$IMAGE_NAME:$IMAGE_TAG" "$FULL_IMAGE"
    fi
    
else
    echo -e "${RED}Docker build failed!${NC}"
    exit 1
fi

rm -f "$PIP_CONF"
trap - EXIT

# Tag with additional tags if needed
if [ "$IMAGE_TAG" != "latest" ] && [ "$PUBLICATION_SUFFIX_BUILD" != true ]; then
    echo -e "${YELLOW}Tagging image as latest...${NC}"
    if docker tag "$IMAGE_NAME:$IMAGE_TAG" "$IMAGE_NAME:latest"; then
        echo -e "${GREEN}Image tagged as latest${NC}"
    else
        echo -e "${RED}Failed to tag image as latest${NC}"
        exit 1
    fi
elif [ "$PUBLICATION_SUFFIX_BUILD" = true ]; then
    echo -e "${YELLOW}Latest tag skipped for publication suffix '${PUBLICATION_TAG_SUFFIX}'.${NC}"
fi

if [ "$PUSH_IMAGE" = true ]; then
    if [ -z "$REGISTRY" ]; then
        echo -e "${RED}--push requires --registry${NC}"
        exit 1
    fi
    echo -e "${YELLOW}Pushing image: $FULL_IMAGE${NC}"
    docker push "$FULL_IMAGE"
    echo -e "${GREEN}Pushed: $FULL_IMAGE${NC}"
fi

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Build completed successfully!          ${NC}"
echo -e "${GREEN}=========================================${NC}"

# Show next steps
echo -e "\n${YELLOW}Next steps:${NC}"
echo -e "  Run the container: docker run -p 8000:8000 $IMAGE_NAME:$IMAGE_TAG"
if [ "$SSL_ENABLED" = true ]; then
    echo -e "  Note: SSL certificates are located in the certs directory"
fi
