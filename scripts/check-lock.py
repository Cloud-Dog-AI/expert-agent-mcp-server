#!/usr/bin/env python3
# W28A-861-R3 — requirements.lock consistency check.
#
# Verifies that the sealed requirements.lock fully pins every direct dependency
# declared in requirements.txt (the exact input installed by Dockerfile.public),
# and that the lock stays index-agnostic (no host/credentials/index-url leaked).
#
# Exit 0 = consistent; exit 1 = a direct dep is unpinned or a leak was found.
#
# Regenerate the lock with:
#   pip-compile --no-emit-index-url --no-header --strip-extras \
#     -o requirements.lock requirements.txt
# (with PIP_INDEX_URL pointed at an index that hosts the cloud-dog-* packages).

import argparse
import importlib.metadata
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def norm(name: str) -> str:
    return name.lower().replace("_", "-")


def direct_deps() -> set[str]:
    deps = set()
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~ \[;]", line, maxsplit=1)[0]
        if name:
            deps.add(norm(name))
    return deps


def locked_pins() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "requirements.lock").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^ ;]+)", line)
        if m:
            pins[norm(m.group(1))] = m.group(2)
    return pins


def exact_platform_requirements() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(cloud[_-]dog[_-][A-Za-z0-9._-]+)==([^ ;]+)$", line)
        if match:
            pins[norm(match.group(1))] = match.group(2)
        elif norm(re.split(r"[<>=!~ \[;]", line, maxsplit=1)[0]).startswith("cloud-dog"):
            raise ValueError(f"Cloud-Dog requirement is not exact-pinned: {line}")
    return pins


def leak_check() -> list[str]:
    findings = []
    for ln, line in enumerate(
        (ROOT / "requirements.lock").read_text().splitlines(), 1
    ):
        if line.lstrip().startswith("#"):
            continue
        if re.search(r"://[^ ]*:[^ ]*@", line):
            findings.append(f"line {ln}: credentialed URL")
        if re.match(r"\s*--(extra-)?index-url", line):
            findings.append(f"line {ln}: index-url directive (must be index-agnostic)")
    return findings


def installed_pins() -> dict[str, str]:
    """Return normalized installed distribution names and versions.

    Native tests must run against the same sealed dependency closure as the
    Docker image.  ``pip check`` only validates dependencies of packages that
    are already installed; it does not report a direct locked package that is
    absent altogether.  Reading installed distribution metadata closes that
    gap without contacting a package index.
    """
    return {
        norm(distribution.metadata["Name"]): distribution.version
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the sealed dependency lock")
    parser.add_argument(
        "--installed",
        action="store_true",
        help="also require the active interpreter to match requirements.lock exactly",
    )
    args = parser.parse_args()
    direct = direct_deps()
    pins = locked_pins()
    missing = sorted(d for d in direct if d not in pins)
    leaks = leak_check()

    print(f"direct deps (requirements.txt): {len(direct)}")
    print(f"pinned packages (requirements.lock): {len(pins)}")
    print(f"MISSING FROM LOCK: {missing or 'none'}")
    print(f"LEAKS: {leaks or 'none'}")

    # The cloud-dog platform packages MUST be pinned in the lock.
    platform_requirements = exact_platform_requirements()
    platform = sorted(platform_requirements)
    unpinned_platform = [p for p in platform if p not in pins]
    platform_mismatches = [
        f"{name}: requirement={version}, lock={pins.get(name, 'missing')}"
        for name, version in sorted(platform_requirements.items())
        if pins.get(name) != version
    ]
    print(f"platform packages pinned: {sorted(p for p in platform if p in pins)}")
    if unpinned_platform:
        print(f"UNPINNED PLATFORM PACKAGES: {unpinned_platform}")
    if platform_mismatches:
        print(f"PLATFORM VERSION MISMATCHES: {platform_mismatches}")

    installed_missing: list[str] = []
    installed_mismatches: list[str] = []
    if args.installed:
        installed = installed_pins()
        installed_missing = sorted(name for name in pins if name not in installed)
        installed_mismatches = [
            f"{name}: lock={version}, installed={installed.get(name, 'missing')}"
            for name, version in sorted(pins.items())
            if installed.get(name) != version
        ]
        print(f"installed packages: {len(installed)}")
        print(f"MISSING FROM ACTIVE ENVIRONMENT: {installed_missing or 'none'}")
        print(f"ACTIVE ENVIRONMENT VERSION MISMATCHES: {installed_mismatches or 'none'}")

    ok = (
        not missing
        and not leaks
        and not unpinned_platform
        and not platform_mismatches
        and not installed_missing
        and not installed_mismatches
    )
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
