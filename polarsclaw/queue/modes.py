"""Queue mode logic — message coalescing and mode predicates."""

from __future__ import annotations

from polarsclaw.types import QueueMode


def collect_messages(messages: list[str], debounce_ms: int = 2000) -> str:
    """Coalesce multiple messages into a single prompt.

    Parameters
    ----------
    messages:
        Ordered list of message strings to combine.
    debounce_ms:
        Debounce window (informational — the actual waiting is done by the
        caller).  Included for potential future use in separator hints.

    Returns
    -------
    str
        A single string joining all non-empty messages with newlines.
    """
    return "\n".join(m for m in messages if m)


def should_coalesce(mode: QueueMode) -> bool:
    """Return *True* if *mode* requires message coalescing."""
    return mode is QueueMode.COLLECT
