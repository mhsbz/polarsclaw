"""Load model provider config from OpenClaw configuration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OPENCLAW_DIR = Path.home() / ".openclaw"
OPENCLAW_CONFIG = OPENCLAW_DIR / "openclaw.json"
OPENCLAW_AUTH_DIR = OPENCLAW_DIR / "agents" / "main" / "agent"
OPENCLAW_AUTH_PROFILES = OPENCLAW_AUTH_DIR / "auth-profiles.json"


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file, returning empty dict on failure."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("Failed to read %s", path)
        return {}


def load_openclaw_api_key(provider_name: str) -> str | None:
    """Extract API key for a provider from OpenClaw auth profiles.

    Looks for a profile matching ``provider_name:*`` in auth-profiles.json.
    """
    data = _read_json(OPENCLAW_AUTH_PROFILES)

    profiles = data.get("profiles", data)
    if isinstance(profiles, list):
        for profile in profiles:
            profile_id = profile.get("id", "")
            if profile_id.startswith(f"{provider_name}:"):
                # Try various key field names
                for key_field in ("api_key", "apiKey", "key", "token"):
                    val = profile.get(key_field)
                    if val:
                        return val
                # Check nested auth object
                auth = profile.get("auth", {})
                for key_field in ("api_key", "apiKey", "key", "token"):
                    val = auth.get(key_field)
                    if val:
                        return val
    elif isinstance(profiles, dict):
        for profile_id, profile in profiles.items():
            if profile_id.startswith(f"{provider_name}:"):
                if isinstance(profile, str):
                    return profile
                if isinstance(profile, dict):
                    for key_field in ("api_key", "apiKey", "key", "token"):
                        val = profile.get(key_field)
                        if val:
                            return val

    return None


def _extract_model_ids(models_raw: list) -> list[str]:
    """Extract model ID strings from OpenClaw model definitions (may be dicts or strings)."""
    ids = []
    for m in models_raw:
        if isinstance(m, str):
            ids.append(m)
        elif isinstance(m, dict) and "id" in m:
            ids.append(m["id"])
    return ids


def load_openclaw_providers() -> dict:
    """Read OpenClaw config and extract model provider configs.

    Returns a dict of provider_name -> ModelProviderConfig instances.
    """
    from polarsclaw.config.settings import ModelProviderConfig

    config = _read_json(OPENCLAW_CONFIG)
    providers: dict[str, ModelProviderConfig] = {}

    # Parse models.providers section
    models_cfg = config.get("models", {})
    provider_list = models_cfg.get("providers", [])

    if isinstance(provider_list, list):
        for entry in provider_list:
            name = entry.get("name", entry.get("id", ""))
            if not name:
                continue
            base_url = entry.get("base_url", entry.get("baseUrl", ""))
            api = entry.get("api", "anthropic-messages")
            if not base_url:
                continue
            providers[name] = ModelProviderConfig(
                name=name,
                base_url=base_url,
                api=api,
                models=_extract_model_ids(entry.get("models", [])),
            )
    elif isinstance(provider_list, dict):
        for name, entry in provider_list.items():
            if not isinstance(entry, dict):
                continue
            base_url = entry.get("base_url", entry.get("baseUrl", ""))
            if not base_url:
                continue
            providers[name] = ModelProviderConfig(
                name=name,
                base_url=base_url,
                api=entry.get("api", "anthropic-messages"),
                models=_extract_model_ids(entry.get("models", [])),
            )

    # If minimax not found but auth profile exists, add default
    if "minimax" not in providers:
        key = load_openclaw_api_key("minimax")
        if key:
            providers["minimax"] = ModelProviderConfig(
                name="minimax",
                base_url="https://api.minimaxi.com/anthropic",
                api="anthropic-messages",
            )

    return providers
