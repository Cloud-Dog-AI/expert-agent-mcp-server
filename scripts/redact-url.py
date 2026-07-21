#!/usr/bin/env python3
"""Redact URL userinfo for safe build diagnostics.

The URL is read from ``URL_TO_REDACT`` so credentials never appear in the
process argument list.  ``--has-userinfo`` emits nothing and reports presence
through its exit status.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit, urlunsplit


def main() -> int:
    url = os.environ.get("URL_TO_REDACT", "")
    parsed = urlsplit(url)
    has_userinfo = parsed.username is not None or parsed.password is not None
    if "--has-userinfo" in sys.argv[1:]:
        return 0 if has_userinfo else 1

    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    netloc = f"***:***@{host}" if has_userinfo else host
    print(urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
