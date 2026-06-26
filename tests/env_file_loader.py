# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0.

"""Test-only env-file loader helper.

Moved out of ``src/config/loader.py`` so service ``src/`` consumes configuration solely
through cloud_dog_config with ZERO ``os.environ`` reads/writes (RULES §1.4.1). Writing the
process environment from a parsed env file is a TEST fixture concern, so it lives here.
"""

from __future__ import annotations

import os
from typing import Dict

from cloud_dog_config.env_parser import parse_env_file


def load_env_files(
    env_file: str,
    *,
    include_secrets: bool = True,
    override: bool = False,
) -> Dict[str, str]:
    """Parse env file(s) and optionally write the values into ``os.environ`` (tests only).

    Args:
        env_file: Primary env file path.
        include_secrets: When true, also merge ``<env_file>-secrets`` if present.
        override: When true, write parsed values into ``os.environ`` and set
            ``CLOUD_DOG_ENV_FILES`` so cloud_dog_config discovers the env file.

    Returns:
        Parsed key/value pairs from the requested env sources.
    """
    merged: Dict[str, str] = {}
    candidate_paths = [str(env_file)]
    if include_secrets:
        secrets_path = f"{env_file}-secrets"
        if os.path.exists(secrets_path):
            candidate_paths.append(secrets_path)

    for path in candidate_paths:
        if not os.path.exists(path):
            continue
        merged.update(parse_env_file(path))

    if override:
        for key, value in merged.items():
            os.environ[key] = value
        os.environ["CLOUD_DOG_ENV_FILES"] = str(env_file)

    return merged
