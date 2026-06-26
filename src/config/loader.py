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

"""
Configuration Loader

License: Apache 2.0
Ownership: Cloud Dog
Description: Compatibility wrapper over cloud_dog_config with project-specific
normalisation for legacy expert-agent config paths.

Related Requirements: NF1.5
Related Tasks: T110
Related Architecture: CM1.1
Related Tests: UT1.32
"""

from __future__ import annotations

import os
import inspect
from functools import lru_cache
from typing import Any, Dict, Optional

from cloud_dog_config import (
    load_config as platform_load_config,
    resolve_runtime_env_files,
)

_ACTIVE_ENV_FILE: str = ""
_ACTIVE_ENV_SECRETS_FILES: str = ""


def _project_root() -> str:
    """Return the repository root inferred from this module path."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _deep_copy_simple(value: Any) -> Any:
    """Copy dict and list values while preserving simple scalar objects."""
    if isinstance(value, dict):
        return {k: _deep_copy_simple(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy_simple(v) for v in value]
    return value


def _deep_merge_dicts(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge source values into the destination mapping."""
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge_dicts(dst[key], value)
        else:
            dst[key] = _deep_copy_simple(value)
    return dst


def _resolve_env_files(project_root: str) -> list[str]:
    """Resolve active env files for the platform config loader."""
    global _ACTIVE_ENV_FILE, _ACTIVE_ENV_SECRETS_FILES
    del project_root

    env_files = resolve_runtime_env_files()
    _ACTIVE_ENV_FILE = env_files[0] if env_files else ""
    _ACTIVE_ENV_SECRETS_FILES = ",".join(env_files[1:]) if len(env_files) > 1 else ""
    return env_files


def _coerce_bool_int(v: Any) -> Any:
    """Coerce string booleans and integers produced by env parsing."""
    if isinstance(v, str):
        low = v.strip().lower()
        if low in ("true", "false"):
            return low == "true"
        if low.isdigit():
            try:
                return int(low)
            except Exception:
                return v
    return v


def _normalise_profile_name(p: str) -> str:
    """Normalise profile names to the legacy uppercase underscore contract."""
    p = (p or "").strip().lower()
    if p in ("default", "_default_"):
        return "_DEFAULT_"
    if p in ("test", "_test_"):
        return "_TEST_"
    if p in ("remote", "_remote_"):
        return "_REMOTE_"
    if not p:
        return "_DEFAULT_"
    return f"_{p.upper()}_"


def _connection_score(profile_cfg: Dict[str, Any]) -> int:
    """Score how complete a vector-store profile connection block is."""
    scalar_keys = (
        "host",
        "port",
        "url",
        "base_url",
        "server_url",
        "database",
        "database_uri",
        "username",
        "password",
        "api_key",
        "auth_token",
        "collection_name",
        "ssl",
    )
    score = 0
    for key in scalar_keys:
        value = profile_cfg.get(key)
        if value not in (None, "", {}):
            score += 1
    return score


def _pick_profile(store_profiles: Dict[str, Any], profile_names: list[str]) -> Dict[str, Any]:
    """Pick the best populated profile from a preferred profile list."""
    best_profile: Dict[str, Any] = {}
    best_score = -1
    for profile_name in profile_names:
        candidate = store_profiles.get(profile_name)
        if not isinstance(candidate, dict) or not candidate:
            continue
        score = _connection_score(candidate)
        if score > best_score:
            best_profile = candidate
            best_score = score
    return best_profile


