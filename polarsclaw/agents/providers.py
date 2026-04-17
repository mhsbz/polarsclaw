"""Model provider resolution — supports standard and custom providers."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel

if TYPE_CHECKING:
    from polarsclaw.config.settings import ModelProviderConfig, Settings

logger = logging.getLogger(__name__)

# Standard providers handled by langchain's init_chat_model
_STANDARD_PROVIDERS = frozenset({
    "anthropic", "openai", "google_genai", "google_vertexai",
    "bedrock", "fireworks", "groq", "mistralai", "together",
    "ollama", "huggingface",
})


def _resolve_api_key(provider_name: str, provider_cfg: "ModelProviderConfig") -> str | None:
    """Resolve API key from provider config, env var, or OpenClaw."""
    # 1. Direct key in config
    if provider_cfg.api_key:
        return provider_cfg.api_key

    # 2. Env var
    if provider_cfg.api_key_env:
        key = os.environ.get(provider_cfg.api_key_env)
        if key:
            return key

    # 3. Common env var patterns
    for env_name in (
        f"{provider_name.upper()}_API_KEY",
        f"MINIMAX_API_KEY" if provider_name == "minimax" else None,
    ):
        if env_name:
            key = os.environ.get(env_name)
            if key:
                return key

    # 4. Try OpenClaw auth profiles
    try:
        from polarsclaw.agents.openclaw_compat import load_openclaw_api_key
        key = load_openclaw_api_key(provider_name)
        if key:
            return key
    except Exception:
        logger.debug("Could not load API key from OpenClaw for %s", provider_name)

    return None


def _create_custom_model(
    provider_name: str,
    model_id: str,
    provider_cfg: "ModelProviderConfig",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> BaseChatModel:
    """Create a LangChain chat model for a custom provider."""
    api_key = _resolve_api_key(provider_name, provider_cfg)

    if provider_cfg.api == "anthropic-messages":
        from langchain_anthropic import ChatAnthropic

        kwargs: dict = {
            "model_name": model_id,
            "base_url": provider_cfg.base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if api_key:
            kwargs["api_key"] = api_key

        logger.info(
            "Creating ChatAnthropic for custom provider %s (model=%s, base_url=%s)",
            provider_name, model_id, provider_cfg.base_url,
        )
        return ChatAnthropic(**kwargs)

    elif provider_cfg.api == "openai-chat":
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": model_id,
            "base_url": provider_cfg.base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if api_key:
            kwargs["api_key"] = api_key

        logger.info(
            "Creating ChatOpenAI for custom provider %s (model=%s, base_url=%s)",
            provider_name, model_id, provider_cfg.base_url,
        )
        return ChatOpenAI(**kwargs)

    else:
        raise ValueError(
            f"Unknown API type '{provider_cfg.api}' for provider '{provider_name}'. "
            f"Supported: 'anthropic-messages', 'openai-chat'"
        )


def resolve_model(
    model_spec: str,
    settings: "Settings",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> BaseChatModel:
    """Resolve 'provider:model' string to a LangChain chat model.

    Standard providers (via init_chat_model):
    - anthropic:claude-sonnet-4-20250514
    - openai:gpt-4o
    - google_genai:gemini-2.0-flash

    Custom providers (via settings.providers):
    - minimax:MiniMax-M2.7-highspeed -> ChatAnthropic(base_url=..., model=..., api_key=...)
    """
    # Split on first ':' only
    if ":" in model_spec:
        provider, model_id = model_spec.split(":", 1)
    else:
        # No provider prefix — pass through to init_chat_model
        from langchain.chat_models import init_chat_model
        return init_chat_model(model_spec, temperature=temperature, max_tokens=max_tokens)

    # Check custom providers first
    if provider in settings.providers:
        return _create_custom_model(
            provider, model_id, settings.providers[provider],
            temperature=temperature, max_tokens=max_tokens,
        )

    # Check if it's a standard provider
    if provider in _STANDARD_PROVIDERS:
        from langchain.chat_models import init_chat_model
        return init_chat_model(
            model_spec, temperature=temperature, max_tokens=max_tokens,
        )

    # Try loading from OpenClaw as a fallback
    try:
        from polarsclaw.agents.openclaw_compat import load_openclaw_providers
        openclaw_providers = load_openclaw_providers()
        if provider in openclaw_providers:
            settings.providers[provider] = openclaw_providers[provider]
            return _create_custom_model(
                provider, model_id, openclaw_providers[provider],
                temperature=temperature, max_tokens=max_tokens,
            )
    except Exception:
        logger.debug("OpenClaw fallback failed for provider %s", provider)

    # Last resort: try init_chat_model
    from langchain.chat_models import init_chat_model
    logger.warning(
        "Unknown provider '%s', attempting init_chat_model with full spec '%s'",
        provider, model_spec,
    )
    return init_chat_model(model_spec, temperature=temperature, max_tokens=max_tokens)
