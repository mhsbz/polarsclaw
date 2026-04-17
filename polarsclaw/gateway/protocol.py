"""WebSocket protocol helpers — encode/decode JSON message envelopes."""

from __future__ import annotations

import json
from typing import Any

from polarsclaw.types import WSMessage, WSMessageType

# Re-export for convenience
HELLO = WSMessageType.HELLO
ACK = WSMessageType.ACK
MESSAGE = WSMessageType.MESSAGE
STREAM = WSMessageType.STREAM
ERROR = WSMessageType.ERROR
DONE = WSMessageType.DONE


def encode(msg: WSMessage) -> str:
    """Serialise a :class:`WSMessage` to a JSON string."""
    return msg.model_dump_json()


def decode(raw: str | bytes) -> WSMessage:
    """Parse a JSON string into a :class:`WSMessage`.

    Raises
    ------
    ValueError
        If *raw* is not valid JSON or fails validation.
    """
    if isinstance(raw, bytes):
        raw = raw.decode()
    data: dict[str, Any] = json.loads(raw)
    return WSMessage(**data)


def make(
    typ: WSMessageType,
    *,
    data: dict[str, Any] | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
) -> WSMessage:
    """Convenience factory for creating a :class:`WSMessage`."""
    return WSMessage(
        type=typ,
        data=data or {},
        session_id=session_id,
        request_id=request_id,
    )
