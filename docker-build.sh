#!/usr/bin/env bash
# Wrapper entrypoint for standard Docker builds.
# Delegates to scripts/docker-build.sh which enforces the required defaults,
# including PUBLICATION_TAG_SUFFIX handling for publication test images.

set -euo pipefail

require_main_or_release_branch() {
  local branch
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  # A publication-suffixed build is an explicitly local, non-pushing
  # verification artifact. Permit that closed-loop path from a repair branch;
  # the delegated builder suppresses registry tagging whenever the suffix is
  # present.
  if [[ -n "${PUBLICATION_TAG_SUFFIX:-}" ]]; then
    return 0
  fi
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
exec bash "${SCRIPT_DIR}/scripts/docker-build.sh" "$@"
