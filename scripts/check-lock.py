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

import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def norm(name: str) -> str:
    return name.lower().replace("_", "-")


def direct_deps() -> set[str]:
    deps = set()
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~ \[;]", line, 1)[0]
        if name:
            deps.add(norm(name))
    return deps


def locked_pins() -> set[str]:
    pins = set()
    for line in (ROOT / "requirements.lock").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==", line)
        if m:
            pins.add(norm(m.group(1)))
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


def main() -> int:
    direct = direct_deps()
    pins = locked_pins()
    missing = sorted(d for d in direct if d not in pins)
    leaks = leak_check()

    print(f"direct deps (requirements.txt): {len(direct)}")
    print(f"pinned packages (requirements.lock): {len(pins)}")
    print(f"MISSING FROM LOCK: {missing or 'none'}")
    print(f"LEAKS: {leaks or 'none'}")

    # The cloud-dog platform packages MUST be pinned in the lock.
    platform = sorted(d for d in direct if d.startswith("cloud-dog"))
    unpinned_platform = [p for p in platform if p not in pins]
    print(f"platform packages pinned: {sorted(p for p in platform if p in pins)}")
    if unpinned_platform:
        print(f"UNPINNED PLATFORM PACKAGES: {unpinned_platform}")

    ok = not missing and not leaks and not unpinned_platform
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
