"""Runtime helpers for dispatching user messages through PolarsClaw."""

from polarsclaw.runtime.dispatcher import (
    DispatchResult,
    build_agent_factory,
    dispatch_message,
    resolve_dm_scope,
    resolve_routed_agent,
)

__all__ = [
    "DispatchResult",
    "build_agent_factory",
    "dispatch_message",
    "resolve_dm_scope",
    "resolve_routed_agent",
]
