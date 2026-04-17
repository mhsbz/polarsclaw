"""Gateway authentication — shared-secret token verification."""

from __future__ import annotations

import hmac

from polarsclaw.config.settings import Settings


def verify_token(token: str | None, settings: Settings) -> bool:
    """Return *True* if *token* is authorised.

    Rules:
    - If ``settings.gateway.auth_token`` is ``None``, all requests pass.
    - Otherwise *token* must match the configured secret (constant-time comparison).
    """
    expected = settings.gateway.auth_token
    if expected is None:
        return True
    if token is None:
        return False
    return hmac.compare_digest(token, expected)
