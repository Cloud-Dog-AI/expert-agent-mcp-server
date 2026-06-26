# Expert Agent MCP Server Dockerfile

FROM python:3.12-slim
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.vendor="Cloud-Dog, Viewdeck Engineering Limited"

# Set working directory
WORKDIR /app

# Optional browser runtime for Selenium-driven test suites.
# Keep disabled by default for deploy images.
ARG INCLUDE_BROWSER_TOOLS=0

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Optional custom CA certificate (path inside build context).
# Example: --build-arg CUSTOM_CA_CERT=certs/ca.crt
ARG CUSTOM_CA_CERT=

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        netcat-openbsd \
        curl \
        procps \
    && if [ "$INCLUDE_BROWSER_TOOLS" = "1" ]; then \
        apt-get install -y --no-install-recommends chromium chromium-driver; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies using the approved BuildKit pip config secret.
RUN --mount=type=secret,id=pip_conf,target=/etc/pip.conf \
    PIP_NO_INPUT=1 pip install --no-cache-dir -r requirements.txt; \
    PIP_NO_INPUT=1 pip install --no-cache-dir \
      cloud-dog-config \
      cloud-dog-api-kit==0.13.0 \
      "cloud-dog-idam>=0.5.2,<0.6" \
      cloud-dog-llm \
      cloud-dog-db \
      cloud-dog-jobs \
      cloud-dog-vdb \
      cloud-dog-storage

# Copy application code
COPY . .
COPY database/migrations /app/migrations

# The PS-30 web UI must be built in the monorepo and copied into ui/dist before image build.
RUN test -f /app/ui/dist/index.html

# EA10 (W28M-FIX-1617): build provenance. The image has no .git tree and no git
# binary, so docker-build.sh computes these on the host and passes them as build
# args. Written after COPY so they never bust the dependency-install cache.
ARG GIT_COMMIT=unknown
ARG GIT_BRANCH=unknown
ARG BUILD_VERSION=0.1.1RC1
ARG BUILD_TIME=unknown
RUN printf '%s\n' "${BUILD_VERSION}" > /app/VERSION \
    && printf '%s\n' "${GIT_COMMIT}" > /app/.git-commit \
    && printf '%s\n' "${GIT_BRANCH}" > /app/.git-branch \
    && printf '{"version":"%s","git_commit":"%s","git_branch":"%s","build_time":"%s","service":"expert-agent-mcp-server"}\n' \
        "${BUILD_VERSION}" "${GIT_COMMIT}" "${GIT_BRANCH}" "${BUILD_TIME}" > /app/build-info.json

# Install custom CA into trust store when provided
RUN if [ -n "${CUSTOM_CA_CERT}" ] && [ -f "${CUSTOM_CA_CERT}" ]; then \
      cp "${CUSTOM_CA_CERT}" /usr/local/share/ca-certificates/custom-ca.crt && \
      update-ca-certificates; \
    fi

# Create directories for logs and database
RUN mkdir -p /var/log/expert \
    && mkdir -p /var/lib/expert

# Expose ports for all servers
EXPOSE 18080 18081 18082 18083

# Create a non-root user
RUN adduser --disabled-password --gecos '' expertuser
RUN chown -R expertuser:expertuser /app /var/log/expert /var/lib/expert
USER expertuser

RUN chmod +x /app/server_control.sh /app/docker-entrypoint.sh /app/healthcheck.sh

# Health check — timeout must exceed the sum of all curl probes in healthcheck.sh
# (4 probes × 8s max each = 32s worst case). Under sustained E2E load the event
# loop may take several seconds to service each probe.
HEALTHCHECK --interval=30s --timeout=45s --start-period=90s --retries=5 \
    CMD /app/healthcheck.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["all"]