def _normalise_store_profiles(store_profiles: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise vector-store profile keys and scalar value types."""
    normalised: Dict[str, Any] = {}
    for profile_name, profile_cfg in store_profiles.items():
        if not isinstance(profile_cfg, dict):
            continue
        profile_key = _normalise_profile_name(str(profile_name).strip("_"))
        dst = normalised.setdefault(profile_key, {})
        for raw_key, raw_value in profile_cfg.items():
            key = str(raw_key).lstrip("_")
            dst[key] = _coerce_bool_int(raw_value)
    return normalised


def _normalise_store_tree(store_tree: Any) -> Dict[str, Any]:
    """Normalise all vector-store provider profiles in a config tree."""
    normalised_tree: Dict[str, Any] = {}
    if not isinstance(store_tree, dict):
        return normalised_tree
    for store_name, profiles in store_tree.items():
        if store_name == "default_backend":
            normalised_tree[store_name] = str(profiles).strip().lower()
            continue
        if not isinstance(profiles, dict):
            continue
        normalised_tree[str(store_name).lower()] = _normalise_store_profiles(profiles)
    return normalised_tree


def _is_placeholder(value: Any) -> bool:
    """Return true for empty or known placeholder config values."""
    text = str(value or "").strip().lower()
    return text in {"", "changeme", "${placeholder}"}


def _project_transform(compiled: dict[str, Any]) -> dict[str, Any]:
    """Apply expert-agent compatibility transforms to compiled config."""
    config = _deep_copy_simple(compiled)

    expert_cfg = config.setdefault("expert", {})
    if not isinstance(expert_cfg, dict):
        expert_cfg = {}
        config["expert"] = expert_cfg
    expert_cfg["env_file"] = _ACTIVE_ENV_FILE
    expert_cfg["env_secrets_files"] = _ACTIVE_ENV_SECRETS_FILES

    test_cfg = config.setdefault("test", {})
    if not isinstance(test_cfg, dict):
        test_cfg = {}
        config["test"] = test_cfg
    test_cfg.setdefault("enabled", "test" in os.path.basename(_ACTIVE_ENV_FILE or "").lower())

    expert_test_cfg = expert_cfg.get("test")
    if isinstance(expert_test_cfg, dict):
        # Runtime env files populate expert.test.*. Those values are the most
        # specific test settings and must override top-level test defaults so
        # middleware and helpers see the same budgets.
        merged_test_cfg = _deep_copy_simple(test_cfg)
        _deep_merge_dicts(merged_test_cfg, expert_test_cfg)
        config["test"] = merged_test_cfg
        test_cfg = merged_test_cfg

    # Preserve the historical project contract where env overrides under
    # expert.<section> are visible through top-level runtime sections.
    expert_agent_cfg = config.get("expert_agent")
    if isinstance(expert_agent_cfg, dict) and expert_agent_cfg:
        _deep_merge_dicts(expert_cfg, expert_agent_cfg)

    legacy_runtime_sections = (
        "api_server",
        "web_server",
        "mcp_server",
        "a2a_server",
        "session",
        "db",
        "redis",
        "llm",
        "embeddings",
        "auth",
        "smtp",
        "log",
        "vector",
        "vector_stores",
        "vector_stores_config",
        "code_runner",
    )
    for section_name in legacy_runtime_sections:
        expert_section = expert_cfg.get(section_name)
        if not isinstance(expert_section, dict) or not expert_section:
            continue
        runtime_section = config.get(section_name)
        if not isinstance(runtime_section, dict):
            runtime_section = {}
            config[section_name] = runtime_section
        _deep_merge_dicts(runtime_section, expert_section)

    api_server_cfg = config.get("api_server")
    if isinstance(api_server_cfg, dict):
        api_scheme = str(api_server_cfg.get("scheme") or "http").strip().lower()
        if api_scheme not in {"http", "https"}:
            api_scheme = "http"
        api_host = api_server_cfg.get("host")
        api_port = api_server_cfg.get("port")
        api_base_path = str(api_server_cfg.get("base_path") or "").strip()
        if api_host and api_port is not None and not api_server_cfg.get("base_url"):
            api_server_cfg["base_url"] = f"{api_scheme}://{api_host}:{int(api_port)}"
        if api_base_path:
            api_server_cfg.setdefault("prefixed_base_url", f"{api_server_cfg['base_url'].rstrip('/')}/{api_base_path.strip('/')}")
        else:
            api_server_cfg.setdefault("prefixed_base_url", str(api_server_cfg["base_url"]).rstrip("/"))

        if _is_placeholder(api_server_cfg.get("api_key")) and not _is_placeholder(test_cfg.get("api_key")):
            api_server_cfg["api_key"] = str(test_cfg["api_key"])
        api_server_cfg.setdefault("api_key_header", "X-API-Key")

    web_server_cfg = config.get("web_server")
    if isinstance(web_server_cfg, dict):
        api_base_url = None
        if isinstance(api_server_cfg, dict):
            api_base_url = api_server_cfg.get("prefixed_base_url") or api_server_cfg.get("base_url")
        if api_base_url and not web_server_cfg.get("api_base_url"):
            web_server_cfg["api_base_url"] = str(api_base_url)

        raw_verify_tls = test_cfg.get("http_verify_tls")
        if raw_verify_tls is not None and web_server_cfg.get("verify_tls") is None:
            web_server_cfg["verify_tls"] = str(raw_verify_tls).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

        raw_request_timeout = test_cfg.get("http_timeout_seconds")
        raw_llm_timeout = (config.get("llm") or {}).get("timeout") if isinstance(config.get("llm"), dict) else None
        try:
            request_timeout = float(raw_request_timeout)
        except (TypeError, ValueError):
            request_timeout = 60.0
        try:
            llm_timeout = float(raw_llm_timeout)
        except (TypeError, ValueError):
            llm_timeout = 300.0

        if not web_server_cfg.get("proxy_timeout"):
            web_server_cfg["proxy_timeout"] = max(request_timeout, llm_timeout, 60.0)

    for section_name, default_base_path in (("mcp_server", "/mcp"), ("a2a_server", "/a2a")):
        server_cfg = config.get(section_name)
        if not isinstance(server_cfg, dict):
            continue
        scheme = str(server_cfg.get("scheme") or "http").strip().lower()
        if scheme not in {"http", "https"}:
            scheme = "http"
        host = server_cfg.get("host")
        port = server_cfg.get("port")
        base_path = str(server_cfg.get("base_path") or default_base_path).strip()
        if host and port is not None and not server_cfg.get("base_url"):
            root_url = f"{scheme}://{host}:{int(port)}"
            server_cfg["base_url"] = root_url
        if server_cfg.get("base_url"):
            root_url = str(server_cfg["base_url"]).rstrip("/")
            if base_path:
                server_cfg.setdefault(
                    "prefixed_base_url",
                    f"{root_url}/{base_path.strip('/')}",
                )
            else:
                server_cfg.setdefault("prefixed_base_url", root_url)

    active_api_key = get_config_value = None
    api_server_cfg = config.get("api_server")
    if isinstance(api_server_cfg, dict):
        get_config_value = api_server_cfg.get("api_key")
    test_api_key = test_cfg.get("api_key")
    if (test_api_key is None or _is_placeholder(test_api_key)) and not _is_placeholder(get_config_value):
        test_cfg["api_key"] = str(get_config_value)
        expert_cfg.setdefault("test", {})
        if isinstance(expert_cfg.get("test"), dict):
            expert_cfg["test"]["api_key"] = str(get_config_value)

    if isinstance(config.get("vector_stores_config"), dict):
        config["vector_stores_config"] = _normalise_store_tree(config["vector_stores_config"])
    if isinstance(config.get("vector_stores"), dict):
        config["vector_stores"] = _normalise_store_tree(config["vector_stores"])

    vector_legacy = {}
    if isinstance(config.get("vector"), dict):
        vector_legacy = (config.get("vector", {}) or {}).get("stores", {}) or {}

    if isinstance(vector_legacy, dict) and vector_legacy:
        config.setdefault("vector_stores_config", {})
        config.setdefault("vector_stores", {})
        for store_name, profiles in vector_legacy.items():
            if not isinstance(profiles, dict):
                continue
            store_key = str(store_name).lower()
            config["vector_stores_config"].setdefault(store_key, {})
            config["vector_stores"].setdefault(store_key, {})
            for profile_name, profile_cfg in profiles.items():
                if not isinstance(profile_cfg, dict):
                    continue
                profile_key = _normalise_profile_name(str(profile_name))
                dst_cfg = config["vector_stores_config"][store_key].setdefault(profile_key, {})
                dst_defaults = config["vector_stores"][store_key].setdefault(profile_key, {})
                for k, v in profile_cfg.items():
                    if k not in dst_cfg:
                        dst_cfg[k] = _coerce_bool_int(v)
                    if k not in dst_defaults:
                        dst_defaults[k] = _coerce_bool_int(v)

    test_vector_stores = test_cfg.setdefault("vector_stores", {})
    if not isinstance(test_vector_stores, dict):
        test_vector_stores = {}
        test_cfg["vector_stores"] = test_vector_stores

    runtime_vector_cfg = config.get("vector_stores_config")
    default_vector_cfg = config.get("vector_stores")
    preferred_profiles = ["_TEST_", "_REMOTE_", "_DEFAULT_"]
    provider_names = ("chroma", "qdrant", "weaviate", "opensearch", "pgvector")

    for provider_name in provider_names:
        merged_provider_cfg: Dict[str, Any] = {}
        runtime_profiles = (
            _normalise_store_profiles(runtime_vector_cfg.get(provider_name, {}))
            if isinstance(runtime_vector_cfg, dict)
            else {}
        )
        default_profiles = (
            _normalise_store_profiles(default_vector_cfg.get(provider_name, {}))
            if isinstance(default_vector_cfg, dict)
            else {}
        )
        default_base_cfg = default_profiles.get("_DEFAULT_", {}) if isinstance(default_profiles, dict) else {}
        runtime_base_cfg = runtime_profiles.get("_DEFAULT_", {}) if isinstance(runtime_profiles, dict) else {}
        if isinstance(default_base_cfg, dict) and default_base_cfg:
            merged_provider_cfg.update(_deep_copy_simple(default_base_cfg))
        if isinstance(runtime_base_cfg, dict) and runtime_base_cfg:
            merged_provider_cfg.update(_deep_copy_simple(runtime_base_cfg))
        selected_default_cfg = _pick_profile(default_profiles, preferred_profiles)
        if selected_default_cfg:
            merged_provider_cfg.update(_deep_copy_simple(selected_default_cfg))
        selected_runtime_cfg = _pick_profile(runtime_profiles, preferred_profiles)
        if selected_runtime_cfg:
            merged_provider_cfg.update(_deep_copy_simple(selected_runtime_cfg))
        if merged_provider_cfg:
            provider_test_cfg = test_vector_stores.setdefault(provider_name, {})
            if not isinstance(provider_test_cfg, dict):
                provider_test_cfg = {}
                test_vector_stores[provider_name] = provider_test_cfg
            for k, v in merged_provider_cfg.items():
                provider_test_cfg.setdefault(k, v)

    if "store_name" not in test_vector_stores:
        default_backend = ""
        if isinstance(default_vector_cfg, dict):
            default_backend = str(default_vector_cfg.get("default_backend") or "").strip().lower()
        if default_backend not in provider_names:
            default_backend = "qdrant"
        test_vector_stores["store_name"] = default_backend

    if "collection_name" not in test_vector_stores:
        default_provider_cfg = test_vector_stores.get(str(test_vector_stores["store_name"]), {})
        if isinstance(default_provider_cfg, dict):
            collection_name = default_provider_cfg.get("collection_name")
            if collection_name:
                test_vector_stores["collection_name"] = collection_name

    return config


def _to_plain_dict(value: Any) -> Any:
    """Convert config snapshot containers to plain Python dict/list values."""
    if isinstance(value, dict):
        return {k: _to_plain_dict(v) for k, v in value.items()}
    if hasattr(value, "items") and not isinstance(value, (str, bytes, list, tuple, set)):
        try:
            return {k: _to_plain_dict(v) for k, v in value.items()}
        except Exception:
            return value
    if isinstance(value, list):
        return [_to_plain_dict(v) for v in value]
    if isinstance(value, tuple):
        return [_to_plain_dict(v) for v in value]
    return value


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """Load configuration through cloud_dog_config and return a plain dict."""
    project_root = _project_root()
    env_files = _resolve_env_files(project_root)
    load_kwargs = {
        "env_files": env_files or None,
        "config_yaml": os.path.join(project_root, "config.yaml"),
        "defaults_yaml": os.path.join(project_root, "defaults.yaml"),
        "unresolved_policy": "strict",
    }
    supports_transforms = "transforms" in inspect.signature(platform_load_config).parameters
    if supports_transforms:
        load_kwargs["transforms"] = [_project_transform]

    snapshot = platform_load_config(**load_kwargs)
    compiled = _to_plain_dict(snapshot.data)
    if not supports_transforms:
        compiled = _project_transform(compiled)
    return compiled


_native_load_config_cache_clear = load_config.cache_clear


def _load_config_cache_clear() -> None:
    """Clear both the platform loader cache and compatibility loader cache."""
    _native_load_config_cache_clear()
    if "_config_loader" in globals():
        try:
            _config_loader._config = None
        except Exception:
            pass


load_config.cache_clear = _load_config_cache_clear  # type: ignore[attr-defined]


class ConfigLoader:
    """Compatibility wrapper retaining the historical project API."""

    def __init__(self) -> None:
        """Create an unloaded compatibility config loader."""
        self._config: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        """Load and cache the current runtime configuration."""
        self._config = load_config()
        return self._config

    def reload(self) -> Dict[str, Any]:
        """Clear caches and reload the current runtime configuration."""
        load_config.cache_clear()  # type: ignore[attr-defined]
        self._config = load_config()
        return self._config

    def get(self, path: str, default: Any = None) -> Any:
        config = self._config if self._config is not None else self.load()
        current: Any = config
        for key in path.split("."):
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current


_config_loader = ConfigLoader()


def get_config(path: str = None, default: Any = None) -> Any:
    """Return the whole config or a dotted config value."""
    if path is None:
        return _config_loader.load()
    return _config_loader.get(path, default)
